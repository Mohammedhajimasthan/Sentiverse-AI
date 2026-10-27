import html
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

from backend.models.aspect_sentiment import analyze_aspect_sentiment
from backend.models.emotion import detect_emotion
from backend.models.fake_review import detect_fake_review
from backend.models.sentiment import predict_sentiment


def clean_review_text(value):
    text = unicodedata.normalize("NFKC", html.unescape(str(value or "")))
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _duplicate_key(text):
    return " ".join(sorted(re.findall(r"\w+", text.casefold())))


def _parse_rating(value):
    if value is None or str(value).strip() == "":
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    rating = float(match.group())
    if not 1 <= rating <= 5:
        return None
    return int(rating) if rating.is_integer() else rating


def _is_spam_like(text):
    words = re.findall(r"\w+", text.casefold())
    if len(words) < 8:
        return False
    return len(set(words)) <= 2 and len(words) / max(1, len(set(words))) >= 4


def _review_sentiment(text):
    predicted = predict_sentiment(text)
    aspect_predictions = analyze_aspect_sentiment(text)
    labels = {item["sentiment"] for item in aspect_predictions}
    label = "Mixed" if "Positive" in labels and "Negative" in labels else predicted["label"]
    return {
        "label": label,
        "confidence": predicted["confidence"],
        "low_confidence": predicted["confidence"] < 0.6,
    }, aspect_predictions


def analyze_review_records(records, source="Manual"):
    received = len(records)
    valid_records = []
    duplicate_count = 0
    invalid_count = 0
    duplicate_keys = set()
    seen_texts = []

    for index, incoming in enumerate(records, start=1):
        row = incoming if isinstance(incoming, dict) else {"text": incoming}
        raw_text = row.get("text", row.get("review", row.get("review_text", "")))
        text = clean_review_text(raw_text)
        if len(re.findall(r"[^\W_]", text, flags=re.UNICODE)) < 3 or len(text) > 10000 or _is_spam_like(text):
            invalid_count += 1
            continue

        key = _duplicate_key(text)
        if key in duplicate_keys:
            duplicate_count += 1
            continue
        duplicate_keys.add(key)

        # Catch small spelling/punctuation variations without quadratic comparisons on large uploads.
        if len(seen_texts) <= 2000 and any(
            abs(len(text) - len(previous)) <= 8 and SequenceMatcher(None, text.casefold(), previous.casefold()).ratio() >= 0.94
            for previous in seen_texts[-250:]
        ):
            duplicate_count += 1
            continue
        seen_texts.append(text)

        sentiment, aspect_predictions = _review_sentiment(text)
        emotion = detect_emotion(text)
        quality = detect_fake_review(text)
        suspicious_probability = (
            quality["confidence"] if quality["review_type"] == "Suspicious" else 1 - quality["confidence"]
        )
        valid_records.append({
            "review_id": str(row.get("review_id") or f"REV{index:05d}"),
            "text": text,
            "rating": _parse_rating(row.get("rating")),
            "date": row.get("date") or None,
            "verified_purchase": row.get("verified_purchase") or None,
            "user_name": row.get("user_name") or None,
            "helpful_votes": row.get("helpful_votes") or None,
            "product_id": row.get("product_id") or None,
            "source": source,
            "sentiment": sentiment,
            "aspects": aspect_predictions,
            "emotion": emotion,
            "suspicious_probability": round(max(0.0, min(1.0, suspicious_probability)), 3),
            "review_quality": quality.get("review_type", "Unknown"),
        })

    return aggregate_review_records(
        valid_records,
        total_received=received,
        duplicate_count=duplicate_count,
        invalid_count=invalid_count,
        source=source,
    )


