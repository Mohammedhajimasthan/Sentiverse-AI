import csv
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.evaluation import evaluate_sentiment_model
from backend.models.prepare_evaluation_dataset import (
    EXPECTED_DOMAINS,
    assign_splits,
    parse_dataset_archive,
)


def _test_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for filename in EXPECTED_DOMAINS:
            archive.writestr(
                f"sentiment labelled sentences/{filename}",
                "positive example\t1\nnegative example\t0\nsplit source\nrejoined sentence\t1\nincomplete source record",
            )
    return buffer.getvalue()


class EvaluationDatasetTests(unittest.TestCase):
    def test_parse_archive_preserves_domains_and_maps_labels(self):
        records, rejected_rows, rejoined_rows = parse_dataset_archive(_test_archive())

        self.assertEqual(len(records), 9)
        self.assertEqual({record["domain"] for record in records}, {"amazon", "imdb", "yelp"})
        self.assertEqual({record["label"] for record in records}, {"Positive", "Negative"})
        self.assertEqual(len(rejected_rows), 3)
        self.assertEqual(rejected_rows[0]["reason"], "Missing review text, tab separator, or binary label.")
        self.assertEqual(len(rejoined_rows), 3)
        self.assertTrue(any(record["text"] == "split source rejoined sentence" for record in records))

    def test_split_is_stratified_and_reproducible(self):
        records = []
        for filename, domain in EXPECTED_DOMAINS.items():
            for label in ("Positive", "Negative"):
                for index in range(10):
                    records.append({
                        "review_id": f"{domain}-{label}-{index}",
                        "text": f"{domain} {label} example {index}",
                        "label": label,
                        "domain": domain,
                    })

        split_once = assign_splits(records)
        split_twice = assign_splits(records)
        self.assertEqual(split_once, split_twice)
        for domain in EXPECTED_DOMAINS.values():
            for label in ("Positive", "Negative"):
                stratum = [
                    row for row in split_once
                    if row["domain"] == domain and row["label"] == label
                ]
                self.assertEqual(sum(row["split"] == "test" for row in stratum), 2)

    def test_evaluation_uses_only_test_rows_and_reports_domains(self):
        rows = [
            {"text": "positive example", "label": "Positive", "domain": "amazon", "split": "test"},
            {"text": "positive example", "label": "Positive", "domain": "amazon", "split": "development"},
            {"text": "negative example", "label": "Negative", "domain": "yelp", "split": "test"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluation.csv"
            with path.open("w", newline="", encoding="utf-8") as output_file:
                writer = csv.DictWriter(output_file, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            metrics = evaluate_sentiment_model(path)

        self.assertEqual(metrics["dataset_size"], 2)
        self.assertEqual(set(metrics["by_domain"]), {"amazon", "yelp"})
        self.assertEqual(metrics["overall"]["sample_count"], 2)
        self.assertEqual(len(metrics["overall"]["confusion_matrix"]), 3)


if __name__ == "__main__":
    unittest.main()
