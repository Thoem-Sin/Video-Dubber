# dubbing_engine.py
import os
import sys
import time
import json
import re
import asyncio
import subprocess
import wave
import base64
import contextlib
import shutil
from dataclasses import dataclass, field
import edge_tts
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator
import whisper
from PIL import Image, ImageDraw, ImageFont
from gender_detector import auto_select_voice
from voices_config import SUPPORTED_LANGUAGES
import font_manager

# Fix Windows console UTF-8 output issues
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

_SILENCE_SEPARATOR = "\n|||SPLIT|||\n"

STYLE_SPEECH_TUNING = {
    "dramatic": {"rate": "+8%", "pitch": "-4Hz"},    # High energy movie review tone
    "fast":     {"rate": "+20%", "pitch": "-2Hz"},   # Ultra-rapid recap narrator speed
    "action":   {"rate": "+15%", "pitch": "-4Hz"},   # Energetic action review tone
    "review":   {"rate": "+18%", "pitch": "-3Hz"},   # Rapid YouTube film reviewer rate
    "standard": {"rate": "+8%", "pitch": "-2Hz"}     # Standard speech dubbing rate
}


# ─── Unified Preview & Render Configuration ───────────────────────────────────

@dataclass
class PreviewRenderConfig:
    """Single structured config for both live subtitle preview and final video rendering.

    Replaces the ad-hoc ``custom_edits`` / ``sub_cfg`` dict pattern so that all
    routes share one validated, self-documenting object.  Use the factory class
    methods to construct from a Flask form or from a legacy ``custom_edits`` dict,
    then call ``to_custom_edits()`` / ``to_sub_cfg()`` to produce the dicts that
    the existing engine methods still accept internally.
    """

    # ── Canvas dimensions ─────────────────────────────────────────────────────
    video_width: int = 1080
    video_height: int = 1920

    # ── Subtitle / caption settings ───────────────────────────────────────────
    sub_enabled: bool = False
    sub_preset: str = "Outline"      # Outline | YellowBox | WhiteText | Glow
    sub_font: str = "Kantumruy Pro"
    sub_font_path: str = ""
    sub_size: float = 3.0            # % of video height
    sub_opacity: float = 100.0       # 0–100
    sub_outline: float = 0.3         # % of video height
    sub_pos_y: float = 62.0          # % from top
    sub_anim: str = "None"           # None | Fade | Pop | Slide
    sub_max_chars: int = 36          # chars per wrapped line (shared with C# CLI)
    sub_text_color: str = "#FFFFFF"  # primary caption text color
    sub_outline_color: str = "#000000" # caption outline/glow color

    # ── Blur region overlay ───────────────────────────────────────────────────
    blur_enabled: bool = False
    blur_pos_x: float = 0.0
    blur_pos_y: float = 57.3
    blur_width: float = 100.0
    blur_height: float = 7.0
    blur_opacity: float = 100.0

    # ── Text banner overlay ───────────────────────────────────────────────────
    text_enabled: bool = False
    text_content: str = ""
    text_font: str = "Kantumruy Pro"
    text_font_path: str = ""
    text_size: float = 4.3
    text_opacity: float = 90.0
    text_pos_y: float = 15.0

    # ── Logo watermark ────────────────────────────────────────────────────────
    logo_enabled: bool = False
    logo_size: float = 54.0          # %
    logo_opacity: float = 10.0       # %

    # ── Factory methods ───────────────────────────────────────────────────────

    @classmethod
    def from_form(cls, form: dict, logo_uploaded: bool = False) -> "PreviewRenderConfig":
        """Build a ``PreviewRenderConfig`` from a Flask ``request.form`` dict.

        Handles the type coercion and boolean string conversion that all routes
        previously repeated individually.
        """
        def _bool(key: str, default: bool = False) -> bool:
            val = form.get(key, "")
            if isinstance(val, bool):
                return val
            return str(val).lower() in ("true", "1", "yes")

        def _float(key: str, default: float = 0.0) -> float:
            try:
                return float(form.get(key, default))
            except (TypeError, ValueError):
                return default

        def _int(key: str, default: int = 0) -> int:
            try:
                return int(form.get(key, default))
            except (TypeError, ValueError):
                return default

        def _str(key: str, default: str = "") -> str:
            return str(form.get(key, default)).strip()

        return cls(
            video_width=_int("video_width", 1080),
            video_height=_int("video_height", 1920),
            # subtitle
            sub_enabled=_bool("sub_enabled") or _bool("burn_subtitles"),
            sub_preset=_str("sub_style_preset", "Outline"),
            sub_font=_str("sub_font", "Kantumruy Pro"),
            sub_font_path=_str("sub_font_path"),
            sub_size=_float("sub_font_size", 3.0),
            sub_opacity=_float("sub_text_opacity", 100.0),
            sub_outline=_float("sub_outline_width", 0.3),
            sub_pos_y=_float("sub_position_percent", 62.0),
            sub_anim=_str("sub_anim", "None"),
            # blur
            blur_enabled=_bool("blur_enabled"),
            blur_pos_x=_float("blur_pos_x", 0.0),
            blur_pos_y=_float("blur_pos_y", 57.3),
            blur_width=_float("blur_width", 100.0),
            blur_height=_float("blur_height", 7.0),
            blur_opacity=_float("blur_opacity", 100.0),
            # text banner
            text_enabled=bool(_str("overlay_text")),
            text_content=_str("overlay_text"),
            text_font=_str("text_font", "Kantumruy Pro"),
            text_font_path=_str("text_font_path"),
            text_size=_float("text_size", 3.0),
            text_opacity=_float("text_opacity", 90.0),
            text_pos_y=_float("text_pos_y", 15.0),
            # logo
            logo_enabled=logo_uploaded,
            logo_size=_float("logo_scale", 0.54) * 100,
            logo_opacity=_float("logo_opacity", 0.1) * 100,
        )

    @classmethod
    def from_custom_edits(cls, custom_edits: dict,
                          width: int = 1080, height: int = 1920) -> "PreviewRenderConfig":
        """Build a ``PreviewRenderConfig`` from a legacy ``custom_edits`` dict.

        Useful when an existing API caller already assembled the dict and you
        need a typed config object for the unified pipeline.
        """
        edits = custom_edits or {}
        sub = edits.get("subtitles", {})
        blur = edits.get("blur", {})
        txt = edits.get("text", {})
        logo = edits.get("logo", {})
        return cls(
            video_width=width,
            video_height=height,
            sub_enabled=bool(sub.get("enabled", False)),
            sub_preset=str(sub.get("preset", "Outline")),
            sub_font=str(sub.get("font", "Kantumruy Pro")),
            sub_font_path=str(sub.get("font_path", "") or ""),
            sub_size=float(sub.get("size", 3.0)),
            sub_opacity=float(sub.get("opacity", 100)),
            sub_outline=float(sub.get("outline", 0.3)),
            sub_pos_y=float(sub.get("posY", 62.0)),
            sub_anim=str(sub.get("anim", "None")),
            sub_max_chars=int(sub.get("max_chars", 36)),
            sub_text_color=str(sub.get("text_color", "#FFFFFF")),
            sub_outline_color=str(sub.get("outline_color", "#000000")),
            blur_enabled=bool(blur.get("enabled", False)),
            blur_pos_x=float(blur.get("posX", 0.0)),
            blur_pos_y=float(blur.get("posY", 57.3)),
            blur_width=float(blur.get("width", 100.0)),
            blur_height=float(blur.get("height", 7.0)),
            blur_opacity=float(blur.get("opacity", 100.0)),
            text_enabled=bool(txt.get("enabled", False)),
            text_content=str(txt.get("content", "")),
            text_font=str(txt.get("font", "Kantumruy Pro")),
            text_font_path=str(txt.get("font_path", "") or ""),
            text_size=float(txt.get("size", 4.3)),
            text_opacity=float(txt.get("opacity", 90.0)),
            text_pos_y=float(txt.get("posY", 15.0)),
            logo_enabled=bool(logo.get("enabled", False)),
            logo_size=float(logo.get("size", 54.0)),
            logo_opacity=float(logo.get("opacity", 10.0)),
        )

    def to_sub_cfg(self) -> dict:
        """Return the ``sub_cfg`` slice consumed by ``render_subtitle_png_overlay()``
        and ``generate_ass_subtitles()``.
        """
        return {
            "enabled":   self.sub_enabled,
            "preset":    self.sub_preset,
            "font":      self.sub_font,
            "font_path": self.sub_font_path,
            "size":      self.sub_size,
            "opacity":   self.sub_opacity,
            "outline":   self.sub_outline,
            "posY":      self.sub_pos_y,
            "anim":      self.sub_anim,
            "max_chars": self.sub_max_chars,
            "text_color": self.sub_text_color,
            "outline_color": self.sub_outline_color,
        }

    def to_custom_edits(self) -> dict:
        """Convert back to the ``custom_edits`` dict format that ``render_edited_video()``
        and other internal engine methods consume.  Keeps the internal API stable.
        """
        return {
            "subtitles": self.to_sub_cfg(),
            "blur": {
                "enabled": self.blur_enabled,
                "posX":    self.blur_pos_x,
                "posY":    self.blur_pos_y,
                "width":   self.blur_width,
                "height":  self.blur_height,
                "opacity": self.blur_opacity,
            },
            "text": {
                "enabled":   self.text_enabled,
                "content":   self.text_content,
                "font":      self.text_font,
                "font_path": self.text_font_path,
                "size":      self.text_size,
                "opacity":   self.text_opacity,
                "posY":      self.text_pos_y,
            },
            "logo": {
                "enabled": self.logo_enabled,
                "size":    self.logo_size,
                "opacity": self.logo_opacity,
            },
        }



_GLOBAL_WHISPER_CACHE = {}
_GLOBAL_GPU_CAPS = None


