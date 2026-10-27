import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.evaluation import evaluate_sentiment_model


if __name__ == "__main__":
    metrics = evaluate_sentiment_model()
    output = json.dumps(metrics, indent=2)
    print(output)

    root = Path(__file__).resolve().parents[2]
    report_paths = [
        root / "results" / "sentiment_uci_evaluation.json",
        root / "models" / "sentiment_metrics.json",
    ]
    for report_path in report_paths:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(output + "\n", encoding="utf-8")
        print(f"\nSaved metrics report to: {report_path}")
