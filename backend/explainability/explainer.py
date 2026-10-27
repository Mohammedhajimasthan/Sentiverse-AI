import re

from backend.preprocessing.cleaner import clean_text

POSITIVE_TOKENS = {
    "excellent", "great", "good", "love", "amazing", "happy", "fast", "smooth",
    "quality", "helpful", "easy", "affordable", "perfect", "satisfied", "nice"
}
NEGATIVE_TOKENS = {
    "bad", "poor", "late", "slow", "terrible", "broken", "damaged", "faulty",
    "disappointed", "expensive", "problem", "issue", "frustrating", "hard", "worst"
}
ASPECT_HINTS = {
    "Product Quality": {"good", "quality", "durable", "reliable", "excellent", "bad", "poor", "broken", "faulty"},
    "Price": {"expensive", "affordable", "price", "cheap", "costly", "value"},
    "Delivery": {"fast", "late", "slow", "delivery", "shipping", "arrived", "delayed"},
    "Customer Service": {"helpful", "support", "service", "unhelpful", "rude", "slow"},
    "Packaging": {"packaging", "box", "damaged", "nice", "secure", "wrapped"},
    "User Experience": {"easy", "smooth", "confusing", "difficult", "intuitive", "experience"},
}


def _tokenize(text):
    cleaned = clean_text(text or "").lower()
    return re.findall(r"[a-z0-9]+", cleaned)


def generate_explanation(review_text: str):
    text = review_text or ""
    tokens = _tokenize(text)
    if not tokens:
        return {"summary": "No review text available for explanation.", "positive_terms": [], "negative_terms": [], "aspects": []}

    positive_terms = sorted({token for token in tokens if token in POSITIVE_TOKENS})
    negative_terms = sorted({token for token in tokens if token in NEGATIVE_TOKENS})

    aspect_hits = []
    for aspect, hints in ASPECT_HINTS.items():
        if any(token in hints for token in tokens):
            aspect_hits.append(aspect)

    if positive_terms and negative_terms:
        summary = (
            f"The model is influenced by positive signals such as {', '.join(positive_terms[:3])} "
            f"and negative signals such as {', '.join(negative_terms[:3])}."
        )
    elif positive_terms:
        summary = f"The review is leaning positive because it contains positive cues like {', '.join(positive_terms[:3])}."
    elif negative_terms:
        summary = f"The review is leaning negative because it contains negative cues like {', '.join(negative_terms[:3])}."
    else:
        summary = "The review uses neutral wording, so the explanation is primarily based on context rather than obvious sentiment markers."

    if aspect_hits:
        summary += f" The main affected areas are {', '.join(aspect_hits[:3])}."

    return {
        "summary": summary,
        "positive_terms": positive_terms[:5],
        "negative_terms": negative_terms[:5],
        "aspects": aspect_hits[:5],
    }
