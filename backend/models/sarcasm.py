from pathlib import Path

import joblib

from backend.preprocessing.cleaner import clean_text

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

POSITIVE_WORDS = {"great", "excellent", "love", "amazing", "perfect", "fantastic", "awesome", "wonderful", "brilliant"}
NEGATIVE_WORDS = {"late", "delay", "bad", "poor", "terrible", "broken", "slow", "worst", "disappointed", "damaged", "frustrating"}
CONTRAST_WORDS = {"but", "however", "though", "yet", "except"}
SARCASM_PHRASES = [
    "great job",
    "love it when",
    "fantastic service",
    "excellent experience",
    "perfect timing",
    "yeah right",
    "sure, great",
]

SARCASTIC_TRAINING_EXAMPLES = [
    ("Great job, the product broke after one day", "Sarcastic"),
    ("Love it when the delivery is delayed for a week", "Sarcastic"),
    ("Fantastic service, the support team never replied", "Sarcastic"),
    ("Excellent quality, the item was damaged on arrival", "Sarcastic"),
    ("The product is great and the battery died immediately", "Sarcastic"),
    ("Perfect timing, the app crashed during checkout", "Sarcastic"),
    ("The service was helpful and the package arrived on time", "Non-Sarcastic"),
    ("I am happy with the product quality and fast shipping", "Non-Sarcastic"),
    ("The experience was smooth and the support was responsive", "Non-Sarcastic"),
    ("Delivery was quick and the packaging was secure", "Non-Sarcastic"),
]

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "sarcasm_model.joblib"
MODEL_VERSION = 2


def _build_model():
    if not SKLEARN_AVAILABLE:
        return None
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, strip_accents="unicode")),
        ("clf", LogisticRegression(max_iter=2500, random_state=42, class_weight="balanced")),
    ])
    texts = [text for text, _ in SARCASTIC_TRAINING_EXAMPLES]
    labels = [label for _, label in SARCASTIC_TRAINING_EXAMPLES]
    pipeline.fit(texts, labels)
    pipeline._sentiverse_version_ = MODEL_VERSION
    return pipeline


def _load_or_train_model():
    if not SKLEARN_AVAILABLE:
        return None
    if MODEL_PATH.exists():
        try:
            model = joblib.load(MODEL_PATH)
            if getattr(model, "_sentiverse_version_", None) == MODEL_VERSION:
                return model
        except Exception:
            pass
    model = _build_model()
    try:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, MODEL_PATH)
    except Exception:
        pass
    return model


def _heuristic_sarcasm(text):
    words = set(text.split())
    positive_hits = sum(1 for word in POSITIVE_WORDS if word in words)
    negative_hits = sum(1 for word in NEGATIVE_WORDS if word in words)
    contrast_hits = sum(1 for word in CONTRAST_WORDS if word in words)
    phrase_hits = sum(1 for phrase in SARCASM_PHRASES if phrase in text)
    direct_irony_markers = any(marker in text for marker in ["yeah right", "sure", "great job", "love it when", "perfect timing", "as expected"])
    exclamation_count = text.count("!")

    score = 0
    if positive_hits:
        score += positive_hits
    if negative_hits:
        score += negative_hits
    if contrast_hits:
        score += contrast_hits
    if phrase_hits:
        score += phrase_hits * 2
    if exclamation_count:
        score += 1

    sarcastic = False
    if phrase_hits > 0 or direct_irony_markers:
        sarcastic = True
    elif positive_hits > 0 and negative_hits > 0 and contrast_hits > 0 and score >= 5:
        sarcastic = True

    confidence = 0.12 if not sarcastic else min(0.99, 0.5 + score * 0.09)

    if sarcastic and not direct_irony_markers and not phrase_hits and positive_hits == 1 and negative_hits == 1 and contrast_hits == 1:
        sarcastic = False
        confidence = 0.15

    return {"sarcasm": "Sarcastic" if sarcastic else "Non-Sarcastic", "confidence": round(confidence, 3)}


def detect_sarcasm(review_text: str):
    text = clean_text(review_text or "").lower()
    if not text:
        return {"sarcasm": "Non-Sarcastic", "confidence": 0.0}

    heuristic = _heuristic_sarcasm(text)
    if text and any(marker in text for marker in ["yeah right", "sure", "great job", "love it when", "perfect timing", "as expected"]):
        return heuristic

    if heuristic["sarcasm"] == "Non-Sarcastic":
        return heuristic

    if SKLEARN_AVAILABLE:
        model = _load_or_train_model()
        if model is not None:
            pred = model.predict([text])[0]
            proba = model.predict_proba([text])[0]
            confidence = float(proba[model.classes_.tolist().index(pred)])
            return {"sarcasm": pred, "confidence": round(min(confidence, 0.99), 3)}

    return heuristic
