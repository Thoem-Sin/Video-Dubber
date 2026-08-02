# app.py
import os
import sys
import uuid
import json
import re
import queue
import threading
import subprocess
import base64

import asyncio
import urllib.request
import urllib.error
import edge_tts

# Force UTF-8 encoding for Windows console and subprocesses
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify, Response, send_from_directory, send_file, after_this_request
from flask_cors import CORS
from voices_config import SUPPORTED_LANGUAGES, get_default_voice
from dubbing_engine import VideoDubberEngine, PreviewRenderConfig
import font_manager

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

app = Flask(__name__, template_folder="templates", static_folder="static")

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(app)

@app.after_request
def add_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

import tempfile
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_BASE = os.path.join(tempfile.gettempdir(), "VideoDubberStudio")
UPLOAD_DIR = os.path.join(TEMP_BASE, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
CONFIG_PATH = os.path.join(BASE_DIR, "user_config.json")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_user_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading user_config.json: {e}")
    return {}

def save_user_config(data):
    current = load_user_config()
    current.update(data)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        print(f"Error saving user_config.json: {e}")

# Load initial config into os.environ
_init_cfg = load_user_config()
if _init_cfg.get("gemini_api_key"):
    os.environ["GEMINI_API_KEY"] = _init_cfg["gemini_api_key"]

@app.route("/api/config", methods=["GET", "POST"])
def manage_config():
    """Auto-save and retrieve persistent user configuration."""
    if request.method == "POST":
        data = request.json or request.form.to_dict()
        save_user_config(data)
        if data.get("gemini_api_key"):
            os.environ["GEMINI_API_KEY"] = data["gemini_api_key"].strip()
        if data.get("groq_api_key"):
            os.environ["GROQ_API_KEY"] = data["groq_api_key"].strip()
        if data.get("deepseek_api_key"):
            os.environ["DEEPSEEK_API_KEY"] = data["deepseek_api_key"].strip()
        if data.get("openrouter_api_key"):
            os.environ["OPENROUTER_API_KEY"] = data["openrouter_api_key"].strip()
        if data.get("openai_api_key"):
            os.environ["OPENAI_API_KEY"] = data["openai_api_key"].strip()
        return jsonify({"status": "saved", "config": load_user_config()})
    else:
        return jsonify(load_user_config())

@app.route("/api/gpu_status", methods=["GET"])
def get_gpu_status():
    """Auto-detect system GPU hardware acceleration capabilities for PyTorch and FFmpeg."""
    engine = VideoDubberEngine()
    caps = engine.detect_gpu_capabilities()
    return jsonify({
        "status": "ok",
        "gpu_available": caps["torch_gpu"] or caps["ffmpeg_encoder"] != "libx264",
        "gpu_name": caps["gpu_name"],
        "whisper_device": f"CUDA GPU ({caps['gpu_name']})" if caps["torch_gpu"] else "CPU",
        "ffmpeg_encoder": caps["ffmpeg_encoder"]
    })

APP_VERSION = "1.2.1"

GITHUB_REPO = "thoem-sin/video-dubber"
GITHUB_BRANCH = "main"

# Cache update result for 5 minutes to avoid hammering network
_update_cache = {"result": None, "expires": 0}

@app.route("/api/check_update", methods=["GET"])
def check_update():
    """Check for updates via version.txt on raw.githubusercontent.com (no rate limits)."""
    import time as _time

    if _update_cache["result"] and _time.time() < _update_cache["expires"]:
        return jsonify(_update_cache["result"])

    latest_tag = ""
    html_url = f"https://github.com/{GITHUB_REPO}/releases"
    notes = ""

    def fetch(url, headers=None):
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "VideoDubberStudio/1.2"})
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.read().decode("utf-8").strip()

    # Method 1: Read version.txt from raw.githubusercontent.com — NO rate limits
    try:
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/version.txt"
        latest_tag = fetch(raw_url).splitlines()[0].strip().lstrip("v")
    except Exception:
        pass

    # Also fetch release notes from RELEASE_NOTES.txt
    try:
        notes_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/RELEASE_NOTES.txt"
        notes = fetch(notes_url)
    except Exception:
        pass

    # Method 2: GitHub Tags API (fallback)
    if not latest_tag:
        try:
            import json as _json
            req = urllib.request.Request(
                f"https://api.github.com/repos/{GITHUB_REPO}/tags",
                headers={"User-Agent": "VideoDubberStudio/1.2"}
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                tags_data = _json.loads(r.read())
            if tags_data:
                latest_tag = tags_data[0].get("name", "").lstrip("v").strip()
        except Exception:
            pass

    update_available = False
    if latest_tag:
        try:
            curr_parts = [int(p) for p in APP_VERSION.split(".") if p.isdigit()]
            latest_parts = [int(p) for p in latest_tag.split(".") if p.isdigit()]
            update_available = latest_parts > curr_parts
        except Exception:
            pass

    result = {
        "status": "ok",
        "current_version": APP_VERSION,
        "latest_version": latest_tag or APP_VERSION,
        "has_update": update_available,
        "update_available": update_available,
        "download_url": html_url,
        "release_notes": notes
    }
    _update_cache["result"] = result
    _update_cache["expires"] = _time.time() + 300
    return jsonify(result)


JOBS = {}




class JobTracker:
    def __init__(self, job_id):
        self.job_id = job_id
        self.status = "queued"
        self.progress = 0
        self.step = "init"
        self.message = "Initializing job..."
        self.error = None
        self.listeners = []
        self.result_data = {}
        self.original_base = "dubbed"

    def update(self, data):
        self.step = data.get("step", self.step)
        self.progress = data.get("progress", self.progress)
        self.message = data.get("message", self.message)
        
        event = {
            "job_id": self.job_id,
            "status": self.status,
            "step": self.step,
            "progress": self.progress,
            "message": self.message,
            "result_data": self.result_data,
            "error": self.error
        }
        
        for q in list(self.listeners):
            try:
                q.put(event)
            except Exception:
                pass

import shutil

@app.route("/api/rvc_models", methods=["GET"])

def get_rvc_models():
    """List available RVC .pth voice cloning models."""
    from rvc_cloner import RVCVoiceCloner
    cloner = RVCVoiceCloner()
    return jsonify({"status": "ok", "models": cloner.list_models()})

@app.route("/api/upload_rvc_model", methods=["POST"])
def upload_rvc_model():
    """Upload a custom RVC model file (.pth or .index) OR an audio file (.wav, .mp3, .flac, .m4a) to auto-clone into .pth and .index files."""
    from rvc_cloner import RVCVoiceCloner
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"error": "No file selected"}), 400

    filename = os.path.basename(f.filename)
    ext = os.path.splitext(filename)[1].lower()

    AUDIO_EXTS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}
    MODEL_EXTS = {".pth", ".index", ".zip", ".tar", ".gz", ".7z"}

    if ext not in AUDIO_EXTS and ext not in MODEL_EXTS:
        return jsonify({"error": "Invalid format. Upload a .pth model, .index file, .zip model archive, or an audio clip (.wav, .mp3, .flac, .m4a)"}), 400

    cloner = RVCVoiceCloner()

    # Zip model archive upload → Extract full model directory structure
    if ext == ".zip":
        import zipfile
        tmp_zip = os.path.join(TEMP_BASE, f"upload_{uuid.uuid4().hex[:8]}.zip")
        os.makedirs(TEMP_BASE, exist_ok=True)
        f.save(tmp_zip)
        try:
            with zipfile.ZipFile(tmp_zip, 'r') as zip_ref:
                zip_ref.extractall(cloner.models_dir)
            try:
                os.remove(tmp_zip)
            except Exception:
                pass
            return jsonify({
                "status": "extracted",
                "message": "Extracted model folder structure successfully!",
                "models": cloner.list_models()
            })
        except Exception as zip_err:
            return jsonify({"error": f"Failed to extract zip model archive: {zip_err}"}), 500

    # Audio file upload → Auto-clone voice into .pth and .index files
    if ext in AUDIO_EXTS:
        tmp_dir = os.path.join(TEMP_BASE, "audio_clones")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_audio_path = os.path.join(tmp_dir, f"upload_{uuid.uuid4().hex[:8]}{ext}")
        f.save(tmp_audio_path)

        try:
            model_base = os.path.splitext(filename)[0]
            gender = request.form.get("gender", "auto")
            res = cloner.clone_voice_from_audio(tmp_audio_path, model_base, gender=gender)
            try:
                os.remove(tmp_audio_path)
            except Exception:
                pass
            return jsonify({
                "status": "cloned",
                "message": f"Voice cloned successfully from audio! Created {res['pth_file']} ({res['gender']})",
                "filename": res["pth_file"],
                "gender": res["gender"],
                "models": cloner.list_models()
            })
        except Exception as err:
            try:
                os.remove(tmp_audio_path)
            except Exception:
                pass
            return jsonify({"error": f"Audio voice cloning failed: {err}"}), 500

    # Direct .pth or .index file upload
    saved_path = cloner.save_model_file(f, filename)
    return jsonify({"status": "success", "filename": filename, "path": saved_path, "models": cloner.list_models()})



