# run_app.py — Native Windows Desktop App using pywebview
import os
import sys
import threading
import time
import shutil
import tempfile

# ─── Fix paths inside PyInstaller bundle ─────────────────────────────────────
BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
if getattr(sys, 'frozen', False):
    os.chdir(BASE_DIR)

OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

# ─── Native Python API exposed to JS ─────────────────────────────────────────
class AppAPI:
    """Methods here are callable from JavaScript via window.pywebview.api.*"""

    def _show_dialog(self, dialog_fn, *args, **kwargs):
        """Helper to manage tkinter dialog lifecycle safely in Windows pywebview desktop app."""
        import tkinter as tk
        root = None
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            res = dialog_fn(*args, **kwargs)
            return res
        except Exception as e:
            print(f"[DialogError] {e}")
            return None
        finally:
            if root:
                try:
                    root.quit()
                    root.destroy()
                except Exception:
                    pass

    def save_file(self, job_id, file_type):
        """Open a native Save dialog and copy the output file to chosen path."""
        from tkinter import filedialog
        import urllib.request
        import json

        orig_base = "dubbed"
        try:
            req = urllib.request.urlopen(f"http://127.0.0.1:5000/api/job/{job_id}", timeout=1)
            info = json.loads(req.read().decode())
            orig_base = info.get("result_data", {}).get("original_base", "dubbed")
        except Exception:
            pass

        file_map = {
            "video": ("dubbed_video.mp4",  [("MP4 Video", "*.mp4")],     f"{orig_base}_dubbed.mp4"),
            "audio": ("dubbed_speech.wav", [("WAV Audio", "*.wav")],     f"{orig_base}_dubbed.wav"),
            "srt":   ("subtitles.srt",     [("SRT Subtitles", "*.srt")],  f"{orig_base}_dubbed.srt"),
        }

        if file_type not in file_map:
            return {"ok": False, "error": "Unknown file type"}

        src_name, filetypes, default_name = file_map[file_type]
        src_path = os.path.join(BASE_DIR, "outputs", job_id, src_name)
        if not os.path.exists(src_path):
            alt_path = os.path.join(tempfile.gettempdir(), "VideoDubberStudio", "outputs", job_id, src_name)
            if os.path.exists(alt_path):
                src_path = alt_path

        # If SRT requested but file doesn't exist on disk yet, export on-the-fly from job result_data
        if file_type == "srt" and not os.path.exists(src_path):
            try:
                req = urllib.request.urlopen(f"http://127.0.0.1:5000/api/job/{job_id}", timeout=2)
                info = json.loads(req.read().decode())
                segs = (info.get("result_data") or {}).get("segments", [])
                if segs:
                    os.makedirs(os.path.dirname(src_path), exist_ok=True)
                    from dubbing_engine import VideoDubberEngine
                    VideoDubberEngine().export_srt(segs, src_path)
            except Exception as ex:
                print(f"[SaveFile] On-the-fly SRT export note: {ex}")

        if not os.path.exists(src_path):
            return {"ok": False, "error": f"File not found: {src_path}"}

        # Show native Save As dialog
        dest = self._show_dialog(
            filedialog.asksaveasfilename,
            title="Save As",
            initialfile=default_name,
            defaultextension=os.path.splitext(default_name)[1],
            filetypes=filetypes
        )

        if not dest:
            return {"ok": False, "error": "Cancelled"}

        try:
            shutil.copy2(src_path, dest)
            # Auto-clean input, intermediate, and output files from temp folder after output save completed
            try:
                urllib.request.urlopen(f"http://127.0.0.1:5000/api/cleanup/{job_id}", timeout=1)
            except Exception:
                pass
            return {"ok": True, "path": dest}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def select_batch_files(self):
        """Open native multi-file dialog for selecting multiple videos for batch queue."""
        from tkinter import filedialog
        files = self._show_dialog(
            filedialog.askopenfilenames,
            title="Select Videos for Batch Processing",
            filetypes=[("Video Files", "*.mp4 *.mkv *.mov *.avi *.webm *.flv *.ts")]
        )
        return list(files) if files else []

    def select_folder(self):
        """Open native Windows directory picker dialog."""
        from tkinter import filedialog
        folder = self._show_dialog(filedialog.askdirectory, title="Select Output Folder")
        return folder if folder else ""

    def get_video_duration(self, video_path):
        """Native PyWebView method to get exact duration in seconds."""
        try:
            if video_path:
                norm_path = os.path.normpath(os.path.abspath(video_path))
                if os.path.exists(norm_path):
                    from dubbing_engine import VideoDubberEngine
                    dur = VideoDubberEngine().get_media_duration(norm_path)
                    return float(dur)
        except Exception as e:
            print(f"Native get_video_duration error: {e}")
        return 0.0

    def detect_caption_region(self, video_path):
        """Native PyWebView method to auto-detect original hardcoded subtitle region."""
        try:
            if video_path:
                norm_path = os.path.normpath(os.path.abspath(video_path))
                if os.path.exists(norm_path):
                    from dubbing_engine import VideoDubberEngine
                    return VideoDubberEngine().detect_caption_region(norm_path)
        except Exception as e:
            print(f"Native detect_caption_region error: {e}")
        return {"posY": 0.0, "height": 0.0, "posX": 0.0, "width": 100.0, "detected": False}



# ─── Start Flask in a background thread ───────────────────────────────────────
def start_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    from app import app
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False, threaded=True)

flask_thread = threading.Thread(target=start_flask, daemon=True)
flask_thread.start()

# Wait for Flask to be ready
def wait_for_flask(timeout=10):
    import urllib.request
    for _ in range(timeout * 10):
        try:
            urllib.request.urlopen("http://127.0.0.1:5000", timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False

print("Starting Video Dubber Studio...")
wait_for_flask()
print("Ready!")

# ─── Open native desktop window via pywebview ─────────────────────────────────
import webview

win_width = 860
win_height = 675
pos_x = None
pos_y = None

try:
    if hasattr(webview, 'screens') and webview.screens:
        primary_screen = webview.screens[0]
        pos_x = max(0, (primary_screen.width - win_width) // 2)
        pos_y = max(0, (primary_screen.height - win_height) // 2)
except Exception:
    pass

window = webview.create_window(
    title="Video Dubber Studio",
    url="http://127.0.0.1:5000",
    width=win_width,
    height=win_height,
    min_size=(win_width, win_height),
    x=pos_x,
    y=pos_y,
    resizable=True,
    text_select=True,
    background_color='#0b0f19',
    js_api=AppAPI(),   # expose Python API to JavaScript
)

webview.start(debug=False)