class VideoDubberEngine:
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback
        self._loaded_whisper_model = None
        self._loaded_model_name = None

    def log(self, step, progress, message):
        safe_msg = str(message)
        try:
            print(f"[{step}] {progress}% - {safe_msg}")
        except Exception:
            pass
        if self.progress_callback:
            self.progress_callback({"step": step, "progress": progress, "message": safe_msg})

    def run_command(self, cmd):
        """Run a subprocess command with UTF-8 encoding."""
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            shell=isinstance(cmd, str)
        )
        if res.returncode != 0:
            raise RuntimeError(f"Command failed (exit {res.returncode}): {res.stderr}")
        return res.stdout

    def get_media_duration(self, file_path):
        """Get duration in seconds using wave fast-path for WAV (<0.0001s), OpenCV/ffprobe for video."""
        if not file_path or not os.path.exists(file_path):
            return 0.0

        if str(file_path).lower().endswith(".wav"):
            try:
                with contextlib.closing(wave.open(file_path, 'r')) as f:
                    frames = f.getnframes()
                    rate = f.getframerate()
                    if rate > 0:
                        return frames / float(rate)
            except Exception:
                pass

        # Tier 1: Try ffprobe
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        try:
            output = self.run_command(cmd)
            val = float(output.strip())
            if val > 0:
                return val
        except Exception:
            pass

        # Tier 2: Try OpenCV VideoCapture
        try:
            import cv2
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                cap.release()
                if fps > 0 and frame_count > 0:
                    return frame_count / fps
        except Exception:
            pass

        # Tier 3: Try ffmpeg -i parsing from stderr
        try:
            res = subprocess.run(["ffmpeg", "-i", file_path], stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="replace")
            import re
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
            if match:
                h, m, s = match.groups()
                return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            pass

        return 0.0

    def detect_caption_region(self, video_path):
        """
        Smart horizontal edge-density projection to auto-detect original hardcoded subtitle strip.
        Scans the lower 40%-98% of each frame, builds a per-row edge density profile,
        and finds the continuous band of rows with the highest text activity.
        Returns: { 'posY': float, 'height': float, 'posX': float, 'width': float, 'detected': bool }
        """
        no_detect = {"posY": 0.0, "height": 0.0, "posX": 0.0, "width": 100.0, "detected": False}
        if not video_path or not os.path.exists(video_path):
            return no_detect

        try:
            import cv2
            import numpy as np

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return no_detect

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            if width <= 0 or height <= 0 or total_frames <= 0:
                cap.release()
                return no_detect

            # Search zone: lower 40% to 98% of frame height
            search_top    = int(height * 0.40)
            search_bottom = int(height * 0.98)
            search_h      = search_bottom - search_top

            if search_h <= 0:
                cap.release()
                return no_detect

            # Accumulate row-wise edge density profile across sampled frames
            density_profile = np.zeros(search_h, dtype=np.float64)
            frames_used = 0

            sample_indices = np.linspace(
                int(total_frames * 0.08),
                int(total_frames * 0.92),
                num=24, dtype=int
            )

            for f_idx in sample_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                roi  = gray[search_top:search_bottom, :]

                # Canny edges
                edges = cv2.Canny(roi, 80, 200)

                # Bright pixel mask (white / yellow subtitle text, luminance > 170)
                _, bright = cv2.threshold(roi, 170, 255, cv2.THRESH_BINARY)
                text_signal = cv2.bitwise_and(edges, bright)

                # Per-row sum → how many bright edge pixels in this row
                row_sums = np.sum(text_signal, axis=1).astype(np.float64)
                density_profile += row_sums
                frames_used += 1

            cap.release()

            if frames_used == 0:
                return no_detect

            # Normalize profile
            density_profile /= frames_used

            # Smooth with a small Gaussian kernel to merge nearby lines into a strip
            kernel_size = max(3, int(search_h * 0.015))
            if kernel_size % 2 == 0:
                kernel_size += 1
            smoothed = cv2.GaussianBlur(
                density_profile.reshape(-1, 1).astype(np.float32),
                (1, kernel_size), 0
            ).flatten()

            # Threshold: consider rows that exceed 25% of the max density as "active"
            threshold = smoothed.max() * 0.25
            if threshold <= 0:
                return no_detect

            active_rows = np.where(smoothed >= threshold)[0]
            if len(active_rows) == 0:
                return no_detect

            # Find the densest continuous run of active rows
            # Split by gaps > 5% of search height
            max_gap = max(4, int(search_h * 0.05))
            runs = []
            run_start = active_rows[0]
            prev = active_rows[0]
            for r in active_rows[1:]:
                if r - prev > max_gap:
                    runs.append((run_start, prev))
                    run_start = r
                prev = r
            runs.append((run_start, prev))

            # Pick the run with highest total density
            best_run = max(runs, key=lambda seg: smoothed[seg[0]:seg[1]+1].sum())
            strip_top    = best_run[0]
            strip_bottom = best_run[1]

            # Add a 1px per side padding
            pad = max(2, int(search_h * 0.008))
            strip_top    = max(0, strip_top - pad)
            strip_bottom = min(search_h - 1, strip_bottom + pad)

            # Convert back to full-frame absolute pixels
            abs_top    = search_top + strip_top
            abs_bottom = search_top + strip_bottom
            strip_h    = abs_bottom - abs_top

            # Cap: no wider than 15% of frame height (avoid picking up scene content)
            max_h_px = int(height * 0.15)
            if strip_h > max_h_px:
                # Anchor to the bottom of the detected band and shrink upward
                abs_top  = abs_bottom - max_h_px
                strip_h  = max_h_px

            if strip_h < int(height * 0.02):
                return no_detect

            pos_y_pct  = round((abs_top  / float(height)) * 100.0, 2)
            height_pct = round((strip_h  / float(height)) * 100.0, 2)

            return {
                "posY":     pos_y_pct,
                "height":   height_pct,
                "posX":     0.0,
                "width":    100.0,
                "detected": True
            }

        except Exception as e:
            print(f"Caption region auto-detection error: {e}")
            return no_detect


    def extract_audio(self, video_path, output_audio_path):

        """Extract 16kHz mono WAV — optimised for Whisper transcription."""
        self.log("extract_audio", 10, "Extracting audio track from video...")
        self.run_command([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            output_audio_path
        ])
        return output_audio_path

    def extract_stereo_audio(self, video_path, output_audio_path):
        """Extract full-quality stereo 44.1kHz WAV — required for vocal removal.

        Center-channel cancellation (c0-c1) only works on STEREO audio.
        Using mono audio would give c0-c1 = 0 (complete silence).
        """
        self.log("extract_audio", 12, "Extracting stereo audio for background processing...")
        self.run_command([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            output_audio_path
        ])
        return output_audio_path

    def extract_all_audio_tracks(self, video_path, output_mono_path, output_stereo_path):
        """Extract both 16kHz mono WAV (Whisper) and 44.1kHz stereo WAV (BGM/UVR) in a single high-speed FFmpeg pass."""
        self.log("extract_audio", 10, "Extracting audio tracks from video (single-pass high speed)...")
        self.run_command([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", output_mono_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", output_stereo_path
        ])
        return output_mono_path, output_stereo_path

    def detect_gpu_capabilities(self):
        """Auto-detect available GPU hardware acceleration for PyTorch (Whisper) and FFmpeg (NVENC/QSV/AMF), tuned for system hardware."""
        global _GLOBAL_GPU_CAPS
        if _GLOBAL_GPU_CAPS is not None:
            return _GLOBAL_GPU_CAPS

        caps = {
            "torch_gpu": False,
            "gpu_name": "None",
            "vram_gb": 0.0,
            "ffmpeg_encoder": "libx264",
            "ffmpeg_preset": ["-preset", "superfast", "-threads", "0"]
        }
        try:
            import torch
            if torch.cuda.is_available():
                caps["torch_gpu"] = True
                caps["gpu_name"] = torch.cuda.get_device_name(0)
                tot_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                caps["vram_gb"] = round(tot_mem, 1)
        except Exception:
            pass

        try:
            res = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            encoders = res.stdout or ""
            if "h264_nvenc" in encoders:
                caps["ffmpeg_encoder"] = "h264_nvenc"
                # Ultra-fast high throughput GPU hardware encoding (p1 preset, low-latency, 500+ FPS)
                caps["ffmpeg_preset"] = ["-preset", "p1", "-tune", "ll", "-rc", "vbr", "-cq", "23", "-b:v", "0"]
            elif "h264_qsv" in encoders:
                caps["ffmpeg_encoder"] = "h264_qsv"
                caps["ffmpeg_preset"] = ["-preset", "veryfast"]
            elif "h264_amf" in encoders:
                caps["ffmpeg_encoder"] = "h264_amf"
                caps["ffmpeg_preset"] = ["-quality", "speed"]
            else:
                caps["ffmpeg_encoder"] = "libx264"
                caps["ffmpeg_preset"] = ["-preset", "ultrafast", "-threads", "0"]
        except Exception as e:
            print(f"FFmpeg GPU detection error: {e}")

        _GLOBAL_GPU_CAPS = caps
        return caps

    def load_whisper_model(self, model_name="base"):
        global _GLOBAL_WHISPER_CACHE
        if model_name in _GLOBAL_WHISPER_CACHE:
            self._loaded_whisper_model = _GLOBAL_WHISPER_CACHE[model_name]
            self._loaded_model_name = model_name
            return self._loaded_whisper_model

        if self._loaded_whisper_model is None or self._loaded_model_name != model_name:
            caps = self.detect_gpu_capabilities()
            device = "cpu"
            # VRAM safety check: GTX 1050 (2GB VRAM) handles tiny, base, small on CUDA GPU (~0.4 - 1.0GB VRAM)
            # If medium/large requested on 2GB VRAM, auto-fallback to CPU to avoid CUDA Out-Of-Memory error!
            if caps["torch_gpu"]:
                if caps["vram_gb"] < 3.5 and model_name.lower() in ["medium", "large", "large-v3"]:
                    self.log("transcribe", 20, f"ℹ️ Model '{model_name}' requires >3GB VRAM (GPU has {caps['vram_gb']}GB). Running safely on multi-core CPU...")
                    device = "cpu"
                else:
                    device = "cuda"

            if device == "cuda":
                self.log("transcribe", 20, f"🚀 Hardware Acceleration: Running Whisper AI ('{model_name}') on GPU [{caps['gpu_name']} - {caps['vram_gb']}GB VRAM]...")
            else:
                try:
                    import torch
                    threads = max(4, os.cpu_count() or 8)
                    torch.set_num_threads(threads)
                    torch.set_num_interop_threads(2)
                except Exception:
                    pass
                self.log("transcribe", 20, f"Running Whisper AI model ('{model_name}') on multi-core CPU...")

            model = whisper.load_model(model_name, device=device)
            _GLOBAL_WHISPER_CACHE[model_name] = model
            self._loaded_whisper_model = model
            self._loaded_model_name = model_name
        return self._loaded_whisper_model

    def transcribe_with_gemini(self, audio_path, api_key, model_name="gemini-1.5-flash"):
        """Transcribe audio track directly using Google Gemini Multimodal Audio API."""
        if not api_key:
            return None, "en"

        self.log("transcribe", 30, f"Transcribing audio with Google Gemini Audio AI ({model_name})...")
        try:
            target_audio_file = audio_path
            mime_type = "audio/wav"
            temp_mp3 = audio_path + ".compressed.mp3"
            try:
                self.run_command([
                    "ffmpeg", "-y", "-i", audio_path,
                    "-ac", "1", "-ar", "16000", "-b:a", "32k", temp_mp3
                ])
                if os.path.exists(temp_mp3) and os.path.getsize(temp_mp3) > 100:
                    target_audio_file = temp_mp3
                    mime_type = "audio/mp3"
            except Exception as e:
                print(f"Gemini audio compression warning: {e}")

            with open(target_audio_file, "rb") as f:
                audio_bytes = f.read()

            if len(audio_bytes) > 18 * 1024 * 1024:
                audio_bytes = audio_bytes[:18 * 1024 * 1024]

            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")

            prompt = """You are an expert audio transcriber.
Listen to this audio file and transcribe all spoken dialogue accurately.
Respond STRICTLY in valid JSON list format of segment objects with precise start, end timestamps (in seconds) and spoken text:
[
  {"start": 0.0, "end": 3.5, "text": "Transcribed speech line..."},
  {"start": 3.5, "end": 7.0, "text": "Next segment..."}
]"""

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": b64_audio
                                }
                            }
                        ]
                    }
                ]
            }

            clean_key = re.sub(r'\s+', '', str(api_key))
            clean_key = re.sub(r'[^\w\-\._]', '', clean_key)

            primary_model = model_name.strip() if model_name and model_name not in ["gemini-audio", "base"] else "gemini-2.0-flash"
            valid_models = [primary_model, "gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro"]
            seen = set()
            models_to_try = [m for m in valid_models if m and not (m in seen or seen.add(m))]

            for m in models_to_try:
                for ver in ["v1beta", "v1"]:
                    url = f"https://generativelanguage.googleapis.com/{ver}/models/{m}:generateContent?key={clean_key}"
                    data = json.dumps(payload).encode("utf-8")
                    
                    # Retry on 429 rate limit up to 2 times
                    for attempt in range(2):
                        try:
                            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                            with urllib.request.urlopen(req, timeout=35) as resp:
                                result = json.loads(resp.read().decode("utf-8"))
                                text_res = result["candidates"][0]["content"]["parts"][0]["text"]
                                clean_json = re.sub(r'```(?:json)?', '', text_res).strip('` \n')
                                parsed = json.loads(clean_json)
                                if isinstance(parsed, list) and len(parsed) > 0:
                                    segs = []
                                    for idx, s in enumerate(parsed, start=1):
                                        txt = str(s.get("text", "")).strip()
                                        st = float(s.get("start", 0.0))
                                        et = float(s.get("end", st + 2.5))
                                        if txt:
                                            segs.append({
                                                "id": idx,
                                                "start": round(st, 3),
                                                "end": round(et, 3),
                                                "duration": round(et - st, 3),
                                                "original_text": txt,
                                                "translated_text": txt
                                            })
                                    if segs:
                                        self.log("transcribe", 40, f"Gemini Audio Transcription complete! ({len(segs)} segments using {m})")
                                        return segs, "auto"
                        except urllib.error.HTTPError as he:
                            if he.code == 429 and attempt == 0:
                                print(f"Gemini Audio ({m} [{ver}]) rate limited (429). Pausing 2.5s before retry...")
                                time.sleep(2.5)
                                continue
                            elif he.code == 404:
                                break
                            print(f"Gemini Audio ({m} [{ver}]) HTTP error {he.code}: {he}")
                            break
                        except Exception as ex:
                            print(f"Gemini Audio ({m} [{ver}]) error: {ex}")
                            break

        except Exception as e:
            print(f"Gemini Audio Transcription error: {e}")

        return None, "en"

    def transcribe_with_groq(self, audio_path, api_key):
        """Transcribe audio using Groq Cloud free Whisper-Large-v3 API (Ultra Fast & 100% Free)."""
        if not api_key:
            return None, "en"
        try:
            self.log("transcribe", 30, "Transcribing with Groq Cloud Whisper-Large-v3 AI...")
            clean_key = re.sub(r'\s+', '', str(api_key)).strip()
            
            # Compress audio to 32k MP3 for rapid upload
            target_mp3 = audio_path + ".groq.mp3"
            try:
                self.run_command([
                    "ffmpeg", "-y", "-i", audio_path,
                    "-ac", "1", "-ar", "16000", "-b:a", "32k", target_mp3
                ])
                upload_file = target_mp3 if os.path.exists(target_mp3) else audio_path
            except Exception:
                upload_file = audio_path

            import uuid
            boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
            body = []
            
            fields = [
                ("model", "whisper-large-v3"),
                ("response_format", "verbose_json"),
                ("timestamp_granularities[]", "word"),
            ]
            for k, v in fields:
                body.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8'))
            
            filename = os.path.basename(upload_file)
            body.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode('utf-8'))
            with open(upload_file, 'rb') as f:
                body.append(f.read())
            body.append(f'\r\n--{boundary}--\r\n'.encode('utf-8'))
            
            full_body = b''.join(body)
            headers = {
                "Authorization": f"Bearer {clean_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}"
            }
            
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            req = urllib.request.Request(url, data=full_body, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                raw_segs = result.get("segments", [])
                detected_lang = result.get("language", "en")
                segs = []
                for idx, s in enumerate(raw_segs, start=1):
                    txt = str(s.get("text", "")).strip()
                    if not txt:
                        continue
                    words = s.get("words", [])
                    if words:
                        st = round(float(words[0]["start"]), 3)
                        et = round(float(words[-1]["end"]), 3)
                    else:
                        st = round(float(s.get("start", 0.0)), 3)
                        et = round(float(s.get("end", st + 2.5)), 3)
                    if (et - st) < 0.1:
                        et = round(st + 0.5, 3)
                    segs.append({
                        "id": idx,
                        "start": st,
                        "end": et,
                        "duration": round(et - st, 3),
                        "original_text": txt,
                        "translated_text": txt
                    })
                if segs:
                    self.log("transcribe", 40, f"Groq Whisper-Large-v3 complete! ({len(segs)} segments, lang='{detected_lang}')")
                    return segs, detected_lang
        except Exception as e:
            print(f"Groq Cloud Whisper API error: {e}")
        return None, "en"

    def transcribe(self, audio_path, model_name="base", source_lang=None, gemini_api_key=None, gemini_model="gemini-2.0-flash", groq_api_key=None):
        """Transcribe speech with Groq Cloud Whisper, Gemini Audio AI, or Local Whisper AI."""
        if "groq" in str(model_name).lower():
            groq_key = groq_api_key or os.environ.get("GROQ_API_KEY")
            if groq_key:
                g_segs, g_lang = self.transcribe_with_groq(audio_path, groq_key)
                if g_segs:
                    return g_segs, g_lang
            self.log("transcribe", 25, "Groq API key missing or failed. Falling back to Whisper AI...")
            model_name = "base"

        if str(model_name).lower() in ["gemini-audio", "gemini"] or str(model_name).startswith("gemini"):
            gemini_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
            if gemini_key:
                g_segs, g_lang = self.transcribe_with_gemini(audio_path, gemini_key, model_name=gemini_model)
                if g_segs:
                    return g_segs, g_lang
            self.log("transcribe", 25, "Gemini Audio API key missing or failed. Falling back to Whisper AI...")
            model_name = "base"

        self.log("transcribe", 25, "Transcribing speech with Whisper AI...")
        model = self.load_whisper_model(model_name)

        use_fp16 = False
        try:
            import torch
            if torch.cuda.is_available():
                use_fp16 = True
        except Exception:
            pass

        options = {
            "beam_size": 1,                       # Greedy decoding — 3x faster than beam=5
            "best_of": 1,
            "condition_on_previous_text": False,  # Crucial for 1h+ audio: prevents hallucination loops
            "compression_ratio_threshold": 2.4,   # Filter out repetitive loop text
            "logprob_threshold": -1.0,            # Discard low confidence hallucinated segments
            "no_speech_threshold": 0.6,           # Skip silence/noise segments
            "temperature": 0.0,                   # Deterministic
            "fp16": use_fp16,                     # Use FP16 if CUDA GPU available
            "word_timestamps": True,              # Precise per-word timestamps
        }
        if source_lang and source_lang != "auto":
            options["language"] = source_lang

        result = model.transcribe(audio_path, **options)
        raw_segments = result.get("segments", [])
        detected_lang = result.get("language", "en")

        processed_segments = []
        for seg in raw_segments:
            text = seg.get("text", "").strip()
            if not text:
                continue

            # Anchor start to first spoken word for precise sync
            words = seg.get("words", [])
            if words:
                start_t = round(float(words[0]["start"]), 3)
                end_t   = round(float(words[-1]["end"]), 3)
            else:
                start_t = round(float(seg["start"]), 3)
                end_t   = round(float(seg["end"]), 3)

            if (end_t - start_t) < 0.2:  # Skip sub-200ms blips
                continue
            processed_segments.append({
                "id": len(processed_segments) + 1,
                "start": start_t,
                "end":   end_t,
                "duration": round(end_t - start_t, 3),
                "original_text": text,
                "translated_text": text
            })

        self.log("transcribe", 40, f"Transcription done! {len(processed_segments)} segments, lang='{detected_lang}'")
        return processed_segments, detected_lang

    def translate_segments(self, segments, target_lang="km", source_lang="auto", gemini_api_key=None, gemini_model="gemini-2.0-flash", groq_api_key=None, deepseek_api_key=None, openrouter_api_key=None, openai_api_key=None, relationship_mode="auto", primary_ai_model="gemini"):
        """LLM Story-Aware Batched Translation: DeepSeek -> Groq AI -> Gemini -> OpenRouter -> GoogleTranslator fallback."""
        total_segs = len(segments)
        if not segments:
            return segments, {"summary": "Empty"}

        gemini_key = gemini_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        groq_key = groq_api_key or os.environ.get("GROQ_API_KEY")
        ds_key = deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY")
        or_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")
        oai_key = openai_api_key or os.environ.get("OPENAI_API_KEY")

        translated_by_llm = False
        story_report = None

        if ds_key or groq_key or gemini_key or or_key or oai_key:
            try:
                # Pre-run Whole-Transcript Smart Story Context Analysis (Groq Llama 3.3 70B / Gemini)
                llm_fn = lambda p: self._call_llm_api(
                    p,
                    gemini_api_key=gemini_key,
                    gemini_model=gemini_model,
                    groq_api_key=groq_key,
                    deepseek_api_key=ds_key,
                    openrouter_api_key=or_key,
                    openai_api_key=oai_key,
                    primary_ai_model=primary_ai_model
                )
                try:
                    from context_analyzer import StoryContextAnalyzer
                    analyzer = StoryContextAnalyzer()
                    story_report = analyzer.analyze_story_context(segments, llm_fn=llm_fn)
                    self.log("translate", 41, f"Story Context Analyzed: {story_report.get('summary', 'Context detected.')}")
                except Exception as c_err:
                    print(f"[StoryContext] Pre-analysis notice: {c_err}")

                # Label reflects user-selected primary provider
                if primary_ai_model == "gemini" and gemini_key:
                    engine_label = "Gemini AI (Primary)"
                elif primary_ai_model == "deepseek" and ds_key:
                    engine_label = "DeepSeek AI (Primary)"
                elif primary_ai_model == "groq" and groq_key:
                    engine_label = "Groq Llama 3.3 70B (Primary)"
                elif gemini_key:
                    engine_label = "Gemini LLM Story Translation"
                elif ds_key:
                    engine_label = "DeepSeek AI"
                else:
                    engine_label = "Groq Llama 3.3 70B AI"
                self.log("translate", 42, f"Translating {total_segs} segments to '{target_lang}' via {engine_label}...")
                translated_by_llm = self._translate_segments_llm(
                    segments,
                    target_lang=target_lang,
                    gemini_api_key=gemini_key,
                    gemini_model=gemini_model,
                    groq_api_key=groq_key,
                    deepseek_api_key=ds_key,
                    openrouter_api_key=or_key,
                    openai_api_key=oai_key,
                    primary_ai_model=primary_ai_model,
                    story_report=story_report
                )
            except Exception as exc:
                print(f"LLM translation pass failed ({exc}), falling back to GoogleTranslator.")
                translated_by_llm = False

        if not translated_by_llm:
            self.log("translate", 42, f"Translating {total_segs} segments to '{target_lang}' (GoogleTranslator fallback)...")
            self._translate_segments_google(segments, target_lang=target_lang, source_lang=source_lang)

        # ── Khmer Relational Pronoun Refinement Post-Pass ─────────────────────────
        if str(target_lang).lower() == "km":
            try:
                from context_analyzer import StoryContextAnalyzer
                analyzer = StoryContextAnalyzer()
                if story_report is None:
                    llm_fn = lambda p: self._call_llm_api(
                        p,
                        gemini_api_key=gemini_key,
                        gemini_model=gemini_model,
                        groq_api_key=groq_key,
                        deepseek_api_key=ds_key,
                        openrouter_api_key=or_key,
                        openai_api_key=oai_key,
                        primary_ai_model=primary_ai_model
                    )
                    report = analyzer.analyze_story_context(segments, llm_fn=llm_fn)
                else:
                    report = story_report
                segments = analyzer.refine_khmer_pronouns(segments, relationship_mode, report)
                self.log("translate", 56, f"Applied Khmer relational pronoun refinement ({report.get('detected_relationship', 'couple')}).")
            except Exception as p_err:
                print(f"Khmer pronoun post-pass notice: {p_err}")

        self.log("translate", 57, f"All {total_segs} segments translated successfully!")
        return segments, {"summary": "LLM Story Translation" if translated_by_llm else "Parallel Google Translation"}

    def _translate_segments_llm(self, segments, target_lang, gemini_api_key=None, gemini_model="gemini-2.0-flash", groq_api_key=None, deepseek_api_key=None, openrouter_api_key=None, openai_api_key=None, api_key=None, model_name=None, primary_ai_model="gemini", story_report=None):
        """Batched LLM Story Translation pass using _call_llm_api with Whole-Story & Relationship Context."""
        # Backward-compat shim: old callers pass positional api_key/model_name
        if api_key and not gemini_api_key:
            gemini_api_key = api_key
        if model_name and not gemini_model:
            gemini_model = model_name
        lang_info = SUPPORTED_LANGUAGES.get(target_lang, {})
        lang_name = lang_info.get("name", target_lang)

        # Build Whole-Story Context & Relationship Guide Block from story_report
        story_context_block = ""
        if story_report:
            rel_name = story_report.get("relationship_name", "")
            summary = story_report.get("summary", "")
            roles = story_report.get("character_roles", "")
            story_context_block = (
                f"\nWHOLE-STORY NARRATIVE & CHARACTER CONTEXT:\n"
                f"- Relationship Dynamic: {rel_name}\n"
                f"- Narrative Summary: {summary}\n"
                f"- Character Roles & Context: {roles}\n"
            )

        # Narrative chunk size: ~40 segments per batch (safe for context window & robust JSON response)
        BATCH_SIZE = 40
        batches = [segments[i:i + BATCH_SIZE] for i in range(0, len(segments), BATCH_SIZE)]
        num_batches = len(batches)

        self.log("translate", 43, f"Split into {num_batches} story translation LLM batches...")

        def translate_llm_batch(batch_idx, batch_segs):
            formatted_lines = []
            for idx, seg in enumerate(batch_segs):
                seg_id = str(seg.get("id", idx + 1))
                st = float(seg.get("start", 0.0))
                et = float(seg.get("end", st + 2.0))
                text = (seg.get("original_text") or seg.get("text") or "").strip()
                formatted_lines.append(f"{seg_id}. [{st:.1f}s - {et:.1f}s] {text}")

            chunk_text = "\n".join(formatted_lines)
            first_id = str(batch_segs[0].get("id", 1))
            last_id = str(batch_segs[-1].get("id", len(batch_segs)))

            prompt = f"""You are an expert film, television, and video dubbing translator.
Translate the following movie/video transcript into {lang_name}.
{story_context_block}
CRITICAL DUBBING TRANSLATION INSTRUCTIONS:
1. Translate for COMPLETE STORY MEANING, NARRATIVE CONTINUITY, CHARACTER RELATIONSHIPS, EMOTION, AND NATURAL DIALOGUE.
2. DO NOT do word-for-word or literal line translation. Adapt the dialogue so it sounds natural when spoken aloud in dubbing while conveying the exact story context.
3. Use appropriate relational terms, character pronouns, and conversational phrasing for {lang_name}:
   - Romantic Partners: Husband is 'បង', Wife is 'អូន'
   - Family: Parents use 'ម៉ាក់/ប៉ា', Children use 'កូន'
   - Close Friends: Use 'ឯង', 'ខ្ញុំ'
   - Formal/Professional: Use 'លោក', 'អ្នក'
4. Keep each line concise enough to match spoken video duration.
5. PRESERVE ALL SEGMENT IDs ({first_id} to {last_id}). DO NOT merge, skip, or split segment IDs.

REQUIRED OUTPUT FORMAT:
You MUST return ONLY a valid JSON object mapping string segment IDs to their translated text string:
{{
  "{first_id}": "translated text for line {first_id}...",
  ...
  "{last_id}": "translated text for line {last_id}..."
}}

TRANSCRIPT TO TRANSLATE:
{chunk_text}"""

            res_text = self._call_llm_api(
                prompt,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                groq_api_key=groq_api_key,
                deepseek_api_key=deepseek_api_key,
                openrouter_api_key=openrouter_api_key,
                openai_api_key=openai_api_key,
                primary_ai_model=primary_ai_model
            )
            if not res_text:
                raise ValueError(f"LLM returned empty response for batch {batch_idx+1}")

            # Clean JSON markdown fences or surrounding text
            clean_text = res_text.strip()
            clean_text = re.sub(r'^```(?:json)?', '', clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r'```$', '', clean_text, flags=re.MULTILINE).strip()

            first_brace = clean_text.find('{')
            last_brace = clean_text.rfind('}')
            if first_brace != -1 and last_brace != -1:
                clean_text = clean_text[first_brace:last_brace + 1]

            try:
                parsed_dict = json.loads(clean_text)
            except Exception as json_err:
                print(f"JSON parse error on LLM batch {batch_idx+1}: {json_err}. Raw output snippet: {res_text[:200]}")
                raise ValueError(f"Invalid JSON returned by LLM: {json_err}")

            if not isinstance(parsed_dict, dict):
                raise ValueError("LLM output is not a JSON object")

            missing_segs = []
            for idx, seg in enumerate(batch_segs):
                s_id = str(seg.get("id", idx + 1))
                if s_id in parsed_dict and str(parsed_dict[s_id]).strip():
                    seg["translated_text"] = str(parsed_dict[s_id]).strip()
                else:
                    missing_segs.append(seg)

            # Fill any missing segments via GoogleTranslator fallback
            if missing_segs:
                print(f"LLM Batch {batch_idx+1}: {len(missing_segs)} segments missing from JSON output, translating via GoogleTranslator...")
                translator = GoogleTranslator(source="auto", target=target_lang)
                for seg in missing_segs:
                    orig = (seg.get("original_text") or seg.get("text") or "").strip()
                    if orig:
                        try:
                            seg["translated_text"] = translator.translate(orig) or orig
                        except Exception:
                            seg["translated_text"] = orig

            return batch_idx, len(batch_segs)

        completed = 0
        workers = min(4, max(1, num_batches))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(translate_llm_batch, idx, b) for idx, b in enumerate(batches)]
            for future in as_completed(futures):
                idx, count = future.result()
                completed += 1
                pct = 42 + int((completed / num_batches) * 14)
                self.log("translate", pct, f"Translated LLM batch {completed}/{num_batches} ({count} segments)")

        return True

    def _translate_segments_google(self, segments, target_lang="km", source_lang="auto"):
        """Parallel GoogleTranslator fallback pass."""
        total_segs = len(segments)
        src = "auto" if source_lang == "auto" else source_lang
        translator = GoogleTranslator(source=src, target=target_lang)

        batches = []
        current_batch = []
        current_length = 0

        for seg in segments:
            text = (seg.get("original_text") or seg.get("text") or "").strip()
            if not text:
                continue
            if len(current_batch) >= 25 or (current_length + len(text) > 2200):
                batches.append(current_batch)
                current_batch = [seg]
                current_length = len(text)
            else:
                current_batch.append(seg)
                current_length += len(text) + 12

        if current_batch:
            batches.append(current_batch)

        num_batches = len(batches)

        def translate_single_batch(batch_tuple):
            idx, batch_segs = batch_tuple
            texts = [(s.get("original_text") or s.get("text") or "") for s in batch_segs]
            joined_text = " |||SPLIT||| ".join(texts)
            try:
                translated_str = translator.translate(joined_text)
                parts = [p.strip() for p in translated_str.split("|||SPLIT|||")]
                if len(parts) == len(batch_segs):
                    for seg, part in zip(batch_segs, parts):
                        seg["translated_text"] = part or (seg.get("original_text") or seg.get("text") or "")
                else:
                    for seg in batch_segs:
                        orig = (seg.get("original_text") or seg.get("text") or "")
                        try:
                            seg["translated_text"] = translator.translate(orig) or orig
                        except Exception:
                            seg["translated_text"] = orig
            except Exception as e:
                print(f"Batch {idx+1}/{num_batches} failed, translating individually: {e}")
                for seg in batch_segs:
                    orig = (seg.get("original_text") or seg.get("text") or "")
                    try:
                        seg["translated_text"] = translator.translate(orig) or orig
                    except Exception:
                        seg["translated_text"] = orig
            return idx, len(batch_segs)

        completed_count = 0
        workers = min(10, max(1, num_batches))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(translate_single_batch, (idx, batch)) for idx, batch in enumerate(batches)]
            for future in as_completed(futures):
                idx, count = future.result()
                completed_count += 1
                pct = 42 + int((completed_count / num_batches) * 14)
                self.log("translate", pct, f"Translated batch {completed_count}/{num_batches} ({count} segments)")


    def _call_groq_api(self, prompt, api_key, model_name="llama-3.3-70b-versatile"):
        """Call Groq Cloud AI API with expert system prompt for high-accuracy story translation."""
        if not api_key:
            return None

        clean_key = re.sub(r'\s+', '', str(api_key)).strip()
        if not clean_key or len(clean_key) < 10:
            return None

        valid_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"]
        model = model_name if model_name in valid_models else "llama-3.3-70b-versatile"

        system_prompt = (
            "You are an elite multilingual AI powered by Groq Llama 3.3 70B, specialized in film, television, and video dubbing translation.\n"
            "CRITICAL STORY & DUBBING PRINCIPLES:\n"
            "1. Analyze the WHOLE story narrative continuity and plot flow across the full transcript.\n"
            "2. Strictly enforce character relationship dynamics & social honorifics:\n"
            "   - Romantic Couples / Lovers: Male husband uses 'បង', Female wife uses 'អូន'\n"
            "   - Family (Parent & Child): Parents use 'ម៉ាក់/ប៉ា', Children use 'កូន'\n"
            "   - Close Friends / Peers: Friendly informal dialogue using 'ឯង', 'ខ្ញុំ'\n"
            "   - Formal / Professional: Business, official, or polite dialogue using 'លោក', 'អ្នក'\n"
            "3. Prioritize natural spoken dialogue flow and emotional tone for video dubbing — NEVER isolated word-for-word translation.\n"
            "4. Always respond with valid, well-formed JSON exactly as instructed. Never add explanations or markdown outside JSON."
        )

        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 8192
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {clean_key}",
            "User-Agent": "groq-python/0.11.0",
            "Accept": "application/json"
        }

        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                text = result["choices"][0]["message"]["content"]
                print(f"[Groq Cloud AI] Request successful ({model})!")
                return text
        except Exception as e:
            print(f"[Groq Cloud AI] Error calling {model}: {e}")
            return None

    def _call_openrouter_api(self, prompt, api_key, model_name=None):
        """Call OpenRouter AI API — tries top free models in cascade: DeepSeek-V3 → Llama-4 Maverick → Qwen3-72B."""
        if not api_key:
            return None

        clean_key = re.sub(r'\s+', '', str(api_key)).strip()
        if not clean_key or len(clean_key) < 10:
            return None

        # Best free models on OpenRouter ranked by reasoning quality
        free_models = [
            model_name if model_name else None,
            "deepseek/deepseek-chat-v3-0324:free",
            "meta-llama/llama-4-maverick:free",
            "qwen/qwen3-72b:free",
            "qwen/qwen-2.5-72b-instruct:free",
        ]
        # Remove None entries and deduplicate
        free_models = list(dict.fromkeys(m for m in free_models if m))

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {clean_key}",
            "HTTP-Referer": "https://videodubber.studio",
            "X-Title": "VideoDubberStudio"
        }

        system_msg = "You are an elite video dubbing and film localization AI. You specialize in producing natural, culturally accurate spoken dialogue translations that sound authentic when performed by voice actors."

        for model in free_models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": prompt}
                ],
                "temperature": 0.15
            }
            data = json.dumps(payload).encode("utf-8")
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    text = result["choices"][0]["message"]["content"]
                    print(f"[OpenRouter AI] ✓ Success with {model}")
                    return text
            except Exception as e:
                print(f"[OpenRouter AI] ✗ {model} failed: {e} — trying next model...")
                continue

        return None

    def _call_deepseek_api(self, prompt, api_key, model_name="deepseek-chat"):
        """Call DeepSeek AI API (Very cheap / generous free tier, OpenAI-compatible endpoint)."""
        if not api_key:
            return None

        clean_key = re.sub(r'\s+', '', str(api_key)).strip()
        if not clean_key or len(clean_key) < 10:
            return None

        valid_models = ["deepseek-chat", "deepseek-reasoner"]
        model = model_name if model_name in valid_models else "deepseek-chat"

        url = "https://api.deepseek.com/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {clean_key}"
        }

        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                text = result["choices"][0]["message"]["content"]
                print(f"[DeepSeek AI] Request successful ({model})!")
                return text
        except urllib.error.HTTPError as he:
            print(f"[DeepSeek AI] HTTP {he.code} error calling {model}: {he.reason}")
            return None
        except Exception as e:
            print(f"[DeepSeek AI] Error calling {model}: {e}")
            return None

    def _call_openai_api(self, prompt, api_key, model_name="gpt-4o-mini"):
        """Call OpenAI ChatGPT API (gpt-4o-mini / gpt-4o)."""
        if not api_key:
            return None

        clean_key = re.sub(r'\s+', '', str(api_key)).strip()
        if not clean_key or len(clean_key) < 10:
            return None

        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are an elite video dubbing & story context translator."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {clean_key}"
        }

        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=35) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                text = result["choices"][0]["message"]["content"]
                print(f"[OpenAI ChatGPT] Request successful ({model_name})!")
                return text
        except Exception as e:
            print(f"[OpenAI ChatGPT] Error calling {model_name}: {e}")
            return None

    def _call_llm_api(self, prompt, gemini_api_key=None, gemini_model="gemini-2.0-flash", groq_api_key=None, openrouter_api_key=None, deepseek_api_key=None, openai_api_key=None, primary_ai_model="gemini"):
        """Unified multi-provider LLM generator with user-selectable primary provider.
        Supports: Gemini, OpenAI ChatGPT, OpenRouter (50+ free models), DeepSeek, Groq.
        """
        g_key  = gemini_api_key   or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        ds_key = deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY")
        groq_key = groq_api_key   or os.environ.get("GROQ_API_KEY")
        or_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")
        oai_key = openai_api_key  or os.environ.get("OPENAI_API_KEY")

        def try_gemini():
            if g_key:
                res = self._call_gemini_api(prompt, g_key, model_name=gemini_model)
                if res:
                    return res
            return None

        def try_openai():
            if oai_key:
                res = self._call_openai_api(prompt, oai_key, model_name="gpt-4o-mini")
                if res:
                    return res
            return None

        def try_openrouter():
            if or_key:
                res = self._call_openrouter_api(prompt, or_key)
                if res:
                    return res
            return None

        def try_deepseek():
            if ds_key:
                res = self._call_deepseek_api(prompt, ds_key, model_name="deepseek-chat")
                if res:
                    return res
            return None

        def try_groq():
            if groq_key:
                res = self._call_groq_api(prompt, groq_key, model_name="llama-3.3-70b-versatile")
                if res:
                    return res
            return None

        # Build provider cascade based on user's primary model selection
        if primary_ai_model == "openai":
            cascade = [try_openai, try_openrouter, try_gemini, try_deepseek, try_groq]
        elif primary_ai_model == "openrouter":
            cascade = [try_openrouter, try_openai, try_gemini, try_deepseek, try_groq]
        elif primary_ai_model == "gemini":
            cascade = [try_gemini, try_openrouter, try_openai, try_deepseek, try_groq]
        elif primary_ai_model == "deepseek":
            cascade = [try_deepseek, try_openai, try_openrouter, try_groq, try_gemini]
        elif primary_ai_model == "groq":
            cascade = [try_groq, try_openrouter, try_gemini, try_deepseek, try_openai]
        elif primary_ai_model == "google_translate":
            # Google Translate only — skip all LLM providers
            return None
        else:
            # "auto" or unknown: Try all available providers
            cascade = [try_gemini, try_openai, try_openrouter, try_deepseek, try_groq]

        for provider_fn in cascade:
            result = provider_fn()
            if result:
                return result

        return None

    _KEY_RATE_LIMIT_EXPIRY = {}

    def _call_gemini_api(self, prompt, api_key, model_name="gemini-2.0-flash"):
        """Call Google Gemini REST API with multi-key pool rotation and instant 429 rate limit failover.
        Supports both standard API keys (AIzaSy...) and OAuth2 Bearer tokens (AQ... format).
        """
        if not api_key:
            return None

        # Parse potential multi-key pool (comma/newline/space separated)
        raw_keys = re.split(r'[,\s;\n]+', str(api_key))
        keys = []
        for k in raw_keys:
            ck = k.strip()
            # Preserve the key as-is (keep dots, dashes, underscores) - support AQ. prefix
            ck = re.sub(r'[^\w\-\._]', '', ck)
            if len(ck) >= 10 and ck not in keys:
                keys.append(ck)

        if not keys:
            print("Gemini API error: Invalid API key format.")
            return None

        import time
        now = time.time()

        # Filter out keys that were rate-limited in the last 45 seconds
        valid_keys = [k for k in keys if now > VideoDubberEngine._KEY_RATE_LIMIT_EXPIRY.get(k, 0)]
        if not valid_keys:
            print("[Gemini API] All API keys in pool are currently rate-limited (429). Instant failover to GoogleTranslator...")
            return None

        valid_models = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash", "gemini-1.5-pro"]
        primary_model = model_name if model_name in valid_models else "gemini-2.0-flash"

        def _is_bearer_token(k):
            """Detect OAuth2 / Bearer token format (AQ., ya29., etc.) vs standard API key."""
            return k.startswith(("AQ.", "ya29.", "AQ4", "AQV")) or (len(k) > 60 and "." in k[:5])

        def _make_gemini_request(url, data, headers):
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=35) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["candidates"][0]["content"]["parts"][0]["text"]

        models_to_try = [primary_model]
        for m in ["gemini-2.0-flash", "gemini-2.0-flash-lite"]:
            if m not in models_to_try:
                models_to_try.append(m)

        # Try each valid key in pool sequentially
        for key_idx, clean_key in enumerate(valid_keys, start=1):
            for current_model in models_to_try:
                base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent"
                payload = {
                    "systemInstruction": {
                        "parts": [{
                            "text": (
                                "You are an elite multilingual AI specialized in film, television, and video dubbing translation.\n"
                                "CRITICAL DUBBING PRINCIPLES:\n"
                                "1. Analyze the full narrative context and maintain story continuity across all segments.\n"
                                "2. Enforce character relationship dynamics & social honorifics consistently:\n"
                                "   - Romantic Couples: Male husband uses 'បង', Female wife uses 'អូន'\n"
                                "   - Family: Parents use 'ម៉ាក់/ប៉ា', Children use 'កូន'\n"
                                "   - Close Friends/Peers: Use informal 'ឯង', 'ខ្ញុំ'\n"
                                "   - Formal/Professional: Use 'លោក', 'អ្នក'\n"
                                "3. Produce natural spoken dialogue flow for dubbing — NOT word-for-word literal translation.\n"
                                "4. Respond ONLY with valid JSON exactly as instructed. No explanations or markdown outside the JSON."
                            )
                        }]
                    },
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.1, "topP": 0.85}
                }
                data = json.dumps(payload).encode("utf-8")

                try:
                    # Strategy 1: Standard ?key= param (works for AIzaSy AND AQ. style keys)
                    url = f"{base_url}?key={clean_key}"
                    text = _make_gemini_request(url, data, {"Content-Type": "application/json"})
                    if text:
                        return text

                except urllib.error.HTTPError as he:
                    if he.code == 429:
                        VideoDubberEngine._KEY_RATE_LIMIT_EXPIRY[clean_key] = time.time() + 45.0
                        print(f"Gemini API key #{key_idx} rate limited (429). Marked on 45s cooldown.")
                        if key_idx < len(valid_keys):
                            print(f"⚡ Rotating to Gemini API key #{key_idx + 1}...")
                            break
                        else:
                            print("[Gemini API] Key pool rate limited (429). Instant failover to GoogleTranslator.")
                            return None
                    elif he.code in (404, 400):
                        print(f"[Gemini API] Model '{current_model}' returned {he.code}, trying fallback model...")
                        continue
                    elif he.code in (401, 403):
                        # Strategy 2: ?key= rejected — retry as Bearer token (OAuth2 access tokens)
                        print(f"[Gemini API] Key #{key_idx} rejected as API key (HTTP {he.code}), retrying as Bearer token...")
                        try:
                            bearer_headers = {
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {clean_key}"
                            }
                            text = _make_gemini_request(base_url, data, bearer_headers)
                            if text:
                                return text
                        except urllib.error.HTTPError as he2:
                            if he2.code == 429:
                                VideoDubberEngine._KEY_RATE_LIMIT_EXPIRY[clean_key] = time.time() + 45.0
                                if key_idx < len(valid_keys):
                                    break
                                return None
                            elif he2.code in (404, 400):
                                continue
                            print(f"[Gemini API] Bearer retry also failed (HTTP {he2.code}): {he2}")
                        except Exception as e2:
                            print(f"[Gemini API] Bearer retry also failed: {e2}")
                    else:
                        print(f"Gemini API HTTP error {he.code}: {he}")
                        break
                except Exception as e:
                    print(f"Gemini API network error: {e}")
                    break

        return None

    def generate_movie_recap_script(self, segments, video_duration, target_lang="km", style="dramatic", gemini_api_key=None, gemini_model="gemini-2.0-flash", deepseek_api_key=None, groq_api_key=None, intro_speech=None, outro_speech=None):
        """Generate a 100% accurate, rich AI Movie Recap narration script anchored to exact original video scene timestamps."""
        if not segments:
            return []

        total_dur = float(video_duration) if video_duration and float(video_duration) > 5.0 else 60.0

        # Build timestamped scene transcript context
        scene_lines = []
        for idx, s in enumerate(segments, start=1):
            st = float(s.get("start", 0.0))
            et = float(s.get("end", st + 2.5))
            txt = (s.get("translated_text") or s.get("original_text") or s.get("text") or "").strip()
            scene_lines.append(f"Scene {idx} [{st:.1f}s - {et:.1f}s]: {txt}")

        transcript_context = "\n".join(scene_lines)
        num_orig_scenes = len(segments)
        self.log("recap", 45, f"Analyzing {num_orig_scenes} video scenes & generating 100% scene-accurate AI Movie Recap narration (style: '{style}', lang: '{target_lang}')...")

        recap_narrations = None
        gemini_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        ds_key = deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY")
        groq_key = groq_api_key or os.environ.get("GROQ_API_KEY")

        if ds_key or groq_key or gemini_key:
            provider_label = "DeepSeek AI" if ds_key else ("Groq AI" if groq_key else "Google Gemini")
            self.log("recap", 48, f"Invoking {provider_label} to compose {num_orig_scenes} scene-matched film review sentences...")
            prompt = f"""You are a top-tier YouTube Movie Recap Storyteller and Film Reviewer (សម្រាយរឿង).

CRITICAL REQUIREMENT - STRICT SCENE ACCURACY & CHARACTER ACTION FOCUS:
Base your movie recap summary STRICTLY on the provided video scenes below.
Describe the character actions, decisions, and movements happening in each scene.

INSTRUCTIONS:
1. Write a 100% ACCURATE third-person Movie Recap Script in {target_lang} (style: {style}).
2. Provide EXACTLY {num_orig_scenes} narrator review sentences in a JSON list, where string i describes the character action in Scene i.
3. Clearly name the characters and describe their exact actions (e.g. what they do, who they talk to, where they go, how they react).
4. Each sentence must be 1 short, vivid, action-focused narrator statement in {target_lang}.

SCENE TRANSCRIPT CONTENT:
{transcript_context}

Respond STRICTLY in valid JSON list format of EXACTLY {num_orig_scenes} string sentences:
[
  "Vivid character action recap for Scene 1...",
  "Vivid character action recap for Scene 2...",
  ...
]"""

            llm_res = self._call_llm_api(
                prompt,
                gemini_api_key=gemini_key,
                gemini_model=gemini_model,
                groq_api_key=groq_key,
                deepseek_api_key=ds_key
            )
            if llm_res:
                try:
                    clean_json = re.sub(r'```(?:json)?', '', llm_res).strip('` \n')
                    parsed = json.loads(clean_json)
                    if isinstance(parsed, list) and len(parsed) >= 2:
                        recap_narrations = [str(p) for p in parsed]
                except Exception as ex:
                    print(f"Failed to parse LLM recap response JSON: {ex}")

        # Fallback if all LLM providers fail or no keys set
        if not recap_narrations or len(recap_narrations) != num_orig_scenes:
            recap_narrations = []
            for s in segments:
                txt = (s.get("translated_text") or s.get("original_text") or "").strip()
                recap_narrations.append(txt or "នៅក្នុងឈុតឆាកនេះ សកម្មភាពបានបន្តទៅមុខ។")

        recap_segments = []
        curr_st = 0.0

        # Prepend Custom Intro Welcome Speech if enabled and provided
        if intro_speech and str(intro_speech).strip():
            clean_intro = self._fix_khmer_spelling(str(intro_speech).strip())
            spoken_dur = round(max(3.0, min(8.0, len(re.sub(r'\s+', '', clean_intro)) * 0.07)), 2)
            recap_segments.append({
                "id": 1,
                "start": 0.0,
                "end": spoken_dur,
                "duration": spoken_dur,
                "original_text": clean_intro,
                "translated_text": clean_intro,
                "text": clean_intro
            })
            curr_st = round(spoken_dur + 0.4, 2)

        for idx, (seg, item) in enumerate(zip(segments, recap_narrations), start=1):
            if isinstance(item, dict):
                sentence_text = str(item.get("text", "")).strip()
            else:
                sentence_text = str(item).strip()

            clean_sentence = self._fix_khmer_spelling(sentence_text).strip()
            if not clean_sentence:
                clean_sentence = (seg.get("translated_text") or seg.get("original_text") or "").strip()

            orig_st = float(seg.get("start", 0.0))
            orig_et = float(seg.get("end", orig_st + 3.0))
            orig_dur = max(1.8, orig_et - orig_st)

            # Rapid spoken speech rate (~0.045s/char at +18% speed)
            char_count = len(re.sub(r'\s+', '', clean_sentence))
            spoken_dur = round(max(1.8, min(orig_dur, char_count * 0.045)), 2)

            # Strictly cap start & end timestamps so recap segment NEVER exceeds original scene duration
            st = round(orig_st, 2)
            et = min(round(orig_et, 2), round(st + spoken_dur, 2))

            if et > total_dur:
                et = total_dur

            recap_segments.append({
                "id": len(recap_segments) + 1,
                "start": round(st, 2),
                "end": round(et, 2),
                "duration": round(et - st, 2),
                "original_text": clean_sentence,
                "translated_text": clean_sentence,
                "text": clean_sentence
            })

        # Append Custom Outro Ending Speech if enabled and provided
        if outro_speech and str(outro_speech).strip():
            clean_outro = self._fix_khmer_spelling(str(outro_speech).strip())
            spoken_dur = round(max(3.0, min(8.0, len(re.sub(r'\s+', '', clean_outro)) * 0.07)), 2)
            st = round(curr_st, 2)
            et = round(st + spoken_dur, 2)
            recap_segments.append({
                "id": len(recap_segments) + 1,
                "start": st,
                "end": et,
                "duration": spoken_dur,
                "original_text": clean_outro,
                "translated_text": clean_outro,
                "text": clean_outro
            })

        return recap_segments

    # ─── TTS: parallel async generation ──────────────────────────────────────

    async def _tts_one(self, text, voice, path, sem, rate="+0%", pitch="+0Hz"):
        """Async TTS for a single clip with concurrency throttling and voice tuning (rate, pitch)."""
        async with sem:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
            try:
                communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
                await communicate.save(path)
            except Exception:
                try:
                    communicate = edge_tts.Communicate(text, voice)
                    await communicate.save(path)
                except Exception as ex:
                    print(f"EdgeTTS error for '{path}' (voice={voice}): {ex}")
                    raise

    async def _generate_all_tts_async(self, tasks, rate="+0%", pitch="+0Hz"):
        """Run all (text, voice, path) TTS tasks with max 50 concurrent connections."""
        sem = asyncio.Semaphore(50)
        coros = []
        for text, voice, path in tasks:
            if text.strip():
                coros.append(self._tts_one(text, voice, path, sem, rate=rate, pitch=pitch))
            else:
                coros.append(asyncio.sleep(0))
        await asyncio.gather(*coros, return_exceptions=True)

    def synthesize_all_tts(self, segments, voice_id, temp_dir, audio_path_for_gender=None, target_lang="km", recap_style="standard", rvc_model=None, rvc_pitch=0):
        """Synthesize ALL TTS clips in PARALLEL with professional speech pitch & rate tuning and optional RVC Voice Cloning.

        Respects per-segment gender overrides stored in seg['gender']:
          'Female' / 'Male' → use the matching voice for target_lang
          'auto' / missing   → use the resolved global voice_id
        Applies RVC Voice Conversion if rvc_model is specified.
        """
        raw_voice_id = str(voice_id or "auto").strip()
        is_auto_voice_requested = (raw_voice_id.lower() == "auto")
        is_auto_rvc_requested = (str(rvc_model).strip().lower() == "auto_gender_match")

        if is_auto_voice_requested:
            self.log("tts_synthesis", 58, "Auto-detecting speaker gender from audio pitch...")
            voice_id = auto_select_voice(audio_path_for_gender or "", target_lang, SUPPORTED_LANGUAGES)
            self.log("tts_synthesis", 59, f"Auto-detected → voice: '{voice_id}'")
        else:
            self.log("tts_synthesis", 59, f"Using selected voice preference: '{voice_id}'")

        # Build a gender→voice_id lookup for this language so per-segment
        # overrides & auto-detections can be resolved to appropriate voices.
        lang_voices = SUPPORTED_LANGUAGES.get(target_lang, {}).get("voices", [])
        gender_voice_map: dict[str, str] = {}
        for v in lang_voices:
            g = str(v.get("gender", "")).strip().lower()
            if g and g not in gender_voice_map:
                gender_voice_map[g] = v["id"]

        from voices_config import get_voice_gender
        selected_voice_gender = get_voice_gender(voice_id, target_lang)

        # RVC Model Alignment: If RVC is enabled with a specific voice model, align base TTS voice gender to RVC model's gender!
        rvc_model_gender = "Unknown"
        is_rvc_enabled = rvc_model and str(rvc_model).lower() not in ("none", "disabled", "")
        if is_rvc_enabled and not is_auto_rvc_requested:
            try:
                from rvc_cloner import RVCVoiceCloner
                cloner = RVCVoiceCloner()
                models = cloner.list_models()
                target_key = os.path.basename(str(rvc_model)).strip().lower()
                target_m = next((m for m in models if m["filename"].lower() == target_key or m["id"].lower() == target_key or m["name"].lower() == target_key or target_key in m["filename"].lower()), None)
                if target_m and target_m.get("gender") in ("Female", "Male"):
                    rvc_model_gender = target_m["gender"]
                    g_key = rvc_model_gender.lower()
                    if g_key in gender_voice_map:
                        voice_id = gender_voice_map[g_key]
                        selected_voice_gender = rvc_model_gender
                        self.log("tts_synthesis", 59, f"RVC model '{os.path.basename(str(rvc_model))}' is {rvc_model_gender} → Base TTS voice aligned to {rvc_model_gender} ({voice_id})")
            except Exception as rvc_align_err:
                print(f"[TTS Synthesis] RVC model gender check note: {rvc_align_err}")

        # Load full source audio track for per-segment pitch & gender analysis
        y_full = None
        sr_full = 16000
        full_f0_series = None
        if (is_auto_voice_requested or is_auto_rvc_requested) and audio_path_for_gender and os.path.exists(audio_path_for_gender):
            try:
                import librosa
                from gender_detector import precompute_whole_track_f0, detect_gender_from_f0_slice
                y_full, sr_full = librosa.load(audio_path_for_gender, sr=16000, mono=True)
                full_f0_series = precompute_whole_track_f0(y_full, sr=sr_full)
                if full_f0_series is not None:
                    print(f"[TTS Synthesis] Loaded {len(y_full)/sr_full:.1f}s audio track (whole-track pitch vector pre-computed for fast slicing).")
                else:
                    print(f"[TTS Synthesis] Loaded {len(y_full)/sr_full:.1f}s audio track.")
            except Exception as e:
                print(f"[GenderDetector] Per-segment audio load note: {e}")

        # Per-Segment Gender Detection & Voice Assignment
        # In RECAP mode: always use the selected narrator voice — no gender switching.
        is_recap_mode = str(recap_style).lower() not in ("standard", "auto", "", "none")

        from gender_detector import detect_gender_from_audio, detect_gender_from_f0_slice, SHORT_SEG_TARGET_SEC, MAX_PAD_SEC
        if is_recap_mode:
            # Lock all segments to the selected narrator voice — single consistent narrator voice
            self.log("tts_synthesis", 58, f"Recap mode: all {len(segments)} segments use single narrator voice '{voice_id}'.")
            for seg in segments:
                seg["gender"] = "recap_narrator"  # special tag — bypasses gender_voice_map lookup
        elif not is_auto_voice_requested and not is_auto_rvc_requested:
            # Respect user's selected voice preference across all segments unless row has an explicit override
            self.log("tts_synthesis", 58, f"Using user selected voice preference '{voice_id}' ({selected_voice_gender}) across all segments...")
            for seg in segments:
                g_val = str(seg.get("gender", "")).strip().lower()
                if g_val not in ("male", "female"):
                    seg["gender"] = selected_voice_gender
        else:
            # Establish a whole-clip "anchor" gender once.
            anchor_gender = selected_voice_gender if selected_voice_gender in ("Female", "Male") else "Female"
            if full_f0_series is not None:
                anchor_gender = detect_gender_from_f0_slice(full_f0_series, 0.0, len(y_full) / sr_full)
            elif y_full is not None and len(y_full) > 0:
                anchor_gender = detect_gender_from_audio(y_full, sr_input=sr_full)
            last_known_gender = anchor_gender

            self.log("tts_synthesis", 58, f"Analyzing pitch per-segment for {len(segments)} dialogue clips (anchor: {anchor_gender})...")
            for idx, seg in enumerate(segments, start=1):
                g_val = str(seg.get("gender", "")).strip()

                # If segment has no explicit gender override or is 'auto', detect per segment!
                if not g_val or g_val.lower() in ("auto", "none"):
                    st = float(seg.get("start", 0.0))
                    et = float(seg.get("end", st + 1.0))
                    if full_f0_series is not None:
                        seg_gender = detect_gender_from_f0_slice(
                            full_f0_series, st, et, sr=sr_full, fallback_gender=last_known_gender
                        )
                    elif y_full is not None and len(y_full) > 0:
                        dur = et - st
                        pad = min(MAX_PAD_SEC, max(0.0, (SHORT_SEG_TARGET_SEC - dur) / 2.0))
                        s_idx = max(0, int((st - pad) * sr_full))
                        e_idx = min(len(y_full), int((et + pad) * sr_full))
                        seg_audio = y_full[s_idx:e_idx]

                        if len(seg_audio) >= int(sr_full * 0.15):
                            seg_gender = detect_gender_from_audio(
                                seg_audio, sr_input=sr_full, fallback_gender=last_known_gender
                            )
                        else:
                            seg_gender = last_known_gender
                    else:
                        seg_gender = last_known_gender

                    seg["gender"] = seg_gender
                    last_known_gender = seg_gender  # carry forward as continuity for the next uncertain segment
                    print(f"[TTS Synthesis] Segment #{idx} ({seg.get('start', 0)}s - {seg.get('end', 0)}s) → Gender: {seg_gender}")

        def _voice_for_segment(seg: dict) -> str:
            """Return the correct voice ID for this segment based on seg['gender']."""
            g_override = str(seg.get("gender", "")).strip().lower()
            # Recap mode: always return the single selected narrator voice
            if g_override == "recap_narrator":
                return voice_id
            if g_override in gender_voice_map:
                return gender_voice_map[g_override]
            if voice_id and voice_id != "auto":
                return voice_id
            return gender_voice_map.get("female", "km-KH-SreymomNeural")

        rate_val = "+0%"
        pitch_val = "+0Hz"
        self.log("tts_synthesis", 60, f"Synthesizing pure 100% original voice timbre speech (rate: {rate_val}, pitch: {pitch_val})...")

        os.makedirs(temp_dir, exist_ok=True)

        tts_clips = []
        tts_tasks = []
        silence_needed = []

        for i, seg in enumerate(segments):
            clip_path = os.path.join(temp_dir, f"seg_{seg['id']}.mp3")
            tts_clips.append(clip_path)
            text = seg.get("translated_text", "").strip()
            if text:
                seg_voice = _voice_for_segment(seg)
                tts_tasks.append((text, seg_voice, clip_path))
            else:
                silence_needed.append((i, clip_path))

        for _, clip_path in silence_needed:
            self.run_command([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                "-t", "0.5", "-q:a", "9", "-acodec", "libmp3lame", clip_path
            ])

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._generate_all_tts_async(tts_tasks, rate=rate_val, pitch=pitch_val))
        finally:
            loop.close()

        # Verify clips exist; replace missing with silence
        for i, clip_path in enumerate(tts_clips):
            if not os.path.exists(clip_path) or os.path.getsize(clip_path) < 100:
                self.run_command([
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", "0.5", "-q:a", "9", "-acodec", "libmp3lame", clip_path
                ])

        # ── RVC Voice Conversion Pass ─────────────────────────────────────────────
        if rvc_model and str(rvc_model).lower() not in ("none", "disabled", ""):
            try:
                from rvc_cloner import RVCVoiceCloner
                cloner = RVCVoiceCloner()

                is_auto_gender_rvc = str(rvc_model).strip().lower() == "auto_gender_match"

                batch_items = []
                cached_count = 0
                for i, clip_path in enumerate(tts_clips):
                    if os.path.exists(clip_path) and os.path.getsize(clip_path) > 100:
                        conv_out = os.path.join(temp_dir, f"rvc_seg_{i+1}.wav")

                        # Reuse an existing voice-cloned WAV ONLY if it was produced
                        # from the CURRENT TTS clip (i.e. conv_out is newer than
                        # clip_path). _tts_one() always deletes+rewrites clip_path
                        # fresh at the start of every synthesis pass, so a stale
                        # conv_out left over from an earlier pass (edited segments,
                        # changed RVC model/pitch, re-render) will always be OLDER
                        # than the freshly-written clip_path. Reusing it purely by
                        # index — without this check — plays the wrong segment's
                        # audio, which is what caused some segments to sound like
                        # duplicated/overlapping speech after an edit or re-render.
                        is_fresh_cache = (
                            os.path.exists(conv_out)
                            and os.path.getsize(conv_out) > 100
                            and os.path.getmtime(conv_out) >= os.path.getmtime(clip_path)
                        )
                        if is_fresh_cache:
                            cached_count += 1
                            tts_clips[i] = conv_out
                            continue
                        elif os.path.exists(conv_out):
                            # Stale leftover from a previous pass — remove it so it
                            # can never be picked up by mistake later.
                            try:
                                os.remove(conv_out)
                            except OSError:
                                pass

                        batch_item = {
                            "index": i,
                            "input": clip_path,
                            "output": conv_out
                        }
                        if is_auto_gender_rvc:
                            batch_item["gender"] = str(segments[i].get("gender", "")).strip().lower()
                        batch_items.append(batch_item)

                if cached_count > 0:
                    self.log("tts_synthesis", 70, f"Reusing {cached_count} voice-cloned clips from transcript pass (skipping duplicate RVC pass)...")

                if batch_items:
                    total_items = len(batch_items)

                    def rvc_progress_cb(curr, tot):
                        pct = 70 + int((curr / tot) * 4)
                        self.log("tts_synthesis", min(pct, 74), f"RVC Voice Cloning: clip {curr}/{tot}...")

                    if is_auto_gender_rvc:
                        male_models = cloner.get_models_by_gender("Male")
                        female_models = cloner.get_models_by_gender("Female")
                        gender_model_map = {}
                        if male_models:
                            gender_model_map["male"] = male_models[0]["path"]
                        if female_models:
                            gender_model_map["female"] = female_models[0]["path"]

                        if not gender_model_map:
                            self.log("tts_synthesis", 70, "Auto Gender Match RVC: no gender-tagged voice models found; skipping RVC.")
                        else:
                            missing = [g for g in ("male", "female") if g not in gender_model_map]
                            if missing:
                                self.log("tts_synthesis", 70, f"Auto Gender Match RVC: no {'/'.join(missing)} model tagged -- those segments will use the other gender's voice.")
                            self.log("tts_synthesis", 70, "Applying RVC Voice Cloning (auto gender match)...")
                            converted_cnt = cloner.convert_clips_batch_gender_matched(
                                clip_items=batch_items,
                                gender_model_map=gender_model_map,
                                pitch_shift=int(rvc_pitch or 0),
                                progress_callback=rvc_progress_cb,
                                per_segment_source_se=True,
                            )
                    else:
                        self.log("tts_synthesis", 70, f"Applying RVC Voice Cloning model: '{os.path.basename(rvc_model)}'...")
                        converted_cnt = cloner.convert_clips_batch(
                            clip_items=batch_items,
                            model_name_or_path=rvc_model,
                            pitch_shift=int(rvc_pitch or 0),
                            progress_callback=rvc_progress_cb,
                            per_segment_source_se=True,
                        )

                    # Update tts_clips to point to RVC-converted WAVs
                    for item in batch_items:
                        idx = item["index"]
                        conv_out = item["output"]
                        if os.path.exists(conv_out) and os.path.getsize(conv_out) > 100:
                            tts_clips[idx] = conv_out

                    if converted_cnt > 0:
                        self.log("tts_synthesis", 74, f"RVC Voice Cloning complete! Converted {converted_cnt}/{total_items} clips.")
                    else:
                        self.log("tts_synthesis", 74, "WARNING: RVC Voice Cloning produced 0 converted clips (using TTS audio fallback).")

            except Exception as rvc_err:
                print(f"RVC Voice Conversion notice: {rvc_err}")

        self.log("tts_synthesis", 75, f"All {len(tts_clips)} clips synthesized!")
        return tts_clips



    # ─── Alignment ────────────────────────────────────────────────────────────

    def _create_silence_wav(self, filepath, duration_sec, sample_rate=44100, channels=2):
        """Generate a binary 16-bit PCM WAV silence file in Python (<1ms without launching FFmpeg subprocess)."""
        if duration_sec <= 0:
            return filepath
        num_samples = int(round(duration_sec * sample_rate))
        silence_bytes = b'\x00\x00' * channels * num_samples
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(silence_bytes)
        return filepath

    def align_and_combine_speech(self, segments, tts_clips, total_video_duration, output_speech_path, temp_dir, is_recap=False):
        """Align TTS clips to timestamps using multi-threaded parallel clip rendering.
        
        is_recap=False (Full Speech Dubbing - YouTube Dubbing 1:1):
            Guarantees 100% exact 1:1 timestamp alignment matching original video audio.
            Auto speed adjustment calculated directly based on segment target duration (end - start).
        is_recap=True (Movie Recap AI):
            Applies smooth continuous narrator pacing.
        """
        self.log("align_audio", 78, "Aligning speech timestamps (parallel processing)...")

        # Build list of alignment sub-tasks with full complete speech preservation
        align_tasks = []
        timeline_cursor = 0.0

        for i, (seg, raw_clip) in enumerate(zip(segments, tts_clips)):
            start = float(seg.get("start", timeline_cursor))
            end = float(seg.get("end", start + 2.0))
            target_duration = max(0.1, round(end - start, 3))
            clip_duration = self.get_media_duration(raw_clip)

            if is_recap:
                if clip_duration <= target_duration:
                    speed = 1.0
                    actual_content_dur = clip_duration
                else:
                    speed = min(1.25, clip_duration / target_duration)
                    actual_content_dur = max(target_duration, clip_duration / speed)

                gap = start - timeline_cursor
                if gap > 1.5:
                    gap = 1.5
                elif gap < 0:
                    gap = 0.0
            else:
                # 100% Exact 1:1 YouTube Dubbing Mode:
                # Calculate auto speed adjustment ratio based on target segment duration.
                # If synthesized audio clip is longer than target_duration (end - start),
                # speed up clip via atempo filter so output audio duration == target_duration.
                if clip_duration > 0 and target_duration > 0:
                    if clip_duration > target_duration:
                        speed = clip_duration / target_duration
                    else:
                        speed = 1.0
                else:
                    speed = 1.0

                actual_content_dur = target_duration

                gap = start - timeline_cursor
                if gap < 0:
                    gap = 0.0

            gap_file = None
            if gap > 0.01:
                gap_file = os.path.join(temp_dir, f"silence_pre_{i}.wav")

            adj_file = os.path.join(temp_dir, f"adj_{seg['id']}.wav")

            align_tasks.append({
                "index": i,
                "raw_clip": raw_clip,
                "gap": gap,
                "gap_file": gap_file,
                "target_duration": target_duration,
                "clip_duration": clip_duration,
                "speed": speed,
                "adj_file": adj_file,
                "seg_id": seg["id"]
            })

            if is_recap:
                timeline_cursor = timeline_cursor + gap + actual_content_dur
            else:
                # Anchor next timeline cursor to start + target_duration (= end)
                timeline_cursor = start + target_duration

        FADE_SEC = 0.01  # 10ms

        def _fade_filter(total_duration):
            if total_duration <= (FADE_SEC * 2.2):
                return None
            fade_out_start = max(0.0, total_duration - FADE_SEC)
            return f"afade=t=in:st=0:d={FADE_SEC:.3f},afade=t=out:st={fade_out_start:.3f}:d={FADE_SEC:.3f}"

        def process_align_item(task):
            item_clips = []
            if task["gap_file"]:
                self._create_silence_wav(task["gap_file"], task["gap"])
                item_clips.append(task["gap_file"])

            raw_clip = task["raw_clip"]
            target_duration = task["target_duration"]
            clip_duration = task["clip_duration"]
            speed = task["speed"]
            adj_file = task["adj_file"]

            filters = []
            if speed > 1.001:
                s = speed
                while s > 2.0:
                    filters.append("atempo=2.0")
                    s /= 2.0
                if s > 1.001:
                    filters.append(f"atempo={s:.5f}")
            elif speed < 0.999:
                s = speed
                while s < 0.5:
                    filters.append("atempo=0.5")
                    s /= 0.5
                if s < 0.999:
                    filters.append(f"atempo={s:.5f}")

            actual_out_dur = clip_duration / speed if speed > 0 else clip_duration
            fade = _fade_filter(actual_out_dur)
            if fade:
                filters.append(fade)

            cmd = ["ffmpeg", "-y", "-i", raw_clip]
            if filters:
                cmd.extend(["-filter:a", ",".join(filters)])
            cmd.extend(["-ar", "44100", "-ac", "2", adj_file])
            self.run_command(cmd)

            item_clips.append(adj_file)

            # If clip is shorter than target_duration, pad trailing silence to reach target_duration cleanly
            if is_recap:
                if actual_out_dur < target_duration:
                    remaining = target_duration - actual_out_dur
                    if remaining > 1.0:
                        remaining = 1.0
                    if remaining > 0.01:
                        pad_file = os.path.join(temp_dir, f"pad_{task['index']}.wav")
                        self._create_silence_wav(pad_file, remaining)
                        item_clips.append(pad_file)
            else:
                if actual_out_dur < target_duration - 0.005:
                    remaining = target_duration - actual_out_dur
                    pad_file = os.path.join(temp_dir, f"pad_{task['index']}.wav")
                    self._create_silence_wav(pad_file, remaining)
                    item_clips.append(pad_file)

            return task["index"], item_clips

        results_by_index = {}
        workers = min(12, max(1, len(align_tasks)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_align_item, task) for task in align_tasks]
            for future in as_completed(futures):
                idx, item_clips = future.result()
                results_by_index[idx] = item_clips

        adjusted_clips = []
        for i in range(len(align_tasks)):
            adjusted_clips.extend(results_by_index[i])

        if timeline_cursor < total_video_duration:
            tail_gap = total_video_duration - timeline_cursor
            silence_file = os.path.join(temp_dir, "silence_tail.wav")
            self._create_silence_wav(silence_file, tail_gap)
            adjusted_clips.append(silence_file)

        concat_list = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for cfile in adjusted_clips:
                abs_path = os.path.abspath(cfile).replace(chr(92), "/")
                f.write(f"file '{abs_path}'\n")

        self.run_command([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c:a", "pcm_s16le", output_speech_path
        ])
        self.log("align_audio", 85, "Speech track aligned!")
        return output_speech_path

    # ─── Vocal Removal ────────────────────────────────────────────────────────

    # Persistent model cache — shared across all jobs, downloaded only once.
    _UVR_MODELS_DIR: str = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "VideoDubberStudio", "uvr_models",
    )

    def _separate_vocals_uvr(self, audio_path: str, temp_dir: str, requested_model: str = None) -> str:
        """Run audio-separator (UVR/VR-arch backend) and return the instrumental stem."""
        try:
            from audio_separator.separator import Separator  # type: ignore
        except ImportError:
            self.log("vocal_isolation", 86,
                     "audio-separator not installed – falling back to center-channel cancellation.")
            return None

        # Maximize PyTorch & ONNX parallel threading across all CPU cores (e.g. 20 cores)
        try:
            import torch
            num_cores = os.cpu_count() or 8
            torch.set_num_threads(num_cores)
            torch.set_num_interop_threads(min(4, num_cores))
        except Exception:
            pass

        # Persistent per-machine cache — downloaded once, reused every job.
        models_dir = self._UVR_MODELS_DIR
        os.makedirs(models_dir, exist_ok=True)

        candidate_models = []
        if requested_model and requested_model != "auto":
            candidate_models.append(requested_model)

        candidate_models.extend([
            "Kim_Vocal_2.onnx",                           # Ultra-fast ONNX model (~5-8s on 20-core CPU)
            "model_bs_roformer_ep_317_sdr_12.9755.ckpt",  # BS-Roformer Viperx (#1 rated AI vocal separator)
            "mel_band_roformer_kim_ft_unvoiced.ckpt",     # Mel-Band Roformer Kim
        ])
        candidate_models = list(dict.fromkeys(candidate_models))

        try:
            sep = Separator(
                output_dir=temp_dir,
                model_file_dir=models_dir,
                output_format="WAV",
                sample_rate=44100,
                invert_using_spec=False,
                output_single_stem="Instrumental",
                vr_params={
                    "batch_size": 4,
                    "window_size": 512,
                    "aggression": 5,          # low = less music treated as vocal
                    "enable_tta": False,      # TTA would double runtime on CPU
                    "enable_post_process": False,
                    "post_process_threshold": 0.2,
                    "high_end_process": False,
                },
                mdx_params={
                    "hop_length": 1024,
                    "segment_size": 256,
                    "overlap": 0.15,          # fast stride for 40% speedup
                    "batch_size": 4,
                    "enable_denoise": False,
                },
            )

            stems = None
            used_model = None
            for model_name in candidate_models:
                try:
                    self.log("vocal_isolation", 86, f"AI vocal removal – loading model: {model_name}...")
                    sep.load_model(model_name)
                    stems = sep.separate(audio_path)
                    if stems:
                        used_model = model_name
                        break
                except Exception as m_ex:
                    self.log("vocal_isolation", 86, f"Model '{model_name}' separation note: {m_ex}")
                    continue

            if not stems:
                self.log("vocal_isolation", 86, "No stems returned by model candidates — will fall back.")
                return None

            self.log("vocal_isolation", 87, f"Stems returned by {used_model}: {[os.path.basename(s) for s in stems]}")

            instrumental = next(
                (s for s in stems if os.path.isfile(s)),
                None,
            )

            if not instrumental:
                self.log("vocal_isolation", 86, "stem not found in return list — scanning output dir by mtime.")
                job_start = os.path.getmtime(audio_path)
                candidates = [
                    os.path.join(temp_dir, f)
                    for f in os.listdir(temp_dir)
                    if f.lower().endswith(".wav")
                    and os.path.getmtime(os.path.join(temp_dir, f)) >= job_start
                    and "vocal" not in f.lower()   # exclude the vocals stem
                ]
                if candidates:
                    instrumental = max(candidates, key=os.path.getmtime)

            if instrumental and os.path.isfile(instrumental):
                self.log("vocal_isolation", 88, f"AI BS-Roformer vocal removal complete → {os.path.basename(instrumental)}")
                return instrumental

            self.log("vocal_isolation", 86, "No instrumental stem found after separation — will fall back.")

        except Exception as exc:
            self.log("vocal_isolation", 86,
                     f"UVR separation failed ({exc}) — falling back to center-channel cancellation.")

        return None  # triggers the FFmpeg fallback in the caller

    def _remove_vocals_ffmpeg_fallback(self, audio_path: str, output_path: str) -> None:
        """Legacy center-channel cancellation – used only when UVR is unavailable."""
        self.log("vocal_isolation", 86,
                 "Removing vocals (center-channel cancellation fallback)…")
        filter_str = (
            "highpass=f=80,"
            "pan=stereo|c0=c0-c1|c1=c0-c1,"
            "volume=3.8"
        )
        self.run_command([
            "ffmpeg", "-y", "-i", audio_path,
            "-af", filter_str,
            "-ar", "44100", "-ac", "2", output_path,
        ])

    def process_background_audio(self, original_audio_path, vocal_mode="remove",
                                 duck_level=0.15, output_bgm_path=None, temp_dir=None, uvr_model=None):
        if vocal_mode in ("keep", "original", "none", "100", "full") or duck_level >= 0.99:
            self.log("vocal_isolation", 88, "Keeping 100% original background audio (bit-exact 0s fast pass)...")
            if output_bgm_path and os.path.abspath(original_audio_path) != os.path.abspath(output_bgm_path):
                shutil.copy2(original_audio_path, output_bgm_path)
            return output_bgm_path or original_audio_path

        elif vocal_mode == "remove":
            self.log("vocal_isolation", 85, "Starting high-speed AI vocal removal (Kim Vocal 2 / BS-Roformer)...")

            instrumental = self._separate_vocals_uvr(original_audio_path, temp_dir or os.path.dirname(output_bgm_path), requested_model=uvr_model)

            if instrumental:
                # Normalise sample-rate / channels to 44.1 kHz stereo WAV with 2.2x gain boost for 100% full BGM volume
                self.run_command([
                    "ffmpeg", "-y", "-i", instrumental,
                    "-af", "volume=2.2",
                    "-ar", "44100", "-ac", "2", output_bgm_path,
                ])
            else:
                # Graceful fallback: center-channel phase cancellation
                self._remove_vocals_ffmpeg_fallback(original_audio_path, output_bgm_path)

            self.log("vocal_isolation", 88, "Background audio isolated (100% full volume)!")
            return output_bgm_path

        elif vocal_mode == "mute":
            self.log("vocal_isolation", 88, "Muting original audio...")
            duration = self.get_media_duration(original_audio_path)
            self._create_silence_wav(output_bgm_path, duration)
            return output_bgm_path

        else:  # duck
            self.log("vocal_isolation", 88, f"Ducking audio to {int(duck_level*100)}%...")
            self.run_command([
                "ffmpeg", "-y", "-i", original_audio_path,
                "-filter:a", f"volume={duck_level}",
                "-ar", "44100", "-ac", "2", output_bgm_path
            ])
            return output_bgm_path

    # ─── Export & Merge ───────────────────────────────────────────────────────

    def _fix_khmer_spelling(self, text):
        """Fix Khmer coeng subscript spaces, orphaned vowels, dotted circles (U+25CC), normalize Khmer numerals, and convert full stops (។) to natural phrasing pauses for VoxCMP2 Khmer speech synthesis."""
        if not text:
            return ""

        # Normalize Khmer numbers & digits for clear spoken Khmer pronunciation
        khmer_digits_map = {
            '០': 'សូន្យ', '១': 'មួយ', '២': 'ពីរ', '៣': 'បី', '៤': 'បួន',
            '៥': 'ប្រាំ', '៦': 'ប្រាំមួយ', '៧': 'ប្រាំពីរ', '៨': 'ប្រាំបី', '៩': 'ប្រាំបួន'
        }
        for dig, val in khmer_digits_map.items():
            text = text.replace(dig, f" {val} ")

        if re.search(r'[\u1780-\u17ff]', text):
            # Remove orphan coeng spaces
            text = re.sub(r'\s*[\u17d2]\s*', '\u17d2', text)
            # Remove orphan vowel spaces
            text = re.sub(r'\s+([\u17b4-\u17d3])', r'\1', text)
            # Remove dotted circle placeholder
            text = text.replace('\u25cc', '')
            # Convert Khmer full stop (។) to a comma pause for natural breath phrasing
            text = text.replace('\u17d4', ', ')
            # Clean multi-spaces
            text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def _split_long_segments(self, segments):
        """Split long subtitle segments at punctuation marks ('។', '?', '.', ',') into separate phrase segments with proportional timing."""
        if not segments:
            return []

        punct_pattern = re.compile(r'[^\u17d4?\.,]+[\u17d4?\.,]?')
        new_segments = []

        for seg in segments:
            st = float(seg.get("start", 0))
            et = float(seg.get("end", 0))
            txt = str(seg.get("text") or seg.get("translated_text") or "").strip()

            if not txt or et <= st:
                continue

            raw_chunks = [c.strip() for c in punct_pattern.findall(txt) if c.strip()]

            if len(raw_chunks) <= 1 or (len(txt) <= 30 and len(raw_chunks) <= 1):
                new_segments.append(seg)
                continue

            total_duration = et - st
            total_len = float(sum(len(c) for c in raw_chunks))
            if total_len == 0:
                new_segments.append(seg)
                continue

            curr_st = st
            for idx, chunk in enumerate(raw_chunks):
                frac = len(chunk) / total_len
                chunk_dur = max(0.8, total_duration * frac)
                chunk_et = curr_st + chunk_dur
                if idx == len(raw_chunks) - 1:
                    chunk_et = et

                if chunk_et <= curr_st:
                    chunk_et = curr_st + 1.0

                new_seg = dict(seg)
                new_seg["start"] = round(curr_st, 2)
                new_seg["end"] = round(chunk_et, 2)
                new_seg["text"] = chunk
                new_seg["translated_text"] = chunk
                new_segments.append(new_seg)

                curr_st = round(chunk_et + 0.05, 2)

        return new_segments

    def _clean_and_fix_subtitle_segments(self, segments):
        """Clean subtitle segments while preserving 100% 1:1 original timestamps from transcription:
        1. Non-overlapping sequential timing.
        2. No duplicate stacked phrases rendering at the same timestamp.
        4. Correct Khmer script spelling without broken coeng spaces or dotted circles.
        5. Auto-split long segments at punctuation marks ('។', '?', '.', ',').
        """
        if not segments:
            return []

        split_segs = self._split_long_segments(segments)
        sorted_segs = sorted(split_segs, key=lambda x: float(x.get("start", 0)))
        cleaned = []

        for seg in sorted_segs:
            st = float(seg.get("start", 0))
            et = float(seg.get("end", 0))
            raw_txt = str(seg.get("text") or seg.get("translated_text") or "").strip()
            txt = self._fix_khmer_spelling(raw_txt)

            if not txt or et <= st:
                continue

            clean_norm = re.sub(r'\s+', '', txt.lower())
            if cleaned:
                prev_norm = re.sub(r'\s+', '', cleaned[-1]["text"].lower())
                if clean_norm == prev_norm or (abs(st - cleaned[-1]["start"]) < 0.4 and clean_norm in prev_norm):
                    continue

            if cleaned and cleaned[-1]["end"] > st:
                cleaned[-1]["end"] = max(cleaned[-1]["start"] + 0.5, st - 0.05)

            new_seg = dict(seg)
            new_seg["start"] = st
            new_seg["end"] = et
            new_seg["text"] = txt
            new_seg["translated_text"] = txt
            cleaned.append(new_seg)

        return cleaned

    def _parse_srt_file(self, srt_path):
        segments = []
        if not srt_path or not os.path.exists(srt_path):
            return segments
        try:
            with open(srt_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            blocks = re.split(r'\n\s*\n', content)
            for block in blocks:
                lines = [l.strip() for l in block.split('\n') if l.strip()]
                if len(lines) >= 3:
                    time_line = lines[1]
                    text = "\n".join(lines[2:]).strip()
                    times = time_line.split("-->")
                    if len(times) == 2:
                        def to_sec(t_str):
                            t_str = t_str.strip().replace(',', '.')
                            parts = t_str.split(':')
                            return float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
                        s = to_sec(times[0])
                        e = to_sec(times[1])
                        segments.append({"start": s, "end": e, "text": text})
        except Exception as e:
            print(f"Error parsing SRT: {e}")
        return self._clean_and_fix_subtitle_segments(segments)

    def _resolve_font_file(self, font_cfg):
        """Resolve a font config dict (from the UI's subtitles/text settings) to an
        ffmpeg-drawtext-safe fontfile string.

        font_manager.resolve_font_path() is the SAME function that backs the
        /api/fonts and /api/font-file routes the browser preview uses, so a
        font_path chosen in the UI resolves to the literal identical file here —
        no separate guessing logic that can silently diverge from the preview.
        `font_path` (an exact, already-verified file the UI resolved) always wins;
        `font` (a display name) is used as a fallback for older saved configs that
        predate font_path.
        """
        name = font_cfg.get("font", "Kantumruy Pro")
        path = font_cfg.get("font_path")
        resolved = font_manager.resolve_font_path(name=name, path=path)

        base = os.path.basename(resolved).lower()
        if base in ("khmerui.ttf", "arial.ttf"):
            self.log("merge_video", 90, f"WARNING: could not find requested font '{name}', falling back to {resolved}")
        else:
            self.log("merge_video", 90, f"Using font: {resolved}")

        clean = resolved.replace("\\", "/")
        if len(clean) >= 2 and clean[1] == ':':
            clean = clean[0] + '\\:' + clean[2:]
        return clean

    def _wrap_subtitle_text(self, text, max_chars=0):
        """Intelligently wrap subtitle text using Khmer syllable-cluster-aware tokenization.
        Guarantees that Khmer consonant-vowel clusters (e.g. 'ការ', 'រៀប', 'ក្នុង') are NEVER split mid-word!
        If max_chars <= 0, no artificial character length limit is imposed.
        """
        if not text:
            return ""
        if max_chars is None or max_chars <= 0:
            return text.replace("\n", " ").strip()
        if "\n" in text:
            return text


        lines = []
        for raw_line in text.split("\n"):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            if len(raw_line) <= max_chars:
                lines.append(raw_line)
                continue

            # Tokenize into atomic Khmer syllable clusters & space/punctuation chunks
            pattern = r'[\u1780-\u17b3](?:[\u17d2][\u1780-\u17b3])?[\u17b6-\u17c5]*[\u17c6-\u17d3]*|[^\u1780-\u17d3\s]+|\s+'
            syllables = [t for t in re.findall(pattern, raw_line) if t]

            curr_line = ""
            for s in syllables:
                starts_with_subscript_or_vowel = len(s) > 0 and (s[0] == '\u17d2' or '\u17b6' <= s[0] <= '\u17c5')
                if len(curr_line + s) > max_chars and curr_line.strip() and not starts_with_subscript_or_vowel:
                    lines.append(curr_line.strip())
                    curr_line = s
                else:
                    curr_line += s
            if curr_line.strip():
                lines.append(curr_line.strip())

        return "\n".join(lines)

    def _wrap_subtitle_text_by_pixel_width(self, text, measure_fn, max_allowed_w):
        """Wrap subtitle text based strictly on measured pixel width rather than character count.
        Preserves atomic Khmer syllable clusters so words are never split mid-syllable.
        """
        if not text or not str(text).strip():
            return ""

        lines = []
        for raw_line in str(text).split("\n"):
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            if measure_fn(raw_line) <= max_allowed_w:
                lines.append(raw_line)
                continue

            pattern = r'[\u1780-\u17b3](?:[\u17d2][\u1780-\u17b3])?[\u17b6-\u17c5]*[\u17c6-\u17d3]*|[^\u1780-\u17d3\s]+|\s+'
            syllables = [t for t in re.findall(pattern, raw_line) if t]

            curr_line = ""
            for s in syllables:
                starts_with_subscript_or_vowel = len(s) > 0 and (s[0] == '\u17d2' or '\u17b6' <= s[0] <= '\u17c5')
                test_line = curr_line + s
                if curr_line.strip() and measure_fn(test_line) > max_allowed_w and not starts_with_subscript_or_vowel:
                    lines.append(curr_line.strip())
                    curr_line = s.lstrip()
                else:
                    curr_line += s

            if curr_line.strip():
                lines.append(curr_line.strip())

        return "\n".join(lines)

    def export_srt(self, segments, srt_path, sub_cfg=None):
        sub_cfg = sub_cfg or {}
        max_chars = int(sub_cfg.get("max_chars", 0))
        def fmt(s):
            h = int(s // 3600); m = int((s % 3600) // 60)
            sec = int(s % 60);   ms = int(round((s - int(s)) * 1000))
            return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
        with open(srt_path, "w", encoding="utf-8") as f:
            for seg in segments:
                text_content = seg.get('translated_text') or seg.get('text') or ''
                wrapped_text = self._wrap_subtitle_text(text_content, max_chars=max_chars)
                f.write(f"{seg.get('id', 1)}\n{fmt(seg.get('start', 0))} --> {fmt(seg.get('end', 0))}\n{wrapped_text}\n\n")
        return srt_path

    def generate_ass_subtitles(self, srt_path, sub_cfg, output_ass_path, video_width=1080, video_height=1920):
        """Generate high-precision ASS (Advanced SubStation Alpha) subtitle file.
        
        ASS standard defines canvas resolution (PlayResX/PlayResY), precise font size,
        outline, shadow, box background, and bottom margins for 99.9% preview-to-export parity.
        """
        srt_segs = self._parse_srt_file(srt_path)
        if not srt_segs:
            return None

        max_chars = int(sub_cfg.get("max_chars", 0))

        font_name = sub_cfg.get("font", "Kantumruy Pro")
        font_path = sub_cfg.get("font_path")
        font_family, font_file_path = font_manager.get_font_family_and_path(name=font_name, path=font_path)

        size_pct = float(sub_cfg.get("size", 3.0))
        font_size = max(16, int(video_height * (size_pct / 100.0)))

        opacity_pct = float(sub_cfg.get("opacity", 100)) / 100.0
        alpha_hex = f"{int((1.0 - opacity_pct) * 255):02X}"

        outline_pct = float(sub_cfg.get("outline", 0.3))
        scaled_outline = max(1, int(video_height * (outline_pct / 100.0)))

        preset = sub_cfg.get("preset", "Outline")

        primary_colour = f"&H{alpha_hex}FFFFFF"
        outline_colour = "&H00000000"
        back_colour = "&H80000000"
        border_style = 1
        outline_val = scaled_outline
        shadow_val = 0

        if preset == "YellowBox":
            primary_colour = f"&H{alpha_hex}00FFFF"
            border_style = 3
            back_colour = "&H47000000"
            outline_val = max(1, int(video_height * 0.015))
        elif preset == "Outline":
            primary_colour = f"&H{alpha_hex}FFFFFF"
            border_style = 1
            outline_colour = "&H00000000"
            outline_val = scaled_outline
            shadow_val = 0
        elif preset == "WhiteText":
            primary_colour = f"&H{alpha_hex}FFFFFF"
            border_style = 1
            outline_val = 0
            shadow_val = 0
        elif preset == "Glow":
            primary_colour = f"&H{alpha_hex}FFFFFF"
            border_style = 1
            outline_colour = "&H80000000"
            outline_val = scaled_outline
            shadow_val = scaled_outline

        pos_y_pct = float(sub_cfg.get("posY", 62))
        margin_v = max(10, int(video_height * (1.0 - (pos_y_pct / 100.0))))

        def fmt_ass(seconds):
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            cs = int(round((seconds - int(seconds)) * 100))
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

        ass_header = (
            "[Script Info]\n"
            "Title: Video Dubber Studio Subtitles\n"
            "ScriptType: v4.00+\n"
            "WrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\n"
            "YCbCr Matrix: None\n"
            f"PlayResX: {video_width}\n"
            f"PlayResY: {video_height}\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{font_family},{font_size},{primary_colour},&H000000FF,{outline_colour},{back_colour},-1,0,0,0,100,100,0,0,{border_style},{outline_val},{shadow_val},2,20,20,{margin_v},1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        anim_style = sub_cfg.get("anim", "None")
        anim_prefix = ""
        if anim_style == "Fade":
            anim_prefix = "{\\fad(150,150)}"
        elif anim_style == "Pop":
            anim_prefix = "{\\t(0,120,\\fscx106\\fscy106)\\t(120,240,\\fscx100\\fscy100)}"
        elif anim_style == "Slide":
            anim_prefix = "{\\fad(100,100)\\t(0,150,\\fscy105)}"

        dialogues = []
        for seg in srt_segs:
            st = fmt_ass(seg["start"])
            et = fmt_ass(seg["end"])
            wrapped_text = self._wrap_subtitle_text(seg["text"], max_chars=max_chars)
            text = anim_prefix + wrapped_text.replace("\n", "\\N").replace("'", "’")
            dialogues.append(f"Dialogue: 0,{st},{et},Default,,0,0,0,,{text}")

        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write(ass_header + "\n".join(dialogues) + "\n")

        return output_ass_path

    # ─── Unified Preview & Render Entry-Point ────────────────────────────────

    def process_preview_and_render(
        self,
        config: "PreviewRenderConfig",
        text: str = "",
        output_png_path: str = None,
        video_path: str = None,
        dubbed_speech_path: str = None,
        bgm_audio_path: str = None,
        output_video_path: str = None,
        srt_path: str = None,
        logo_file_path: str = None,
    ) -> dict:
        """Unified entry-point for preview PNG generation and final video rendering.

        **Preview mode** (``output_png_path`` is provided):
            Renders a single subtitle caption as a transparent RGBA PNG using the
            ``PreviewRenderConfig`` settings.  Returns::

                {"mode": "preview", "ok": True, "png_path": "<path>"}

        **Render mode** (``output_video_path`` is provided):
            Translates the ``PreviewRenderConfig`` into the ``custom_edits`` dict and
            calls ``render_edited_video()``.  Returns::

                {"mode": "render", "ok": True, "video_path": "<path>"}

        Both modes share the same config object so preview ↔ export settings are
        guaranteed to be identical — no more silent divergence between the live
        preview and the final burn-in output.

        Args:
            config:              Unified preview/render configuration.
            text:                Subtitle text for preview mode.
            output_png_path:     Destination path for the preview PNG (triggers preview mode).
            video_path:          Source video for render mode.
            dubbed_speech_path:  Dubbed audio WAV for render mode.
            bgm_audio_path:      Background music/BGM WAV for render mode.
            output_video_path:   Destination MP4 path (triggers render mode).
            srt_path:            SRT subtitle file for render mode (optional).
            logo_file_path:      Logo image path for render mode (optional).

        Returns:
            dict with keys ``mode``, ``ok``, and the relevant output path.
        """
        # ── Preview mode ──────────────────────────────────────────────────────
        if output_png_path is not None:
            sub_cfg = config.to_sub_cfg()
            result_path = self.render_subtitle_png_overlay(
                text,
                sub_cfg,
                output_png_path,
                video_width=config.video_width,
                video_height=config.video_height,
            )
            ok = bool(result_path and os.path.exists(result_path))
            return {"mode": "preview", "ok": ok, "png_path": result_path}

        # ── Render mode ───────────────────────────────────────────────────────
        if output_video_path is not None:
            if not video_path or not os.path.exists(video_path):
                return {"mode": "render", "ok": False, "error": "video_path not found"}
            if not dubbed_speech_path or not os.path.exists(dubbed_speech_path):
                return {"mode": "render", "ok": False, "error": "dubbed_speech_path not found"}
            if not bgm_audio_path or not os.path.exists(bgm_audio_path):
                return {"mode": "render", "ok": False, "error": "bgm_audio_path not found"}

            custom_edits = config.to_custom_edits()
            result_path = self.render_edited_video(
                video_path=video_path,
                dubbed_speech_path=dubbed_speech_path,
                bgm_audio_path=bgm_audio_path,
                output_video_path=output_video_path,
                srt_path=srt_path,
                custom_edits=custom_edits,
                logo_file_path=logo_file_path,
            )
            ok = bool(result_path and os.path.exists(result_path))
            return {"mode": "render", "ok": ok, "video_path": result_path}

        return {"mode": "none", "ok": False, "error": "Neither output_png_path nor output_video_path was provided"}

    def _get_cli_path(self) -> str:
        """Return the absolute path to VideoDubberRenderCLI.exe."""
        return os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "cli", "VideoDubberRenderCLI.exe")
        )

    def _build_cli_sub_config(self, sub_cfg: dict) -> dict:
        """Convert the Python sub_cfg dict to the JSON schema the C# CLI expects."""
        return {
            "Enabled":      True,
            "Preset":       sub_cfg.get("preset",       "Outline"),
            "Font":         sub_cfg.get("font",         "Kantumruy Pro"),
            "FontPath":     sub_cfg.get("font_path",    "") or "",
            "Size":         float(sub_cfg.get("size",       3.0)),
            "Opacity":      float(sub_cfg.get("opacity",    100)),
            "Outline":      float(sub_cfg.get("outline",    0.3)),
            "PosY":         float(sub_cfg.get("posY",       62)),
            "MaxChars":     int(sub_cfg.get("max_chars",    36)),
            "TextColor":    str(sub_cfg.get("text_color",   "#FFFFFF")),
            "OutlineColor": str(sub_cfg.get("outline_color","#000000")),
            "Bold":         bool(sub_cfg.get("bold",        True)),
            "Italic":       bool(sub_cfg.get("italic",      False)),
        }

    def _render_subtitles_batch_cli(self, srt_path: str, sub_cfg: dict,
                                     out_dir: str, width: int, height: int) -> list:
        """Render ALL subtitle PNG overlays in C# CLI batch call with PIL fallback.

        Returns a list of dicts: [{"png": path, "st": start_sec, "et": end_sec}, ...]
        """
        cli_path = self._get_cli_path()
        if os.path.exists(cli_path):
            try:
                os.makedirs(out_dir, exist_ok=True)
                csharp_cfg = self._build_cli_sub_config(sub_cfg)
                cmd = [
                    cli_path,
                    "--mode",    "batch",
                    "--srt",     srt_path,
                    "--config",  json.dumps(csharp_cfg),
                    "--out-dir", out_dir,
                    "--width",   str(width),
                    "--height",  str(height),
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if res.returncode == 0:
                    manifest = json.loads(res.stdout.strip())
                    return [{"png": entry["path"], "st": entry["start"], "et": entry["end"]} for entry in manifest]
            except Exception as e:
                print(f"CLI batch subtitle render failed ({e}), falling back to PIL batch renderer...")

        # Fallback: pure Python PIL subtitle renderer
        os.makedirs(out_dir, exist_ok=True)
        srt_segs = self._parse_srt_file(srt_path)
        events = []
        for idx, seg in enumerate(srt_segs):
            png_path = os.path.join(out_dir, f"sub_{idx}.png")
            self._render_subtitle_png_overlay_pil(seg["text"], sub_cfg, png_path, width, height)
            events.append({"png": png_path, "st": seg["start"], "et": seg["end"]})
        return events

    def _escape_movie_path(self, path):
        """Format and escape file path for FFmpeg movie filter inside filter_complex_script."""
        p = os.path.abspath(path).replace("\\", "/")
        p = p.replace(":", "\\:").replace("'", "'\\''")
        return p

    def render_subtitle_png_overlay(self, text, sub_cfg, output_png_path, video_width=1080, video_height=1920):
        """Render a single subtitle caption to a transparent RGBA PNG via C# SkiaSharp CLI with PIL fallback."""
        cli_path = self._get_cli_path()
        if os.path.exists(cli_path):
            try:
                csharp_cfg = self._build_cli_sub_config(sub_cfg)
                cmd = [
                    cli_path,
                    "--mode",   "preview",
                    "--text",   text,
                    "--config", json.dumps(csharp_cfg),
                    "--out",    output_png_path,
                    "--width",  str(video_width),
                    "--height", str(video_height),
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if res.returncode == 0 and os.path.exists(output_png_path):
                    return output_png_path
            except Exception as e:
                print(f"CLI subtitle preview failed ({e}), falling back to PIL renderer...")

        return self._render_subtitle_png_overlay_pil(text, sub_cfg, output_png_path, video_width, video_height)

    def _render_subtitle_png_overlay_pil(self, text, sub_cfg, output_png_path, video_width=1080, video_height=1920):
        """Pure Python PIL Subtitle PNG Overlay Renderer fallback with auto-dynamic font size & unlimited char flow."""
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        if not text or not str(text).strip():
            out_dir = os.path.dirname(output_png_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            img.save(output_png_path, "PNG")
            return output_png_path

        max_chars = int(sub_cfg.get("max_chars", 0))

        font_name = sub_cfg.get("font", "Kantumruy Pro")
        font_path = sub_cfg.get("font_path")
        resolved = font_manager.resolve_font_path(name=font_name, path=font_path)

        size_pct = float(sub_cfg.get("size", 3.0))
        target_font_size = max(14, int(video_height * (size_pct / 100.0)))
        font_size = target_font_size

        def load_font(fs):
            try:
                return ImageFont.truetype(resolved, fs)
            except Exception:
                try:
                    return ImageFont.truetype("arial.ttf", fs)
                except Exception:
                    return ImageFont.load_default()

        font = load_font(font_size)
        max_allowed_w = int(video_width * 0.94)
        # Allow font size to scale down to 12px so single line display can fit any standard dialogue sentence
        min_single_line_size = 12

        outline_pct = float(sub_cfg.get("outline", 0.3))
        preset = sub_cfg.get("preset", "Outline")

        def calc_outline(fs):
            ow = max(1, int(video_height * (outline_pct / 100.0) * (fs / float(target_font_size))))
            return 0 if preset == "WhiteText" else ow

        outline_w = calc_outline(font_size)

        if max_chars <= 0:
            # ── UNCONSTRAINED 1-SINGLE-LINE MODE (No max_chars wrapping) ─────────────
            single_text = text.replace("\n", " ").strip()
            lines = [single_text]

            shrink_size = font_size
            b = draw.textbbox((0, 0), single_text, font=font, stroke_width=outline_w)
            single_line_w = b[2] - b[0]

            while single_line_w > max_allowed_w and shrink_size > 8:
                shrink_size = max(8, int(shrink_size * 0.94))
                font = load_font(shrink_size)
                outline_w = calc_outline(shrink_size)
                b = draw.textbbox((0, 0), single_text, font=font, stroke_width=outline_w)
                single_line_w = b[2] - b[0]

            font_size = shrink_size
            line_widths = [single_line_w]
            line_heights = [b[3] - b[1]]
        else:
            # ── EXPLICIT MULTI-LINE WRAP MODE (User set max_chars > 0) ─────────────
            wrapped = self._wrap_subtitle_text(text, max_chars=max_chars)
            lines = [line.strip() for line in wrapped.split("\n") if line.strip()]
            if not lines:
                lines = [text]

            line_widths = []
            line_heights = []
            for l in lines:
                bbox = draw.textbbox((0, 0), l, font=font, stroke_width=outline_w)
                line_widths.append(bbox[2] - bbox[0])
                line_heights.append(bbox[3] - bbox[1])
            max_w = max(line_widths) if line_widths else 0

            while max_w > max_allowed_w and font_size > 12:
                font_size = max(12, int(font_size * 0.92))
                font = load_font(font_size)
                outline_w = calc_outline(font_size)
                wrapped = self._wrap_subtitle_text(text, max_chars=max_chars)
                lines = [line.strip() for line in wrapped.split("\n") if line.strip()]
                line_widths = []
                line_heights = []
                for l in lines:
                    bbox = draw.textbbox((0, 0), l, font=font, stroke_width=outline_w)
                    line_widths.append(bbox[2] - bbox[0])
                    line_heights.append(bbox[3] - bbox[1])
                max_w = max(line_widths) if line_widths else 0

        # Colors & Alpha
        text_hex = str(sub_cfg.get("text_color", "#FFFFFF")).lstrip("#")
        outline_hex = str(sub_cfg.get("outline_color", "#000000")).lstrip("#")
        if len(text_hex) < 6: text_hex = text_hex.ljust(6, "F")
        if len(outline_hex) < 6: outline_hex = outline_hex.ljust(6, "0")

        opacity_pct = float(sub_cfg.get("opacity", 100)) / 100.0
        alpha = int(opacity_pct * 255)

        r_txt, g_txt, b_txt = int(text_hex[0:2], 16), int(text_hex[2:4], 16), int(text_hex[4:6], 16)
        text_color = (r_txt, g_txt, b_txt, alpha)

        r_out, g_out, b_out = int(outline_hex[0:2], 16), int(outline_hex[2:4], 16), int(outline_hex[4:6], 16)
        outline_color = (r_out, g_out, b_out, alpha)

        line_spacing = max(4, int(font_size * 0.25))
        total_h = sum(line_heights) + line_spacing * max(0, len(lines) - 1)

        pos_y_pct = float(sub_cfg.get("posY", 62))
        center_y = int(video_height * (pos_y_pct / 100.0))
        start_y = center_y - (total_h // 2)

        # Dynamic box styling scaled to font size
        if preset in ("YellowBox", "GreenBox", "RedHighlight"):
            box_alpha = int(alpha * 0.82)
            if preset == "YellowBox":
                box_color = (0, 0, 0, box_alpha)
                text_color = (255, 255, 0, alpha)
            elif preset == "GreenBox":
                box_color = (0, 77, 32, box_alpha)
                text_color = (255, 255, 255, alpha)
            else:
                box_color = (190, 18, 60, box_alpha)
                text_color = (255, 255, 255, alpha)

            pad_x = max(10, int(font_size * 0.45))
            pad_y = max(6, int(font_size * 0.22))

            curr_y = start_y
            for idx, line in enumerate(lines):
                lw = line_widths[idx]
                lh = line_heights[idx]
                box_rect = [
                    (video_width - lw) // 2 - pad_x,
                    curr_y - pad_y,
                    (video_width + lw) // 2 + pad_x,
                    curr_y + lh + pad_y
                ]
                draw.rectangle(box_rect, fill=box_color)
                curr_y += lh + line_spacing

        curr_y = start_y
        for i, line in enumerate(lines):
            lx = (video_width - line_widths[i]) // 2
            draw.text(
                (lx, curr_y),
                line,
                font=font,
                fill=text_color,
                stroke_width=outline_w,
                stroke_fill=outline_color if outline_w > 0 else None
            )
            curr_y += line_heights[i] + line_spacing

        out_dir = os.path.dirname(output_png_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        img.save(output_png_path, "PNG")
        return output_png_path

        return output_png_path

    def render_text_overlay_png(self, text_cfg: dict, output_png_path: str, video_width=1080, video_height=1920):
        """Render custom Text Overlay to a pixel-exact transparent RGBA PNG matching the live HTML5 preview canvas."""
        from PIL import Image, ImageDraw, ImageFont, ImageFilter

        img = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        content = str(text_cfg.get("content", "")).strip()
        if not content:
            out_dir = os.path.dirname(output_png_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            img.save(output_png_path, "PNG")
            return output_png_path

        # Font resolution
        font_file = self._resolve_font_file(text_cfg)
        size_pct = float(text_cfg.get("size", 3))
        font_size = max(14, int(size_pct * (video_height / 100.0) * 0.45)) if video_height > 0 else int(size_pct * 12)

        try:
            font = ImageFont.truetype(font_file, font_size)
        except Exception:
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()

        # Parse colors & opacity
        fill_hex = str(text_cfg.get("color_fill", "#FFFFFF")).lstrip("#")
        bg_hex = str(text_cfg.get("color_bg", "#808080")).lstrip("#")
        outline_hex = str(text_cfg.get("color_outline", "#FFFFFF")).lstrip("#")

        if len(fill_hex) < 6: fill_hex = fill_hex.ljust(6, "F")
        if len(bg_hex) < 6: bg_hex = bg_hex.ljust(6, "0")
        if len(outline_hex) < 6: outline_hex = outline_hex.ljust(6, "F")

        text_op = int(float(text_cfg.get("opacity", 90)) * 2.55)
        bg_op = int(float(text_cfg.get("bg_opacity", 0)) * 2.55)

        r_fill, g_fill, b_fill = int(fill_hex[0:2], 16), int(fill_hex[2:4], 16), int(fill_hex[4:6], 16)
        fill_color = (r_fill, g_fill, b_fill, text_op)

        r_bg, g_bg, b_bg = int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16)
        bg_color = (r_bg, g_bg, b_bg, bg_op)

        r_out, g_out, b_out = int(outline_hex[0:2], 16), int(outline_hex[2:4], 16), int(outline_hex[4:6], 16)
        outline_color = (r_out, g_out, b_out, text_op)
        outline_w = int(float(text_cfg.get("outline", 0)))
        shadow_w = float(text_cfg.get("shadow", 0))

        # Position Y
        pos_y_pct = float(text_cfg.get("posY", 15))
        target_y = int(video_height * (pos_y_pct / 100.0))

        # Calculate bounding box
        bbox = draw.textbbox((0, 0), content, font=font, stroke_width=outline_w)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        target_x = (video_width - text_w) // 2

        # Draw Background Box if opacity > 0
        if bg_op > 0:
            pad_x = int(font_size * 0.4)
            pad_y = int(font_size * 0.2)
            box_rect = [
                target_x - pad_x,
                target_y - pad_y,
                target_x + text_w + pad_x,
                target_y + text_h + pad_y
            ]
            draw.rectangle(box_rect, fill=bg_color)

        # Drop Shadow (matches the live preview's CSS drop-shadow filter): a soft,
        # Gaussian-blurred silhouette of the text offset below it, composited
        # before the crisp text/outline pass on top.
        if shadow_w > 0:
            shadow_layer = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow_layer)
            shadow_alpha = int(text_op * 0.75)
            shadow_offset = max(1, int(shadow_w * 0.5))
            shadow_draw.text(
                (target_x, target_y + shadow_offset),
                content,
                font=font,
                fill=(0, 0, 0, shadow_alpha),
                stroke_width=outline_w,
                stroke_fill=(0, 0, 0, shadow_alpha) if outline_w > 0 else None
            )
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(max(1, int(shadow_w))))
            img = Image.alpha_composite(img, shadow_layer)
            draw = ImageDraw.Draw(img)

        # Draw Text
        draw.text(
            (target_x, target_y),
            content,
            font=font,
            fill=fill_color,
            stroke_width=outline_w,
            stroke_fill=outline_color if outline_w > 0 else None
        )

        out_dir = os.path.dirname(output_png_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        img.save(output_png_path, "PNG")
        return output_png_path

    def merge_final_video(self, video_path, dubbed_speech_path, bgm_audio_path,
                          output_video_path, burn_subtitles=False, srt_path=None):
        return self.render_edited_video(
            video_path=video_path,
            dubbed_speech_path=dubbed_speech_path,
            bgm_audio_path=bgm_audio_path,
            output_video_path=output_video_path,
            srt_path=srt_path,
            custom_edits={"subtitles": {"enabled": burn_subtitles}}
        )

    def render_edited_video(self, video_path, dubbed_speech_path, bgm_audio_path,
                            output_video_path, srt_path=None, custom_edits=None, logo_file_path=None):
        """Render final video applying blur region, styled burn-in subtitles, text banner, and logo watermark."""
        self.log("merge_video", 90, "Applying custom video edits & rendering final video...")

        has_bgm = (
            bgm_audio_path
            and os.path.exists(bgm_audio_path)
            and os.path.isfile(bgm_audio_path)
            and os.path.getsize(bgm_audio_path) > 100
            and os.path.abspath(bgm_audio_path) != os.path.abspath(dubbed_speech_path)
        )

        bgm_vol_pct = 100.0
        if custom_edits and isinstance(custom_edits, dict):
            if "audio" in custom_edits and isinstance(custom_edits["audio"], dict) and "bgm_volume" in custom_edits["audio"]:
                bgm_vol_pct = custom_edits["audio"]["bgm_volume"]
            elif "bgm_volume" in custom_edits:
                bgm_vol_pct = custom_edits["bgm_volume"]
            elif "bgm_vol" in custom_edits:
                bgm_vol_pct = custom_edits["bgm_vol"]

        try:
            bgm_vol_pct = float(bgm_vol_pct)
        except Exception:
            bgm_vol_pct = 100.0

        vol_factor = max(0.0, bgm_vol_pct / 100.0)

        # Mute completely if volume factor is 0
        if vol_factor <= 0.001:
            has_bgm = False

        inputs = ["ffmpeg", "-y", "-i", video_path, "-i", dubbed_speech_path]
        if has_bgm:
            inputs.extend(["-i", bgm_audio_path])
            audio_filter = f"[2:a]volume={vol_factor:.2f}[bgm];[1:a][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
            next_input_idx = 3
        else:
            audio_filter = "[1:a]anull[aout]"
            next_input_idx = 2

        if not custom_edits:
            custom_edits = {}

        # Probe input video dimensions
        width, height = 1080, 1920
        try:
            cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", video_path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.stdout.strip():
                parts = res.stdout.strip().split("x")
                if len(parts) == 2:
                    width, height = int(parts[0]), int(parts[1])
        except Exception as e:
            print(f"Could not probe video size: {e}")

        v_filters = []

        # 0. Mirror Video (Horizontal Flip)
        mirror_cfg = custom_edits.get("mirror", {}) or custom_edits.get("crop", {})
        if mirror_cfg.get("enabled"):
            v_filters.append("hflip")

        # 0.1 Video Color Adjustment (Brightness, Contrast, Saturation, Hue)
        color_cfg = custom_edits.get("color", {})
        if color_cfg.get("enabled"):
            br = float(color_cfg.get("brightness", 0)) / 100.0
            ct = float(color_cfg.get("contrast", 100)) / 100.0
            sat = float(color_cfg.get("saturation", 100)) / 100.0
            hue = float(color_cfg.get("hue", 0))
            
            eq_filter = f"eq=brightness={br:.2f}:contrast={ct:.2f}:saturation={sat:.2f}"
            v_filters.append(eq_filter)
            if hue != 0:
                v_filters.append(f"hue=h={hue:.1f}")

        # 1. Blur Box Region (heavy Gaussian boxblur crop-overlay with opacity)
        blur_cfg = custom_edits.get("blur", {})
        if blur_cfg.get("enabled"):
            if blur_cfg.get("auto_detect") and video_path and os.path.exists(video_path):
                try:
                    detected_box = self.detect_caption_region(video_path)
                    if detected_box.get("detected"):
                        blur_cfg["posY"] = detected_box["posY"]
                        blur_cfg["height"] = detected_box["height"]
                        blur_cfg["posX"] = detected_box["posX"]
                        blur_cfg["width"] = detected_box["width"]
                        self.log("blur_auto_detect", 20, f"✨ Auto-detected original caption region: Y={detected_box['posY']}%, H={detected_box['height']}%, X={detected_box['posX']}%, W={detected_box['width']}%")
                except Exception as ex:
                    print(f"Blur auto-detect error during rendering: {ex}")

            px = max(0, int(width * (blur_cfg.get("posX", 0) / 100.0)))
            py = max(0, int(height * (blur_cfg.get("posY", 57.3) / 100.0)))
            bw = max(4, int(width * (blur_cfg.get("width", 100) / 100.0)))
            bh = max(4, int(height * (blur_cfg.get("height", 7) / 100.0)))

            if px + bw > width: bw = width - px
            if py + bh > height: bh = height - py
            blur_opacity = float(blur_cfg.get("opacity", 100)) / 100.0
            if bw > 4 and bh > 4:
                r = max(2, min(int(bh * 0.4), 8))
                p = max(1, min(int(r * 0.5), 4))
                v_filters.append(
                    f"crop={bw}:{bh}:{px}:{py},"
                    f"boxblur={r}:{p},boxblur={r}:{p},"
                    f"format=rgba,colorchannelmixer=aa={blur_opacity:.3f}[blurred];"
                    f"[0:v][blurred]overlay={px}:{py}"
                )

        # 2. Custom Styled Subtitles via Pixel-Exact PIL PNG Overlay Engine
        sub_cfg = custom_edits.get("subtitles", {})
        sub_png_inputs = []
        sub_filter_events = []

        if sub_cfg.get("enabled", False) and srt_path and os.path.exists(srt_path):
            sub_dir = os.path.join(os.path.dirname(srt_path), "sub_pngs")
            self.log("merge_video", 91, "🎨 Batch-rendering subtitle PNGs via C# SkiaSharp CLI (unified renderer)...")
            events = self._render_subtitles_batch_cli(srt_path, sub_cfg, sub_dir, width, height)
            for ev in events:
                sub_png_inputs.append(ev["png"])
                sub_filter_events.append(ev)

        # 3. Custom Text Overlay Banner (Pixel-Exact PNG Overlay Renderer, identical to Subtitles)
        text_cfg = custom_edits.get("text", {})
        text_png_path = None
        if text_cfg.get("enabled") and text_cfg.get("content"):
            text_png_path = os.path.join(os.path.dirname(output_video_path), "text_overlay.png")
            self.log("merge_video", 91, "🎨 Rendering text overlay banner PNG...")
            self.render_text_overlay_png(text_cfg, text_png_path, width, height)

        # Add Text Overlay PNG input if rendered
        text_input_idx = None
        if text_png_path and os.path.exists(text_png_path):
            text_input_idx = next_input_idx
            inputs.extend(["-loop", "1", "-i", text_png_path])
            next_input_idx += 1

        caps = self.detect_gpu_capabilities()
        v_codec = ["-c:v", caps["ffmpeg_encoder"]] + caps["ffmpeg_preset"]
        if caps["ffmpeg_encoder"] != "libx264":
            self.log("merge_video", 92, f"🚀 Using Hardware Acceleration GPU Encoder: '{caps['ffmpeg_encoder']}'")
        else:
            self.log("merge_video", 92, "Using CPU Video Encoder ('libx264 superfast')")

        v_filter_chains = []
        curr_v = "[0:v]"

        if v_filters:
            filter_base = ",".join(v_filters)
            v_filter_chains.append(f"[0:v]{filter_base}[vbase]")
            curr_v = "[vbase]"

        # Chain PIL PNG Subtitle Overlays via movie filter inside filter_script to prevent Windows CLI command length limits
        if sub_filter_events:
            for idx, event in enumerate(sub_filter_events):
                st = event["st"]
                et = event["et"]
                esc_png = self._escape_movie_path(event["png"])
                next_v = f"[vsub{idx}]"
                v_filter_chains.append(f"movie='{esc_png}'[smovie{idx}]; {curr_v}[smovie{idx}]overlay=0:0:enable='between(t,{st:.2f},{et:.2f})':repeatlast=1{next_v}")
                curr_v = next_v

        # Chain Text Overlay PNG for 100% pixel-exact preview match (identical to Captions)
        if text_input_idx is not None:
            anim = text_cfg.get("anim", "slide_top")
            speed = max(0.5, float(text_cfg.get("speed", 10)))
            is_loop = text_cfg.get("loop", True)

            if anim == "slide_top":
                y_expr = f"-h+(h+H)*mod(t\\,{speed})/{speed}" if is_loop else f"-h+(h+H)*min(t\\,{speed})/{speed}"
                next_v = "[vtext]"
                v_filter_chains.append(f"{curr_v}[{text_input_idx}:v]overlay=x=0:y='{y_expr}':eval=frame:repeatlast=1{next_v}")
                curr_v = next_v
            elif anim == "slide_bottom":
                y_expr = f"H-(h+H)*mod(t\\,{speed})/{speed}" if is_loop else f"H-(h+H)*min(t\\,{speed})/{speed}"
                next_v = "[vtext]"
                v_filter_chains.append(f"{curr_v}[{text_input_idx}:v]overlay=x=0:y='{y_expr}':eval=frame:repeatlast=1{next_v}")
                curr_v = next_v
            elif anim == "slide_left":
                x_expr = f"-w+(w+W)*mod(t\\,{speed})/{speed}" if is_loop else f"-w+(w+W)*min(t\\,{speed})/{speed}"
                next_v = "[vtext]"
                v_filter_chains.append(f"{curr_v}[{text_input_idx}:v]overlay=x='{x_expr}':y=0:eval=frame:repeatlast=1{next_v}")
                curr_v = next_v
            else:
                next_v = "[vtext]"
                v_filter_chains.append(f"{curr_v}[{text_input_idx}:v]overlay=0:0:repeatlast=1{next_v}")
                curr_v = next_v

        # 4. Logo Watermark Overlay
        logo_cfg = custom_edits.get("logo", {})
        if logo_cfg.get("enabled") and logo_file_path and os.path.exists(logo_file_path):
            logo_idx = next_input_idx
            inputs.extend(["-loop", "1", "-i", logo_file_path])
            next_input_idx += 1
            logo_size_pct = float(logo_cfg.get("size", 54)) / 100.0
            lw = max(20, int(width * logo_size_pct))
            logo_opacity = float(logo_cfg.get("opacity", 10)) / 100.0
            v_filter_chains.append(f"[{logo_idx}:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa={logo_opacity}[logo]")
            v_filter_chains.append(f"{curr_v}[logo]overlay=x=W-w-20:y=20:repeatlast=1[vout]")
        else:
            if curr_v == "[0:v]":
                v_filter_chains.append("[0:v]null[vout]")
            else:
                v_filter_chains.append(f"{curr_v}null[vout]")

        full_filter_list = [audio_filter] + v_filter_chains
        filter_complex_str = "; ".join(full_filter_list)


        # Save filter complex script to prevent Windows CLI command length limits
        filter_script_path = os.path.join(os.path.dirname(output_video_path), "filter_script.txt")
        with open(filter_script_path, "w", encoding="utf-8") as f:
            f.write(filter_complex_str)

        cmd = inputs + [
            "-filter_complex_script", filter_script_path,
            "-map", "[vout]", "-map", "[aout]"
        ] + v_codec + [
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart", output_video_path
        ]

        self.run_command(cmd)
        self.log("merge_video", 100, "Edited video rendered successfully with 100% preview match!")
        return output_video_path
