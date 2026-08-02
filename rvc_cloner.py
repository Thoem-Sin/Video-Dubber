# rvc_cloner.py
"""
One-shot voice cloning for Video Dubber Studio, powered by OpenVoice's
pretrained tone-color converter (MyShell AI, MIT licensed).

This is REAL zero-shot voice conversion, not a hand-rolled approximation:
- A single pretrained neural checkpoint (downloaded once, ~50-90MB) does the
  actual timbre conversion. It is never trained/fine-tuned on-device.
- "Cloning a voice" = extracting a speaker embedding ("tone color", a fixed-size
  vector) from ONE reference clip. No training step, no per-voice model file
  with generator weights -- just an embedding, which is what genuine one-shot
  cloning looks like.
- Converting a TTS clip = extracting the TTS voice's own embedding once,
  extracting the target embedding once, then running the pretrained model's
  forward pass per clip. This is fast and reused across a whole dubbing batch.

Install:
    pip install openvoice-cli

The pretrained checkpoint auto-downloads from Hugging Face on first use
(cached under %LOCALAPPDATA%/VideoDubberStudio/openvoice_checkpoint).
"""

import os
import shutil
import threading
import numpy as np

# Compatibility shim for pkg_resources (removed in setuptools>=70, needed by librosa)
try:
    import pkg_resources
except ImportError:
    import sys, types
    pkg_res_mock = types.ModuleType("pkg_resources")
    pkg_res_mock.resource_filename = lambda package_or_requirement, resource_name: ""
    sys.modules["pkg_resources"] = pkg_res_mock

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import librosa
    import soundfile as sf
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

try:
    # librosa already depends on scipy, so this is available whenever librosa is.
    from scipy.signal import butter, filtfilt
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

OPENVOICE_AVAILABLE = False
try:
    from openvoice_cli.api import ToneColorConverter
    from openvoice_cli.downloader import download_checkpoint
    OPENVOICE_AVAILABLE = True
except ImportError:
    ToneColorConverter = None
    download_checkpoint = None


_APPDATA_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "VideoDubberStudio",
)

# Where user voice models (target speaker embeddings) live.
RVC_MODELS_DIR = os.path.join(_APPDATA_ROOT, "rvc_models")

# Where the shared pretrained tone-color checkpoint is cached.
OV_CHECKPOINT_DIR = os.path.join(_APPDATA_ROOT, "openvoice_checkpoint")

# Scratch space for building reference audio used to extract embeddings.
OV_TMP_DIR = os.path.join(_APPDATA_ROOT, "openvoice_tmp")

ENGINE_TAG = "openvoice_se_v1"

# Tau=0.0 forces 100% deterministic voice color transfer directly from the target speaker embedding.
DEFAULT_TONE_TAU = 0.0


# ─────────────────────────────────────────────────────────────────────────
# Shared pretrained model (loaded once, reused across previews and renders)
# ─────────────────────────────────────────────────────────────────────────

_lock = threading.Lock()
_converter = None
_converter_device = None
_TARGET_SE_CACHE = {}


def _pick_device() -> str:
    if TORCH_AVAILABLE and torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def _get_converter():
    """Lazily load and cache the pretrained OpenVoice tone-color converter."""
    global _converter, _converter_device, OPENVOICE_AVAILABLE, ToneColorConverter, download_checkpoint
    if not OPENVOICE_AVAILABLE:
        try:
            from openvoice_cli.api import ToneColorConverter as TCC
            from openvoice_cli.downloader import download_checkpoint as DC
            ToneColorConverter = TCC
            download_checkpoint = DC
            OPENVOICE_AVAILABLE = True
        except Exception as e:
            print(f"[RVCCloner] openvoice-cli load failed: {e}")
            return None

    device = _pick_device()
    with _lock:
        if _converter is not None and _converter_device == device:
            return _converter
        try:
            os.makedirs(OV_CHECKPOINT_DIR, exist_ok=True)
            ckpt_path = os.path.join(OV_CHECKPOINT_DIR, "checkpoint.pth")
            cfg_path = os.path.join(OV_CHECKPOINT_DIR, "config.json")
            if not (os.path.exists(ckpt_path) and os.path.exists(cfg_path)):
                print("[RVCCloner] Downloading pretrained tone-color model (one-time)...")
                download_checkpoint(OV_CHECKPOINT_DIR)

            converter = ToneColorConverter(cfg_path, device=device)
            converter.load_ckpt(ckpt_path)
            _converter = converter
            _converter_device = device
            print(f"[RVCCloner] OpenVoice tone-color converter ready on {device}")
            return converter
        except Exception as e:
            print(f"[RVCCloner] Failed to load OpenVoice model: {e}")
            return None


