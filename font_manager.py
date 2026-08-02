# font_manager.py
#
# Enumerates real, installed font files (no third-party dependency — parses the
# TTF/OTF 'name' table directly with struct) so the UI can offer whatever fonts
# actually exist on the user's Windows machine, instead of a hardcoded guess list.
#
# This is the SINGLE SOURCE OF TRUTH for font resolution: the browser preview and
# the ffmpeg burn-in both resolve a font by its absolute file path returned from
# here, rather than the browser guessing from a font-family name and the renderer
# separately guessing a Windows font-folder path. Same path in, same glyphs out.

import os
import sys
import struct
import threading

_cache_lock = threading.Lock()
_font_cache = None  # list[dict(name=str, path=str)] once scanned


def _base_dir():
    """Directory this module lives in (or the PyInstaller bundle dir when frozen)."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


def _candidate_font_dirs():
    dirs = [os.path.join(_base_dir(), "static", "fonts")]  # bundled fonts, highest priority
    if sys.platform == "win32":
        dirs.append(r"C:\Windows\Fonts")
        dirs.append(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"))
    return [d for d in dirs if os.path.isdir(d)]


def _decode_name_record(data, platform_id, encoding_id):
    try:
        if platform_id in (0, 3):  # Unicode / Windows -> UTF-16BE
            return data.decode("utf-16-be", errors="ignore").strip()
        if platform_id == 1:  # Macintosh -> Mac Roman (close enough for family names)
            return data.decode("mac_roman", errors="ignore").strip()
        return data.decode("utf-16-be", errors="ignore").strip()
    except Exception:
        return ""


def _read_sfnt_names(f, table_dir_offset):
    """Read family (16 else 1) and subfamily (17 else 2) names from one sfnt table directory."""
    f.seek(table_dir_offset + 4)
    num_tables = struct.unpack(">H", f.read(2))[0]
    f.seek(table_dir_offset + 12)  # skip searchRange/entrySelector/rangeShift
    name_table_offset = None
    for _ in range(num_tables):
        tag, _checksum, offset, _length = struct.unpack(">4sIII", f.read(16))
        if tag == b"name":
            name_table_offset = offset
    if name_table_offset is None:
        return None, None

    f.seek(name_table_offset)
    _fmt, count, string_offset = struct.unpack(">HHH", f.read(6))
    records = []
    for _ in range(count):
        platform_id, encoding_id, _lang_id, name_id, length, offset = struct.unpack(">HHHHHH", f.read(12))
        records.append((platform_id, encoding_id, name_id, length, offset))

    strings_base = name_table_offset + string_offset
    best = {1: None, 2: None, 16: None, 17: None}
    for platform_id, encoding_id, name_id, length, offset in records:
        if name_id not in best:
            continue
        if best[name_id] is not None and platform_id != 3:
            continue  # prefer Windows-platform entries when we already have one
        f.seek(strings_base + offset)
        raw = f.read(length)
        text = _decode_name_record(raw, platform_id, encoding_id)
        if text:
            best[name_id] = text

    family = best[16] or best[1]
    subfamily = best[17] or best[2] or ""
    return family, subfamily


def _read_font_names(path):
    """Return (family_name, subfamily_name) for a .ttf/.otf/.ttc file, or (None, None)."""
    try:
        with open(path, "rb") as f:
            tag = f.read(4)
            if tag == b"ttcf":
                f.seek(12)
                first_offset = struct.unpack(">I", f.read(4))[0]
                return _read_sfnt_names(f, first_offset)
            else:
                return _read_sfnt_names(f, 0)
    except Exception:
        return None, None


KHMER_FONT_KEYWORDS = [
    "kantumruy", "battambang", "siemreap", "nokora", "hanuman", "moul", "muol",
    "content", "dangrek", "freehand", "fasthand", "bokor", "khmer", "khmerui"
]


def is_khmer_font(name, path=""):
    n = (name or "").lower()
    p = (path or "").lower()
    return any(kw in n for kw in KHMER_FONT_KEYWORDS) or any(kw in p for kw in KHMER_FONT_KEYWORDS)


def scan_fonts(force_refresh=False):
    """Scan bundled + system font directories, returning sorted list of Khmer fonts {name, path}."""
    global _font_cache
    with _cache_lock:
        if _font_cache is not None and not force_refresh:
            return _font_cache

        by_family = {}  # family_name -> (path, subfamily, priority)
        for priority, folder in enumerate(_candidate_font_dirs()):
            try:
                entries = os.listdir(folder)
            except Exception:
                continue
            for fname in entries:
                if not fname.lower().endswith((".ttf", ".otf", ".ttc")):
                    continue
                fpath = os.path.join(folder, fname)
                family, subfamily = _read_font_names(fpath)
                if not family:
                    continue
                existing = by_family.get(family)
                is_regular = subfamily.strip().lower() in ("regular", "book", "normal", "")
                if existing is None:
                    by_family[family] = (fpath, is_regular, priority)
                else:
                    _existing_path, existing_is_regular, existing_priority = existing
                    if priority < existing_priority or (priority == existing_priority and is_regular and not existing_is_regular):
                        by_family[family] = (fpath, is_regular, priority)

        result = [{"name": name, "path": path} for name, (path, _reg, _prio) in by_family.items()]

        # Ensure Kantumruy Pro is always present as the primary font if available
        if not any(f["name"] == "Kantumruy Pro" for f in result):
            bundled = os.path.join(_base_dir(), "static", "fonts", "KantumruyPro.ttf")
            if os.path.exists(bundled):
                result.insert(0, {"name": "Kantumruy Pro", "path": bundled})

        result.sort(key=lambda x: (x["name"] != "Kantumruy Pro", x["name"].lower()))
        _font_cache = result
        return result


def resolve_font_path(name=None, path=None):
    """Resolve a font to an absolute file path.

    `path` (if given and it still exists on disk) always wins — this is the exact
    file the preview/UI already picked, so the renderer uses the identical bytes.
    Falls back to a name lookup against the scanned font list, then to the
    bundled Kantumruy Pro, then to Arial.
    """
    if path:
        norm_p = os.path.normpath(path)
        if os.path.exists(norm_p):
            return norm_p

    fonts = scan_fonts()
    if name:
        name_clean = name.strip().lower()
        for f in fonts:
            if f["name"].strip().lower() == name_clean:
                return f["path"]
        for f in fonts:
            if name_clean in f["name"].strip().lower():
                return f["path"]

    for f in fonts:
        if f["name"] == "Kantumruy Pro":
            return f["path"]

    bundled = os.path.join(_base_dir(), "static", "fonts", "KantumruyPro.ttf")
    if os.path.exists(bundled):
        return bundled

    return r"C:\Windows\Fonts\arial.ttf"


def get_font_family_and_path(name=None, path=None):
    """Resolve both the exact SFNT font family name (for libass Fontname)
    and the absolute file path (for fontsdir and preview).
    """
    resolved_path = resolve_font_path(name=name, path=path)
    family_name, _sub = _read_font_names(resolved_path)
    if not family_name:
        family_name = name or "Kantumruy Pro"
    return family_name, resolved_path

