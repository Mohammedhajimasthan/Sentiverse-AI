import csv
from pathlib import Path

from backend.analytics.insights import compute_dashboard_stats
from backend.api.routes import analyze_review, ReviewRequest


def analyze_csv_reviews(csv_path):
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("CSV file does not contain a header row.")

        review_column = next(
            (field for field in ["review", "text", "comment", "feedback", "review_text"] if field.lower() in [name.lower() for name in reader.fieldnames]),
            reader.fieldnames[0],
        )

        reviews = []
        for row in reader:
            value = row.get(review_column)
            if value and str(value).strip():
                reviews.append(str(value).strip())

    if not reviews:
        return {"total_reviews": 0, "results": [], "dashboard": compute_dashboard_stats([])}

    results = [analyze_review(ReviewRequest(text=review)) for review in reviews]
    return {
        "total_reviews": len(results),
        "results": results,
        "dashboard": compute_dashboard_stats(reviews),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze review data in a CSV file.")
    parser.add_argument("csv_path", help="Path to the CSV file containing review text.")
    args = parser.parse_args()

    summary = analyze_csv_reviews(args.csv_path)
    print(summary)
