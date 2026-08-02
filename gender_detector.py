# gender_detector.py
"""
Auto Gender Detection from audio using energy-gated pitch (F0) analysis.

Strategy:
  1. Run pYIN (falls back to plain YIN) to get a per-frame F0 + voiced flag.
  2. Compute per-frame RMS energy over the SAME frame/hop grid and keep only
     the top-energy frames (speech sits louder & more consistently than
     background music bleed-through — this is the "energy gate" the
     original docstring described but the old implementation never actually
     applied, which was the main source of inaccurate segment-level results
     on clips with background music).
  3. Classify using BOTH the median and the histogram mode of the surviving
     F0 values. When they agree, that's a confident result. When they
     disagree (bimodal / noisy pitch distribution) or too few F0 values
     survive the gate, fall back to a caller-supplied `fallback_gender`
     (e.g. the whole-clip dominant gender, or the previous segment's
     result) instead of silently defaulting to "Female" — that hard-coded
     bias was the other main source of wrong per-segment calls on short or
     noisy dialogue clips.
  4. A small hysteresis margin around the threshold also prefers
     `fallback_gender` when the pitch sits right on the male/female
     boundary, so a single speaker doesn't flip-flop between segments.

Pitch reference:
  Male speech:   80 – 160 Hz  (average ~120 Hz)
  Female speech: 160 – 280 Hz (average ~210 Hz)
  Threshold: 155 Hz, ±12 Hz hysteresis band
"""

import os
import numpy as np

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

# ── Constants ─────────────────────────────────────────────────────────────────

FMIN        = 70.0    # Hz — below any human speech fundamental
FMAX        = 320.0   # Hz — above any normal speech fundamental
THRESHOLD   = 155.0   # Hz — below = Male, at or above = Female
HYSTERESIS  = 12.0    # Hz — within this margin of THRESHOLD, prefer fallback_gender

# Keep only the top (100 - ENERGY_PERCENTILE)% highest-RMS frames, i.e. the
# bottom 40% quietest frames (background music bleed-through, room tone,
# breath noise) are discarded before pitch is ever considered.
ENERGY_PERCENTILE = 40

# Minimum number of valid (voiced + high-energy) F0 values needed to trust
# a segment's own signal rather than falling back.
MIN_F0_VALUES = 8

ANALYSIS_SR = 16_000

# Maximum audio to load (seconds) when given a file path
SAMPLE_DURATION = 45.0

# Short segments get padded with a little surrounding audio (never crossing
# more than this many seconds into a neighbour) so there are enough frames
# to analyse — short interjections are exactly where the old code had the
# least signal to work with.
SHORT_SEG_TARGET_SEC = 1.2
MAX_PAD_SEC = 0.3

_VALID_GENDERS = ("Male", "Female")


_GENDER_CACHE = {}


# ── Core ──────────────────────────────────────────────────────────────────────

def _fast_autocorr_f0(y: np.ndarray, sr: int, frame_length: int = 1024, hop_length: int = 256) -> np.ndarray | None:
    """Ultra-fast vectorised 2D FFT autocorrelation pitch estimator (<0.03s per 30s audio).
    
    Returns array of F0 values in Hz, with np.nan for unvoiced/low-energy frames.
    """
    try:
        n_frames = 1 + (len(y) - frame_length) // hop_length
        if n_frames <= 0:
            return None

        min_lag = int(sr / FMAX)
        max_lag = int(sr / FMIN)

        frames = np.lib.stride_tricks.sliding_window_view(y[:(n_frames - 1) * hop_length + frame_length], frame_length)[::hop_length]
        win = np.hanning(frame_length)
        w_frames = frames * win

        n_fft = 2 ** int(np.ceil(np.log2(2 * frame_length)))
        fft_frames = np.fft.rfft(w_frames, n=n_fft, axis=1)
        autocorr = np.fft.irfft(np.abs(fft_frames) ** 2, n=n_fft, axis=1)[:, :max_lag + 1]

        r0 = np.maximum(autocorr[:, 0:1], 1e-7)
        norm_autocorr = autocorr / r0

        search_region = norm_autocorr[:, min_lag:max_lag + 1]
        best_lags = np.argmax(search_region, axis=1) + min_lag
        best_scores = np.max(search_region, axis=1)

        f0 = sr / best_lags.astype(float)

        # Energy mask over frame RMS
        rms = np.sqrt(np.mean(w_frames ** 2, axis=1))
        cutoff = np.percentile(rms, ENERGY_PERCENTILE) if len(rms) > 0 else 0.0

        voiced = (best_scores > 0.35) & (f0 >= FMIN + 5) & (f0 <= FMAX - 5) & (rms >= cutoff)
        f0_clean = np.where(voiced, f0, np.nan)
        return f0_clean
    except Exception as ex:
        print(f"[GenderDetector] Fast autocorr error: {ex}")
        return None


