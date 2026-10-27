import warnings
from pathlib import Path

import joblib

from backend.preprocessing.cleaner import clean_text, expand_emoji_cues

warnings.filterwarnings("ignore", message=".*Unknown solver options: iprint.*")

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

POSITIVE_WORDS = {
    "excellent", "great", "good", "amazing", "nice", "happy", "fast", "smooth",
    "reliable", "quality", "love", "easy", "helpful", "value", "best", "perfect",
    "impressed", "supports", "affordable", "durable", "clean", "satisfied",
    "fantastic", "wonderful", "awesome", "premium", "improve", "smoothly",
    "clear", "balanced", "rich", "powerful", "crisp", "blocks", "block",
    "peaceful", "lasts", "plenty", "quick", "stable", "comfortable", "secure",
    "natural", "fun", "compact", "sturdy", "straightforward", "resolved",
    "immersive", "reliable", "neat", "pleasant", "responsive", "convenient",
}

NEGATIVE_WORDS = {
    "bad", "poor", "late", "slow", "terrible", "broken", "issue", "problem",
    "worst", "disappointed", "damaged", "delay", "expensive", "hard", "difficult",
    "worse", "not", "never", "fragile", "missing", "faulty", "cheap", "hate",
    "unhappy", "annoying", "wrong", "confusing", "buggy", "limited",
    "muddy", "barely", "shorter", "drains", "disappointing", "disconnects",
    "disconnect", "hurts", "painful", "flimsy", "unclear", "struggle", "overwhelms",
    "wind", "uncomfortable", "unstable", "drops", "faulty", "gimmicky"
}

NEGATION_WORDS = {"not", "never", "no", "cannot", "can't", "won't", "hardly"}

MODEL_TRAINING_EXAMPLES = [
    ("excellent product quality and fast delivery", "Positive"),
    ("really love this product and packaging was nice", "Positive"),
    ("customer service was helpful and response was quick", "Positive"),
    ("easy to use and very smooth experience", "Positive"),
    ("great value for money and affordable price", "Positive"),
    ("overall good experience with quality and support", "Positive"),
    ("average product with okay quality", "Neutral"),
    ("fine but nothing special", "Neutral"),
    ("it works okay and the experience was acceptable", "Neutral"),
    ("delivery was late and support was poor", "Negative"),
    ("product quality is bad and packaging was damaged", "Negative"),
    ("terrible service and the product broke quickly", "Negative"),
    ("very disappointed with slow response and expensive price", "Negative"),
    ("worst experience ever, faulty and frustrating", "Negative"),
    ("broken on arrival and customer care was unhelpful", "Negative"),
]

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "sentiment_model.joblib"


def _build_model():
    if not SKLEARN_AVAILABLE:
        return None
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, strip_accents="unicode")),
        ("clf", LogisticRegression(max_iter=2000, random_state=42, class_weight="balanced")),
    ])
    texts = [text for text, _ in MODEL_TRAINING_EXAMPLES]
    labels = [label for _, label in MODEL_TRAINING_EXAMPLES]
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


class SentimentModel:
    def __init__(self):
        self.pipeline = _load_or_train_model()

    def predict(self, text: str):
        if not text or not str(text).strip():
            return {"label": "Neutral", "confidence": 0.0}

        cleaned = clean_text(text).lower()
        if not cleaned:
            return {"label": "Neutral", "confidence": 0.0}

        if self.pipeline is None:
            return _fallback_predict(cleaned)

        probabilities = self.pipeline.predict_proba([cleaned])[0]
        index = int(probabilities.argmax())
        label = str(self.pipeline.classes_[index])
        confidence = float(probabilities[index])
        return {"label": label, "confidence": round(min(confidence, 0.99), 3)}


MODEL = SentimentModel()


def _fallback_predict(cleaned_text: str):
    tokens = cleaned_text.split()
    score = 0

    for idx, token in enumerate(tokens):
        if token in POSITIVE_WORDS:
            score += 1
            if idx > 0 and tokens[idx - 1] in NEGATION_WORDS:
                score -= 2
        elif token in NEGATIVE_WORDS:
            score -= 1
            if idx > 0 and tokens[idx - 1] in NEGATION_WORDS:
                score += 2

    if score > 0:
        label = "Positive"
    elif score < 0:
        label = "Negative"
    else:
        label = "Neutral"

    confidence = 0.55 if score == 0 else min(0.98, 0.60 + abs(score) * 0.10)
    return {"label": label, "confidence": round(confidence, 3)}


def predict_sentiment(text: str):
    cleaned = clean_text(expand_emoji_cues(text or "")).lower()
    if not cleaned:
        return {"label": "Neutral", "confidence": 0.0}

    rule_result = _fallback_predict(cleaned)
    model_result = MODEL.predict(cleaned)

    rule_hits = any(token in POSITIVE_WORDS or token in NEGATIVE_WORDS for token in cleaned.split())
    if rule_hits and (rule_result["label"] != model_result["label"] or model_result["confidence"] < 0.6):
        return rule_result

    return model_result