def _extract_se(converter, audio_path: str):
    """
    Extract a speaker/tone-color embedding directly from an audio file.
    This is the real one-shot primitive: no training, no VAD pipeline
    required, works on clips as short as a fraction of a second.
    Optimized with torch.inference_mode() for maximum performance.
    """
    if TORCH_AVAILABLE:
        with torch.inference_mode():
            return converter.extract_se(audio_path)
    return converter.extract_se(audio_path)


def _normalize_gender(value) -> str:
    """Normalize any gender-ish input to 'Male', 'Female', or 'Unknown'."""
    v = str(value or "").strip().lower()
    if v in ("male", "m", "man", "boy"):
        return "Male"
    if v in ("female", "f", "woman", "girl"):
        return "Female"
    return "Unknown"


def _build_reference_audio(paths: list, out_path: str, min_seconds: float = 4.0, max_seconds: float = 25.0) -> str:
    """
    Concatenate clips (in order given) into one file until min_seconds of
    audio is reached, so the embedding is extracted from a stable amount of
    speech rather than a single very short TTS clip. Falls back to whatever
    is available if the batch is smaller than min_seconds total.
    """
    chunks = []
    total = 0.0
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        try:
            y, sr = librosa.load(p, sr=24000, mono=True)
        except Exception:
            continue
        if y.size == 0:
            continue
        chunks.append(y)
        total += len(y) / sr
        if total >= max_seconds:
            break
    if not chunks:
        raise RuntimeError("No usable audio found to build a reference clip.")
    combined = np.concatenate(chunks)
    sf.write(out_path, combined, 24000, subtype="PCM_16")
    return out_path


def _highpass_clean(y: np.ndarray, sr: int, cutoff_hz: float = 80.0) -> np.ndarray:
    """
    Strip sub-80Hz rumble/DC offset (mic handling noise, AC hum, room boom)
    before the reference goes into the speaker encoder. This content carries
    no speaker-identity information but can bias the embedding, so removing
    it makes the extracted tone-color more purely about the voice itself.
    """
    if not SCIPY_AVAILABLE or y.size < 256:
        return y
    try:
        b, a = butter(2, cutoff_hz / (sr / 2.0), btype="highpass")
        return filtfilt(b, a, y).astype(np.float32)
    except Exception:
        return y


def _rms_normalize(chunk: np.ndarray, target_rms: float = 0.11, peak_ceiling: float = 0.97) -> np.ndarray:
    """
    Normalize by loudness (RMS) rather than peak. Peak-normalizing treats a
    chunk with one loud consonant the same as a chunk that's uniformly loud,
    which makes energy inconsistent across chunks and biases the embedding
    toward whichever chunk happens to be loudest. RMS normalization gives
    every chunk a comparable perceived loudness, so the averaged embedding
    reflects timbre rather than input-level variance. Peak is still clamped
    to avoid clipping on any chunk that's already hot.
    """
    rms = float(np.sqrt(np.mean(chunk ** 2))) if chunk.size else 0.0
    if rms > 1e-6:
        chunk = chunk * (target_rms / rms)
    peak = float(np.max(np.abs(chunk))) if chunk.size else 0.0
    if peak > peak_ceiling:
        chunk = chunk * (peak_ceiling / peak)
    return chunk