def _energy_gated_f0(y: np.ndarray, sr: int, frame_length: int = 1024, hop_length: int = 256):
    """Run fast autocorrelation (pYIN/YIN fallback) and keep high-energy voiced frames."""
    fast_f0 = _fast_autocorr_f0(y, sr, frame_length, hop_length)
    if fast_f0 is not None:
        valid_f0 = fast_f0[~np.isnan(fast_f0)].tolist()
        if len(valid_f0) >= MIN_F0_VALUES:
            return valid_f0

    f0_all: list[float] = []

    def _rms_mask(signal: np.ndarray, n_frames: int) -> np.ndarray:
        """Boolean mask selecting the top ENERGY_PERCENTILE-complement frames by RMS."""
        try:
            rms = librosa.feature.rms(y=signal, frame_length=frame_length, hop_length=hop_length)[0]
        except Exception:
            return np.ones(n_frames, dtype=bool)
        # Align lengths (pyin/yin and rms can differ by 1 frame at the edges)
        n = min(len(rms), n_frames)
        if n == 0:
            return np.ones(n_frames, dtype=bool)
        cutoff = np.percentile(rms[:n], ENERGY_PERCENTILE)
        mask = np.ones(n_frames, dtype=bool)
        mask[:n] = rms[:n] >= cutoff
        return mask

    # 1. pYIN — probabilistic voicing + F0 per frame
    try:
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=FMIN, fmax=FMAX, sr=sr,
            frame_length=frame_length, hop_length=hop_length
        )
        if f0 is not None and len(f0) > 0:
            energy_mask = _rms_mask(y, len(f0))
            valid_mask = (
                (voiced_flag == True) & ~np.isnan(f0)
                & (f0 >= FMIN + 5) & (f0 <= FMAX - 5)
                & energy_mask
            )
            valid_f0 = f0[valid_mask]
            if len(valid_f0) > 0:
                f0_all.extend(valid_f0.tolist())
    except Exception as ex:
        print(f"[GenderDetector] pYIN note: {ex}")

    # 2. YIN fallback (same energy gate applied) if pYIN gave too little
    if len(f0_all) < MIN_F0_VALUES:
        try:
            f0_full = librosa.yin(y, fmin=FMIN, fmax=FMAX, sr=sr, frame_length=frame_length, hop_length=hop_length)
            energy_mask = _rms_mask(y, len(f0_full))
            valid_mask = (f0_full >= FMIN + 5) & (f0_full <= FMAX - 5) & energy_mask
            valid_full = f0_full[valid_mask]
            if len(valid_full) > 0:
                f0_all.extend(valid_full.tolist())
        except Exception:
            pass

    return f0_all