def aggregate_review_records(records, total_received=None, duplicate_count=0, invalid_count=0, source="Manual"):
    sentiment_labels = ["Positive", "Neutral", "Negative", "Mixed"]
    sentiment_counts = Counter(record["sentiment"]["label"] for record in records)
    total_valid = len(records)
    counts = {label: sentiment_counts.get(label, 0) for label in sentiment_labels}
    distribution = {
        label: round(count / total_valid * 100, 2) if total_valid else None
        for label, count in counts.items()
    }

    if total_valid:
        highest = max(counts.values())
        leading = [label for label, count in counts.items() if count == highest]
        overall = leading[0] if len(leading) == 1 else "Mixed"
    else:
        overall = None

    aspect_totals = {}
    emotion_counts = Counter()
    rating_counts = Counter()
    suspicious_count = 0
    low_confidence_count = 0
    for record in records:
        for aspect in record["aspects"]:
            result = aspect_totals.setdefault(aspect["aspect"], Counter())
            result[aspect["sentiment"]] += 1
        emotion_counts[record["emotion"]["emotion"]] += 1
        if record["rating"] is not None:
            rating_counts[str(record["rating"])] += 1
        suspicious_count += record["review_quality"] == "Suspicious"
        low_confidence_count += record["sentiment"]["low_confidence"]

    aspects = [
        {
            "aspect": name,
            "positive": values.get("Positive", 0),
            "neutral": values.get("Neutral", 0),
            "negative": values.get("Negative", 0),
            "total": sum(values.values()),
            "reviews": [
                {"review_id": record["review_id"], "text": record["text"], "sentiment": item["sentiment"]}
                for record in records
                for item in record["aspects"]
                if item["aspect"] == name
            ],
        }
        for name, values in sorted(aspect_totals.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    ]
    sentiment_drivers = {}
    for sentiment in ("Positive", "Negative"):
        key = sentiment.lower()
        drivers = []
        for aspect in aspects:
            count = aspect[key]
            if not count:
                continue
            drivers.append({
                "aspect": aspect["aspect"],
                "sentiment": sentiment,
                "count": count,
                "mentions": aspect["total"],
                "share_of_valid_reviews": round(count / total_valid * 100, 2) if total_valid else None,
                "evidence": [
                    review for review in aspect["reviews"]
                    if review["sentiment"] == sentiment
                ][:3],
            })
        sentiment_drivers[key] = sorted(
            drivers,
            key=lambda item: (-item["count"], -item["share_of_valid_reviews"], item["aspect"]),
        )[:3]

    rated_records = [record for record in records if record["rating"] is not None]
    agreement = (
        sum(
            (record["rating"] >= 4 and record["sentiment"]["label"] == "Positive")
            or (record["rating"] <= 2 and record["sentiment"]["label"] == "Negative")
            or (record["rating"] == 3 and record["sentiment"]["label"] in {"Neutral", "Mixed"})
            for record in rated_records
        )
        if rated_records else None
    )
    quality = {
        "total_received": total_received if total_received is not None else total_valid,
        "valid_reviews": total_valid,
        "duplicates_removed": duplicate_count,
        "invalid_reviews": invalid_count,
        "removed_reviews": duplicate_count + invalid_count,
        "unique_reviews": total_valid,
        "suspicious_reviews": suspicious_count,
        "low_confidence_reviews": low_confidence_count,
    }

    if total_valid:
        summary = (
            f"Based on {total_valid} valid customer reviews, overall sentiment is {overall.lower()}. "
            f"{counts['Positive']} are positive, {counts['Neutral']} neutral, "
            f"{counts['Negative']} negative, and {counts['Mixed']} mixed."
        )
        leading_positive = sentiment_drivers["positive"][0] if sentiment_drivers["positive"] else None
        leading_negative = sentiment_drivers["negative"][0] if sentiment_drivers["negative"] else None
        if leading_positive:
            summary += (
                f" The most-mentioned positive factor is {leading_positive['aspect']} "
                f"({leading_positive['count']} reviews)."
            )
        if leading_negative:
            summary += (
                f" The leading reported concern is {leading_negative['aspect']} "
                f"({leading_negative['count']} reviews)."
            )
    else:
        summary = "No valid customer reviews were available for analysis."

    recommendations = []
    for aspect in aspects:
        if aspect["total"] < 2:
            continue
        negative_share = aspect["negative"] / aspect["total"]
        positive_share = aspect["positive"] / aspect["total"]
        if negative_share >= 0.4:
            recommendations.append(f"Prioritize {aspect['aspect']}: {aspect['negative']} of {aspect['total']} mentions are negative.")
        elif positive_share >= 0.75:
            recommendations.append(f"Maintain {aspect['aspect']} as a strength: {aspect['positive']} of {aspect['total']} mentions are positive.")

    rating_distribution = {
        str(rating): {"count": rating_counts.get(str(rating), 0),
                      "percentage": round(rating_counts.get(str(rating), 0) / len(rated_records) * 100, 2)}
        for rating in range(1, 6)
    } if rated_records else None

    return {
        "source": source,
        "status": "ok" if total_valid else "insufficient_data",
        "total_reviews": total_valid,
        "overall_sentiment": overall,
        "sentiment_counts": counts,
        "sentiment_distribution": distribution,
        "review_quality": quality,
        "rating_distribution": rating_distribution,
        "rating_sentiment_agreement": {
            "count": agreement,
            "total_rated": len(rated_records),
            "percentage": round(agreement / len(rated_records) * 100, 2) if rated_records else None,
        },
        "aspects": aspects,
        "sentiment_drivers": sentiment_drivers,
        "top_aspects": [{"aspect": item["aspect"], "count": item["total"]} for item in aspects[:5]],
        "emotion_distribution": {
            emotion: {"count": count, "percentage": round(count / total_valid * 100, 2)}
            for emotion, count in emotion_counts.most_common()
        } if total_valid else {},
        "suspicious_probability": round(suspicious_count / total_valid, 3) if total_valid else None,
        "summary": summary,
        "recommendations": recommendations,
        "insights": {"recommendations": recommendations, "strengths": [], "concerns": []},
        "reviews": records,
        "dashboard": {
            "total_reviews": total_valid,
            "positive": distribution["Positive"],
            "negative": distribution["Negative"],
            "neutral": distribution["Neutral"],
            "mixed": distribution["Mixed"],
            "sentiment_distribution": counts,
            "sentiment_drivers": {
                direction: [
                    {key: value for key, value in driver.items() if key != "evidence"}
                    for driver in drivers
                ]
                for direction, drivers in sentiment_drivers.items()
            },
            "top_aspects": [{"aspect": item["aspect"], "count": item["total"]} for item in aspects[:5]],
            "summary": summary,
        },
    }


def build_demo_reviews():
    examples = [
        ("The sound is clear and balanced, and the bass feels rich without drowning out vocals.", 5),
        ("ANC blocks the bus noise well and makes my commute much more peaceful.", 5),
        ("Battery lasts through my workday and the case still has plenty of charge.", 5),
        ("Pairing with my phone was quick and Bluetooth has stayed stable.", 4),
        ("The earbuds fit comfortably for long listening sessions and feel secure.", 5),
        ("Microphone sounds natural on calls even when I am walking outside.", 4),
        ("Spatial audio is fun for films, although I use it less for music.", 4),
        ("The case is compact and the hinge feels sturdy in my bag.", 4),
        ("For this price the audio quality and noise cancellation are excellent value.", 5),
        ("Charging is fast and the case reaches full power before I leave home.", 4),
        ("The microphone picks up wind badly and people struggle to hear me outdoors.", 2),
        ("Battery life is shorter than advertised when noise cancellation is enabled.", 2),
        ("ANC barely reduces traffic noise and the setting made little difference.", 2),
        ("Left earbud disconnects several times a day and pairing again is annoying.", 1),
        ("The fit hurts my ears after an hour, even with the smallest tips.", 2),
        ("Bass is powerful but overwhelms voices, so podcasts sound muddy.", 3),
        ("Sound is pleasant but the case feels flimsy and the lid does not close firmly.", 3),
        ("Call quality is fine indoors but poor in a crowded room.", 3),
        ("Battery is reliable, but charging the case takes longer than I expected.", 3),
        ("The product works as described, though there is nothing special about it.", 3),
        ("Setup was straightforward and the controls are easy to learn.", 4),
        ("The earbuds arrived late, but support resolved the delivery issue politely.", 4),
        ("Excellent excellent best ever perfect purchase absolutely love it.", 5),
        ("I expected better durability because one earbud stopped working after a week.", 1),
    ]
    time_context = [
        "After a week of daily use,",
        "After two weeks of listening,",
        "On my daily commute,",
        "During calls and music playback,",
        "After testing them at home,",
    ]
    reviews = []
    for index, (text, rating) in enumerate(examples):
        for variation, context in enumerate(time_context):
            reviews.append({
                "review_id": f"DEMO{index * len(time_context) + variation + 1:03d}",
                "text": f"{context} {text}",
                "rating": rating,
                "date": f"2026-09-{(index * len(time_context) + variation) % 28 + 1:02d}",
                "verified_purchase": variation % 2 == 0,
            })
    reviews.extend([
        {"review_id": "DEMO121", "text": examples[0][0], "rating": 5},
        {"review_id": "DEMO122", "text": examples[0][0], "rating": 5},
        {"review_id": "DEMO123", "text": " ".join(reversed(examples[0][0].split())), "rating": 5},
    ])
    return reviews