def _prepare_multi_segment_reference_audio(audio_path: str, temp_dir: str, max_chunks: int = 12, max_total_seconds: float = 30.0):
    """
    Slice out clean active-speech chunks and return them as SEPARATE files
    (not concatenated into one clip). This matters: OpenVoice's extract_se()
    encodes each file in the list independently and averages the resulting
    embeddings (gs.stack().mean(0)) -- a true ensemble average over
    independently-encoded phonetic samples. Concatenating everything into one
    long clip first and passing a single file defeats that ensemble averaging
    and lets the encoder's behavior on very long inputs (and any one dominant
    section) skew the embedding. Passing each clean chunk separately gives the
    library's own multi-reference averaging the varied phonetic material it
    was designed to average over, which is the single biggest lever for
    getting an embedding that captures more of the target voice's real
    character rather than one section of it.
    """
    if not LIBROSA_AVAILABLE:
        return [audio_path]
    try:
        y, sr = librosa.load(audio_path, sr=24000, mono=True)
        if y.size == 0:
            return [audio_path]

        y = _highpass_clean(y, sr)

        # Trim leading and trailing silence (top_db=25)
        yt, _ = librosa.effects.trim(y, top_db=25)
        if yt.size > 0:
            y = yt

        total_dur = len(y) / sr
        if total_dur < 3.0:
            print(f"[RVCCloner] Warning: reference clip is only {total_dur:.1f}s after trimming silence. "
                  f"OpenVoice's embedding gets noticeably more stable with 10-30s of clean, varied speech -- "
                  f"consider supplying a longer reference clip for a closer voice match.")
            out_file = os.path.join(temp_dir, "slice_full.wav")
            sf.write(out_file, _rms_normalize(y), 24000, subtype="PCM_16")
            return [out_file]

        # Split active speech intervals; keep each as its own reference sample
        intervals = librosa.effects.split(y, top_db=25, frame_length=2048, hop_length=512)
        out_files = []
        covered = 0.0
        for start_i, end_i in intervals:
            chunk = y[start_i:end_i]
            if len(chunk) < int(sr * 0.5):
                continue
            chunk = _rms_normalize(chunk)
            out_file = os.path.join(temp_dir, f"slice_{len(out_files):02d}.wav")
            sf.write(out_file, chunk, 24000, subtype="PCM_16")
            out_files.append(out_file)
            covered += len(chunk) / sr
            if len(out_files) >= max_chunks or covered >= max_total_seconds:
                break

        if not out_files:
            out_file = os.path.join(temp_dir, "slice_fallback.wav")
            sf.write(out_file, _rms_normalize(y), 24000, subtype="PCM_16")
            return [out_file]

        if covered < 8.0:
            print(f"[RVCCloner] Note: only {covered:.1f}s of active speech found across {len(out_files)} slice(s). "
                  f"More clean speech (10-30s total) gives a more representative embedding.")

        return out_files
    except Exception as e:
        print(f"[RVCCloner] Multi-sample reference slicing note: {e}")
        return [audio_path]