def _f0_to_gender(f0_values: list[float], fallback_gender: str | None = None):
    """Classify a list of F0 values using median + histogram-mode agreement.

    Returns (gender, median_f0, mode_f0, confident: bool).
    """
    arr = np.array(f0_values, dtype=float)
    median_f0 = float(np.median(arr))

    # Histogram mode in 5 Hz bins — resistant to a handful of stray
    # outlier frames (e.g. a surviving music note) that would otherwise
    # drag the median around.
    bins = np.arange(FMIN, FMAX + 5, 5)
    hist, edges = np.histogram(arr, bins=bins)
    mode_idx = int(np.argmax(hist))
    mode_f0 = float((edges[mode_idx] + edges[mode_idx + 1]) / 2.0)

    median_gender = "Female" if median_f0 >= THRESHOLD else "Male"
    mode_gender = "Female" if mode_f0 >= THRESHOLD else "Male"

    near_boundary = abs(median_f0 - THRESHOLD) < HYSTERESIS
    agree = median_gender == mode_gender

    if fallback_gender in _VALID_GENDERS and (not agree or near_boundary):
        # Low-confidence read (disagreement between median/mode, or sitting
        # right on the boundary) — trust continuity/whole-clip context
        # instead of guessing.
        return fallback_gender, median_f0, mode_f0, False

    return median_gender, median_f0, mode_f0, agree


# ── Public API ────────────────────────────────────────────────────────────────

def detect_gender_from_audio(
    audio_source,
    sr_input: int = ANALYSIS_SR,
    sample_duration: float = SAMPLE_DURATION,
    fallback_gender: str | None = None,
) -> str:
    """
    Analyse audio file path OR numpy audio slice array and return 'Male' or 'Female'.
    """
    default_gender = fallback_gender if fallback_gender in _VALID_GENDERS else "Female"

    if isinstance(audio_source, str) and audio_source in _GENDER_CACHE:
        return _GENDER_CACHE[audio_source]

    if not LIBROSA_AVAILABLE:
        print(f"[GenderDetector] librosa not available — defaulting to {default_gender}.")
        return default_gender

    if isinstance(audio_source, str):
        if not audio_source or not os.path.exists(audio_source):
            print(f"[GenderDetector] File not found: '{audio_source}' — defaulting to {default_gender}.")
            return default_gender
        try:
            y, sr = librosa.load(
                audio_source, sr=ANALYSIS_SR, mono=True, duration=sample_duration
            )
        except Exception as e:
            print(f"[GenderDetector] Load error: {e} — defaulting to {default_gender}.")
            return default_gender
    elif isinstance(audio_source, np.ndarray):
        y, sr = audio_source, sr_input
    else:
        return default_gender

    if len(y) < int(sr * 0.15):
        return default_gender

    # Speech bandpass (80 Hz – 1200 Hz) to remove sub-bass rumble & high
    # music harmonics before any pitch/energy analysis.
    try:
        from scipy.signal import butter, filtfilt
        b, a = butter(4, [80.0 / (sr / 2.0), 1200.0 / (sr / 2.0)], btype='band')
        y_speech = filtfilt(b, a, y)
    except Exception:
        y_speech = y

    f0_values = _energy_gated_f0(y_speech, sr)

    if len(f0_values) < MIN_F0_VALUES:
        if f0_values:
            median_f0 = float(np.median(f0_values))
            gender = "Female" if median_f0 >= THRESHOLD else "Male"
            if abs(median_f0 - THRESHOLD) < HYSTERESIS and fallback_gender in _VALID_GENDERS:
                gender = fallback_gender
            if isinstance(audio_source, str):
                _GENDER_CACHE[audio_source] = gender
            return gender
        if isinstance(audio_source, str):
            _GENDER_CACHE[audio_source] = default_gender
        return default_gender

    gender, median_f0, mode_f0, confident = _f0_to_gender(f0_values, fallback_gender=fallback_gender)
    if isinstance(audio_source, str):
        _GENDER_CACHE[audio_source] = gender
    return gender


