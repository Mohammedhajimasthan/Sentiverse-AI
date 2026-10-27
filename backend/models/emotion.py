from pathlib import Path

import joblib

from backend.preprocessing.cleaner import clean_text, expand_emoji_cues

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

EMOTION_KEYWORDS = {
    "Joy": {"happy", "great", "excellent", "amazing", "satisfied", "good", "enjoyed", "pleasant", "delighted"},
    "Anger": {"angry", "terrible", "hate", "annoyed", "frustrated", "mad", "furious", "upset"},
    "Sadness": {"sad", "disappointed", "upset", "hurt", "bad", "poor", "regret", "letdown"},
    "Fear": {"worried", "afraid", "scared", "concerned", "nervous", "unsafe", "panic"},
    "Surprise": {"wow", "unexpected", "shocked", "surprised", "amazing", "astounded"},
    "Love": {"love", "adore", "favorite", "perfect", "cherish", "loyal"},
    "Neutral": {"okay", "fine", "average", "normal", "standard"},
}

PHRASE_WEIGHTS = {
    "love this product": "Love",
    "great job": "Joy",
    "very happy": "Joy",
    "so disappointed": "Sadness",
    "really angry": "Anger",
    "worried about": "Fear",
    "unexpectedly good": "Surprise",
    "totally shocked": "Surprise",
    "very bad": "Sadness",
    "super frustrated": "Anger",
}

EMOTION_TRAINING_EXAMPLES = [
    ("I am very happy with the product quality and fast delivery", "Joy"),
    ("The product is excellent and I love it", "Love"),
    ("This was a great experience and the service was helpful", "Joy"),
    ("I am disappointed because the product arrived damaged", "Sadness"),
    ("The customer support was terrible and I am really angry", "Anger"),
    ("I am worried that the battery will fail soon", "Fear"),
    ("Wow, I did not expect the packaging to be so good", "Surprise"),
    ("The product is okay and the experience was fine", "Neutral"),
    ("I am very satisfied with the quality and price", "Joy"),
    ("This was frustrating and the order was delayed", "Anger"),
    ("I was shocked by how smooth and easy it was to use", "Surprise"),
    ("I feel hurt because the item broke quickly", "Sadness"),
    ("The service was polite and I am happy overall", "Joy"),
    ("I am worried about the quality and safety", "Fear"),
]

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "emotion_model.joblib"


def _build_model():
    if not SKLEARN_AVAILABLE:
        return None
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, strip_accents="unicode")),
        ("clf", LogisticRegression(max_iter=2500, random_state=42, class_weight="balanced")),
    ])
    texts = [text for text, _ in EMOTION_TRAINING_EXAMPLES]
    labels = [label for _, label in EMOTION_TRAINING_EXAMPLES]
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


def _heuristic_emotion(text):
    scores = {emotion: 0 for emotion in EMOTION_KEYWORDS}
    words = text.split()
    word_counts = {}
    for word in words:
        word_counts[word] = word_counts.get(word, 0) + 1

    for emotion, keywords in EMOTION_KEYWORDS.items():
        for keyword in keywords:
            scores[emotion] += word_counts.get(keyword, 0)

    for phrase, emotion in PHRASE_WEIGHTS.items():
        if phrase in text:
            scores[emotion] += 2

    if "but" in words and any(word in words for word in {"love", "great", "excellent", "amazing", "happy"}):
        negative_after_but = any(word in words for word in {"bad", "poor", "broken", "slow", "terrible", "late", "disappointed"})
        if negative_after_but:
            scores["Anger"] += 2
            scores["Sadness"] += 1

    best_emotion = max(scores, key=scores.get)
    max_score = scores[best_emotion]
    total_score = sum(scores.values())

    if max_score <= 0:
        return {"emotion": "Neutral", "confidence": 0.35}

    confidence = 0.55 + (max_score / max(1, total_score)) * 0.35 + min(0.2, max_score * 0.05)
    return {"emotion": best_emotion, "confidence": round(min(confidence, 0.99), 3)}


def detect_emotion(review_text: str):
    text = clean_text(expand_emoji_cues(review_text or "")).lower()
    if not text:
        return {"emotion": "Neutral", "confidence": 0.0}

    if SKLEARN_AVAILABLE:
        model = _load_or_train_model()
        if model is not None:
            pred = model.predict([text])[0]
            proba = model.predict_proba([text])[0]
            confidence = float(proba[model.classes_.tolist().index(pred)])
            return {"emotion": pred, "confidence": round(min(confidence, 0.99), 3)}

    return _heuristic_emotion(text)
