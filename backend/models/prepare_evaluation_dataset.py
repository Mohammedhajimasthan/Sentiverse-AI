from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "datasets" / "sentiment_labelled_sentences.csv"
METADATA_PATH = ROOT / "datasets" / "sentiment_labelled_sentences.metadata.json"
DATASET_URL = "https://archive.ics.uci.edu/static/public/331/sentiment+labelled+sentences.zip"
EXPECTED_DOMAINS = {
    "amazon_cells_labelled.txt": "amazon",
    "imdb_labelled.txt": "imdb",
    "yelp_labelled.txt": "yelp",
}
EXPECTED_ROWS_PER_DOMAIN = 1000
TEST_FRACTION = 0.2
CSV_FIELDS = ["review_id", "text", "label", "domain", "split"]


def parse_dataset_archive(
    archive_bytes: bytes,
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str | int]],
    list[dict[str, str | int]],
]:
    records = []
    rejected_rows = []
    rejoined_rows = []
    seen_files = set()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        for member in archive.infolist():
            filename = Path(member.filename).name
            if filename not in EXPECTED_DOMAINS:
                continue
            if filename in seen_files:
                raise ValueError(f"Dataset archive contains duplicate file: {filename}")
            seen_files.add(filename)
            domain = EXPECTED_DOMAINS[filename]
            content = archive.read(member).decode("utf-8-sig")
            lines = content.splitlines()
            line_index = 0
            while line_index < len(lines):
                line_number = line_index + 1
                line = lines[line_index]
                text, separator, raw_label = line.rpartition("\t")
                if not line.strip():
                    line_index += 1
                    continue
                if not separator and line_index + 1 < len(lines):
                    continuation_text, continuation_separator, continuation_label = lines[
                        line_index + 1
                    ].rpartition("\t")
                    if continuation_separator and continuation_label.strip() in {"0", "1"}:
                        text = f"{line.strip()} {continuation_text.strip()}"
                        raw_label = continuation_label
                        separator = continuation_separator
                        rejoined_rows.append({
                            "domain": domain,
                            "source_file": filename,
                            "source_line_numbers": f"{line_number}-{line_number + 1}",
                        })
                        line_index += 1
                if not separator or not text.strip() or raw_label.strip() not in {"0", "1"}:
                    rejected_rows.append({
                        "domain": domain,
                        "source_file": filename,
                        "line_number": line_number,
                        "reason": "Missing review text, tab separator, or binary label.",
                    })
                    line_index += 1
                    continue
                label = "Positive" if raw_label.strip() == "1" else "Negative"
                records.append({
                    "review_id": f"uci-331-{domain}-{line_number:04d}",
                    "text": text.strip(),
                    "label": label,
                    "domain": domain,
                })
                line_index += 1

    if seen_files != set(EXPECTED_DOMAINS):
        missing = sorted(set(EXPECTED_DOMAINS) - seen_files)
        raise ValueError(f"Dataset archive is missing expected source files: {', '.join(missing)}")

    return records, rejected_rows, rejoined_rows


def assign_splits(records: list[dict[str, str]]) -> list[dict[str, str]]:
    strata: dict[tuple[str, str], list[dict[str, str]]] = {}
    for record in records:
        strata.setdefault((record["domain"], record["label"]), []).append(record)

    split_records = []
    for (domain, label), group in sorted(strata.items()):
        ordered = sorted(
            group,
            key=lambda record: hashlib.sha256(
                record["text"].strip().casefold().encode("utf-8")
            ).hexdigest(),
        )
        test_count = max(1, round(len(ordered) * TEST_FRACTION))
        test_ids = {record["review_id"] for record in ordered[:test_count]}
        for record in group:
            split_records.append({
                **record,
                "split": "test" if record["review_id"] in test_ids else "development",
            })
    text_splits = {}
    for record in split_records:
        normalized_text = record["text"].strip().casefold()
        previous_split = text_splits.setdefault(normalized_text, record["split"])
        if previous_split != record["split"]:
            raise ValueError("Duplicate normalized review text crosses dataset splits.")
    return sorted(split_records, key=lambda record: record["review_id"])


def prepare_dataset(
    output_path: Path = DATASET_PATH,
    metadata_path: Path | None = None,
) -> tuple[Path, Path]:
    request = urllib.request.Request(
        DATASET_URL,
        headers={"User-Agent": "SentiverseAI/1.0 (academic evaluation dataset download)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        archive_bytes = response.read(5_000_001)
    if len(archive_bytes) > 5_000_000:
        raise ValueError("UCI dataset archive exceeded the 5 MB safety limit")

    parsed_records, rejected_rows, rejoined_rows = parse_dataset_archive(archive_bytes)
    total_counts = Counter(record["domain"] for record in parsed_records)
    rejected_counts = Counter(row["domain"] for row in rejected_rows)
    for domain in EXPECTED_DOMAINS.values():
        source_count = total_counts[domain] + rejected_counts[domain]
        if source_count != EXPECTED_ROWS_PER_DOMAIN:
            raise ValueError(
                f"Expected {EXPECTED_ROWS_PER_DOMAIN} source rows for {domain}, got {source_count}"
            )
    records = assign_splits(parsed_records)
    output_path = Path(output_path)
    metadata_path = Path(metadata_path) if metadata_path else output_path.with_suffix(".metadata.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)

    counts = Counter((row["domain"], row["label"], row["split"]) for row in records)
    metadata = {
        "dataset": "UCI Sentiment Labelled Sentences",
        "uci_id": 331,
        "doi": "10.24432/C57604",
        "source_url": "https://archive.ics.uci.edu/dataset/331/sentiment+labelled+sentences",
        "download_url": DATASET_URL,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_records": len(records),
        "rejected_source_rows": len(rejected_rows),
        "rejected_rows": rejected_rows,
        "rejoined_source_rows": rejoined_rows,
        "languages": ["English"],
        "domains": ["amazon", "imdb", "yelp"],
        "labels": ["Negative", "Positive"],
        "license_status": (
            "No license was declared in the retrieved UCI dataset metadata. "
            "Use the source under its applicable terms; this project does not redistribute the corpus."
        ),
        "citation": (
            "D. Kotzias, M. Denil, N. de Freitas, and P. Smyth, "
            "\"From Group to Individual Labels Using Deep Features,\" KDD, 2015. "
            "UCI Machine Learning Repository, doi:10.24432/C57604."
        ),
        "split_method": (
            "Deterministic 80/20 development/test split within each domain and sentiment label; "
            "SHA-256 of normalized text determines test membership."
        ),
        "split_counts": {
            f"{domain}/{label}/{split}": count
            for (domain, label, split), count in sorted(counts.items())
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return output_path, metadata_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and prepare the UCI sentiment benchmark.")
    parser.add_argument("--output", type=Path, default=DATASET_PATH)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    dataset_path, metadata_path = prepare_dataset(args.output, args.metadata)
    print(f"Prepared dataset: {dataset_path}")
    print(f"Dataset metadata: {metadata_path}")


if __name__ == "__main__":
    main()