@app.route("/api/delete_rvc_model", methods=["POST"])
def delete_rvc_model():
    """Delete an installed RVC model (.pth) and its paired .index file if present."""
    from rvc_cloner import RVCVoiceCloner
    data = request.json or {}
    filename = os.path.basename(data.get("filename", ""))
    if not filename or not filename.lower().endswith(".pth"):
        return jsonify({"error": "Invalid filename. Must be a .pth file."}), 400

    cloner = RVCVoiceCloner()
    target_path = os.path.join(cloner.models_dir, filename)

    if not os.path.exists(target_path):
        return jsonify({"error": f"Model file not found: {filename}"}), 404

    try:
        os.remove(target_path)
        # Remove paired .index file if it exists
        base_name = os.path.splitext(filename)[0]
        for f_other in list(os.listdir(cloner.models_dir)):
            if f_other.lower().endswith(".index") and base_name.lower() in f_other.lower():
                try:
                    os.remove(os.path.join(cloner.models_dir, f_other))
                except Exception:
                    pass
        return jsonify({"status": "deleted", "filename": filename, "models": cloner.list_models()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/rename_rvc_model", methods=["POST"])
def rename_rvc_model():
    """Rename an installed RVC model (.pth) and its paired .index file."""
    from rvc_cloner import RVCVoiceCloner
    data = request.json or {}
    old_filename = os.path.basename(data.get("old_filename", ""))
    new_filename = os.path.basename(data.get("new_filename", ""))

    if not old_filename or not old_filename.lower().endswith(".pth"):
        return jsonify({"error": "Invalid old filename. Must be a .pth file."}), 400
    if not new_filename or not new_filename.lower().endswith(".pth"):
        return jsonify({"error": "Invalid new filename. Must be a .pth file."}), 400
    if old_filename == new_filename:
        cloner = RVCVoiceCloner()
        return jsonify({"status": "renamed", "models": cloner.list_models()})

    cloner = RVCVoiceCloner()
    old_path = os.path.join(cloner.models_dir, old_filename)
    new_path = os.path.join(cloner.models_dir, new_filename)

    if not os.path.exists(old_path):
        return jsonify({"error": f"Model not found: {old_filename}"}), 404
    if os.path.exists(new_path):
        return jsonify({"error": f"A model named '{new_filename}' already exists."}), 409

    try:
        os.rename(old_path, new_path)
        # Rename paired .index file if present
        old_base = os.path.splitext(old_filename)[0]
        new_base = os.path.splitext(new_filename)[0]
        for f_other in list(os.listdir(cloner.models_dir)):
            if f_other.lower().endswith(".index") and old_base.lower() in f_other.lower():
                old_idx = os.path.join(cloner.models_dir, f_other)
                new_idx = os.path.join(cloner.models_dir, f_other.replace(old_base, new_base, 1))
                try:
                    os.rename(old_idx, new_idx)
                except Exception:
                    pass
        return jsonify({"status": "renamed", "old_filename": old_filename, "new_filename": new_filename, "models": cloner.list_models()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/set_rvc_model_gender", methods=["POST"])
def set_rvc_model_gender():
    """Tag or retag an installed RVC model with a gender ('Male'/'Female'), used for Auto Gender Match RVC."""
    from rvc_cloner import RVCVoiceCloner
    data = request.json or {}
    filename = os.path.basename(data.get("filename", ""))
    gender = data.get("gender", "")

    if not filename or not filename.lower().endswith(".pth"):
        return jsonify({"error": "Invalid filename. Must be a .pth file."}), 400
    if str(gender).strip().lower() not in ("male", "female"):
        return jsonify({"error": "Gender must be 'Male' or 'Female'."}), 400

    cloner = RVCVoiceCloner()
    try:
        resolved_gender = cloner.set_model_gender(filename, gender)
        return jsonify({"status": "tagged", "filename": filename, "gender": resolved_gender, "models": cloner.list_models()})
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500



def process_dubbing_task(job_id, video_path, target_lang, voice_id, ducking_level, burn_subtitles, whisper_model, vocal_mode="remove", custom_output_dir=None, custom_segments=None, custom_edits=None, logo_file_path=None, gemini_api_key=None, gemini_model="gemini-2.0-flash", groq_api_key=None, deepseek_api_key=None, openrouter_api_key=None, openai_api_key=None, rvc_model=None, rvc_pitch=0, primary_ai_model="gemini"):
    job = JOBS[job_id]
    job.status = "processing"
    
    job_out_dir = os.path.join(OUTPUT_DIR, job_id)
    temp_dir = os.path.join(job_out_dir, "temp")
    os.makedirs(job_out_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    engine = VideoDubberEngine(progress_callback=job.update)

    try:
        extracted_audio_path = os.path.join(temp_dir, "original_audio.wav")
        extracted_stereo_path = os.path.join(temp_dir, "original_stereo.wav")

        if not os.path.exists(extracted_audio_path) or not os.path.exists(extracted_stereo_path):
            engine.extract_all_audio_tracks(video_path, extracted_audio_path, extracted_stereo_path)
        
        video_duration = engine.get_media_duration(video_path)

        if custom_segments:
            translated_segments = custom_segments
            detected_lang = "auto"
        else:
            # Step 2: Auto-Transcribe with Whisper
            segments, detected_lang = engine.transcribe(
                extracted_audio_path,
                model_name=whisper_model,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                groq_api_key=groq_api_key
            )
            # Step 3: LLM Story Translation (Gemini first by default → DeepSeek → Groq → GoogleTranslator fallback)
            translated_segments, _ = engine.translate_segments(
                segments,
                target_lang=target_lang,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                groq_api_key=groq_api_key,
                deepseek_api_key=deepseek_api_key,
                openrouter_api_key=openrouter_api_key,
                openai_api_key=openai_api_key,
                primary_ai_model=primary_ai_model
            )


        # Save transcript JSON & check if segments were modified by user
        transcript_json_path = os.path.join(job_out_dir, "transcript.json")
        segments_modified = False
        if custom_segments and os.path.exists(transcript_json_path):
            try:
                with open(transcript_json_path, "r", encoding="utf-8") as f:
                    old_segs = json.load(f)
                if json.dumps(old_segs, sort_keys=True) != json.dumps(custom_segments, sort_keys=True):
                    segments_modified = True
            except Exception:
                segments_modified = True
        elif custom_segments:
            segments_modified = True

        with open(transcript_json_path, "w", encoding="utf-8") as f:
            json.dump(translated_segments, f, ensure_ascii=False, indent=2)

        # Step 4 & 5: Synthesize TTS & RVC Voice Cloning (reuse if already generated in transcript pass)
        if not voice_id:
            voice_id = "auto"

        dubbed_speech_path = os.path.join(job_out_dir, "dubbed_speech.wav")

        if os.path.exists(dubbed_speech_path) and os.path.getsize(dubbed_speech_path) > 1000 and not segments_modified:
            engine.log("tts_synthesis", 75, "Reusing existing voice-cloned speech track from transcript pass (skipping duplicate RVC pass)...")
        else:
            tts_clips = engine.synthesize_all_tts(
                translated_segments, voice_id, temp_dir,
                audio_path_for_gender=extracted_audio_path,
                target_lang=target_lang,
                rvc_model=rvc_model,
                rvc_pitch=rvc_pitch
            )
            # Step 5: Audio Speed & Timestamp Alignment
            engine.align_and_combine_speech(translated_segments, tts_clips, video_duration, dubbed_speech_path, temp_dir)

        # Step 6: Process Original Audio (Vocal Removal / Ducking / Mute)
        bgm_processed_path = os.path.join(temp_dir, "bgm_processed.wav")
        saved_bgm_output = os.path.join(job_out_dir, "bgm_audio.wav")

        if os.path.exists(saved_bgm_output) and os.path.getsize(saved_bgm_output) > 1000:
            engine.log("vocal_isolation", 88, "Reusing isolated BGM track from transcript pass (0s - skipping duplicate AI vocal removal)...")
            shutil.copy2(saved_bgm_output, bgm_processed_path)
        else:
            engine.process_background_audio(
                extracted_stereo_path, vocal_mode=vocal_mode,
                duck_level=ducking_level, output_bgm_path=bgm_processed_path,
                temp_dir=temp_dir
            )
            try:
                shutil.copy2(bgm_processed_path, saved_bgm_output)
            except Exception:
                pass

        # Step 7: Export Subtitles
        srt_path = os.path.join(job_out_dir, "subtitles.srt")
        engine.export_srt(translated_segments, srt_path)

        # Step 8: Final Video Re-encoding & Merging
        # Always use render_edited_video so Editor Lab settings (subtitles, blur, text, logo) are applied.
        sub_enabled = False
        if custom_edits and "subtitles" in custom_edits:
            sub_enabled = bool(custom_edits["subtitles"].get("enabled", False))
        elif burn_subtitles:
            sub_enabled = True

        if not custom_edits:
            custom_edits = {"subtitles": {"enabled": sub_enabled}}
        else:
            if "subtitles" not in custom_edits:
                custom_edits["subtitles"] = {}
            custom_edits["subtitles"]["enabled"] = sub_enabled

        output_video_path = os.path.join(job_out_dir, "dubbed_video.mp4")
        engine.render_edited_video(
            video_path, dubbed_speech_path, bgm_processed_path, output_video_path,
            srt_path=srt_path, custom_edits=custom_edits, logo_file_path=logo_file_path
        )

        # Copy outputs to custom user directory if specified
        orig_base = getattr(job, "original_base", "dubbed") or "dubbed"
        out_video_name = f"{orig_base}_dubbed.mp4"
        out_srt_name = f"{orig_base}_dubbed.srt"

        copied_custom_path = None
        cfg = load_user_config()
        save_srt_enabled = cfg.get("save_srt", True)
        if custom_output_dir:
            try:
                os.makedirs(custom_output_dir, exist_ok=True)
                custom_file_path = os.path.join(custom_output_dir, out_video_name)
                shutil.copy2(output_video_path, custom_file_path)
                if save_srt_enabled and os.path.exists(srt_path):
                    shutil.copy2(srt_path, os.path.join(custom_output_dir, out_srt_name))
                copied_custom_path = custom_file_path
                engine.log("merge_video", 98, f"Copied output files to custom folder: {custom_output_dir}")
            except Exception as e:
                print(f"Warning: Could not copy to custom output directory '{custom_output_dir}': {e}")

        # Derive the detected gender from the resolved voice_id
        detected_gender = "Female"  # safe default
        for _v in SUPPORTED_LANGUAGES.get(target_lang, {}).get("voices", []):
            if _v["id"] == voice_id:
                detected_gender = _v.get("gender", "Female")
                break

        # Stamp each segment with the detected gender so the UI pill initialises correctly
        for seg in translated_segments:
            if not seg.get("gender"):
                seg["gender"] = detected_gender

        job.result_data = {
            "job_id": job_id,
            "original_base": orig_base,
            "out_video_name": out_video_name,
            "out_srt_name": out_srt_name,
            "detected_lang": detected_lang,
            "target_lang": target_lang,
            "voice_id": voice_id,
            "detected_gender": detected_gender,
            "vocal_mode": vocal_mode,
            "video_duration": round(video_duration, 2),
            "video_url": f"/outputs/{job_id}/dubbed_video.mp4",
            "original_audio_url": f"/outputs/{job_id}/temp/original_audio.wav",
            "dubbed_audio_url": f"/outputs/{job_id}/dubbed_speech.wav",
            "srt_url": f"/outputs/{job_id}/subtitles.srt",
            "segments": translated_segments
        }


        job.status = "completed"
        job.update({"step": "completed", "progress": 100, "message": "Dubbing complete!"})

        # Auto-remove the internal outputs/<job_id> working folder now that the
        # final video (and .srt, if enabled) are safely copied to the user's
        # chosen save folder. This is only done when the copy above actually
        # succeeded, so a failed copy never results in losing the only copy
        # of the render. In-app preview/download for this job will no longer
        # be available afterward — the finished files live in the custom
        # save folder instead.
        if copied_custom_path and os.path.exists(job_out_dir):
            try:
                shutil.rmtree(job_out_dir, ignore_errors=True)
                print(f"[Cleanup] Auto-deleted output folder for job {job_id}: {job_out_dir}")
            except Exception as e:
                print(f"Warning: Could not auto-delete output folder '{job_out_dir}': {e}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        job.status = "failed"
        job.error = str(e)
        job.update({"step": "error", "progress": 0, "message": f"Error: {str(e)}"})

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/api/voices")
def get_voices():
    return jsonify({
        "languages": SUPPORTED_LANGUAGES
    })

@app.route("/api/fonts")
def get_fonts():
    """List real installed fonts (bundled + Windows Fonts folders), scanned by
    reading each file's actual name table — not a hardcoded guess list. The
    frontend uses these exact {name, path} entries to build both its font
    dropdown and a dynamic @font-face for the preview, and sends the chosen
    path back with the render request so ffmpeg burns in the identical file."""
    try:
        return jsonify({"fonts": font_manager.scan_fonts()})
    except Exception as e:
        return jsonify({"fonts": [], "error": str(e)}), 500

@app.route("/api/font-file")
def get_font_file():
    """Serve the raw bytes of one font file so the browser preview can register
    a @font-face pointing at the EXACT same file ffmpeg/Pillow will use for the burn-in.
    Only paths that came back from font_manager.scan_fonts() are servable."""
    raw_path = request.args.get("path", "")
    if not raw_path:
        return jsonify({"error": "No path provided"}), 400
    req_path = os.path.normpath(raw_path)
    allowed = {os.path.normpath(f["path"]) for f in font_manager.scan_fonts()}

    # Also allow any file in static/fonts or system Windows font folders
    if req_path not in allowed:
        base_fonts_dir = os.path.normpath(os.path.join(BASE_DIR, "static", "fonts"))
        win_fonts_1 = os.path.normpath(r"C:\Windows\Fonts")
        win_fonts_2 = os.path.normpath(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"))
        if not (req_path.startswith(base_fonts_dir) or req_path.startswith(win_fonts_1) or req_path.startswith(win_fonts_2)):
            return jsonify({"error": "Unknown font path"}), 404

    if not os.path.exists(req_path):
        return jsonify({"error": "Font file not found on disk"}), 404

    ext = os.path.splitext(req_path)[1].lower()
    mimetype = "font/ttf" if ext == ".ttf" else ("font/otf" if ext == ".otf" else "font/collection")
    resp = send_file(req_path, mimetype=mimetype, conditional=True)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp

global_engine = VideoDubberEngine()

@app.route("/api/preview_overlay", methods=["POST"])
def preview_overlay():
    """Generate 100% bit-for-bit identical C# SkiaSharp PNG subtitle overlay for live browser preview.

    Accepts a ``sub_cfg`` dict and canvas dimensions then delegates to the unified
    ``engine.process_preview_and_render()`` pipeline so preview and export settings
    are always derived from the same ``PreviewRenderConfig`` object.
    """
    try:
        data = request.json or {}
        text = data.get("text", "")
        sub_cfg = data.get("sub_cfg", {})
        width = int(data.get("width", 1080))
        height = int(data.get("height", 1920))

        # Build a typed config from the incoming sub_cfg dict
        config = PreviewRenderConfig.from_custom_edits(
            {"subtitles": sub_cfg}, width=width, height=height
        )

        tmp_filename = f"live_preview_{uuid.uuid4().hex[:8]}.png"
        tmp_png_path = os.path.join(UPLOAD_DIR, tmp_filename)

        result = global_engine.process_preview_and_render(
            config=config,
            text=text,
            output_png_path=tmp_png_path,
        )

        if result["ok"] and result.get("png_path") and os.path.exists(result["png_path"]):
            with open(result["png_path"], "rb") as f:
                b64_data = base64.b64encode(f.read()).decode('utf-8')
            try:
                os.remove(result["png_path"])
            except Exception:
                pass
            return jsonify({"ok": True, "image": f"data:image/png;base64,{b64_data}"})

        return jsonify({"error": result.get("error", "Failed to render PNG")}), 500
    except Exception as e:
        print(f"Preview overlay error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/import_srt", methods=["POST"])
def import_srt():
    """Import an external .srt file, parse subtitle segments, and update/create current job state."""
    file = request.files.get("srt_file")
    if not file or not file.filename:
        return jsonify({"error": "No SRT file provided"}), 400

    job_id = request.form.get("job_id") or str(uuid.uuid4())
    job_out_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(job_out_dir, exist_ok=True)

    srt_path = os.path.join(job_out_dir, "subtitles.srt")
    file.save(srt_path)

    engine = VideoDubberEngine()
    segments = engine._parse_srt_file(srt_path)

    if not segments:
        return jsonify({"error": "Failed to parse SRT file or file is empty"}), 400

    formatted_segs = []
    for idx, seg in enumerate(segments, start=1):
        formatted_segs.append({
            "id": idx,
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "original_text": seg["text"],
            "translated_text": seg["text"]
        })

    if job_id not in JOBS:
        job = JobTracker(job_id)
        job.status = "completed"
        JOBS[job_id] = job
    else:
        job = JOBS[job_id]

    if not job.result_data:
        job.result_data = {}

    job.result_data["segments"] = formatted_segs
    job.result_data["job_id"] = job_id
    if "original_base" not in job.result_data:
        raw_name = os.path.splitext(file.filename)[0]
        job.result_data["original_base"] = raw_name
        job.original_base = raw_name

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "segments": formatted_segs,
        "srt_url": f"/outputs/{job_id}/subtitles.srt"
    })

@app.route("/api/preview_voice", methods=["POST"])
def preview_voice():
    """Generate a 2-second audio preview of a chosen EdgeTTS voice or RVC model."""
    try:
        data = request.json or {}
        voice_id = data.get("voice_id", "km-KH-PisethNeural")
        target_lang = data.get("target_lang", "km")
        gender = data.get("gender", "Female")
        rvc_model = data.get("rvc_model", "none")
        rvc_pitch = int(data.get("rvc_pitch", 0))
        sample_text = data.get("text", "").strip()

        if not sample_text:
            if target_lang == "km":
                sample_text = "សួរស្តី!! នេះគីជាការតេស្តសំឡេងរបស់ម៉ូឌែល ដែលអ្នកបានជ្រើសរើស សូមអរគុណ。"
            else:
                sample_text = "Hello! This is a test of the selected voice."

        # Auto-detect male gender when previewing male RVC models (Sengkea, Mengly, Polyratanak)
        if rvc_model and rvc_model != "none":
            m_lower = rvc_model.lower()
            if any(k in m_lower for k in ["sengkea", "mengly", "polyratanak", "male", "man"]):
                gender = "Male"

        # Resolve voice ID if set to auto
        if voice_id == "auto" or not voice_id:
            lang_voices = SUPPORTED_LANGUAGES.get(target_lang, {}).get("voices", [])
            matched = [v for v in lang_voices if v.get("gender", "").lower() == gender.lower()]
            voice_id = matched[0]["id"] if matched else (lang_voices[0]["id"] if lang_voices else "km-KH-PisethNeural")


        tmp_dir = os.path.join(TEMP_BASE, "voice_previews")
        os.makedirs(tmp_dir, exist_ok=True)
        raw_mp3 = os.path.join(tmp_dir, f"preview_{uuid.uuid4().hex[:8]}.mp3")
        final_wav = os.path.join(tmp_dir, f"preview_{uuid.uuid4().hex[:8]}.wav")

        # Synthesize via EdgeTTS
        async def _gen():
            communicate = edge_tts.Communicate(sample_text, voice_id)
            await communicate.save(raw_mp3)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_gen())
        loop.close()

        output_audio = raw_mp3

        # Apply RVC Voice Conversion if enabled
        if rvc_model and rvc_model != "none":
            from rvc_cloner import RVCVoiceCloner
            cloner = RVCVoiceCloner()
            output_audio = cloner.convert_clip(raw_mp3, final_wav, rvc_model, pitch_shift=rvc_pitch)

        with open(output_audio, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")

        for p in [raw_mp3, final_wav]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        mime_type = "audio/wav" if output_audio.endswith(".wav") else "audio/mp3"
        return jsonify({"ok": True, "audio": f"data:{mime_type};base64,{audio_b64}"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/preview_rvc_with_sample", methods=["POST"])
def preview_rvc_with_sample():
    """
    Preview an RVC voice model. Serves the authentic real model reference audio sample
    if available. Otherwise converts sample text through the model embedding.
    """
    try:
        data = request.json or {}
        rvc_model = os.path.basename(data.get("rvc_model", ""))
        rvc_pitch = int(data.get("rvc_pitch", 0))

        if not rvc_model or rvc_model == "none":
            return jsonify({"error": "No RVC model specified"}), 400

        from rvc_cloner import RVCVoiceCloner
        cloner = RVCVoiceCloner()

        # Check if authentic real reference audio sample clip exists for this model
        sample_audio = cloner.get_model_sample_audio(rvc_model)
        if sample_audio and os.path.exists(sample_audio):
            with open(sample_audio, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")
            mime_type = "audio/wav" if sample_audio.endswith(".wav") else "audio/mp3"
            return jsonify({"ok": True, "audio": f"data:{mime_type};base64,{audio_b64}", "source": "real_model_sample"})

        sample_text = "សួរស្តី!! នេះគីជាការតេស្តសំឡេងរបស់ម៉ូឌែល ដែលអ្នកបានជ្រើសរើស សូមអរគុណ。"

        models = cloner.list_models()
        target_model = next((m for m in models if m["filename"].lower() == rvc_model.lower()), None)
        model_gender = (target_model.get("gender") if target_model else "Female") or "Female"

        base_voice = "km-KH-SreymomNeural" if model_gender == "Female" else "km-KH-PisethNeural"

        tmp_dir = os.path.join(TEMP_BASE, "voice_previews")
        os.makedirs(tmp_dir, exist_ok=True)
        raw_mp3 = os.path.join(tmp_dir, f"rvc_raw_{uuid.uuid4().hex[:8]}.mp3")
        out_wav = os.path.join(tmp_dir, f"rvc_sample_{uuid.uuid4().hex[:8]}.wav")

        async def _gen():
            communicate = edge_tts.Communicate(sample_text, base_voice)
            await communicate.save(raw_mp3)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_gen())
        loop.close()

        output_audio = cloner.convert_clip(raw_mp3, out_wav, rvc_model, pitch_shift=rvc_pitch)

        with open(output_audio, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")

        for p in [raw_mp3, out_wav]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        return jsonify({"ok": True, "audio": f"data:audio/wav;base64,{audio_b64}"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500




@app.route("/api/get_duration", methods=["POST"])
def get_video_duration():
    """Get actual media duration in seconds for a local video file with multi-tier fallback."""
    try:
        data = request.json or {}
        video_path = data.get("video_path", "").strip()
        if video_path:
            norm_path = os.path.normpath(os.path.abspath(video_path))
            if os.path.exists(norm_path):
                dur = engine.get_media_duration(norm_path)
                if dur and float(dur) > 0:
                    return jsonify({"status": "success", "duration": float(dur)})
    except Exception as e:
        logger.warning(f"Failed to get video duration: {e}")
    return jsonify({"status": "error", "duration": 0})

@app.route("/api/detect_captions_region", methods=["POST"])
def api_detect_captions_region():
    """Detect original hardcoded caption/subtitle bounding box region using OpenCV computer vision."""
    try:
        file_path = ""
        tmp_file = None

        # Handle both JSON (file_path string) and multipart/form-data (file upload)
        ct = request.content_type or ""
        if "application/json" in ct:
            data = request.get_json(silent=True) or {}
            file_path = data.get("file_path", "").strip()
        elif "multipart/form-data" in ct or "application/x-www-form-urlencoded" in ct:
            file_path = (request.form.get("file_path") or "").strip()
            uploaded = request.files.get("video_file")
            if uploaded and not file_path:
                import tempfile
                suffix = os.path.splitext(uploaded.filename or ".mp4")[1] or ".mp4"
                tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                uploaded.save(tmp_file.name)
                tmp_file.close()
                file_path = tmp_file.name
        else:
            # Try JSON fallback silently for any other content type
            data = request.get_json(silent=True, force=True) or {}
            file_path = data.get("file_path", "").strip()

        if file_path:
            norm_path = os.path.normpath(os.path.abspath(file_path))
            if os.path.exists(norm_path):
                from dubbing_engine import VideoDubberEngine
                res = VideoDubberEngine().detect_caption_region(norm_path)
                res["success"] = True
                # Clean up temp file if created from upload
                if tmp_file:
                    try: os.unlink(tmp_file.name)
                    except Exception: pass
                return jsonify(res)
    except Exception as e:
        print(f"api_detect_captions_region error: {e}")
    finally:
        if 'tmp_file' in locals() and tmp_file:
            try: os.unlink(tmp_file.name)
            except Exception: pass
    return jsonify({"success": False, "posY": 0.0, "height": 0.0, "posX": 0.0, "width": 100.0, "detected": False})



@app.route("/api/browse_folder", methods=["GET", "POST"])
def browse_folder():
    """Open a native Windows folder picker dialog via clean GUI subprocess."""
    try:
        cmd = [
            sys.executable, "-c",
            "import tkinter as tk, tkinter.filedialog as fd; root=tk.Tk(); root.withdraw(); root.attributes('-topmost', True); p=fd.askdirectory(title='Select Output Folder'); print(p)"
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=60)
        folder = res.stdout.strip()
        if folder:
            folder = os.path.normpath(folder)
            return jsonify({"folder": folder})
        return jsonify({"folder": ""})
    except Exception as e:
        print(f"Browse folder error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/open_output_folder", methods=["POST", "GET"])
def open_output_folder():
    """Open Windows File Explorer directly to the outputs folder."""
    try:
        data = request.json if request.is_json else (request.form or {})
        folder_path = data.get("folder_path", "").strip() or OUTPUT_DIR
        
        job_id = data.get("job_id", "").strip()
        if job_id:
            job_dir = os.path.join(OUTPUT_DIR, job_id)
            if os.path.exists(job_dir):
                folder_path = job_dir

        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)

        if sys.platform == "win32":
            os.startfile(folder_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", folder_path])
        else:
            subprocess.run(["xdg-open", folder_path])

        return jsonify({"ok": True, "folder_path": folder_path})
    except Exception as e:
        print(f"Error opening output folder: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/test_llm_key", methods=["POST"])
def test_llm_key():
    """Test live connection for DeepSeek AI or Groq AI API keys."""
    try:
        provider = request.form.get("provider", "").strip().lower()
        raw_key = request.form.get("api_key", "").strip()
        clean_key = re.sub(r'[^\w\-\._]', '', raw_key.strip())

        if not clean_key or len(clean_key) < 10:
            return jsonify({"valid": False, "message": "Invalid API Key format."}), 200

        if provider == "deepseek":
            url = "https://api.deepseek.com/chat/completions"
            payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": "Ping"}], "max_tokens": 1}
            data = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {clean_key}"}
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        return jsonify({"valid": True, "message": "DeepSeek AI Connected! (deepseek-chat Live ✓)"}), 200
            except urllib.error.HTTPError as he:
                if he.code == 402:
                    return jsonify({"valid": True, "message": "DeepSeek Key Valid! (Insufficient balance - add credits at platform.deepseek.com)"}), 200
                elif he.code in (401, 403):
                    return jsonify({"valid": False, "message": "DeepSeek: API Key rejected or invalid."}), 200
                else:
                    return jsonify({"valid": False, "message": f"DeepSeek: HTTP {he.code} - {he.reason}"}), 200
            except Exception as e:
                return jsonify({"valid": False, "message": f"DeepSeek connection failed: {str(e)}"}), 200

        elif provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "Ping"}], "max_tokens": 1}
            data = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {clean_key}", "User-Agent": "groq-python/0.11.0", "Accept": "application/json"}
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        return jsonify({"valid": True, "message": "Groq Cloud AI Connected! (Llama 3.3 70B Live ✓)"}), 200
            except urllib.error.HTTPError as he:
                if he.code == 429:
                    return jsonify({"valid": True, "message": "Groq Key Valid! (Rate-limited - App will auto-retry)"}), 200
                elif he.code in (401, 403):
                    return jsonify({"valid": False, "message": "Groq: API Key rejected or invalid."}), 200
                else:
                    return jsonify({"valid": False, "message": f"Groq: HTTP {he.code} - {he.reason}"}), 200
            except Exception as e:
                return jsonify({"valid": False, "message": f"Groq connection failed: {str(e)}"}), 200

        elif provider == "openrouter":
            url = "https://openrouter.ai/api/v1/chat/completions"
            payload = {"model": "qwen/qwen-2.5-72b-instruct:free", "messages": [{"role": "user", "content": "Ping"}], "max_tokens": 1}
            data = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {clean_key}", "HTTP-Referer": "https://videodubber.studio"}
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        return jsonify({"valid": True, "message": "OpenRouter AI Connected! (50+ Free AI Models Live ✓)"}), 200
            except urllib.error.HTTPError as he:
                if he.code == 429:
                    return jsonify({"valid": True, "message": "OpenRouter Key Valid! (Rate-limited)"}), 200
                elif he.code in (401, 403):
                    return jsonify({"valid": False, "message": "OpenRouter: API Key rejected or invalid."}), 200
                else:
                    return jsonify({"valid": False, "message": f"OpenRouter: HTTP {he.code} - {he.reason}"}), 200
            except Exception as e:
                return jsonify({"valid": False, "message": f"OpenRouter connection failed: {str(e)}"}), 200

        elif provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Ping"}], "max_tokens": 1}
            data = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {clean_key}"}
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        return jsonify({"valid": True, "message": "OpenAI ChatGPT Connected! (gpt-4o-mini Live ✓)"}), 200
            except urllib.error.HTTPError as he:
                if he.code == 429:
                    return jsonify({"valid": True, "message": "OpenAI Key Valid! (Rate-limited / Quota limit)"}), 200
                elif he.code in (401, 403):
                    return jsonify({"valid": False, "message": "OpenAI ChatGPT: API Key rejected or invalid."}), 200
                else:
                    return jsonify({"valid": False, "message": f"OpenAI: HTTP {he.code} - {he.reason}"}), 200
            except Exception as e:
                return jsonify({"valid": False, "message": f"OpenAI connection failed: {str(e)}"}), 200

        return jsonify({"valid": False, "message": "Unknown provider. Supported: gemini, deepseek, groq, openrouter, openai."}), 200
    except Exception as outer_e:
        return jsonify({"valid": False, "message": f"Server error: {str(outer_e)}"}), 200

@app.route("/api/test_gemini_key", methods=["POST"])
def test_gemini_key():
    """Test live connection to Google Gemini API with automatic model failover."""
    try:
        raw_key = request.form.get("api_key", "").strip() or (request.json.get("api_key", "").strip() if request.is_json else "")
        model_name = request.form.get("model_name", "gemini-2.0-flash").strip()

        # Split multi-key pool by comma, semicolon, space, or newline
        raw_keys = re.split(r'[,\s;\n]+', str(raw_key))
        keys = []
        for k in raw_keys:
            ck = re.sub(r'[^\w\-\._]', '', k.strip())
            if len(ck) >= 10 and ck not in keys:
                keys.append(ck)

        if not keys:
            return jsonify({"valid": False, "message": "Invalid API Key format. Please paste your Google Gemini API Key."}), 200

        # Candidate models to try in sequence if requested model yields 404
        candidate_models = [model_name]
        for m in ["gemini-2.0-flash", "gemini-2.0-flash-lite"]:
            if m not in candidate_models:
                candidate_models.append(m)

        valid_keys_count = 0
        rate_limited_count = 0
        last_error = ""
        working_model = "gemini-2.0-flash"

        payload = {"contents": [{"parts": [{"text": "Ping"}]}]}
        data = json.dumps(payload).encode("utf-8")

        for idx, api_key in enumerate(keys, start=1):
            key_valid = False

            for test_model in candidate_models:
                base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{test_model}:generateContent"
                
                # Try standard ?key= param first
                try:
                    url = f"{base_url}?key={api_key}"
                    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        if resp.status == 200:
                            valid_keys_count += 1
                            key_valid = True
                            working_model = test_model
                            break
                except urllib.error.HTTPError as he:
                    if he.code == 429:
                        rate_limited_count += 1
                        valid_keys_count += 1  # 429 = authentic key with quota limit
                        key_valid = True
                        working_model = test_model
                        break
                    elif he.code in (404, 400):
                        # Model not supported on this endpoint -> try next candidate model
                        try:
                            err_body = he.read().decode('utf-8', errors='ignore')
                            err_json = json.loads(err_body)
                            last_error = err_json.get("error", {}).get("message", f"Model {test_model} not found.")
                        except Exception:
                            last_error = f"HTTP {he.code}: Model {test_model} not found"
                        continue
                    elif he.code in (401, 403):
                        # Try Bearer token fallback for this model
                        try:
                            req_b = urllib.request.Request(base_url, data=data, headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {api_key}"
                            })
                            with urllib.request.urlopen(req_b, timeout=8) as resp_b:
                                if resp_b.status == 200:
                                    valid_keys_count += 1
                                    key_valid = True
                                    working_model = test_model
                                    break
                        except urllib.error.HTTPError as he2:
                            if he2.code == 429:
                                rate_limited_count += 1
                                valid_keys_count += 1
                                key_valid = True
                                working_model = test_model
                                break
                            elif he2.code in (404, 400):
                                continue
                            else:
                                last_error = f"HTTP {he2.code}: Key rejected by Google"
                                break
                        except Exception as e:
                            last_error = str(e)
                            break
                    else:
                        last_error = f"HTTP {he.code}: {he.reason}"
                        break
                except Exception as e:
                    last_error = str(e)
                    break

        if valid_keys_count > 0:
            if len(keys) == 1:
                if rate_limited_count > 0:
                    return jsonify({"valid": True, "message": f"Gemini Key Valid! ({working_model} Rate-Limited 429 - App will auto-rotate)"}), 200
                return jsonify({"valid": True, "message": f"Gemini Connected! ({working_model} Live)"}), 200
            else:
                return jsonify({"valid": True, "message": f"Gemini Pool Connected! ({valid_keys_count}/{len(keys)} Keys Active & Valid)"}), 200

        return jsonify({"valid": False, "message": f"Connection failed: {last_error or 'Invalid API Key'}"}), 200
    except Exception as outer_e:
        return jsonify({"valid": False, "message": f"Server error: {str(outer_e)}"}), 200

@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/api/transcribe_only", methods=["POST"])
def transcribe_only():
    if "video_file" not in request.files:
        return jsonify({"error": "No video file provided"}), 400
        
    file = request.files["video_file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
        
    target_lang = request.form.get("target_lang", "km")
    whisper_model = request.form.get("whisper_model", "base")
    voice_id = request.form.get("voice_id", "auto")
    is_recap = request.form.get("is_recap", "false").lower() == "true"
    recap_style = request.form.get("recap_style", "dramatic")
    gemini_api_key = request.form.get("gemini_api_key", "").strip() or None
    gemini_model = request.form.get("gemini_model", "gemini-2.0-flash").strip()
    groq_api_key = request.form.get("groq_api_key", "").strip() or None
    deepseek_api_key = request.form.get("deepseek_api_key", "").strip() or None
    openrouter_api_key = request.form.get("openrouter_api_key", "").strip() or None
    openai_api_key = request.form.get("openai_api_key", "").strip() or None
    intro_speech = request.form.get("intro_speech", "").strip() or None
    outro_speech = request.form.get("outro_speech", "").strip() or None
    rvc_model = request.form.get("rvc_model", "none").strip()
    rvc_pitch = request.form.get("rvc_pitch", "0").strip()
    vocal_mode = request.form.get("vocal_mode", "remove").strip()
    primary_ai_model = request.form.get("primary_ai_model", "").strip() or load_user_config().get("primary_ai_model", "gemini")

    job_id = str(uuid.uuid4())
    raw_base = os.path.splitext(os.path.basename(file.filename))[0].strip()
    orig_base = raw_base if raw_base else f"video_{job_id[:8]}"
    ext = os.path.splitext(file.filename)[1] or ".mp4"
    saved_video_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
    file.save(saved_video_path)

    job = JobTracker(job_id)
    job.original_base = orig_base
    job.video_path = saved_video_path
    job.rvc_model = rvc_model
    job.rvc_pitch = rvc_pitch
    JOBS[job_id] = job


    def run_transcribe_task():
        job.status = "processing"
        job_out_dir = os.path.join(OUTPUT_DIR, job_id)
        temp_dir = os.path.join(job_out_dir, "temp")
        os.makedirs(job_out_dir, exist_ok=True)
        os.makedirs(temp_dir, exist_ok=True)

        engine = VideoDubberEngine(progress_callback=job.update)
        try:
            # Step 1: Extract Audio
            job.update({"step": "extract_audio", "progress": 10, "message": "Extracting audio from video..."})
            extracted_audio_path = os.path.join(temp_dir, "original_audio.wav")
            extracted_stereo_path = os.path.join(temp_dir, "original_stereo.wav")
            engine.extract_audio(saved_video_path, extracted_audio_path)
            engine.extract_stereo_audio(saved_video_path, extracted_stereo_path)
            video_duration = engine.get_media_duration(saved_video_path)
            job.update({"step": "extract_audio", "progress": 25, "message": "Audio extracted successfully!"})

            # Step 2: Speech Recognition (Groq AI, Whisper AI or Gemini Audio AI)
            model_msg = "Groq Cloud Whisper-Large-v3 AI" if "groq" in str(whisper_model).lower() else ("Google Gemini Audio AI" if str(whisper_model).startswith("gemini") else f"Whisper AI ({whisper_model})")
            job.update({"step": "transcribe", "progress": 30, "message": f"Running Speech Recognition ({model_msg})..."})
            segments, detected_lang = engine.transcribe(
                extracted_audio_path,
                model_name=whisper_model,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                groq_api_key=groq_api_key
            )
            job.update({"step": "transcribe", "progress": 55, "message": f"Transcribed {len(segments)} segments (lang: {detected_lang})"})

            # Step 3: Translation / Movie Recap
            job.update({"step": "translate", "progress": 60, "message": f"Translating to {target_lang}..."})
            translated_segments, _ = engine.translate_segments(
                segments,
                target_lang=target_lang,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                groq_api_key=groq_api_key,
                deepseek_api_key=deepseek_api_key,
                openrouter_api_key=openrouter_api_key,
                openai_api_key=openai_api_key,
                primary_ai_model=primary_ai_model
            )


            if is_recap:
                job.update({"step": "translate", "progress": 70, "message": "Generating AI Movie Recap script with LLM..."})
                translated_segments = engine.generate_movie_recap_script(
                    segments=translated_segments,
                    video_duration=video_duration,
                    target_lang=target_lang,
                    style=recap_style,
                    gemini_api_key=gemini_api_key,
                    gemini_model=gemini_model,
                    deepseek_api_key=deepseek_api_key,
                    groq_api_key=groq_api_key,
                    intro_speech=intro_speech,
                    outro_speech=outro_speech
                )

            job.update({"step": "translate", "progress": 75, "message": f"Translation complete ({len(translated_segments)} segments)"})

            # Step 4: Synthesize Neural Voice Dubbing & Align Audio Track
            job.update({"step": "tts_synthesis", "progress": 80, "message": f"Synthesizing Neural Voice dubbing clips ({voice_id or 'auto'})..."})
            tts_clips = engine.synthesize_all_tts(
                translated_segments, voice_id or "auto", temp_dir,
                audio_path_for_gender=extracted_audio_path,
                target_lang=target_lang,
                recap_style=recap_style if is_recap else "standard",
                rvc_model=rvc_model,
                rvc_pitch=rvc_pitch
            )

            dubbed_speech_path = os.path.join(job_out_dir, "dubbed_speech.wav")
            engine.align_and_combine_speech(translated_segments, tts_clips, video_duration, dubbed_speech_path, temp_dir, is_recap=is_recap)

            # Export SRT Subtitles
            srt_path = os.path.join(job_out_dir, "subtitles.srt")
            engine.export_srt(translated_segments, srt_path)

            # Process & isolate BGM track for live preview & final render reuse
            saved_bgm_output = os.path.join(job_out_dir, "bgm_audio.wav")
            if not os.path.exists(saved_bgm_output):
                engine.process_background_audio(
                    extracted_stereo_path, vocal_mode=vocal_mode,
                    duck_level=0.15, output_bgm_path=saved_bgm_output,
                    temp_dir=temp_dir
                )

            job.result_data = {
                "job_id": job_id,
                "original_base": orig_base,
                "out_video_name": f"{orig_base}_dubbed.mp4",
                "out_srt_name": f"{orig_base}_dubbed.srt",
                "detected_lang": detected_lang,
                "target_lang": target_lang,
                "video_duration": round(video_duration, 2),
                "segments": translated_segments,
                "video_url": f"/uploads/{job_id}{ext}",
                "dubbed_audio_url": f"/outputs/{job_id}/dubbed_speech.wav",
                "bgm_url": f"/outputs/{job_id}/bgm_audio.wav",
                "srt_url": f"/outputs/{job_id}/subtitles.srt"
            }
            job.status = "transcribed"
            job.update({"step": "tts_synthesis", "progress": 100, "message": f"Dubbing complete! Ready to preview target voice."})
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.update({"step": "error", "progress": 0, "message": f"Transcription/Dubbing error: {str(e)}"})

    t = threading.Thread(target=run_transcribe_task)
    t.daemon = True
    t.start()

    return jsonify({"job_id": job_id})

@app.route("/api/generate_recap", methods=["POST"])
def generate_recap():
    """AI Movie Recap / Story Summary generation endpoint."""
    job_id = request.form.get("job_id", "").strip()
    target_lang = request.form.get("target_lang", "km")
    recap_style = request.form.get("recap_style", "dramatic")
    whisper_model = request.form.get("whisper_model", "base")
    gemini_api_key = request.form.get("gemini_api_key", "").strip() or (request.json.get("gemini_api_key", "").strip() if request.is_json else "") or None
    gemini_model = request.form.get("gemini_model", "gemini-2.0-flash").strip()
    groq_api_key = request.form.get("groq_api_key", "").strip() or None
    deepseek_api_key = request.form.get("deepseek_api_key", "").strip() or None
    custom_output_dir = request.form.get("output_path", "").strip() or None
    primary_ai_model = request.form.get("primary_ai_model", "").strip() or load_user_config().get("primary_ai_model", "gemini")

    job = JOBS.get(job_id) if job_id else None

    # Handle direct video_file upload if no pre-existing job exists
    if not job and "video_file" in request.files:
        file = request.files["video_file"]
        if file and file.filename != "":
            job_id = str(uuid.uuid4())
            raw_base = os.path.splitext(os.path.basename(file.filename))[0].strip()
            orig_base = raw_base if raw_base else f"video_{job_id[:8]}"
            ext = os.path.splitext(file.filename)[1] or ".mp4"
            saved_video_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
            file.save(saved_video_path)

            job = JobTracker(job_id)
            job.original_base = orig_base
            job.video_path = saved_video_path
            JOBS[job_id] = job

    if not job or not getattr(job, "video_path", None) or not os.path.exists(job.video_path):
        return jsonify({"error": "Video file not found or invalid job"}), 400

    def run_recap():
        try:
            job.status = "processing"
            engine = VideoDubberEngine(progress_callback=job.update)
            
            job_out_dir = os.path.join(OUTPUT_DIR, job_id)
            temp_dir = os.path.join(job_out_dir, "temp")
            os.makedirs(job_out_dir, exist_ok=True)
            os.makedirs(temp_dir, exist_ok=True)

            wav_path = os.path.join(temp_dir, "extracted.wav")

            if not os.path.exists(wav_path):
                engine.extract_audio(job.video_path, wav_path)

            v_duration = engine.get_media_duration(job.video_path)

            raw_segs, detected_lang = engine.transcribe(wav_path, model_name=whisper_model)
            trans_segs, _ = engine.translate_segments(
                raw_segs,
                target_lang=target_lang,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                groq_api_key=groq_api_key,
                deepseek_api_key=deepseek_api_key,
                primary_ai_model=primary_ai_model
            )

            recap_segs = engine.generate_movie_recap_script(
                segments=trans_segs,
                video_duration=v_duration,
                target_lang=target_lang,
                style=recap_style,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
                groq_api_key=groq_api_key,
                deepseek_api_key=deepseek_api_key
            )

            ext = os.path.splitext(job.video_path)[1] or ".mp4"
            srt_path = os.path.join(job_out_dir, "subtitles.srt")
            engine.export_srt(recap_segs, srt_path)

            if custom_output_dir and os.path.isdir(custom_output_dir):
                try:
                    custom_srt_path = os.path.join(custom_output_dir, f"{job.original_base}_recap.srt")
                    shutil.copy2(srt_path, custom_srt_path)
                except Exception as ex:
                    print(f"Error copying recap srt to custom output directory: {ex}")

            job.result_data = {
                "job_id": job_id,
                "original_base": job.original_base,
                "out_video_name": f"{job.original_base}_recap.mp4",
                "out_srt_name": f"{job.original_base}_recap.srt",
                "target_lang": target_lang,
                "video_duration": round(v_duration, 2),
                "segments": recap_segs,
                "video_url": f"/uploads/{job_id}{ext}",
                "srt_url": f"/outputs/{job_id}/subtitles.srt"
            }
            job.status = "completed"
            job.update({"step": "completed", "progress": 100, "message": "AI Movie Recap generated successfully!"})

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.update({"step": "error", "progress": 0, "message": f"Movie recap failed: {str(e)}"})

    t = threading.Thread(target=run_recap)
    t.daemon = True
    t.start()

    return jsonify({"job_id": job_id, "status": "processing"})

@app.route("/api/process_file", methods=["POST"])
def process_file():
    job_id = request.form.get("job_id", "").strip()
    
    target_lang = request.form.get("target_lang", "km")
    voice_id = request.form.get("voice_id", "auto")
    vocal_mode = request.form.get("vocal_mode", "remove")
    ducking_level = float(request.form.get("ducking_level", 0.15))
    burn_subtitles = request.form.get("burn_subtitles", "false").lower() == "true"
    whisper_model = request.form.get("whisper_model", "base")
    custom_output_dir = request.form.get("output_path", "").strip() or None
    if not custom_output_dir:
        return jsonify({"error": "Please choose an output folder before starting the final render."}), 400
    gemini_api_key = request.form.get("gemini_api_key", "").strip() or None
    gemini_model = request.form.get("gemini_model", "gemini-2.0-flash").strip()
    groq_api_key = request.form.get("groq_api_key", "").strip() or None
    deepseek_api_key = request.form.get("deepseek_api_key", "").strip() or None
    openrouter_api_key = request.form.get("openrouter_api_key", "").strip() or None
    openai_api_key = request.form.get("openai_api_key", "").strip() or None
    rvc_model = request.form.get("rvc_model", "").strip() or None
    rvc_pitch = int(request.form.get("rvc_pitch", 0) or 0)
    primary_ai_model = request.form.get("primary_ai_model", "").strip() or load_user_config().get("primary_ai_model", "gemini")
    
    segments_json = request.form.get("segments", "")
    custom_segments = None
    if segments_json:
        try:
            custom_segments = json.loads(segments_json)
        except Exception as e:
            print(f"Error parsing custom segments: {e}")

    edits_json = request.form.get("custom_edits", "")
    custom_edits = None
    if edits_json:
        try:
            custom_edits = json.loads(edits_json)
        except Exception as e:
            print(f"Error parsing custom edits: {e}")

    logo_file_path = None
    if "logo_file" in request.files:
        lf = request.files["logo_file"]
        if lf and lf.filename != "":
            logo_ext = os.path.splitext(lf.filename)[1] or ".png"
            logo_file_path = os.path.join(UPLOAD_DIR, f"logo_{uuid.uuid4().hex[:8]}{logo_ext}")
            lf.save(logo_file_path)

    # Case A: Re-use existing transcribed job_id
    if job_id and job_id in JOBS:
        job = JOBS[job_id]
        saved_video_path = getattr(job, "video_path", None)
        if not saved_video_path or not os.path.exists(saved_video_path):
            if os.path.exists(UPLOAD_DIR):
                for fname in os.listdir(UPLOAD_DIR):
                    if fname.startswith(job_id):
                        saved_video_path = os.path.join(UPLOAD_DIR, fname)
                        break

        if not saved_video_path or not os.path.exists(saved_video_path):
            if "video_file" in request.files:
                file = request.files["video_file"]
                if file and file.filename != "":
                    ext = os.path.splitext(file.filename)[1] or ".mp4"
                    saved_video_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
                    file.save(saved_video_path)
                    job.video_path = saved_video_path

        if not saved_video_path or not os.path.exists(saved_video_path):
            return jsonify({"error": f"Uploaded video file not found for job '{job_id}'. Please select your video file again."}), 400

        job.status = "processing"
        # Always refresh rvc_model/rvc_pitch from the current request so the
        # Final-Process form overrides any stale value stored from transcription.
        job.rvc_model = rvc_model or "none"
        job.rvc_pitch = rvc_pitch
        job.voice_id  = voice_id
        
        t = threading.Thread(
            target=process_dubbing_task,
            kwargs={
                "job_id": job_id,
                "video_path": saved_video_path,
                "target_lang": target_lang,
                "voice_id": voice_id,
                "ducking_level": ducking_level,
                "burn_subtitles": burn_subtitles,
                "whisper_model": whisper_model,
                "vocal_mode": vocal_mode,
                "custom_output_dir": custom_output_dir,
                "custom_segments": custom_segments,
                "custom_edits": custom_edits,
                "logo_file_path": logo_file_path,
                "gemini_api_key": gemini_api_key,
                "gemini_model": gemini_model,
                "groq_api_key": groq_api_key,
                "deepseek_api_key": deepseek_api_key,
                "openrouter_api_key": openrouter_api_key,
                "openai_api_key": openai_api_key,
                "rvc_model": rvc_model,
                "rvc_pitch": rvc_pitch,
                "primary_ai_model": primary_ai_model,
            }
        )
        t.daemon = True
        t.start()

        return jsonify({"job_id": job_id})

    # Case B: Local file path string OR Direct file upload
    file_path_param = request.form.get("file_path", "").strip()
    saved_video_path = None
    orig_base = "dubbed"
    job_id = str(uuid.uuid4())

    if file_path_param and os.path.exists(file_path_param):
        raw_base = os.path.splitext(os.path.basename(file_path_param))[0].strip()
        orig_base = raw_base if raw_base else f"video_{job_id[:8]}"
        ext = os.path.splitext(file_path_param)[1] or ".mp4"
        saved_video_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
        shutil.copy2(file_path_param, saved_video_path)
    elif "video_file" in request.files:
        file = request.files["video_file"]
        if file and file.filename != "":
            raw_base = os.path.splitext(os.path.basename(file.filename))[0].strip()
            orig_base = raw_base if raw_base else f"video_{job_id[:8]}"
            ext = os.path.splitext(file.filename)[1] or ".mp4"
            saved_video_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
            file.save(saved_video_path)

    if not saved_video_path or not os.path.exists(saved_video_path):
        return jsonify({"error": "No valid video file or file path provided"}), 400

    job = JobTracker(job_id)
    job.original_base = orig_base
    # Persist rvc/voice settings so re-render and render_edits routes can read them.
    job.rvc_model = rvc_model or "none"
    job.rvc_pitch = rvc_pitch
    job.voice_id  = voice_id
    JOBS[job_id] = job

    t = threading.Thread(
        target=process_dubbing_task,
        kwargs={
            "job_id": job_id,
            "video_path": saved_video_path,
            "target_lang": target_lang,
            "voice_id": voice_id,
            "ducking_level": ducking_level,
            "burn_subtitles": burn_subtitles,
            "whisper_model": whisper_model,
            "vocal_mode": vocal_mode,
            "custom_output_dir": custom_output_dir,
            "custom_segments": custom_segments,
            "custom_edits": custom_edits,
            "logo_file_path": logo_file_path,
            "gemini_api_key": gemini_api_key,
            "gemini_model": gemini_model,
            "groq_api_key": groq_api_key,
            "deepseek_api_key": deepseek_api_key,
            "openrouter_api_key": openrouter_api_key,
            "openai_api_key": openai_api_key,
            "rvc_model": rvc_model,
            "rvc_pitch": rvc_pitch,
            "primary_ai_model": primary_ai_model,
        }
    )
    t.daemon = True
    t.start()


    return jsonify({"job_id": job_id})

@app.route("/api/process_url", methods=["POST"])
def process_url():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No video URL provided"}), 400
        
    target_lang = data.get("target_lang", "km")
    voice_id = data.get("voice_id", "auto")
    vocal_mode = data.get("vocal_mode", "remove")
    ducking_level = float(data.get("ducking_level", 0.15))
    burn_subtitles = data.get("burn_subtitles", False)
    whisper_model = data.get("whisper_model", "base")
    custom_output_dir = data.get("output_path", "").strip() or None
    if not custom_output_dir:
        return jsonify({"error": "Please choose an output folder before starting the final render."}), 400

    job_id = str(uuid.uuid4())
    saved_video_path = os.path.join(UPLOAD_DIR, f"{job_id}.mp4")

    job = JobTracker(job_id)
    JOBS[job_id] = job
    job.update({"step": "download_url", "progress": 5, "message": "Downloading video from URL with yt-dlp..."})

    def run_download_and_process():
        try:
            cmd = [
                "yt-dlp", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "-o", saved_video_path, url
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            if res.returncode != 0:
                raise RuntimeError(f"yt-dlp download failed: {res.stderr}")
                
            process_dubbing_task(job_id, saved_video_path, target_lang, voice_id, ducking_level, burn_subtitles, whisper_model, vocal_mode, custom_output_dir)
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.update({"step": "error", "progress": 0, "message": f"Download failed: {str(e)}"})

    t = threading.Thread(target=run_download_and_process)
    t.daemon = True
    t.start()

    return jsonify({"job_id": job_id})

@app.route("/api/progress/<job_id>")
def stream_progress(job_id):
    if job_id not in JOBS:
        return jsonify({"error": "Job not found"}), 404

    job = JOBS[job_id]

    def event_stream():
        q = queue.Queue()
        job.listeners.append(q)
        
        init_evt = {
            "job_id": job_id,
            "status": job.status,
            "step": job.step,
            "progress": job.progress,
            "message": job.message,
            "result_data": job.result_data,
            "error": job.error
        }
        yield f"data: {json.dumps(init_evt)}\n\n"
        
        while True:
            try:
                evt = q.get(timeout=30)
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("status") in ["completed", "failed"]:
                    break
            except queue.Empty:
                yield ": keep-alive\n\n"

    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/api/job/<job_id>")
def get_job_info(job_id):
    if job_id not in JOBS:
        return jsonify({"error": "Job not found"}), 404
    job = JOBS[job_id]
    return jsonify({
        "job_id": job_id,
        "status": job.status,
        "step": job.step,
        "progress": job.progress,
        "message": job.message,
        "result_data": job.result_data,
        "error": job.error
    })

@app.route("/api/re-render/<job_id>", methods=["POST"])
def rerender_job(job_id):
    if job_id not in JOBS:
        return jsonify({"error": "Job not found"}), 404
        
    job = JOBS[job_id]
    data = request.json or {}
    new_segments = data.get("segments", [])
    voice_id = data.get("voice_id", job.result_data.get("voice_id"))

    def run_rerender():
        try:
            job.status = "processing"
            job.update({"step": "rerender", "progress": 10, "message": "Re-synthesizing dubbed speech from edited transcript..."})

            job_out_dir = os.path.join(OUTPUT_DIR, job_id)
            temp_dir = os.path.join(job_out_dir, "temp")
            video_path = os.path.join(UPLOAD_DIR, f"{job_id}.mp4")
            if not os.path.exists(video_path):
                for fname in os.listdir(UPLOAD_DIR):
                    if fname.startswith(job_id):
                        video_path = os.path.join(UPLOAD_DIR, fname)
                        break

            engine = VideoDubberEngine(progress_callback=job.update)
            video_duration = engine.get_media_duration(video_path)

            rvc_model = getattr(job, "rvc_model", "none")
            rvc_pitch = getattr(job, "rvc_pitch", "0")
            tts_clips = engine.synthesize_all_tts(new_segments, voice_id, temp_dir, rvc_model=rvc_model, rvc_pitch=rvc_pitch)


            dubbed_speech_path = os.path.join(job_out_dir, "dubbed_speech.wav")
            engine.align_and_combine_speech(new_segments, tts_clips, video_duration, dubbed_speech_path, temp_dir)

            srt_path = os.path.join(job_out_dir, "subtitles.srt")
            engine.export_srt(new_segments, srt_path)

            bgm_processed_path = os.path.join(temp_dir, "bgm_processed.wav")
            output_video_path = os.path.join(job_out_dir, "dubbed_video.mp4")
            engine.merge_final_video(video_path, dubbed_speech_path, bgm_processed_path, output_video_path, srt_path=srt_path)

            job.result_data["segments"] = new_segments
            job.result_data["voice_id"] = voice_id
            job.status = "completed"
            job.update({"step": "completed", "progress": 100, "message": "Re-rendering complete!"})

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.update({"step": "error", "progress": 0, "message": f"Re-render failed: {str(e)}"})

    t = threading.Thread(target=run_rerender)
    t.daemon = True
    t.start()

    return jsonify({"message": "Re-rendering initiated"})

@app.route("/api/render_edits/<job_id>", methods=["POST"])
def render_edits_job(job_id):
    if job_id not in JOBS:
        return jsonify({"error": "Job not found"}), 404
        
    job = JOBS[job_id]

    logo_file = request.files.get("logo_file")
    logo_path = None
    if logo_file and logo_file.filename:
        logo_ext = os.path.splitext(logo_file.filename)[1] or ".png"
        logo_path = os.path.join(UPLOAD_DIR, f"logo_{job_id}{logo_ext}")
        logo_file.save(logo_path)

    form = request.form
    custom_edits = None

    # Read rvc params from form if provided; fall back to stored job attribute.
    # This ensures the Editor Lab render always picks up the correct RVC model.
    form_rvc_model = form.get("rvc_model", "").strip()
    form_rvc_pitch = form.get("rvc_pitch", "").strip()
    if form_rvc_model and form_rvc_model not in ("none", "disabled"):
        job.rvc_model = form_rvc_model
    if form_rvc_pitch:
        try:
            job.rvc_pitch = int(form_rvc_pitch)
        except ValueError:
            pass

    # Try parsing a pre-built custom_edits JSON blob first (sent by Editor Lab)
    if "custom_edits" in form:
        try:
            custom_edits = json.loads(form["custom_edits"])
        except Exception:
            pass

    if not custom_edits:
        # Build a typed PreviewRenderConfig from the form fields, then convert to
        # the internal custom_edits dict.  This eliminates the previous 30-line
        # manual dict assembly and guarantees type-safe defaults via the dataclass.
        render_cfg = PreviewRenderConfig.from_form(
            form=form,
            logo_uploaded=(logo_path is not None),
        )
        custom_edits = render_cfg.to_custom_edits()

    form_bgm_vol = form.get("bgm_volume") or form.get("bgmVolume") or form.get("bgm_vol")
    if form_bgm_vol is not None:
        try:
            if not custom_edits:
                custom_edits = {}
            if "audio" not in custom_edits or not isinstance(custom_edits["audio"], dict):
                custom_edits["audio"] = {}
            val = float(form_bgm_vol)
            custom_edits["audio"]["bgm_volume"] = val
            custom_edits["bgm_volume"] = val
        except Exception:
            pass

    def run_video_edit():
        try:
            job.status = "processing"
            job.update({"step": "merge_video", "progress": 85, "message": "Rendering custom video overlays & styled captions..."})

            job_out_dir = os.path.join(OUTPUT_DIR, job_id)
            temp_dir = os.path.join(job_out_dir, "temp")
            os.makedirs(job_out_dir, exist_ok=True)
            os.makedirs(temp_dir, exist_ok=True)

            dubbed_speech_path = os.path.join(job_out_dir, "dubbed_speech.wav")
            bgm_processed_path = os.path.join(temp_dir, "bgm_processed.wav")
            output_video_path = os.path.join(job_out_dir, "dubbed_video.mp4")
            srt_path = os.path.join(job_out_dir, "subtitles.srt")
            logo_path = getattr(job, "logo_path", None)

            video_path = os.path.join(UPLOAD_DIR, f"{job_id}.mp4")
            if not os.path.exists(video_path):
                for fname in os.listdir(UPLOAD_DIR):
                    if fname.startswith(job_id) and not fname.startswith("logo_"):
                        video_path = os.path.join(UPLOAD_DIR, fname)
                        break

            engine = VideoDubberEngine(progress_callback=job.update)

            # Ensure dubbed speech WAV is available
            if not os.path.exists(dubbed_speech_path) or os.path.getsize(dubbed_speech_path) < 100:
                segments = (job.result_data.get("segments") if job.result_data else None) or []
                voice_id = getattr(job, "voice_id", "auto")
                rvc_model = getattr(job, "rvc_model", "none")
                rvc_pitch = getattr(job, "rvc_pitch", "0")
                video_duration = engine.get_media_duration(video_path)
                tts_clips = engine.synthesize_all_tts(segments, voice_id, temp_dir, rvc_model=rvc_model, rvc_pitch=rvc_pitch)
                engine.align_and_combine_speech(segments, tts_clips, video_duration, dubbed_speech_path, temp_dir)

            if not os.path.exists(bgm_processed_path):
                bgm_processed_path = None

            engine.render_edited_video(
                video_path=video_path,
                dubbed_speech_path=dubbed_speech_path,
                bgm_audio_path=bgm_processed_path,
                output_video_path=output_video_path,
                srt_path=srt_path,
                custom_edits=custom_edits,
                logo_file_path=logo_path
            )

            if isinstance(job.result_data, dict):
                job.result_data["dubbed_video_url"] = f"/outputs/{job_id}/dubbed_video.mp4"
                job.result_data["output_video_path"] = output_video_path

            job.status = "completed"
            job.update({"step": "completed", "progress": 100, "message": "Custom video rendered successfully!"})


        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.update({"step": "error", "progress": 0, "message": f"Render failed: {str(e)}"})

    t = threading.Thread(target=run_video_edit)
    t.daemon = True
    t.start()

    return jsonify({"status": "processing"})

@app.route("/api/tts_preview", methods=["POST"])
def tts_preview():
    data = request.get_json(silent=True) or request.form
    text = data.get("text", "").strip()
    target_lang = data.get("target_lang", "km")
    voice_id = data.get("voice_id", "auto")
    gender = data.get("gender", "")   # 'Female' | 'Male' | ''

    if not text:
        return jsonify({"error": "No text provided"}), 400

    if voice_id == "auto" or not voice_id:
        # Try to resolve via gender hint before falling back to default
        if gender:
            lang_voices = SUPPORTED_LANGUAGES.get(target_lang, {}).get("voices", [])
            for v in lang_voices:
                if v.get("gender", "").lower() == gender.lower():
                    voice_id = v["id"]
                    break
        if voice_id == "auto" or not voice_id:
            voice_id = get_default_voice(target_lang)


    temp_id = str(uuid.uuid4())
    preview_file = f"preview_{temp_id}.mp3"
    preview_path = os.path.join(OUTPUT_DIR, preview_file)

    try:
        communicate = edge_tts.Communicate(text, voice_id)
        # Use a fresh event loop to avoid conflicts on Windows/Flask threads
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(communicate.save(preview_path))
        finally:
            loop.close()
        return jsonify({"audio_url": f"/outputs/{preview_file}"})
    except Exception as e:
        print(f"TTS preview error (voice={voice_id}, lang={target_lang}): {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/outputs/<path:filepath>")
def serve_output(filepath):
    return send_from_directory(OUTPUT_DIR, filepath)

def cleanup_job_files(job_id: str):
    """Purge input upload files and intermediate temp folder for job_id, leaving rendered outputs intact."""
    if not job_id:
        return
        
    # 1. Purge uploaded video file / logo file from UPLOAD_DIR
    try:
        if os.path.exists(UPLOAD_DIR):
            for fname in os.listdir(UPLOAD_DIR):
                if fname.startswith(job_id) or f"_{job_id}" in fname:
                    fpath = os.path.join(UPLOAD_DIR, fname)
                    try:
                        if os.path.isfile(fpath) or os.path.islink(fpath):
                            os.remove(fpath)
                        elif os.path.isdir(fpath):
                            shutil.rmtree(fpath, ignore_errors=True)
                    except Exception as ex:
                        print(f"Note: Could not remove uploaded file {fpath}: {ex}")
    except Exception as e:
        print(f"Error cleaning upload temp files for {job_id}: {e}")

    # 2. Purge ONLY the intermediate temp subfolder inside outputs/<job_id>/temp
    try:
        job_out_dir = os.path.join(OUTPUT_DIR, job_id)
        temp_dir = os.path.join(job_out_dir, "temp")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"[Cleanup] Auto-deleted temp folder for job {job_id}: {temp_dir}")
    except Exception as e:
        print(f"Error cleaning temp directory for {job_id}: {e}")

@app.route("/api/cleanup/<job_id>", methods=["POST", "GET"])
def api_cleanup_job(job_id):
    """Clean up input and intermediate temp files from system temp folder for the given job_id."""
    cleanup_job_files(job_id)
    return jsonify({"ok": True, "message": f"Cleaned temp files for {job_id}"})

@app.route("/api/download/<job_id>/<file_type>")
def download_file(job_id, file_type):
    """Direct download endpoint with explicit filename, mime type, and automatic temp folder cleanup."""
    folder = os.path.join(OUTPUT_DIR, job_id)
    job = JOBS.get(job_id)
    orig_base = getattr(job, "original_base", None) or (job.result_data.get("original_base") if job and job.result_data else "dubbed")

    if file_type == "video":
        filepath = os.path.join(folder, "dubbed_video.mp4")
        filename = f"{orig_base}_dubbed.mp4"
        mimetype = "video/mp4"
    elif file_type == "audio":
        filepath = os.path.join(folder, "dubbed_speech.wav")
        filename = f"{orig_base}_dubbed.wav"
        mimetype = "audio/wav"
    elif file_type == "srt":
        filepath = os.path.join(folder, "subtitles.srt")
        filename = f"{orig_base}_dubbed.srt"
        mimetype = "text/plain"
    else:
        return "Invalid file type", 400

    @after_this_request
    def _auto_clean_temp(response):
        try:
            cleanup_job_files(job_id)
        except Exception as e:
            print(f"[Download] Auto-clean temp note: {e}")
        return response

    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )

# ─── ONLINE VERSION & UPDATE CHECK ENDPOINTS ────────────────────────────────
APP_VERSION = "1.2.0"

# ── Set USE_LOCAL_TEST_DATA = True to test with the simulated v1.3.0 response
# ── Set USE_LOCAL_TEST_DATA = False + set VERSION_CHECK_URL for real production
USE_LOCAL_TEST_DATA = True
VERSION_CHECK_URL = "https://raw.githubusercontent.com/SEN/Video_Dubber_Studio/main/version.json"

def _get_local_test_version_data():
    """Returns simulated remote version data for testing the update feature locally."""
    return {
        "version": "1.3.0",
        "release_notes": (
            "v1.3.0 — What's New:\n"
            "• Single-line subtitle rendering: captions now always display on one line\n"
            "• Online version update checker with release notes\n"
            "• Improved batch processing performance\n"
            "• Fixed Khmer font rendering edge cases\n"
            "• UI polish: unified button styles across all modals"
        ),
        "download_url": "https://github.com/SEN/Video_Dubber_Studio/releases"
    }

@app.route("/api/local_version_info", methods=["GET"])
def local_version_info():
    """Endpoint that exposes the local test version data (for manual inspection)."""
    return jsonify(_get_local_test_version_data())


@app.route("/api/version", methods=["GET"])
def get_app_version():
    """Returns local app version info."""
    return jsonify({
        "ok": True,
        "version": APP_VERSION,
        "app_name": "AutoVideoDubber Studio PRO"
    })

@app.route("/api/check_update", methods=["GET", "POST"])
def check_online_update():
    """Check online server/GitHub for newer versions of Video Dubber Studio."""

    def parse_ver(v):
        try:
            return tuple(map(int, v.lstrip("vV").split(".")))
        except Exception:
            return (0,)

    def build_response(remote_data):
        latest_ver = remote_data.get("version", APP_VERSION)
        rel_notes = remote_data.get("release_notes", "Latest performance and feature enhancements.")
        dl_url = remote_data.get("download_url", "https://github.com/SEN/Video_Dubber_Studio/releases")
        has_update = parse_ver(latest_ver) > parse_ver(APP_VERSION)
        return jsonify({
            "ok": True,
            "current_version": APP_VERSION,
            "latest_version": latest_ver,
            "has_update": has_update,
            "release_notes": rel_notes,
            "download_url": dl_url,
            "status": "online" if has_update else "up_to_date"
        })

    try:
        # ── TEST MODE: use local simulated data (no HTTP self-loop) ──────────
        if USE_LOCAL_TEST_DATA:
            remote_data = _get_local_test_version_data()
            return build_response(remote_data)

        # ── PRODUCTION MODE: fetch from remote GitHub URL ─────────────────────
        import urllib.request
        import json as json_lib
        req = urllib.request.Request(
            VERSION_CHECK_URL,
            headers={"User-Agent": "VideoDubberStudio-Updater/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    remote_data = json_lib.loads(resp.read().decode("utf-8"))
                    return build_response(remote_data)
        except Exception as net_err:
            print(f"[UpdateCheck] Remote fetch notice: {net_err}")

    except Exception as e:
        print(f"[UpdateCheck] General error: {e}")

    # Fallback: already on latest
    return jsonify({
        "ok": True,
        "current_version": APP_VERSION,
        "latest_version": APP_VERSION,
        "has_update": False,
        "release_notes": "You are using the latest version of AutoVideoDubber Studio PRO.",
        "download_url": "https://github.com/SEN/Video_Dubber_Studio",
        "status": "up_to_date"
    })



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)