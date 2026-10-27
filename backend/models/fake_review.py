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

GENERIC_WORDS = {"good", "nice", "great", "excellent", "love", "best", "amazing", "perfect", "awesome", "fantastic"}
RETENTION_WORDS = {"delivery", "quality", "service", "price", "support", "packaging", "product", "experience", "battery", "screen", "shipping"}

FAKE_REVIEW_TRAINING_EXAMPLES = [
    ("Amazing product! Great! Love it! Best ever!", "Suspicious"),
    ("Excellent quality, I love this product so much", "Suspicious"),
    ("Great great great product amazing best ever", "Suspicious"),
    ("The product quality is excellent and the battery is reliable", "Genuine"),
    ("Delivery was late and support was slow but the product quality is decent", "Genuine"),
    ("I was disappointed with the packaging and the shipping took too long", "Genuine"),
    ("Love it! Best service ever! Amazing quality!", "Suspicious"),
    ("The item arrived damaged and customer service was unhelpful", "Genuine"),
    ("Wonderful product and helpful support team", "Genuine"),
    ("Amazing amazing amazing! Perfect purchase!", "Suspicious"),
    ("Product quality is poor and the price is too high", "Genuine"),
    ("This is the best product ever, definitely worth it", "Suspicious"),
]

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "fake_review_model.joblib"


def _build_model():
    if not SKLEARN_AVAILABLE:
        return None
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, strip_accents="unicode")),
        ("clf", LogisticRegression(max_iter=2500, random_state=42, class_weight="balanced")),
    ])
    texts = [text for text, _ in FAKE_REVIEW_TRAINING_EXAMPLES]
    labels = [label for _, label in FAKE_REVIEW_TRAINING_EXAMPLES]
    pipeline.fit(texts, labels)
    return pipeline


def _load_or_train_model():
    if not SKLEARN_AVAILABLE:
        return None
    if MODEL_PATH.exists():
        try:
            return joblib.load(MODEL_PATH)
        except Exception:
            pass
    model = _build_model()
    try:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, MODEL_PATH)
    except Exception:
        pass
    return model


def _heuristic_fake_review(review_text: str):
    text = clean_text(review_text or "")
    if not text:
        return {"review_type": "Genuine", "confidence": 0.0}

    words = text.lower().split()
    generic_count = sum(1 for w in words if w in GENERIC_WORDS)
    repeated_word_count = sum(1 for w in set(words) if words.count(w) > 1)
    text_length = len(words)
    specific_count = sum(1 for w in words if w in RETENTION_WORDS)
    exclamation_count = text.count("!")
    caps_ratio = sum(1 for ch in text if ch.isupper()) / max(1, len(text))

    suspicious_score = 0

    if generic_count >= 2 and text_length <= 25:
        suspicious_score += 2
    if repeated_word_count >= 2:
        suspicious_score += 1
    if exclamation_count >= 2:
        suspicious_score += 1
    if caps_ratio > 0.08:
        suspicious_score += 1
    if specific_count == 0 and generic_count >= 2:
        suspicious_score += 1
    if text_length <= 10 and generic_count >= 1:
        suspicious_score += 1

    suspicious = suspicious_score >= 2
    confidence = 0.15 if not suspicious else min(0.99, 0.55 + suspicious_score * 0.12)

    return {"review_type": "Suspicious" if suspicious else "Genuine", "confidence": round(confidence, 3)}


def detect_fake_review(review_text: str):
    text = clean_text(review_text or "")
    if not text:
        return {"review_type": "Genuine", "confidence": 0.0}

    if SKLEARN_AVAILABLE:
        model = _load_or_train_model()
        if model is not None:
            pred = model.predict([text])[0]
            proba = model.predict_proba([text])[0]
            confidence = float(proba[model.classes_.tolist().index(pred)])
            return {"review_type": pred, "confidence": round(min(confidence, 0.99), 3)}

    return _heuristic_fake_review(text)
