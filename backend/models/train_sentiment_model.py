from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

TRAINING_EXAMPLES = [
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


def train_and_save_model(output_path=None):
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, strip_accents="unicode")),
        ("clf", LogisticRegression(max_iter=2000, random_state=42, class_weight="balanced")),
    ])

    texts = [text for text, _ in TRAINING_EXAMPLES]
    labels = [label for _, label in TRAINING_EXAMPLES]
    pipeline.fit(texts, labels)

    target = output_path or Path(__file__).resolve().parents[2] / "models" / "sentiment_model.joblib"
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, target)
    return target


if __name__ == "__main__":
    path = train_and_save_model()
    print(f"Saved sentiment model to: {path}")
