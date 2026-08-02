# voices_config.py
"""
Configuration of supported languages and Microsoft Edge Neural TTS voices for Video Dubber.
Prioritized for Khmer (Cambodian / ភាសាខ្មែរ).
"""

SUPPORTED_LANGUAGES = {
    "km": {
        "name": "Khmer (ភាសាខ្មែរ - Cambodian)",
        "voices": [
            {"id": "km-KH-SreymomNeural", "name": "Sreymom - ស្រីមុំ (Female)", "gender": "Female"},
            {"id": "km-KH-PisethNeural", "name": "Piseth - ពិសិដ្ឋ (Male)", "gender": "Male"}
        ]
    },
    "vi": {
        "name": "Vietnamese (Tiếng Việt)",
        "voices": [
            {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My (Female)", "gender": "Female"},
            {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh (Male)", "gender": "Male"}
        ]
    },
    "en": {
        "name": "English",
        "voices": [
            {"id": "en-US-AvaNeural", "name": "Ava (Female - US)", "gender": "Female"},
            {"id": "en-US-AndrewNeural", "name": "Andrew (Male - US)", "gender": "Male"},
            {"id": "en-GB-SoniaNeural", "name": "Sonia (Female - UK)", "gender": "Female"},
            {"id": "en-GB-RyanNeural", "name": "Ryan (Male - UK)", "gender": "Male"}
        ]
    },
    "es": {
        "name": "Spanish (Español)",
        "voices": [
            {"id": "es-ES-ElviraNeural", "name": "Elvira (Female - Spain)", "gender": "Female"},
            {"id": "es-ES-AlvaroNeural", "name": "Álvaro (Male - Spain)", "gender": "Male"}
        ]
    },
    "fr": {
        "name": "French (Français)",
        "voices": [
            {"id": "fr-FR-DeniseNeural", "name": "Denise (Female)", "gender": "Female"},
            {"id": "fr-FR-HenriNeural", "name": "Henri (Male)", "gender": "Male"}
        ]
    },
    "de": {
        "name": "German (Deutsch)",
        "voices": [
            {"id": "de-DE-KatjaNeural", "name": "Katja (Female)", "gender": "Female"},
            {"id": "de-DE-ConradNeural", "name": "Conrad (Male)", "gender": "Male"}
        ]
    },
    "ja": {
        "name": "Japanese (日本語)",
        "voices": [
            {"id": "ja-JP-NanamiNeural", "name": "Nanami (Female)", "gender": "Female"},
            {"id": "ja-JP-KeitaNeural", "name": "Keita (Male)", "gender": "Male"}
        ]
    },
    "ko": {
        "name": "Korean (한국어)",
        "voices": [
            {"id": "ko-KR-SunHiNeural", "name": "Sun-Hi (Female)", "gender": "Female"},
            {"id": "ko-KR-InJoonNeural", "name": "In-Joon (Male)", "gender": "Male"}
        ]
    },
    "zh-CN": {
        "name": "Chinese Simplified (中文简体)",
        "voices": [
            {"id": "zh-CN-XiaoxiaoNeural", "name": "Xiaoxiao (Female)", "gender": "Female"},
            {"id": "zh-CN-YunjianNeural", "name": "Yunjian (Male)", "gender": "Male"}
        ]
    },
    "ru": {
        "name": "Russian (Русский)",
        "voices": [
            {"id": "ru-RU-SvetlanaNeural", "name": "Svetlana (Female)", "gender": "Female"},
            {"id": "ru-RU-DmitryNeural", "name": "Dmitry (Male)", "gender": "Male"}
        ]
    },
    "th": {
        "name": "Thai (ไทย)",
        "voices": [
            {"id": "th-TH-AcharaNeural", "name": "Achara (Female)", "gender": "Female"},
            {"id": "th-TH-NiwatNeural", "name": "Niwat (Male)", "gender": "Male"}
        ]
    },
    "id": {
        "name": "Indonesian (Bahasa Indonesia)",
        "voices": [
            {"id": "id-ID-GadisNeural", "name": "Gadis (Female)", "gender": "Female"},
            {"id": "id-ID-ArdiNeural", "name": "Ardi (Male)", "gender": "Male"}
        ]
    },
    "fil": {
        "name": "Filipino (Tagalog)",
        "voices": [
            {"id": "fil-PH-BlessicaNeural", "name": "Blessica (Female)", "gender": "Female"},
            {"id": "fil-PH-AngeloNeural", "name": "Angelo (Male)", "gender": "Male"}
        ]
    },
    "hi": {
        "name": "Hindi (हिन्दी)",
        "voices": [
            {"id": "hi-IN-SwaraNeural", "name": "Swara (Female)", "gender": "Female"},
            {"id": "hi-IN-MadhurNeural", "name": "Madhur (Male)", "gender": "Male"}
        ]
    },
    "ar": {
        "name": "Arabic (العربية)",
        "voices": [
            {"id": "ar-SA-ZariyahNeural", "name": "Zariyah (Female)", "gender": "Female"},
            {"id": "ar-SA-HamedNeural", "name": "Hamed (Male)", "gender": "Male"}
        ]
    },
    "pt": {
        "name": "Portuguese (Português)",
        "voices": [
            {"id": "pt-BR-FranciscaNeural", "name": "Francisca (Female)", "gender": "Female"},
            {"id": "pt-BR-AntonioNeural", "name": "Antônio (Male)", "gender": "Male"}
        ]
    },
    "it": {
        "name": "Italian (Italiano)",
        "voices": [
            {"id": "it-IT-ElsaNeural", "name": "Elsa (Female)", "gender": "Female"},
            {"id": "it-IT-DiegoNeural", "name": "Diego (Male)", "gender": "Male"}
        ]
    },
    "nl": {
        "name": "Dutch (Nederlands)",
        "voices": [
            {"id": "nl-NL-ColetteNeural", "name": "Colette (Female)", "gender": "Female"},
            {"id": "nl-NL-MaartenNeural", "name": "Maarten (Male)", "gender": "Male"}
        ]
    },
    "pl": {
        "name": "Polish (Polski)",
        "voices": [
            {"id": "pl-PL-ZofiaNeural", "name": "Zofia (Female)", "gender": "Female"},
            {"id": "pl-PL-MarekNeural", "name": "Marek (Male)", "gender": "Male"}
        ]
    },
    "tr": {
        "name": "Turkish (Türkçe)",
        "voices": [
            {"id": "tr-TR-EmelNeural", "name": "Emel (Female)", "gender": "Female"},
            {"id": "tr-TR-AhmetNeural", "name": "Ahmet (Male)", "gender": "Male"}
        ]
    },
    "uk": {
        "name": "Ukrainian (Українська)",
        "voices": [
            {"id": "uk-UA-PolinaNeural", "name": "Polina (Female)", "gender": "Female"},
            {"id": "uk-UA-OstapNeural", "name": "Ostap (Male)", "gender": "Male"}
        ]
    },
    "ms": {
        "name": "Malay (Bahasa Melayu)",
        "voices": [
            {"id": "ms-MY-YasminNeural", "name": "Yasmin (Female)", "gender": "Female"},
            {"id": "ms-MY-OsmanNeural", "name": "Osman (Male)", "gender": "Male"}
        ]
    },
    "lo": {
        "name": "Lao (ភាសាលាវ - ພາສາລາວ)",
        "voices": [
            {"id": "lo-LA-KeomanyNeural", "name": "Keomany (Female)", "gender": "Female"},
            {"id": "lo-LA-ChanthavongNeural", "name": "Chanthavong (Male)", "gender": "Male"}
        ]
    },
    "my": {
        "name": "Burmese (Myanmar)",
        "voices": [
            {"id": "my-MM-NilarNeural", "name": "Nilar (Female)", "gender": "Female"},
            {"id": "my-MM-ThihaNeural", "name": "Thiha (Male)", "gender": "Male"}
        ]
    }
}

def get_gender_voice_map(lang_code):
    """Return female and male voice IDs for a given language code."""
    female_voice = None
    male_voice = None
    if lang_code in SUPPORTED_LANGUAGES:
        voices = SUPPORTED_LANGUAGES[lang_code]["voices"]
        for v in voices:
            if v["gender"] == "Female" and not female_voice:
                female_voice = v["id"]
            elif v["gender"] == "Male" and not male_voice:
                male_voice = v["id"]
    return {
        "female": female_voice or "km-KH-SreymomNeural",
        "male": male_voice or "km-KH-PisethNeural"
    }

def get_default_voice(lang_code):
    """Return the first (female) voice ID for a given language, or Khmer female as fallback."""
    lang = SUPPORTED_LANGUAGES.get(lang_code)
    if lang and lang.get("voices"):
        return lang["voices"][0]["id"]
    return "km-KH-SreymomNeural"  # fallback to Khmer female

def get_voice_gender(voice_id, lang_code=None):
    """Return 'Female', 'Male', or 'Unknown' for a given voice ID."""
    v_id = str(voice_id or "").strip().lower()
    if not v_id or v_id == "auto":
        return "Unknown"
    for lang, data in SUPPORTED_LANGUAGES.items():
        for v in data.get("voices", []):
            if v["id"].lower() == v_id:
                return v.get("gender", "Female")
    if "sreymom" in v_id or "female" in v_id or "woman" in v_id:
        return "Female"
    if "piseth" in v_id or "male" in v_id or "man" in v_id:
        return "Male"
    return "Female"
