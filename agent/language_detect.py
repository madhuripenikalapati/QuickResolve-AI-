"""Keyword-based language detector for Indian languages in romanized script."""

import re

# Only unambiguous, word-boundary-safe keywords — no single chars or common substrings
LANGUAGE_KEYWORDS = {
    "Telugu": [
        "unnaya", "unnai", "unnayi", "unnaru", "emain", "cheppandi", "chudandi",
        "kaavali", "kavali", "bagundi", "ledha", "ledu", "naaku", "meeru",
        "ikkade", "akkade", "cheyandi", "pampandi", "undaa",
        "enduku", "evaru", "ekkada", "eppudu",
        "evari", "deggara", "dorukutundi",
        "chesukuntanu", "chesukunta", "chesthanu", "cheyali", "cheyyali",
        "nachutundi", "theesukuntanu", "konukuntanu",
        "pampinchu", "ivvandi",
    ],
    # Short Telugu words checked word-boundary only (added separately below)
    "Tamil": [
        "irukka", "iruku", "irruku", "sollu", "solunga", "illai",
        "nalla", "epdi", "yenna", "parunga", "kudunga",
        "vanakkam", "seri", "ungaluku", "enakku", "eppo", "enge", "eppadi",
    ],
    "Kannada": [
        "idya", "bidi", "yenu", "nimage", "hogali",
        "bekaa", "beka", "helri", "yelli",
    ],
    "Malayalam": [
        "undo", "ille", "entha", "njan", "ningal",
        "paranju", "tharaam", "parayoo", "sheriyaa", "okke",
    ],
    "Bengali": [
        "ache", "keno", "kothai", "kobe", "apni", "tumi",
        "deben", "neben", "hobe",
    ],
    "Marathi": [
        "aahe", "kuthe", "keva", "tumhi",
        "sanga", "dyaa", "ghyaa",
    ],
}

# Short Telugu words that need word-boundary matching to avoid substring false positives
TELUGU_WORD_BOUNDARY = [
    "undi", "emi", "andi", "chala", "ayte", "naku", "mee", "ela",
    "anni", "unda", "istam", "istanu",
]

HINDI_MARKERS = ["hai", "hain", "kya", "nahi", "chahiye", "dikhao", "batao", "haan", "theek"]


def detect_language(text: str) -> str:
    """
    Returns detected language name, or 'Hindi' for Hinglish, or 'English' as default.
    Uses substring matching for long keywords, word-boundary matching for short ones.
    """
    text_lower = text.lower()
    words = set(re.split(r'[\s,!?./\-]+', text_lower))

    scores: dict[str, int] = {}

    for lang, keywords in LANGUAGE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[lang] = scores.get(lang, 0) + score

    # Short Telugu words — word-boundary only
    telugu_short_score = sum(1 for kw in TELUGU_WORD_BOUNDARY if kw in words)
    if telugu_short_score > 0:
        scores["Telugu"] = scores.get("Telugu", 0) + telugu_short_score

    if scores:
        return max(scores, key=scores.get)

    hindi_score = sum(1 for hw in HINDI_MARKERS if hw in words)
    if hindi_score >= 1:
        return "Hindi"

    return "English"
