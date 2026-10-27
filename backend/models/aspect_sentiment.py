import re

from backend.models.aspect import ASPECT_KEYWORDS, extract_aspects
from backend.models.sentiment import predict_sentiment


ASPECT_SENTIMENT_HINTS = {
    "Sound Quality": {"positive": {"good", "great", "excellent", "clear", "balanced", "rich", "powerful", "crisp", "immersive", "deep"}, "negative": {"bad", "poor", "muddy", "distorted", "tinny", "weak", "unclear", "overwhelms"}},
    "Active Noise Cancellation": {"positive": {"good", "great", "excellent", "effective", "blocks", "quiet", "peaceful"}, "negative": {"bad", "poor", "barely", "ineffective", "weak", "little difference"}},
    "Ambient Mode": {"positive": {"natural", "clear", "useful", "good"}, "negative": {"unnatural", "poor", "bad", "muffled"}},
    "Spatial Audio": {"positive": {"fun", "immersive", "excellent", "good", "great"}, "negative": {"gimmicky", "poor", "bad", "unnatural"}},
    "Battery Life": {"positive": {"long", "lasts", "reliable", "all-day", "plenty"}, "negative": {"short", "shorter", "drains", "poor", "disappointing", "dies", "limited"}},
    "Charging": {"positive": {"fast", "quick", "convenient", "easy"}, "negative": {"slow", "longer", "faulty", "broken", "inconsistent"}},
    "Comfort and Fit": {"positive": {"comfortable", "secure", "light", "fits"}, "negative": {"uncomfortable", "hurts", "painful", "loose", "falls"}},
    "Microphone and Calls": {"positive": {"clear", "natural", "excellent", "good", "understand"}, "negative": {"poor", "wind", "unclear", "struggle", "muffled", "noisy"}},
    "Bluetooth and Pairing": {"positive": {"quick", "stable", "easy", "reliable"}, "negative": {"disconnects", "disconnect", "unstable", "difficult", "annoying", "drops"}},
    "Latency and Gaming": {"positive": {"low", "responsive", "smooth", "good"}, "negative": {"high", "lag", "delayed", "poor"}},
    "Product Quality": {"positive": {"good", "great", "excellent", "quality", "durable", "reliable", "smooth", "strong", "sturdy"}, "negative": {"bad", "poor", "cheap", "broken", "faulty", "fragile", "damaged", "weak", "flimsy"}},
    "Price": {"positive": {"affordable", "cheap", "value", "worth", "budget", "reasonable"}, "negative": {"expensive", "overpriced", "costly", "pricey", "too expensive"}},
    "Value for Money": {"positive": {"affordable", "value", "worth", "reasonable", "excellent"}, "negative": {"expensive", "overpriced", "costly", "poor"}},
    "Delivery": {"positive": {"fast", "quick", "on time", "timely", "arrived", "prompt"}, "negative": {"late", "slow", "delay", "delayed", "missing", "lost"}},
    "Customer Service": {"positive": {"helpful", "supportive", "friendly", "responsive", "polite", "resolved"}, "negative": {"rude", "slow", "unhelpful", "bad support", "ignored", "unresolved"}},
    "Packaging": {"positive": {"nice packaging", "well packed", "secure", "neat"}, "negative": {"damaged", "poor packaging", "broken box", "messy"}},
    "Warranty": {"positive": {"covered", "replacement", "helpful", "easy"}, "negative": {"denied", "rejected", "difficult", "poor", "unhelpful"}},
    "User Experience": {"positive": {"easy", "smooth", "intuitive", "simple", "comfortable", "straightforward"}, "negative": {"confusing", "difficult", "hard", "bad experience", "clumsy", "annoying"}},
    "General Feedback": {"positive": {"love", "great", "excellent", "amazing", "happy"}, "negative": {"bad", "poor", "terrible", "hate", "disappointed"}},
}

NEGATION_WORDS = {"not", "never", "no", "cannot", "can't", "won't", "hardly"}


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", str(text).lower())
    return re.sub(r"\s+", " ", text).strip()


def _score_term_hits(text, positive_terms, negative_terms):
    positive_hits = 0
    negative_hits = 0
    tokens = _clean_text(text).split()

    for phrase in positive_terms:
        if phrase in text:
            positive_hits += 1

    for phrase in negative_terms:
        if phrase in text:
            negative_hits += 1

    for index, token in enumerate(tokens):
        if token in NEGATION_WORDS and index + 1 < len(tokens):
            next_token = tokens[index + 1]
            if next_token in positive_terms:
                positive_hits -= 1
                negative_hits += 1
            if next_token in negative_terms:
                negative_hits -= 1
                positive_hits += 1

    return positive_hits - negative_hits


def _score_aspect_for_text(aspect, review_text):
    cleaned = _clean_text(review_text)
    hints = ASPECT_SENTIMENT_HINTS.get(aspect, {"positive": set(), "negative": set()})
    positive_terms = sorted(hints["positive"], key=len, reverse=True)
    negative_terms = sorted(hints["negative"], key=len, reverse=True)

    if aspect in ASPECT_KEYWORDS:
        matching_clauses = []
        for sentence in re.split(r"(?<=[.!?])\s+|[;\n]+", review_text):
            clauses = re.split(r"\b(?:but|however|although|though|whereas|while)\b", sentence, flags=re.IGNORECASE)
            for clause in clauses:
                normalized_clause = _clean_text(clause)
                if any(
                    re.search(r"\b" + re.escape(keyword) + r"\b", normalized_clause)
                    for keyword in ASPECT_KEYWORDS[aspect]
                ):
                    matching_clauses.append(normalized_clause)
        context = " ".join(matching_clauses) if matching_clauses else cleaned
    else:
        context = cleaned

    score = _score_term_hits(context, positive_terms, negative_terms)
    if score > 0:
        return "Positive", min(0.99, 0.55 + score * 0.18)
    if score < 0:
        return "Negative", min(0.99, 0.55 + abs(score) * 0.18)

    overall = predict_sentiment(context)
    return overall["label"], overall["confidence"]


def analyze_aspect_sentiment(review_text: str):
    if not review_text or not review_text.strip():
        return []

    aspects = extract_aspects(review_text)
    results = []

    for item in aspects:
        aspect = item["aspect"]
        sentiment_label, confidence = _score_aspect_for_text(aspect, review_text)
        results.append({
            "aspect": aspect,
            "sentiment": sentiment_label,
            "confidence": round(confidence, 3),
        })

    return results