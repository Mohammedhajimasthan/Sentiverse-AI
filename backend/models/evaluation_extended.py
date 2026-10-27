from backend.models.evaluation import evaluate_sentiment_model
from backend.models.emotion import _load_or_train_model as load_emotion_model
from backend.models.fake_review import _load_or_train_model as load_fake_model
from backend.models.sarcasm import _load_or_train_model as load_sarcasm_model
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support


EMOTION_VALIDATION = [
    ("I am very happy with the product quality and shipping", "Joy"),
    ("The service was terrible and I am furious", "Anger"),
    ("I was disappointed because the item arrived broken", "Sadness"),
    ("I am worried the battery will fail soon", "Fear"),
    ("Wow, I did not expect it to be this good", "Surprise"),
    ("I love this product and it is perfect", "Love"),
    ("The product is okay and the experience was fine", "Neutral"),
    ("I am satisfied with the support team and the quality", "Joy"),
]

SARCASM_VALIDATION = [
    ("Great job, the charger broke after one day", "Sarcastic"),
    ("Love it when the delivery is delayed for a week", "Sarcastic"),
    ("Fantastic service, the support team never replied", "Sarcastic"),
    ("The product is good and the packaging was neat", "Non-Sarcastic"),
    ("Customer service was helpful and the order arrived fast", "Non-Sarcastic"),
    ("Excellent experience, everything worked perfectly", "Non-Sarcastic"),
    ("Perfect timing, it crashed right before checkout", "Sarcastic"),
    ("The delivery was quick and the quality was excellent", "Non-Sarcastic"),
]

FAKE_REVIEW_VALIDATION = [
    ("Amazing product! Great! Love it! Best ever!", "Suspicious"),
    ("Great great great product amazing best ever", "Suspicious"),
    ("The item arrived damaged and the support team was rude", "Genuine"),
    ("I am happy with the quality and packaging", "Genuine"),
    ("Excellent quality, battery life is great and reliable", "Genuine"),
    ("Best product ever! Amazing quality!", "Suspicious"),
    ("Delivery was slow and the product was faulty", "Genuine"),
    ("Perfect! Wonderful! Outstanding! Love it!", "Suspicious"),
]


def _calculate_metrics(actual, predicted, labels):
    accuracy = accuracy_score(actual, predicted)
    precision, recall, f1, _ = precision_recall_fscore_support(
        actual, predicted, labels=labels, average="weighted", zero_division=0
    )
    matrix = confusion_matrix(actual, predicted, labels=labels).tolist()
    return {
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1_score": round(float(f1), 4),
        "labels": labels,
        "confusion_matrix": matrix,
    }


def evaluate_emotion_model():
    model = load_emotion_model()
    if model is None:
        return {"status": "unavailable", "message": "scikit-learn is not available."}
    texts = [text for text, _ in EMOTION_VALIDATION]
    actual = [label for _, label in EMOTION_VALIDATION]
    predicted = [model.predict([text])[0] for text in texts]
    return {"status": "ok", "model_type": type(model).__name__, **_calculate_metrics(actual, predicted, ["Joy", "Anger", "Sadness", "Fear", "Surprise", "Love", "Neutral"])}


def evaluate_sarcasm_model():
    model = load_sarcasm_model()
    if model is None:
        return {"status": "unavailable", "message": "scikit-learn is not available."}
    texts = [text for text, _ in SARCASM_VALIDATION]
    actual = [label for _, label in SARCASM_VALIDATION]
    predicted = [model.predict([text])[0] for text in texts]
    return {"status": "ok", "model_type": type(model).__name__, **_calculate_metrics(actual, predicted, ["Sarcastic", "Non-Sarcastic"])}


def evaluate_fake_review_model():
    model = load_fake_model()
    if model is None:
        return {"status": "unavailable", "message": "scikit-learn is not available."}
    texts = [text for text, _ in FAKE_REVIEW_VALIDATION]
    actual = [label for _, label in FAKE_REVIEW_VALIDATION]
    predicted = [model.predict([text])[0] for text in texts]
    return {"status": "ok", "model_type": type(model).__name__, **_calculate_metrics(actual, predicted, ["Suspicious", "Genuine"])}


def evaluate_all_models():
    sentiment = evaluate_sentiment_model()
    emotion = evaluate_emotion_model()
    sarcasm = evaluate_sarcasm_model()
    fake = evaluate_fake_review_model()
    return {
        "sentiment": sentiment,
        "emotion": emotion,
        "sarcasm": sarcasm,
        "fake_review": fake,
        "summary": {
            "sentiment_accuracy": sentiment.get("overall", {}).get("accuracy"),
            "emotion_accuracy": emotion.get("accuracy"),
            "sarcasm_accuracy": sarcasm.get("accuracy"),
            "fake_review_accuracy": fake.get("accuracy"),
        },
    }
