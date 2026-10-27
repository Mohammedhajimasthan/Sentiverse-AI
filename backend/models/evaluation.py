from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

from backend.models.prepare_evaluation_dataset import DATASET_PATH, METADATA_PATH
from backend.models.sentiment import MODEL, predict_sentiment

LABELS = ["Negative", "Positive", "Neutral"]


def _metrics(actual: list[str], predicted: list[str]) -> dict:
    precision, recall, f1, _ = precision_recall_fscore_support(
        actual,
        predicted,
        labels=LABELS,
        average="weighted",
        zero_division=0,
    )
    macro_precision, macro_recall, macro_f1, _ = precision_recall_fscore_support(
        actual,
        predicted,
        labels=LABELS,
        average="macro",
        zero_division=0,
    )
    return {
        "sample_count": len(actual),
        "accuracy": round(float(accuracy_score(actual, predicted)), 4),
        "weighted_precision": round(float(precision), 4),
        "weighted_recall": round(float(recall), 4),
        "weighted_f1": round(float(f1), 4),
        "macro_precision": round(float(macro_precision), 4),
        "macro_recall": round(float(macro_recall), 4),
        "macro_f1": round(float(macro_f1), 4),
        "labels": LABELS,
        "confusion_matrix": confusion_matrix(actual, predicted, labels=LABELS).tolist(),
    }


def evaluate_sentiment_model(dataset_path: Path = DATASET_PATH) -> dict:
    dataset_path = Path(dataset_path)
    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"Evaluation dataset not found at {dataset_path}. "
            "Prepare it with `python -m backend.models.prepare_evaluation_dataset`."
        )
    if MODEL.pipeline is None:
        return {"status": "unavailable", "message": "scikit-learn is not available."}

    test_records = []
    with dataset_path.open(newline="", encoding="utf-8-sig") as dataset_file:
        reader = csv.DictReader(dataset_file)
        required_columns = {"text", "label", "domain", "split"}
        if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
            raise ValueError(
                "Evaluation CSV must include text, label, domain, and split columns."
            )
        for row in reader:
            if row["split"] == "test":
                if row["label"] not in {"Positive", "Negative"} or not row["text"].strip():
                    raise ValueError("Evaluation test rows must have non-empty text and valid labels.")
                test_records.append(row)

    if not test_records:
        raise ValueError("Evaluation dataset contains no test rows.")

    actual_labels = [row["label"] for row in test_records]
    predicted_labels = [predict_sentiment(row["text"])["label"] for row in test_records]
    domain_records = defaultdict(lambda: ([], []))
    for row, actual, predicted in zip(test_records, actual_labels, predicted_labels):
        domain_records[row["domain"]][0].append(actual)
        domain_records[row["domain"]][1].append(predicted)

    metadata_path = dataset_path.with_suffix(".metadata.json")
    metadata = {}
    if dataset_path.resolve() == DATASET_PATH.resolve() and METADATA_PATH.is_file():
        metadata_path = METADATA_PATH
    if metadata_path.is_file():
        import json
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    return {
        "status": "ok",
        "model_type": type(MODEL.pipeline).__name__,
        "dataset": metadata.get("dataset", dataset_path.name),
        "dataset_doi": metadata.get("doi"),
        "dataset_split": "test",
        "dataset_size": len(test_records),
        "overall": _metrics(actual_labels, predicted_labels),
        "by_domain": {
            domain: _metrics(actual, predicted)
            for domain, (actual, predicted) in sorted(domain_records.items())
        },
        "limitations": (
            "This is a binary English sentence-level benchmark, not a measure of multilingual, "
            "aspect, emotion, sarcasm, or fake-review performance."
        ),
    }
