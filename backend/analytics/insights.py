from collections import Counter

from backend.models.aspect import extract_aspects
from backend.models.aspect_sentiment import analyze_aspect_sentiment
from backend.models.sentiment import predict_sentiment


def _clean_review_list(reviews):
    return [str(review).strip() for review in (reviews or []) if review and str(review).strip()]


def summarize_reviews(reviews):
    clean_reviews = _clean_review_list(reviews)
    if not clean_reviews:
        return "No reviews available for summarization."

    sentiment_counts = {"Positive": 0, "Negative": 0, "Neutral": 0}
    aspect_counter = Counter()
    aspect_sentiment = Counter()

    for review in clean_reviews:
        sentiment = predict_sentiment(review)
        sentiment_counts[sentiment["label"]] = sentiment_counts.get(sentiment["label"], 0) + 1
        for aspect in extract_aspects(review):
            aspect_name = aspect["aspect"]
            aspect_counter[aspect_name] += 1

        for item in analyze_aspect_sentiment(review):
            aspect_name = item["aspect"]
            aspect_sentiment[(aspect_name, item["sentiment"])] += 1

    top_aspect = aspect_counter.most_common(1)[0][0] if aspect_counter else "General Feedback"
    positive_total = sentiment_counts["Positive"]
    negative_total = sentiment_counts["Negative"]
    neutral_total = sentiment_counts["Neutral"]

    strongest_positive = max(
        [
            (aspect, count)
            for (aspect, sentiment), count in aspect_sentiment.items()
            if sentiment == "Positive"
        ],
        key=lambda item: item[1],
        default=(top_aspect, 0),
    )
    strongest_negative = max(
        [
            (aspect, count)
            for (aspect, sentiment), count in aspect_sentiment.items()
            if sentiment == "Negative"
        ],
        key=lambda item: item[1],
        default=(top_aspect, 0),
    )

    if strongest_negative[1] > 0 and strongest_positive[1] > 0:
        return (
            f"Across {len(clean_reviews)} reviews, {positive_total} were positive, {negative_total} negative, and "
            f"{neutral_total} neutral. {top_aspect} was the most discussed topic, while {strongest_positive[0]} stood out as the "
            f"strongest positive theme and {strongest_negative[0]} emerged as the most common pain point."
        )

    return (
        f"Across {len(clean_reviews)} reviews, {positive_total} were positive, {negative_total} negative, and "
        f"{neutral_total} neutral. The most discussed area is {top_aspect}, suggesting this is the primary focus "
        "for product and service improvements."
    )


def generate_customer_insights(reviews):
    clean_reviews = _clean_review_list(reviews)
    if not clean_reviews:
        return {"strengths": [], "concerns": [], "recommendations": []}

    aspect_counter = Counter()
    positive_aspects = Counter()
    negative_aspects = Counter()

    for review in clean_reviews:
        for aspect in extract_aspects(review):
            aspect_name = aspect["aspect"]
            aspect_counter[aspect_name] += 1

        for item in analyze_aspect_sentiment(review):
            aspect_name = item["aspect"]
            if item["sentiment"] == "Positive":
                positive_aspects[aspect_name] += 1
            elif item["sentiment"] == "Negative":
                negative_aspects[aspect_name] += 1

    strengths = [
        f"{aspect} is a recurring strength across customer feedback."
        for aspect, _ in positive_aspects.most_common(3)
    ] or [
        f"{aspect} is a frequent positive discussion point."
        for aspect, _ in aspect_counter.most_common(3)
    ]

    concerns = [
        f"{aspect} is a common pain point, especially in negative feedback."
        for aspect, _ in negative_aspects.most_common(3)
    ] or [
        f"{aspect} deserves attention because it appears frequently in mixed feedback."
        for aspect, _ in aspect_counter.most_common(3)
    ]

    recommendations = []
    if negative_aspects:
        top_concern = negative_aspects.most_common(1)[0][0]
        recommendations.append(f"Prioritize improvements in {top_concern} to reduce recurring dissatisfaction.")
    recommendations.append("Keep reinforcing the strongest positive aspects to maintain customer satisfaction and advocacy.")
    recommendations.append("Use aspect-level sentiment trends to guide product, support, and delivery decisions.")

    return {
        "strengths": strengths,
        "concerns": concerns,
        "recommendations": recommendations,
    }


def compute_dashboard_stats(reviews):
    clean_reviews = _clean_review_list(reviews)
    if not clean_reviews:
        return {
            "total_reviews": 0,
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "top_aspects": [],
            "sentiment_distribution": {"Positive": 0, "Negative": 0, "Neutral": 0},
            "summary": "No review data available yet.",
            "insights": {"strengths": [], "concerns": [], "recommendations": []},
            "message": "No review data available yet.",
        }

    sentiment_counts = {"Positive": 0, "Negative": 0, "Neutral": 0}
    aspect_counter = Counter()

    for review in clean_reviews:
        sentiment = predict_sentiment(review)
        sentiment_counts[sentiment["label"]] = sentiment_counts.get(sentiment["label"], 0) + 1
        for aspect in extract_aspects(review):
            aspect_counter[aspect["aspect"]] += 1

    total_reviews = len(clean_reviews)
    positive_pct = round((sentiment_counts["Positive"] / total_reviews) * 100, 2) if total_reviews else 0
    negative_pct = round((sentiment_counts["Negative"] / total_reviews) * 100, 2) if total_reviews else 0
    neutral_pct = round((sentiment_counts["Neutral"] / total_reviews) * 100, 2) if total_reviews else 0

    return {
        "total_reviews": total_reviews,
        "positive": positive_pct,
        "negative": negative_pct,
        "neutral": neutral_pct,
        "top_aspects": [
            {"aspect": aspect, "count": count}
            for aspect, count in aspect_counter.most_common(5)
        ],
        "sentiment_distribution": sentiment_counts,
        "summary": summarize_reviews(clean_reviews),
        "insights": generate_customer_insights(clean_reviews),
        "message": "Dashboard metrics computed from the available review dataset.",
    }
