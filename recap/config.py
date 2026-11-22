import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root
def env_bool(name, default=False):
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")

CHANNEL_ID = "UCNzmmbXIbMzlqE8nD1PBXfg"          # Dangal TV official channel
FEED = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
W, H, FPS = 1920, 1080, 24
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION") or "v26.0"
VOICE = os.getenv("SERIAL_VOICE") or "hi-IN-SwaraNeural"
CHANNEL_NAME = os.getenv("SERIAL_CHANNEL_NAME") or "सीरियल की कहानी"
WPS = 2.3
IMAGES_PER_SCENE = int(os.getenv("IMAGES_PER_SCENE") or 2)   # 2 = a wide shot + a close-up per scene (more visual variety)
CUT_SECONDS = 2.6                                           # fast visual cut every ~2.6 s (framing changes every cut)
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME") or 0.15)     # background music volume relative to narration
OUTRO_LINE = "अगर आपको ऐसी डेली अपडेट्स पसंद आती हैं तो चैनल को सब्सक्राइब ज़रूर करें।"
BASE_TAGS = ["serial summary", "serial story in hindi", "today episode", "full episode summary", "episode summary in hindi",
             "hindi serial", "hindi tv serial", "dangal tv serial", "dangal tv", "आज का एपिसोड", "आज की कहानी", "सीरियल की कहानी",
             "serial update", "tv serial recap", "episode review", "kal ka episode", "next episode prediction", "serial twist"]
# match = lowercase text that must appear in the video title
SHOWS = {
    "kaisi":      {"match": "kaisi teri dillagi",     "en": "Kaisi Teri Dillagi",      "hi": "कैसी तेरी दिल्लगी",       "alt": ["kaisi teri dilagi", "kaisi teri dillagi serial"]},
    "bhabhi":     {"match": "hamari bhabhi number 1", "en": "Hamari Bhabhi Number 1",  "hi": "हमारी भाभी नंबर 1",      "alt": ["hamari bhabhi no 1", "hamari bhabhi number one"]},
    "sohni":      {"match": "sohni",                  "en": "Sohni Aur Nahi Koi Honi", "hi": "सोहनी और नहीं कोई होनी",   "alt": ["sohni serial", "sohni aur nahi koi honi"]},
    "rimjhim":    {"match": "rimjhim",                "en": "Rimjhim Choti Umar Bada Safar", "hi": "रिमझिम छोटी उम्र बड़ा सफर", "alt": ["rimjhim choti umar bada safar", "rimjhim serial"]},
    "mannsundar": {"match": "mann sundar",            "en": "Mann Sundar",             "hi": "मन सुंदर",               "alt": ["man sundar", "mann sundar serial"]},
    "atisundar":  {"match": "mann atisundar",         "en": "Mann Atisundar",          "hi": "मन अतिसुंदर",            "alt": ["man atisundar", "mann atisundar serial", "mann ati sundar"]},
    "patibrahma": {"match": "pati brahmachari",       "en": "Pati Brahmachari",        "hi": "पति ब्रह्मचारी",          "alt": ["pati brahmachari serial", "pati bramhachari"]},
    "ishq":       {"match": "ishq junooni",           "en": "Ishq Junooni",            "hi": "इश्क़ जुनूनी",            "alt": ["ishq junooni serial", "ishq jununi"]},
    "saanche": {
        "match": "saanche darbar ki jai dhyanu bhagat ki amar kahani",
        "en": "Saanche Darbar Ki Jai Dhyanu Bhagat Ki Amar Kahani",
        "hi": "सांचे दरबार की जय ध्यानु भगत की अमर कहानी",
        "alt": ["sanche darbar ki jai dhyanu bhagat ki amar kahani", "saanche darbaar ki jai dhyanu bhagat ki amar kahani"],
    },
}
HI_MONTHS = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
EMOTION_COLORS = {"tense": (200, 90, 0), "sad": (40, 90, 170), "happy": (30, 150, 70), "angry": (190, 20, 30),
                  "romantic": (190, 40, 120), "shock": (120, 40, 170)}
STYLE = ("graphic novel illustration, dramatic cinematic lighting, rich saturated colors, painterly, Indian family drama, "
         "expressive faces, wide shot, family friendly, no text, no letters, no watermark, no gore")