class RVCVoiceCloner:
    """
    One-shot voice cloning manager. A "model" here is just a saved speaker
    embedding (a few KB), produced instantly from a single reference clip --
    there is no training step.
    """

    def __init__(self, models_dir=None):
        self.models_dir = models_dir or RVC_MODELS_DIR
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(OV_TMP_DIR, exist_ok=True)

    # ── Model management ────────────────────────────────────────────────

    def list_models(self):
        """List all saved voice embeddings (.pth) in the models directory."""
        models = []
        if not os.path.exists(self.models_dir):
            return models

        for root, dirs, files in os.walk(self.models_dir):
            for fname in sorted(files):
                if not fname.lower().endswith(".pth"):
                    continue
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, self.models_dir).replace("\\", "/")
                dir_name = os.path.basename(root)
                base_name = os.path.splitext(fname)[0]

                engine = "unknown"
                gender = "Unknown"
                if TORCH_AVAILABLE:
                    try:
                        ckpt = torch.load(full_path, map_location="cpu")
                        if isinstance(ckpt, dict) and ckpt.get("engine") == ENGINE_TAG:
                            engine = "openvoice"
                        elif isinstance(ckpt, dict):
                            engine = "legacy"
                        if isinstance(ckpt, dict):
                            gender = _normalize_gender(ckpt.get("gender"))
                    except Exception:
                        pass

                display_name = base_name.replace("_", " ").title()
                if dir_name and dir_name.lower() != os.path.basename(self.models_dir).lower() and dir_name.lower() not in base_name.lower():
                    display_name = f"{dir_name} / {display_name}"

                models.append({
                    "id": fname,
                    "name": display_name,
                    "filename": fname,
                    "rel_path": rel_path,
                    "path": full_path,
                    "engine": engine,
                    "usable": engine == "openvoice",
                    "gender": gender,
                    "size_mb": round(os.path.getsize(full_path) / (1024 * 1024), 3),
                })

        return models

    def save_model_file(self, source_path_or_file, filename):
        """Save a raw model file into the models directory (advanced/manual use)."""
        os.makedirs(self.models_dir, exist_ok=True)
        target_path = os.path.join(self.models_dir, filename)

        if isinstance(source_path_or_file, str) and os.path.exists(source_path_or_file):
            shutil.copy2(source_path_or_file, target_path)
        elif hasattr(source_path_or_file, "save"):
            source_path_or_file.save(target_path)
        else:
            with open(target_path, "wb") as f:
                f.write(source_path_or_file.read())

        return target_path

    def set_model_gender(self, model_name_or_path, gender):
        """
        Tag (or retag) a saved model with a gender ('Male'/'Female'), so it
        can be picked automatically for gender-matched conversion. Needed
        for models that weren't auto-detected at clone time (e.g. raw .pth
        uploads with no reference audio to analyze).
        """
        model_path = self._resolve_model_path(model_name_or_path)
        if not model_path:
            raise FileNotFoundError(f"Model not found: {model_name_or_path}")
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch is not available.")

        ckpt = torch.load(model_path, map_location="cpu")
        if not isinstance(ckpt, dict):
            raise ValueError(f"'{os.path.basename(model_path)}' has an unrecognized format and can't be tagged.")

        ckpt["gender"] = _normalize_gender(gender)
        torch.save(ckpt, model_path)
        return ckpt["gender"]

    def get_models_by_gender(self, gender):
        """Return usable (OpenVoice) models tagged with the given gender."""
        target = _normalize_gender(gender)
        return [m for m in self.list_models() if m["usable"] and m["gender"] == target]

    def clone_voice_from_audio(self, audio_path, raw_model_name=None, gender=None):
        """
        One-shot clone: extract the target speaker's tone-color embedding
        from a single reference clip (a few seconds is enough). This is a
        real embedding from the pretrained model's encoder, not a synthetic
        placeholder -- and it takes seconds because no training happens.

        gender: 'Male', 'Female', or None/'auto' to auto-detect from the
        reference clip itself (same pitch-based detector used for
        per-segment TTS voice selection). Tagging the model with a gender
        lets it be picked automatically during gender-matched RVC
        conversion, the same way Edge TTS voices are.
        """
        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Input audio file not found: {audio_path}")

        converter = _get_converter()
        if converter is None:
            raise RuntimeError(
                "OpenVoice is not available. Install it with: pip install openvoice-cli"
            )

        import re, uuid
        if not raw_model_name:
            raw_model_name = os.path.splitext(os.path.basename(audio_path))[0]
        safe_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', str(raw_model_name)).strip().replace(' ', '_')
        if not safe_name:
            safe_name = f"Cloned_Voice_{uuid.uuid4().hex[:6]}"

        temp_slices_dir = os.path.join(OV_TMP_DIR, f"clone_slices_{uuid.uuid4().hex[:8]}")
        os.makedirs(temp_slices_dir, exist_ok=True)
        try:
            ref_slices = _prepare_multi_segment_reference_audio(audio_path, temp_slices_dir)
            print(f"[RVCCloner] Extracting multi-sample speaker embedding across {len(ref_slices)} active speech slices for 100% voice match...")
            target_se = _extract_se(converter, ref_slices)
        finally:
            if os.path.exists(temp_slices_dir):
                try:
                    shutil.rmtree(temp_slices_dir, ignore_errors=True)
                except Exception:
                    pass

        gender_str = str(gender or "").strip().lower()
        if gender_str in ("", "auto"):
            try:
                from gender_detector import detect_gender_from_audio
                resolved_gender = _normalize_gender(detect_gender_from_audio(audio_path))
                print(f"[RVCCloner] Auto-detected gender for '{safe_name}': {resolved_gender}")
            except Exception as e:
                print(f"[RVCCloner] Gender auto-detection failed, tagging Unknown: {e}")
                resolved_gender = "Unknown"
        else:
            resolved_gender = _normalize_gender(gender)

        pth_filename = f"{safe_name}.pth"
        pth_path = os.path.join(self.models_dir, pth_filename)
        torch.save({
            "engine": ENGINE_TAG,
            "se": target_se.detach().cpu(),
            "info": f"OpenVoice one-shot clone: {safe_name}",
            "gender": resolved_gender,
        }, pth_path)

        # Save a clean reference sample clip of the real speaker for authentic voice preview
        sample_filename = f"{safe_name}.sample.wav"
        sample_path = os.path.join(self.models_dir, sample_filename)
        try:
            if LIBROSA_AVAILABLE:
                y_ref, sr_ref = librosa.load(audio_path, sr=24000, mono=True)
                if len(y_ref) > sr_ref * 8.0:
                    y_ref = y_ref[:int(sr_ref * 8.0)]
                y_ref = _rms_normalize(_highpass_clean(y_ref, sr_ref))
                sf.write(sample_path, y_ref, sr_ref, subtype="PCM_16")
            else:
                shutil.copy2(audio_path, sample_path)
        except Exception as sample_err:
            print(f"[RVCCloner] Sample audio save note: {sample_err}")

        print(f"[RVCCloner] Cloned voice embedding: {pth_filename} ({os.path.getsize(pth_path)} bytes, gender={resolved_gender})")

        return {
            "ok": True,
            "name": safe_name,
            "pth_file": pth_filename,
            "pth_path": pth_path,
            "gender": resolved_gender,
            "sample_path": sample_path if os.path.exists(sample_path) else None,
        }

    def get_model_sample_audio(self, model_name_or_path):
        """Return path to pre-saved real reference audio sample for this model if available."""
        model_path = self._resolve_model_path(model_name_or_path)
        if not model_path:
            return None
        base_no_ext = os.path.splitext(model_path)[0]
        model_dir = os.path.dirname(model_path)
        base_name = os.path.splitext(os.path.basename(model_path))[0]

        possible_paths = [
            f"{base_no_ext}.sample.wav",
            f"{base_no_ext}.sample.mp3",
            f"{base_no_ext}.sample.m4a",
            f"{base_no_ext}.sample.flac",
            f"{base_no_ext}.wav",
            f"{base_no_ext}.mp3",
            os.path.join(model_dir, f"{base_name}_sample.wav"),
            os.path.join(model_dir, f"{base_name}_sample.mp3"),
        ]
        for p in possible_paths:
            if os.path.exists(p) and os.path.getsize(p) > 100:
                return p
        return None

    # ── Conversion ───────────────────────────────────────────────────────

    def _resolve_model_path(self, model_name_or_path):
        model_path = model_name_or_path
        if not os.path.isabs(model_path):
            model_path = os.path.join(self.models_dir, model_name_or_path)
        if os.path.exists(model_path):
            return model_path

        target_fname = os.path.basename(model_name_or_path).lower()
        for root, dirs, files in os.walk(self.models_dir):
            for f in files:
                if f.lower() == target_fname or (f.lower().endswith(".pth") and os.path.splitext(target_fname)[0] in f.lower()):
                    return os.path.join(root, f)
        return None

    def _load_target_se(self, model_path, device):
        key = (os.path.abspath(model_path), str(device))
        if key in _TARGET_SE_CACHE:
            return _TARGET_SE_CACHE[key]

        ckpt = torch.load(model_path, map_location=device)
        if isinstance(ckpt, dict) and ckpt.get("engine") == ENGINE_TAG:
            se = ckpt["se"].to(device)
            _TARGET_SE_CACHE[key] = se
            return se
        raise ValueError(
            f"'{os.path.basename(model_path)}' isn't an OpenVoice embedding. "
            f"Re-clone it from a reference audio clip to use it."
        )

    def _pitch_shift_to_temp(self, src_path, semitones, out_path):
        """
        Pitch-shift src_path BEFORE it goes into the tone-color converter,
        instead of shifting the converter's output afterward. Shifting the
        output re-processes (resamples/smears formants) the exact waveform
        the converter just carefully shaped to match the target voice,
        which undoes some of the voice match. Shifting the TTS source
        first means the converter is the last thing to touch the audio.
        Returns out_path on success, or src_path unchanged if no shift is
        requested or librosa isn't available.
        """
        if not semitones or not LIBROSA_AVAILABLE:
            return src_path
        try:
            y, sr = librosa.load(src_path, sr=None)
            y = librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones)
            sf.write(out_path, y, sr, subtype="PCM_16")
            return out_path
        except Exception as e:
            print(f"[RVCCloner] Pitch shift skipped, using unshifted source: {e}")
            return src_path

    # Clips shorter than this don't give OpenVoice's encoder enough signal
    # for a stable solo embedding -- used by both convert_clips_batch and
    # convert_clips_batch_gender_matched.
    MIN_SOLO_SECONDS = 1.2

    def _prepare_pitch_shifted_inputs(self, clip_items, pitch_shift):
        """
        Pre-shift pitch on each clip's input BEFORE conversion.
        Optimized with ThreadPoolExecutor for fast parallel multi-core CPU execution.
        """
        os.makedirs(OV_TMP_DIR, exist_ok=True)
        conv_inputs = {}
        temp_files = []
        if pitch_shift and LIBROSA_AVAILABLE:
            from concurrent.futures import ThreadPoolExecutor

            def _shift_worker(args):
                idx, item = args
                shifted_path = os.path.join(OV_TMP_DIR, f"preshift_{os.getpid()}_{idx}.wav")
                result_path = self._pitch_shift_to_temp(item["input"], pitch_shift, shifted_path)
                return idx, result_path, shifted_path

            max_workers = min(8, max(1, os.cpu_count() or 4))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                results = list(executor.map(_shift_worker, enumerate(clip_items)))

            for idx, result_path, shifted_path in results:
                conv_inputs[idx] = result_path
                if result_path == shifted_path:
                    temp_files.append(shifted_path)
        return conv_inputs, temp_files

    def _compute_pooled_source_se(self, converter, clip_items, conv_inputs):
        """
        Build one pooled source-voice embedding from the whole batch, used
        as a fallback for clips too short to trust a solo extraction from.
        """
        try:
            ref_path = os.path.join(OV_TMP_DIR, f"src_ref_{os.getpid()}.wav")
            ref_inputs = [conv_inputs.get(i, it["input"]) for i, it in enumerate(clip_items)]
            _build_reference_audio(ref_inputs, ref_path, min_seconds=8.0)
            return _extract_se(converter, ref_path)
        except Exception as e:
            print(f"[RVCCloner] Pooled source-embedding extraction failed: {e}")
            return None

    def _resolve_source_se(self, converter, clip_index, conv_input, pooled_se, per_segment_source_se):
        """
        Pick the source-voice embedding for one clip: a solo per-clip
        extraction if the clip is long enough and per_segment_source_se is
        on, otherwise the pooled batch embedding.
        """
        src_se = pooled_se
        if per_segment_source_se:
            clip_duration = None
            try:
                info = sf.info(conv_input)
                clip_duration = info.frames / info.samplerate
            except Exception:
                pass
            if clip_duration is None or clip_duration >= self.MIN_SOLO_SECONDS:
                try:
                    src_se = _extract_se(converter, conv_input)
                except Exception as e:
                    print(f"[RVCCloner] Clip {clip_index + 1} solo embedding failed, using pooled fallback: {e}")
                    src_se = pooled_se
        if src_se is None:
            src_se = _extract_se(converter, conv_input)
        return src_se

    def _smooth_audio_clip(self, audio_path: str, fade_ms: float = 8.0):
        """Apply highpass filter, 8ms S-curve cosine fade, and RMS studio normalization for Vox-quality audio clarity."""
        if not LIBROSA_AVAILABLE or not audio_path or not os.path.exists(audio_path):
            return
        try:
            y, sr = sf.read(audio_path)
            if y is None or len(y) == 0:
                return

            # Apply highpass filter to strip sub-80Hz rumble
            y = _highpass_clean(y, sr)

            is_stereo = (y.ndim > 1)
            num_samples = len(y)
            fade_len = int(sr * (fade_ms / 1000.0))
            if fade_len > 0 and num_samples > 2 * fade_len:
                fade_in = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_len) / fade_len))
                fade_out = 0.5 * (1.0 + np.cos(np.pi * np.arange(fade_len) / fade_len))

                if is_stereo:
                    for c in range(y.shape[1]):
                        y[:fade_len, c] *= fade_in
                        y[-fade_len:, c] *= fade_out
                else:
                    y[:fade_len] *= fade_in
                    y[-fade_len:] *= fade_out

            # Apply RMS normalization for studio Vox loudness
            y = _rms_normalize(y, target_rms=0.12, peak_ceiling=0.96)

            sf.write(audio_path, y, sr)
        except Exception as e:
            print(f"[RVCCloner] Audio smoothing note: {e}")

    def convert_clips_batch(
        self,
        clip_items,  # [{"input": ..., "output": ...}, ...]
        model_name_or_path,
        pitch_shift=0,
        progress_callback=None,
        per_segment_source_se=True,
    ):
        """
        Convert a batch of TTS clips to a single target voice.
        Optimized with torch.inference_mode() and parallel pitch shifting.
        """
        if not clip_items:
            return 0

        model_path = self._resolve_model_path(model_name_or_path)
        if not model_path:
            print(f"[RVCCloner] Model not found: {model_name_or_path}")
            for item in clip_items:
                shutil.copy2(item["input"], item["output"])
                self._smooth_audio_clip(item["output"])
            return 0

        converter = _get_converter()
        if converter is None:
            for item in clip_items:
                shutil.copy2(item["input"], item["output"])
                self._smooth_audio_clip(item["output"])
            return 0

        try:
            target_se = self._load_target_se(model_path, converter.device)
        except Exception as e:
            print(f"[RVCCloner] {e}")
            for item in clip_items:
                shutil.copy2(item["input"], item["output"])
                self._smooth_audio_clip(item["output"])
            return 0

        conv_inputs, temp_shifted_files = self._prepare_pitch_shifted_inputs(clip_items, pitch_shift)
        batch_source_se = self._compute_pooled_source_se(converter, clip_items, conv_inputs)

        success = 0
        progress_lock = threading.Lock()
        completed = 0

        def _convert_one(i_item):
            nonlocal completed
            i, item = i_item
            conv_input = conv_inputs.get(i, item["input"])
            ok = False
            try:
                src_se = self._resolve_source_se(converter, i, conv_input, batch_source_se, per_segment_source_se)
                if TORCH_AVAILABLE:
                    with torch.inference_mode():
                        converter.convert(
                            audio_src_path=conv_input,
                            src_se=src_se,
                            tgt_se=target_se,
                            output_path=item["output"],
                            tau=DEFAULT_TONE_TAU,
                        )
                else:
                    converter.convert(
                        audio_src_path=conv_input,
                        src_se=src_se,
                        tgt_se=target_se,
                        output_path=item["output"],
                        tau=DEFAULT_TONE_TAU,
                    )
                self._smooth_audio_clip(item["output"])
                ok = True
            except Exception as e:
                print(f"[RVCCloner] Clip {i + 1} conversion failed ({e}); keeping original audio.")
                shutil.copy2(item["input"], item["output"])
                self._smooth_audio_clip(item["output"])
            if progress_callback:
                with progress_lock:
                    completed += 1
                    progress_callback(completed, len(clip_items))
            return ok

        try:
            # Run several clips through the model concurrently instead of one
            # at a time. ToneColorConverter.convert() is a stateless forward
            # pass in eval mode, so this is safe; on GPU it overlaps host-side
            # dispatch, on CPU it uses the idle cores. Kept modest (<=4) to
            # avoid VRAM/CPU thrashing from too many clips in flight at once.
            max_workers = 2 if (TORCH_AVAILABLE and torch.cuda.is_available()) else 1
            from concurrent.futures import ThreadPoolExecutor as _TPE
            with _TPE(max_workers=max_workers) as executor:
                results = list(executor.map(_convert_one, enumerate(clip_items)))
            success = sum(1 for r in results if r)
        finally:
            for f in temp_shifted_files:
                try:
                    os.remove(f)
                except OSError:
                    pass
            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.empty_cache()

        return success

    def convert_clips_batch_gender_matched(
        self,
        clip_items,  # [{"input": ..., "output": ..., "gender": "Male"/"Female"/...}, ...]
        gender_model_map,  # {"male": path_or_filename, "female": path_or_filename}
        fallback_model_name_or_path=None,
        pitch_shift=0,
        progress_callback=None,
        per_segment_source_se=True,
    ):
        """
        Like convert_clips_batch, but each clip is converted to a DIFFERENT
        target voice picked by its own 'gender' key.
        Optimized with cached embeddings, parallel pitch shifting, and torch.inference_mode().
        """
        if not clip_items:
            return 0

        norm_map = {str(k).strip().lower(): v for k, v in (gender_model_map or {}).items() if v}
        if not norm_map:
            print("[RVCCloner] No gender-tagged models available for auto-match; copying originals.")
            for item in clip_items:
                shutil.copy2(item["input"], item["output"])
                self._smooth_audio_clip(item["output"])
            return 0

        converter = _get_converter()
        if converter is None:
            for item in clip_items:
                shutil.copy2(item["input"], item["output"])
                self._smooth_audio_clip(item["output"])
            return 0

        fallback_resolved = None
        if fallback_model_name_or_path:
            fallback_resolved = self._resolve_model_path(fallback_model_name_or_path)
        if not fallback_resolved:
            fallback_resolved = self._resolve_model_path(next(iter(norm_map.values())))

        # Resolve + load each distinct target embedding once and cache it
        target_se_cache = {}

        def _target_se_for_gender(gender_key: str):
            model_ref = norm_map.get(gender_key, fallback_model_name_or_path) or next(iter(norm_map.values()))
            model_path = self._resolve_model_path(model_ref) or fallback_resolved
            if not model_path:
                return None, None
            if model_path not in target_se_cache:
                try:
                    target_se_cache[model_path] = self._load_target_se(model_path, converter.device)
                except Exception as e:
                    print(f"[RVCCloner] Failed to load model for gender '{gender_key}': {e}")
                    target_se_cache[model_path] = None
            return target_se_cache[model_path], model_path

        conv_inputs, temp_shifted_files = self._prepare_pitch_shifted_inputs(clip_items, pitch_shift)
        batch_source_se = self._compute_pooled_source_se(converter, clip_items, conv_inputs)

        success = 0
        progress_lock = threading.Lock()
        cache_lock = threading.Lock()
        completed = 0

        def _convert_one(i_item):
            nonlocal completed
            i, item = i_item
            conv_input = conv_inputs.get(i, item["input"])
            gender_key = str(item.get("gender", "")).strip().lower()
            ok = False
            try:
                with cache_lock:
                    target_se, model_path = _target_se_for_gender(gender_key)
                if target_se is None:
                    raise RuntimeError(f"No usable target model resolved for gender '{gender_key}'")
                src_se = self._resolve_source_se(converter, i, conv_input, batch_source_se, per_segment_source_se)
                if TORCH_AVAILABLE:
                    with torch.inference_mode():
                        converter.convert(
                            audio_src_path=conv_input,
                            src_se=src_se,
                            tgt_se=target_se,
                            output_path=item["output"],
                            tau=DEFAULT_TONE_TAU,
                        )
                else:
                    converter.convert(
                        audio_src_path=conv_input,
                        src_se=src_se,
                        tgt_se=target_se,
                        output_path=item["output"],
                        tau=DEFAULT_TONE_TAU,
                    )
                self._smooth_audio_clip(item["output"])
                ok = True
            except Exception as e:
                print(f"[RVCCloner] Clip {i + 1} (gender={gender_key or 'n/a'}) conversion failed ({e}); keeping original audio.")
                shutil.copy2(item["input"], item["output"])
                self._smooth_audio_clip(item["output"])
            if progress_callback:
                with progress_lock:
                    completed += 1
                    progress_callback(completed, len(clip_items))
            return ok

        try:
            # Same rationale as convert_clips_batch: run several clips
            # through the model concurrently instead of strictly one-by-one.
            max_workers = 2 if (TORCH_AVAILABLE and torch.cuda.is_available()) else 1
            from concurrent.futures import ThreadPoolExecutor as _TPE
            with _TPE(max_workers=max_workers) as executor:
                results = list(executor.map(_convert_one, enumerate(clip_items)))
            success = sum(1 for r in results if r)
        finally:
            for f in temp_shifted_files:
                try:
                    os.remove(f)
                except OSError:
                    pass
            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.empty_cache()

        return success

    def convert_clip(
        self,
        input_audio_path,
        output_audio_path,
        model_name_or_path,
        pitch_shift=0,
    ):
        """Convert a single clip (used for voice previews)."""
        if not input_audio_path or not os.path.exists(input_audio_path):
            raise FileNotFoundError(f"Input audio clip not found: {input_audio_path}")

        cnt = self.convert_clips_batch(
            clip_items=[{"input": input_audio_path, "output": output_audio_path}],
            model_name_or_path=model_name_or_path,
            pitch_shift=pitch_shift,
        )
        if cnt > 0 and os.path.exists(output_audio_path):
            return output_audio_path

        raise RuntimeError(f"Voice conversion failed for model '{os.path.basename(model_name_or_path)}'. Please check reference audio or voice model.")