def precompute_whole_track_f0(y: np.ndarray, sr: int = ANALYSIS_SR, frame_length: int = 1024, hop_length: int = 256) -> np.ndarray | None:
    """Pre-compute per-frame F0 array across an entire audio track.

    Returns a 1D numpy array of frame F0 values (or np.nan for unvoiced/low-energy frames).
    Allows segment pitch analysis to slice precomputed frames in O(1) time instead of
    re-running librosa.pyin 50+ times sequentially.
    """
    if len(y) < int(sr * 0.15):
        return None

    try:
        from scipy.signal import butter, filtfilt
        b, a = butter(4, [80.0 / (sr / 2.0), 1200.0 / (sr / 2.0)], btype='band')
        y_speech = filtfilt(b, a, y)
    except Exception:
        y_speech = y

    try:
        f0_clean = _fast_autocorr_f0(y_speech, sr, frame_length=frame_length, hop_length=hop_length)
        if f0_clean is not None and len(f0_clean) > 0 and not np.all(np.isnan(f0_clean)):
            return f0_clean
    except Exception as ex:
        print(f"[GenderDetector] Fast autocorrelation note: {ex}")

    if LIBROSA_AVAILABLE:
        try:
            f0, voiced_flag, _ = librosa.pyin(
                y_speech, fmin=FMIN, fmax=FMAX, sr=sr,
                frame_length=frame_length, hop_length=hop_length
            )
            if f0 is not None and len(f0) > 0:
                return np.where(voiced_flag & ~np.isnan(f0), f0, np.nan)
        except Exception:
            pass

    return None


def detect_gender_from_f0_slice(
    f0_series: np.ndarray,
    start_sec: float,
    end_sec: float,
    sr: int = ANALYSIS_SR,
    hop_length: int = 256,
    fallback_gender: str | None = None,
) -> str:
    """Classify gender for a specific time window [start_sec, end_sec] by slicing a pre-computed F0 series.

    Runs in <0.0001s per segment.
    """
    default_gender = fallback_gender if fallback_gender in _VALID_GENDERS else "Female"
    if f0_series is None or len(f0_series) == 0:
        return default_gender

    pad = MAX_PAD_SEC
    st_padded = max(0.0, start_sec - pad)
    et_padded = end_sec + pad

    s_frame = max(0, int(round(st_padded * sr / hop_length)))
    e_frame = min(len(f0_series), int(round(et_padded * sr / hop_length)))

    if s_frame >= e_frame:
        return default_gender

    seg_frames = f0_series[s_frame:e_frame]
    valid_f0 = seg_frames[~np.isnan(seg_frames)].tolist()

    if len(valid_f0) < MIN_F0_VALUES:
        if valid_f0:
            median_f0 = float(np.median(valid_f0))
            gender = "Female" if median_f0 >= THRESHOLD else "Male"
            if abs(median_f0 - THRESHOLD) < HYSTERESIS and fallback_gender in _VALID_GENDERS:
                gender = fallback_gender
            return gender
        return default_gender

    gender, median_f0, mode_f0, confident = _f0_to_gender(valid_f0, fallback_gender=fallback_gender)
    return gender



def auto_select_voice(audio_path: str, lang_code: str, lang_voices: dict) -> str:
    """
    Auto-detect the predominant speaker gender and pick the best matching
    Neural TTS voice for the given language.

    Args:
        audio_path:  Path to the extracted audio file.
        lang_code:   Language code key (e.g., "km", "en").
        lang_voices: Dict of language voice config from SUPPORTED_LANGUAGES.

    Returns:
        The voice ID string (e.g., "km-KH-PisethNeural").
    """
    detected_gender = detect_gender_from_audio(audio_path)

    voices = lang_voices.get(lang_code, {}).get("voices", [])
    if not voices:
        return "km-KH-SreymomNeural"

    for voice in voices:
        if voice.get("gender", "").lower() == detected_gender.lower():
            print(f"[GenderDetector] Auto-selected voice: {voice['id']} ({detected_gender})")
            return voice["id"]

    fallback = voices[0]["id"]
    print(f"[GenderDetector] No {detected_gender} voice found — fallback: {fallback}")
    return fallback