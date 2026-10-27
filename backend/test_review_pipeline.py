import asyncio
import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

from backend.api import routes
from backend.models.aspect_sentiment import analyze_aspect_sentiment
from backend.models.emotion import detect_emotion
from backend.models.sentiment import predict_sentiment
from backend.services.review_pipeline import analyze_review_records, build_demo_reviews
from fastapi import HTTPException, UploadFile


class ReviewPipelineTests(unittest.TestCase):
    def test_visible_page_extraction_skips_nonvisible_chrome_and_keeps_emojis(self):
        page_html = """
        <html><head><title>Page title</title><script>bad script words</script></head>
        <body>
          <nav>Menu link</nav>
          <main><article><h1>Wonderful earbuds 😍</h1>
            <p>The sound quality is clear and the battery lasts all day. 👍</p>
            <p hidden>hidden negative words</p>
            <div style="display:none">hidden text</div>
          </article></main>
          <footer>Footer links</footer>
        </body></html>
        """

        extracted = routes._extract_visible_page_text(page_html, "text/html")

        self.assertIn("Wonderful earbuds 😍", extracted)
        self.assertIn("battery lasts all day. 👍", extracted)
        self.assertNotIn("bad script words", extracted)
        self.assertNotIn("Menu link", extracted)
        self.assertNotIn("hidden negative words", extracted)
        self.assertNotIn("Footer links", extracted)

    def test_visible_page_extraction_prefers_article_and_filters_common_layout_noise(self):
        page_html = """
        <header class="site-header">Site navigation and sign-in controls.</header>
        <nav class="nav-menu">Home Products Account</nav>
        <div class="advertisement">Sponsored banner content.</div>
        <main>
          <aside class="sidebar">Related links and promotions.</aside>
          <article class="post-content">
            <h1>Why battery life matters</h1>
            <p>Long battery life improves a user's daily experience.</p>
          </article>
        </main>
        <div class="cookie-consent">Accept cookies</div>
        """

        extracted = routes._extract_visible_page_text(page_html, "text/html")

        self.assertIn("Why battery life matters", extracted)
        self.assertIn("Long battery life improves", extracted)
        self.assertNotIn("Site navigation", extracted)
        self.assertNotIn("Related links", extracted)
        self.assertNotIn("Sponsored banner", extracted)
        self.assertNotIn("Accept cookies", extracted)

    def test_bare_domain_and_domain_with_port_are_normalized_to_https(self):
        self.assertEqual(routes._normalize_link_url("example.com/blog"), "https://example.com/blog")
        self.assertEqual(
            routes._normalize_link_url("example.com:8443/blog"),
            "https://example.com:8443/blog",
        )
        self.assertEqual(routes._normalize_link_url("ftp://example.com"), "ftp://example.com")

    def test_link_fetch_extracts_body_text_and_not_head_metadata(self):
        url = "https://example.com/blog"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            "<html><head><title>Blog title</title>"
            '<meta name="description" content="Metadata only"></head>'
            "<body><nav>Navigation</nav><main><article>"
            "<p>Battery life is excellent 😍 and the sound is clear.</p>"
            "</article></main><footer>Footer links</footer></body></html>"
        ).encode("utf-8")
        response.__enter__.return_value.headers.get_content_type.return_value = "text/html"
        response.__enter__.return_value.headers.get_content_charset.return_value = "utf-8"
        response.__enter__.return_value.geturl.return_value = url
        opener = MagicMock()
        opener.open.return_value = response

        with (
            patch.object(routes, "_validate_public_url", return_value=urlparse(url)),
            patch.object(routes, "build_opener", return_value=opener),
        ):
            page_data = routes._extract_page_metadata(url)

        self.assertIn("Battery life is excellent 😍", page_data["text"])
        self.assertNotIn("Metadata only", page_data["text"])
        self.assertNotIn("Navigation", page_data["text"])
        self.assertNotIn("Footer links", page_data["text"])
        self.assertEqual(page_data["document_characters_extracted"], len(page_data["text"]))

    def test_access_interstitial_is_reported_without_analyzing_its_boilerplate(self):
        url = "https://example.com/product"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b"<html><head><title>Example</title></head><body>"
            b"<main><p>Click the button below to continue shopping</p>"
            b"<p>Conditions of Use and Privacy Notice</p></main></body></html>"
        )
        response.__enter__.return_value.headers.get_content_type.return_value = "text/html"
        response.__enter__.return_value.headers.get_content_charset.return_value = "utf-8"
        response.__enter__.return_value.geturl.return_value = url
        opener = MagicMock()
        opener.open.return_value = response

        with (
            patch.object(routes, "_validate_public_url", return_value=urlparse(url)),
            patch.object(routes, "build_opener", return_value=opener),
        ):
            page_data = routes._extract_page_metadata(url)

        self.assertEqual(page_data["text"], "")
        self.assertEqual(page_data["document_characters_extracted"], 0)
        self.assertIn("access or verification page", page_data["fetch_error"])

    def test_link_document_mode_analyzes_bare_domain_and_preserves_full_text_for_model(self):
        long_text = "The sound quality is excellent and the battery lasts all day 😍"
        page_data = {
            "source_url": "https://example.com/blog",
            "platform": "Web page",
            "title": "Earbud review blog",
            "description": long_text,
            "text": long_text,
            "document_characters_extracted": len(long_text),
            "document_truncated": False,
            "reviews": [],
            "reviews_found": 0,
        }
        with (
            patch.object(routes, "_validate_public_url"),
            patch.object(routes, "_extract_page_metadata", return_value=page_data) as extract_page,
            patch.object(routes, "predict_sentiment", return_value={"label": "Positive", "confidence": 0.8}) as sentiment,
            patch.object(routes, "detect_emotion", return_value={"emotion": "Joy", "confidence": 0.7}),
            patch.object(routes, "analyze_aspect_sentiment", return_value=[{"aspect": "Sound Quality", "sentiment": "Positive"}]),
            patch.object(routes, "generate_explanation", return_value={"summary": "Positive cues found."}),
        ):
            result = routes.analyze_link(routes.LinkRequest(url="example.com/blog"))

        extract_page.assert_called_once_with("https://example.com/blog")
        sentiment.assert_called_once_with(long_text)
        self.assertEqual(result["analysis_type"], "page_document")
        self.assertEqual(result["document_analysis"]["sentiment"]["label"], "Positive")
        self.assertIn("😍", result["document_analysis"]["content_preview"])
        self.assertIsNone(result["analysis"])

    def test_emoji_only_sentiment_and_emotion_use_emoji_cues(self):
        self.assertEqual(predict_sentiment("😍😍😍")["label"], "Positive")
        self.assertEqual(predict_sentiment("👎😡😡")["label"], "Negative")
        self.assertEqual(detect_emotion("😍😍")["emotion"], "Love")

    def test_model_metrics_endpoints_report_external_sentiment_and_unassessed_models(self):
        report = {
            "dataset": "UCI Sentiment Labelled Sentences",
            "dataset_size": 600,
            "overall": {
                "accuracy": 0.6,
                "weighted_precision": 0.61,
                "weighted_recall": 0.6,
                "weighted_f1": 0.59,
            },
        }
        with patch.object(routes, "SENTIMENT_METRICS_PATH") as metrics_path:
            metrics_path.is_file.return_value = True
            metrics_path.read_text.return_value = json.dumps(report)

            direct_metrics = routes.model_metrics_endpoint()
            extended_metrics = routes.extended_model_metrics_endpoint()

        self.assertEqual(direct_metrics["dataset"], report["dataset"])
        self.assertEqual(extended_metrics["status"], "partially_evaluated")
        self.assertEqual(extended_metrics["sentiment"]["accuracy"], 0.6)
        self.assertEqual(extended_metrics["sentiment"]["dataset_size"], 600)
        self.assertNotIn("emotion", extended_metrics)
        self.assertNotIn("sarcasm", extended_metrics)
        self.assertNotIn("fake_review", extended_metrics)

    def test_aggregations_use_valid_individual_reviews_and_ratings(self):
        result = analyze_review_records([
            {"text": "ANC blocks noise well and the battery lasts all day.", "rating": "5"},
            {"text": "The microphone sounds poor and calls are unclear.", "rating": "2"},
            {"text": "Sound is excellent but the battery life is disappointing.", "rating": "3"},
            {"text": "Works as described and arrived today.", "rating": "3"},
            {"text": "the battery lasts all day and ANC blocks noise well", "rating": "5"},
            {"text": ""},
        ])

        quality = result["review_quality"]
        self.assertEqual(quality["total_received"], 6)
        self.assertEqual(quality["valid_reviews"], 4)
        self.assertEqual(quality["duplicates_removed"], 1)
        self.assertEqual(quality["invalid_reviews"], 1)
        self.assertEqual(quality["removed_reviews"], 2)
        self.assertEqual(sum(result["sentiment_counts"].values()), 4)
        self.assertEqual(result["rating_distribution"]["5"]["count"], 1)
        self.assertEqual(result["rating_distribution"]["2"]["count"], 1)
        self.assertIn("Active Noise Cancellation", {item["aspect"] for item in result["aspects"]})
        self.assertTrue(all(review["source"] == "Manual" for review in result["reviews"]))

    def test_empty_records_do_not_produce_percentages_or_product_conclusions(self):
        result = analyze_review_records([])

        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["total_reviews"], 0)
        self.assertIsNone(result["overall_sentiment"])
        self.assertTrue(all(value is None for value in result["sentiment_distribution"].values()))
        self.assertIsNone(result["rating_distribution"])

    def test_demo_dataset_has_more_than_one_hundred_labeled_synthetic_records(self):
        records = build_demo_reviews()

        self.assertGreaterEqual(len(records), 100)
        self.assertEqual({record["rating"] for record in records}, {1, 2, 3, 4, 5})
        self.assertTrue(all(record["review_id"].startswith("DEMO") for record in records))

    def test_product_metadata_is_not_treated_as_customer_review_text(self):
        page_html = """
        <script type="application/ld+json">
        {"@type":"Product","name":"realme Buds T310","description":"Marketing description",
         "aggregateRating":{"ratingValue":"4.3","reviewCount":"100"}}
        </script>
        """

        reviews, product_name = routes._extract_structured_reviews(page_html)

        self.assertEqual(product_name, "realme Buds T310")
        self.assertEqual(reviews, [])

    def test_site_brand_title_is_not_reported_as_a_product_title(self):
        url = "https://www.amazon.in/product/dp/B0DBGP48NW/"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"<html><title>Amazon.in</title></html>"
        opener = MagicMock()
        opener.open.return_value = response

        with (
            patch.object(routes, "_validate_public_url", return_value=urlparse(url)),
            patch.object(routes, "build_opener", return_value=opener),
        ):
            page_data = routes._extract_page_metadata(url)

        self.assertIsNone(page_data["title"])
        self.assertEqual(page_data["reviews"], [])
        self.assertEqual(page_data["platform"], "Amazon")

    def test_structured_review_markup_yields_actual_review_body_and_rating(self):
        page_html = """
        <script type="application/ld+json">
        {"@type":"Product","name":"Earbuds","review":[
          {"@type":"Review","reviewBody":"The sound is clear and comfortable.","reviewRating":{"ratingValue":"5"}}
        ]}
        </script>
        """

        reviews, product_name = routes._extract_structured_reviews(page_html)

        self.assertEqual(product_name, "Earbuds")
        self.assertEqual(reviews[0]["text"], "The sound is clear and comfortable.")
        self.assertEqual(reviews[0]["rating"], "5")

    def test_marked_visible_review_text_is_extracted_without_product_description(self):
        page_html = """
        <div class="product-description">These earbuds feature hybrid ANC and long battery life.</div>
        <div data-hook="review-body"><span>The bass is strong but the microphone sounds poor.</span></div>
        """

        reviews = routes._extract_marked_review_bodies(page_html)

        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["text"], "The bass is strong but the microphone sounds poor.")

    def test_aspect_sentiment_scopes_opposite_opinions_to_their_aspects(self):
        result = analyze_aspect_sentiment("ANC is excellent but microphone quality is poor.")

        sentiments = {item["aspect"]: item["sentiment"] for item in result}
        self.assertEqual(sentiments["Active Noise Cancellation"], "Positive")
        self.assertEqual(sentiments["Microphone and Calls"], "Negative")

    def test_sentiment_drivers_rank_aspect_patterns_and_include_matching_evidence(self):
        result = analyze_review_records([
            "The ANC is excellent and blocks noise on my commute.",
            "The noise cancellation blocks background sound very well.",
            "The microphone sounds poor on calls.",
        ])

        self.assertEqual(result["sentiment_drivers"]["positive"][0]["aspect"], "Active Noise Cancellation")
        self.assertEqual(result["sentiment_drivers"]["positive"][0]["count"], 2)
        self.assertEqual(result["sentiment_drivers"]["positive"][0]["share_of_valid_reviews"], 66.67)
        self.assertTrue(all(
            evidence["sentiment"] == "Positive"
            for evidence in result["sentiment_drivers"]["positive"][0]["evidence"]
        ))
        self.assertEqual(result["sentiment_drivers"]["negative"][0]["aspect"], "Microphone and Calls")
        self.assertEqual(result["sentiment_drivers"]["negative"][0]["count"], 1)
        self.assertTrue(all(
            evidence["sentiment"] == "Negative"
            for evidence in result["sentiment_drivers"]["negative"][0]["evidence"]
        ))
        self.assertEqual(
            result["dashboard"]["sentiment_drivers"]["positive"][0]["aspect"],
            "Active Noise Cancellation",
        )
        self.assertNotIn("evidence", result["dashboard"]["sentiment_drivers"]["positive"][0])
        self.assertIn("most-mentioned positive factor is Active Noise Cancellation", result["summary"])
        self.assertIn("leading reported concern is Microphone and Calls", result["summary"])

    def test_csv_upload_preserves_ratings_and_counts_review_records(self):
        csv_data = (
            "review_id,review,rating,date\n"
            "A1,The sound quality is excellent,5,2026-10-01\n"
            "A2,The microphone quality is poor,2,2026-10-02\n"
        )
        upload = UploadFile(file=io.BytesIO(csv_data.encode()), filename="feedback.csv")
        result = asyncio.run(routes.csv_analyze(upload))

        self.assertEqual(result["review_quality"]["valid_reviews"], 2)
        self.assertEqual(result["rating_distribution"]["5"]["count"], 1)
        self.assertEqual(result["reviews"][0]["review_id"], "A1")

    def test_csv_upload_accepts_spaced_review_text_column_header(self):
        csv_data = "Review Text,Star Rating\nThe sound is clear and balanced.,5\nThe fit is uncomfortable.,2\n"
        upload = UploadFile(file=io.BytesIO(csv_data.encode()), filename="feedback.csv")

        result = asyncio.run(routes.csv_analyze(upload))

        self.assertEqual(result["review_column"], "Review Text")
        self.assertEqual(result["review_quality"]["valid_reviews"], 2)
        self.assertEqual(result["rating_distribution"]["5"]["count"], 1)

    def test_notebook_upload_extracts_markdown_code_literals_and_rendered_tables(self):
        notebook = {
            "nbformat": 4,
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "## Customer Reviews\n",
                        "- The sound is clear and balanced.\n",
                        "- Battery lasts all day.\n",
                        "\n",
                        "| review_text | rating |\n",
                        "| --- | ---: |\n",
                        "| Spatial audio sounds immersive. | 5 |\n",
                        "| Charging takes too long. | 2 |",
                    ],
                },
                {
                    "cell_type": "code",
                    "source": [
                        "reviews = [\n",
                        "    'The fit is comfortable for hours.',\n",
                        "    'Bluetooth pairing stays stable.'\n",
                        "]",
                    ],
                    "outputs": [
                        {
                            "data": {
                                "text/html": [
                                    "<table><tr><th>review_text</th><th>rating</th></tr>",
                                    "<tr><td>ANC blocks noise well.</td><td>5</td></tr>",
                                    "<tr><td>The microphone sounds poor.</td><td>2</td></tr></table>",
                                ]
                            }
                        }
                    ],
                },
            ],
        }
        upload = UploadFile(
            file=io.BytesIO(json.dumps(notebook).encode()),
            filename="customer_feedback.ipynb",
        )

        result = asyncio.run(routes.notebook_analyze(upload))

        self.assertEqual(result["file_name"], "customer_feedback.ipynb")
        self.assertEqual(result["reviews_extracted"], 8)
        self.assertEqual(result["review_quality"]["valid_reviews"], 8)
        self.assertEqual(result["rating_distribution"]["5"]["count"], 2)
        self.assertEqual(result["rating_distribution"]["2"]["count"], 2)

    def test_notebook_with_no_review_content_returns_actionable_error(self):
        notebook = {
            "nbformat": 4,
            "cells": [{"cell_type": "code", "source": "print('hello')", "outputs": []}],
        }
        upload = UploadFile(file=io.BytesIO(json.dumps(notebook).encode()), filename="empty.ipynb")

        with self.assertRaises(HTTPException) as error:
            asyncio.run(routes.notebook_analyze(upload))

        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("No review text was found", error.exception.detail)

    def test_public_csv_review_export_link_extracts_review_rows(self):
        url = "https://example.com/customer-reviews.csv"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b"review_text,rating\nThe sound is clear and balanced.,5\nBattery life is too short.,2\n"
        )
        response.__enter__.return_value.headers.get_content_type.return_value = "text/csv"
        opener = MagicMock()
        opener.open.return_value = response

        with (
            patch.object(routes, "_validate_public_url", return_value=urlparse(url)),
            patch.object(routes, "build_opener", return_value=opener),
        ):
            result = routes._extract_page_metadata(url)

        self.assertEqual(result["platform"], "CSV review export")
        self.assertEqual(result["reviews_found"], 2)
        self.assertEqual(result["reviews"][0]["text"], "The sound is clear and balanced.")
        self.assertEqual(result["reviews"][0]["rating"], "5")

    def test_csv_without_review_text_column_is_rejected(self):
        csv_data = "product_id,category\nB1,earbuds\n"
        upload = UploadFile(file=io.BytesIO(csv_data.encode()), filename="feedback.csv")

        with self.assertRaises(HTTPException) as error:
            asyncio.run(routes.csv_analyze(upload))

        self.assertEqual(error.exception.status_code, 400)

    def test_amazon_url_without_structured_reviews_returns_limitation_not_stats(self):
        page_data = {
            "source_url": "https://www.amazon.in/realme/dp/B0DBGP48NW/",
            "platform": "Web page",
            "title": "realme Buds T310",
            "description": "Product marketing text",
            "content_preview": "Product marketing text",
            "reviews": [],
            "reviews_found": 0,
        }
        with (
            patch.object(routes, "_validate_public_url"),
            patch.object(routes, "_extract_page_metadata", return_value=page_data),
        ):
            result = routes.analyze_link(routes.LinkRequest(url=page_data["source_url"]))

        self.assertEqual(result["status"], "insufficient_reviews")
        self.assertEqual(result["title"], "realme Buds T310")
        self.assertEqual(result["reviews_found"], 0)
        self.assertEqual(result["valid_reviews_found"], 0)
        self.assertIsNone(result["analysis"])
        self.assertIn("no visible page text or customer-review text", result["message"])

    def test_blocked_page_returns_content_unavailable_without_running_models(self):
        page_data = {
            "source_url": "https://www.amazon.in/product",
            "platform": "Amazon",
            "title": None,
            "description": None,
            "text": "",
            "content_preview": "",
            "reviews": [],
            "reviews_found": 0,
            "fetch_error": (
                "The site returned an access or verification page instead of readable content. "
                "Sign-in, CAPTCHA, or anti-bot restrictions are not bypassed."
            ),
        }
        with (
            patch.object(routes, "_validate_public_url"),
            patch.object(routes, "_extract_page_metadata", return_value=page_data),
            patch.object(routes, "predict_sentiment") as sentiment,
            patch.object(routes, "detect_emotion") as emotion,
        ):
            result = routes.analyze_link(routes.LinkRequest(url=page_data["source_url"]))

        self.assertEqual(result["status"], "content_unavailable")
        self.assertIsNone(result["analysis"])
        self.assertIn("access or verification page", result["message"])
        sentiment.assert_not_called()
        emotion.assert_not_called()

    def test_link_with_too_few_valid_reviews_explains_minimum(self):
        page_data = {
            "source_url": "https://example.com/product",
            "platform": "Web page",
            "title": "Example product",
            "description": "Product description",
            "reviews": [
                {"text": "The battery life is excellent."},
                {"text": "The sound quality is clear and balanced."},
            ],
            "reviews_found": 2,
        }
        with (
            patch.object(routes, "_validate_public_url"),
            patch.object(routes, "_extract_page_metadata", return_value=page_data),
        ):
            result = routes.analyze_link(routes.LinkRequest(url=page_data["source_url"]))

        self.assertEqual(result["status"], "insufficient_reviews")
        self.assertEqual(result["reviews_found"], 2)
        self.assertEqual(result["valid_reviews_found"], 2)
        self.assertIsNone(result["analysis"])
        self.assertIn("At least 3 valid, unique reviews", result["message"])

    def test_demo_endpoint_aggregates_only_returned_demo_review_records(self):
        result = routes.demo_analysis()

        self.assertEqual(result["source"], "Demo (synthetic sample data)")
        self.assertEqual(result["review_quality"]["total_received"], 123)
        self.assertGreaterEqual(result["review_quality"]["duplicates_removed"], 2)
        self.assertEqual(sum(result["sentiment_counts"].values()), result["review_quality"]["valid_reviews"])


if __name__ == "__main__":
    unittest.main()
