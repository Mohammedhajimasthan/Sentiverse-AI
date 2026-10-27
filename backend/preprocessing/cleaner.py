import re

EMOJI_CUES = {
    "😊": " happy ",
    "☺": " happy ",
    "😀": " happy ",
    "😃": " happy ",
    "😄": " happy ",
    "😁": " happy ",
    "😆": " happy ",
    "😂": " happy ",
    "🥰": " love ",
    "😍": " love ",
    "😘": " love ",
    "🤩": " love ",
    "🥳": " happy ",
    "👍": " good ",
    "🙏": " grateful ",
    "✨": " good ",
    "❤️": " love ",
    "❤": " love ",
    "💖": " love ",
    "😡": " angry ",
    "🤬": " angry ",
    "😠": " angry ",
    "😞": " disappointed ",
    "😔": " disappointed ",
    "🙁": " disappointed ",
    "☹": " disappointed ",
    "😢": " sad ",
    "😭": " sad ",
    "👎": " bad ",
    "💔": " sad ",
    "🤮": " terrible ",
}


def expand_emoji_cues(text: str) -> str:
    for emoji, cue in EMOJI_CUES.items():
        text = text.replace(emoji, cue)
    return text


def clean_text(text: str):
    if text is None:
        return ""

    text = str(text)
    text = text.strip()
    text = re.sub(r"http\S+|www\.\S+", " ", text)
    text = re.sub(r"@\w+|#\w+", " ", text)
    text = re.sub(r"[^a-zA-Z0-9\s,!?.'-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text(text: str):
    return clean_text(text).lower()


def preprocess_review(text: str):
    cleaned = clean_text(text)
    return re.sub(r"\s+", " ", cleaned).strip()
