import csv
import ast
import html
import io
import json
import os
import re
import ipaddress
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request as UrlRequest, build_opener

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from backend.models.aspect import extract_aspects
from backend.models.aspect_sentiment import analyze_aspect_sentiment
from backend.models.emotion import detect_emotion
from backend.models.fake_review import detect_fake_review
from backend.models.sarcasm import detect_sarcasm
from backend.models.sentiment import predict_sentiment
from backend.explainability.explainer import generate_explanation
from backend.services.review_pipeline import analyze_review_records, build_demo_reviews

router = APIRouter()
HOST = os.getenv("SENTIVERSE_HOST", "127.0.0.1")
PORT = int(os.getenv("SENTIVERSE_PORT", "8000"))
MAX_LINK_DOCUMENT_CHARS = 50_000
MAX_LINK_RESPONSE_BYTES = 2_000_000
SENTIMENT_METRICS_PATH = (
    Path(__file__).resolve().parents[2] / "results" / "sentiment_uci_evaluation.json"
)


class ReviewRequest(BaseModel):
    text: str


class BatchReviewRequest(BaseModel):
    reviews: list[str]


class LinkRequest(BaseModel):
    url: str


def _clean_html_text(raw_html: str) -> str:
    if not raw_html:
        return ""

    cleaned = re.sub(r"<head\b.*?</head>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<script.*?</script>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_meta_value(html_content: str, names: list[str]) -> str:
    for name in names:
        pattern = rf"(?i)<meta[^>]+(?:name|property)=['\"]{re.escape(name)}['\"][^>]*content=['\"]([^'\"]+)['\"][^>]*>"
        match = re.search(pattern, html_content)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def _extract_structured_reviews(html_content: str) -> tuple[list[dict], str | None]:
    reviews = []
    product_name = None

    def visit(value):
        nonlocal product_name
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return

        types = value.get("@type", [])
        if isinstance(types, str):
            types = [types]
        normalized_types = {
            str(item).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
            for item in types
        }
        if "Product" in normalized_types:
            product_name = product_name or value.get("name")
        if "Review" in normalized_types:
            body = value.get("reviewBody") or value.get("description")
            if isinstance(body, str) and body.strip():
                rating = value.get("reviewRating")
                if isinstance(rating, dict):
                    rating = rating.get("ratingValue")
                author = value.get("author")
                if isinstance(author, dict):
                    author = author.get("name")
                reviews.append({
                    "text": body.strip(),
                    "rating": rating,
                    "date": value.get("datePublished"),
                    "review_id": value.get("@id"),
                    "user_name": author,
                })
        for child in value.values():
            visit(child)

    scripts = re.findall(
        r"<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for script in scripts:
        try:
            visit(json.loads(script.strip()))
        except (json.JSONDecodeError, RecursionError):
            continue
    return reviews, product_name


class _MarkedReviewParser(HTMLParser):
    _VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.reviews = []
        self._capture_stack = []
        self._capture_parts = []

    def handle_starttag(self, tag, attrs):
        attributes = {name.lower(): value or "" for name, value in attrs}
        itemprop = {value.lower() for value in attributes.get("itemprop", "").split()}
        classes = {value.lower() for value in attributes.get("class", "").split()}
        data_hook = attributes.get("data-hook", "").lower()
        marker = (
            "reviewbody" in itemprop
            or data_hook in {"review-body", "review-text", "review-content"}
            or bool(classes & {"review-body", "review-text"})
        )

        if not self._capture_stack and marker:
            self._capture_stack = [tag]
            self._capture_parts = []
        elif self._capture_stack and tag not in self._VOID_TAGS:
            self._capture_stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self._capture_stack:
            return
        for index in range(len(self._capture_stack) - 1, -1, -1):
            if self._capture_stack[index] == tag:
                del self._capture_stack[index:]
                break
        if not self._capture_stack:
            text = _clean_html_text(" ".join(self._capture_parts))
            if text:
                self.reviews.append({"text": text})
            self._capture_parts = []

    def handle_data(self, data):
        if self._capture_stack:
            self._capture_parts.append(data)


def _extract_marked_review_bodies(html_content: str) -> list[dict]:
    parser = _MarkedReviewParser()
    parser.feed(html_content)
    parser.close()
    return parser.reviews


class _VisiblePageTextParser(HTMLParser):
    _SKIPPED_TAGS = {
        "aside", "button", "canvas", "footer", "form", "head", "header",
        "iframe", "noscript", "nav", "script", "style", "svg", "template",
    }
    _BLOCK_TAGS = {
        "address", "article", "blockquote", "br", "dd", "div", "dl", "dt",
        "h1", "h2", "h3", "h4", "h5", "h6", "li", "main", "ol", "p",
        "section", "table", "td", "th", "tr", "ul",
    }
    _VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }
    _NOISE_MARKERS = re.compile(
        r"(?:^|[\s_-])(?:ad|ads|advert|advertisement|breadcrumb|cookie|consent|"
        r"footer|header|hidden|menu|nav|navigation|navbar|overlay|pagination|popup|promo|"
        r"recommendations?|related|share|sidebar|social)(?:$|[\s_-])",
        re.IGNORECASE,
    )
    _CONTENT_MARKERS = re.compile(
        r"(?:article|post|entry|story|blog|prose|main-content|page-content|"
        r"article-body|post-content|entry-content|story-body|content-body)",
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._root = {"tag": "document", "attrs": {}, "children": []}
        self._stack = [self._root]

    def handle_starttag(self, tag, attrs):
        attributes = {name.lower(): value or "" for name, value in attrs}
        node = {"tag": tag, "attrs": attributes, "children": []}
        self._stack[-1]["children"].append(node)
        if tag not in self._VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index]["tag"] == tag:
                del self._stack[index:]
                break

    def handle_data(self, data):
        self._stack[-1]["children"].append(data)

    @classmethod
    def _is_hidden_or_noise(cls, node) -> bool:
        attrs = node["attrs"]
        classes_and_id = f"{attrs.get('id', '')} {attrs.get('class', '')}"
        return (
            node["tag"] in cls._SKIPPED_TAGS
            or "hidden" in attrs
            or attrs.get("aria-hidden", "").lower() == "true"
            or attrs.get("role", "").lower() in {
                "banner", "complementary", "contentinfo", "navigation", "toolbar",
            }
            or bool(re.search(
                r"(?:^|[\s_-])(?:sr-only|visually-hidden)(?:$|[\s_-])",
                attrs.get("class", ""),
                re.IGNORECASE,
            ))
            or bool(re.search(
                r"display\s*:\s*none|visibility\s*:\s*hidden",
                attrs.get("style", ""),
                re.IGNORECASE,
            ))
            or bool(cls._NOISE_MARKERS.search(classes_and_id))
        )

    @classmethod
    def _render_text(cls, node) -> str:
        if isinstance(node, str):
            return node
        if cls._is_hidden_or_noise(node):
            return ""
        parts = []
        if node["tag"] in cls._BLOCK_TAGS:
            parts.append("\n")
        parts.extend(cls._render_text(child) for child in node["children"])
        if node["tag"] in cls._BLOCK_TAGS:
            parts.append("\n")
        return "".join(parts)

    @classmethod
    def _candidate_score(cls, node) -> int:
        attrs = node["attrs"]
        role = attrs.get("role", "").lower()
        itemprop = attrs.get("itemprop", "").lower().split()
        markers = f"{attrs.get('id', '')} {attrs.get('class', '')}"
        score = 0
        if "articlebody" in itemprop:
            score += 20
        if node["tag"] == "article":
            score += 12
        if role == "main":
            score += 10
        if node["tag"] == "main":
            score += 8
        if cls._CONTENT_MARKERS.search(markers):
            score += 5
        return score

    def get_text(self) -> str:
        candidates = []

        def visit(node):
            if isinstance(node, str) or self._is_hidden_or_noise(node):
                return
            score = self._candidate_score(node)
            if score:
                candidate_text = self._render_text(node)
                if candidate_text.strip():
                    candidates.append((score, len(candidate_text), candidate_text))
            for child in node["children"]:
                visit(child)

        visit(self._root)
        if candidates:
            text = max(candidates, key=lambda item: (item[0], item[1]))[2]
        else:
            text = self._render_text(self._root)
        text = re.sub(r"[ \t]+", " ", text)
        return re.sub(r"[ \t]*\n[ \t]*", "\n", text).strip()


def _extract_visible_page_text(page_content: str, content_type: str) -> str:
    if content_type == "text/plain":
        return html.unescape(page_content).strip()
    parser = _VisiblePageTextParser()
    parser.feed(page_content)
    parser.close()
    return parser.get_text()


def _looks_like_access_interstitial(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).casefold()
    markers = (
        "click the button below to continue shopping",
        "enter the characters you see below",
        "robot check",
        "sorry, we just need to make sure you're not a robot",
        "automated access to this site",
        "enable javascript and cookies to continue",
        "complete the security check to continue",
    )
    return any(marker in normalized for marker in markers)


def _normalize_link_url(url: str) -> str:
    candidate = url.strip()
    if candidate.startswith("//"):
        return f"https:{candidate}"
    if re.match(r"^[A-Za-z0-9.-]+:\d+(?:/|$)", candidate):
        return f"https://{candidate}"
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", candidate):
        return candidate
    return f"https://{candidate}"


def _validate_public_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Enter a valid public http or https URL.")
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("Local network URLs are not supported.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise ValueError("The URL host could not be resolved.") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Only publicly accessible URLs are supported.")
    return parsed


class _PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        _validate_public_url(new_url)
        return super().redirect_request(request, response, code, message, headers, new_url)


def _extract_page_metadata(url: str) -> dict:
    try:
        parsed = _validate_public_url(url)

        request = UrlRequest(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
            method="GET",
        )
        with build_opener(_PublicRedirectHandler).open(request, timeout=20) as response:
            raw = response.read(MAX_LINK_RESPONSE_BYTES + 1)
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset()
            response_url = response.geturl()

        response_truncated = len(raw) > MAX_LINK_RESPONSE_BYTES
        raw = raw[:MAX_LINK_RESPONSE_BYTES]
        if not isinstance(charset, str) or not charset:
            charset = "utf-8"
        try:
            html_content = raw.decode(charset, errors="replace")
        except LookupError:
            html_content = raw.decode("utf-8", errors="replace")
        final_url = response_url if isinstance(response_url, str) and response_url else url
        parsed = _validate_public_url(final_url)
        file_path = parsed.path.lower()
        source_format = None
        document_text = ""
        if content_type in {"text/csv", "application/csv"} or file_path.endswith(".csv"):
            reviews = _records_from_review_csv(html_content)
            product_name = None
            source_format = "CSV review export"
        elif content_type in {"application/json", "application/ld+json"} or file_path.endswith(".json"):
            try:
                json_data = json.loads(html_content)
            except json.JSONDecodeError:
                json_data = None
            reviews = _records_from_notebook_table(json_data)
            product_name = None
            source_format = "JSON review export"
        else:
            reviews, product_name = _extract_structured_reviews(html_content)
            marked_reviews = _extract_marked_review_bodies(html_content)
            review_texts = {review["text"].casefold() for review in reviews}
            reviews.extend(review for review in marked_reviews if review["text"].casefold() not in review_texts)
            if content_type in {"text/html", "application/xhtml+xml", "text/plain"}:
                document_text = _extract_visible_page_text(html_content, content_type)
        interstitial_detected = _looks_like_access_interstitial(document_text)
        if interstitial_detected:
            document_text = ""

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, flags=re.IGNORECASE | re.DOTALL)
        title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else parsed.netloc
        metadata_title = _extract_meta_value(html_content, ["og:title", "twitter:title"])
        product_name = product_name or metadata_title or title
        normalized_title = product_name.casefold().removeprefix("www.") if isinstance(product_name, str) else ""
        normalized_host = (parsed.hostname or "").casefold().removeprefix("www.")
        if not normalized_title or normalized_title in {parsed.netloc.casefold(), normalized_host}:
            product_name = None

        description = _extract_meta_value(
            html_content,
            ["og:description", "twitter:description", "description"],
        )

        cleaned_text = _clean_html_text(html_content)
        preview_text = (
            description
            or document_text[:350]
            or ("" if interstitial_detected else cleaned_text[:350])
        )
        hostname = parsed.netloc.lower()
        platform = "Web page"
        if "amazon." in hostname:
            platform = "Amazon"
        elif "youtube.com" in hostname or "youtu.be" in hostname:
            platform = "YouTube"
        elif "twitter.com" in hostname or "x.com" in hostname:
            platform = "Twitter/X"
        elif "instagram.com" in hostname:
            platform = "Instagram"
        elif "facebook.com" in hostname:
            platform = "Facebook"
        if source_format:
            platform = source_format

        result = {
            "source_url": final_url,
            "platform": platform,
            "title": product_name,
            "description": description or preview_text,
            "text": document_text[:MAX_LINK_DOCUMENT_CHARS],
            "document_characters_extracted": len(document_text),
            "document_truncated": (
                len(document_text) > MAX_LINK_DOCUMENT_CHARS or response_truncated
            ),
            "content_preview": preview_text[:500],
            "reviews": reviews,
            "reviews_found": len(reviews),
        }
        if interstitial_detected:
            result["fetch_error"] = (
                "The site returned an access or verification page instead of readable content. "
                "Sign-in, CAPTCHA, or anti-bot restrictions are not bypassed."
            )
        return result
    except (HTTPError, URLError, ValueError, TimeoutError, OSError):
        return {
            "source_url": url,
            "platform": "Unknown",
            "title": None,
            "description": None,
            "text": "",
            "document_characters_extracted": 0,
            "document_truncated": False,
            "content_preview": "",
            "reviews": [],
            "reviews_found": 0,
            "fetch_error": "The source could not be fetched or its review content was blocked.",
        }


def _normalize_column_name(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _pick_review_column(fieldnames):
    if not fieldnames:
        return None

    normalized = {
        _normalize_column_name(name): name
        for name in fieldnames
        if name is not None
    }
    preferred = [
        "review",
        "review_text",
        "review_body",
        "customer_review",
        "customer_feedback",
        "comment",
        "feedback",
        "text",
        "message",
        "content",
        "body",
    ]

    for name in preferred:
        if name in normalized:
            return normalized[name]

    return None


def _records_from_review_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []

    review_column = _pick_review_column(reader.fieldnames)
    if review_column is None:
        return []

    normalized_fields = {
        _normalize_column_name(name): name
        for name in reader.fieldnames
        if name is not None
    }
    optional_columns = {
        "review_id": ("review_id", "id"),
        "rating": ("rating", "stars", "star_rating"),
        "date": ("date", "review_date", "created_at"),
        "verified_purchase": ("verified_purchase", "verified", "purchase_verified"),
        "user_name": ("user_name", "username", "author", "reviewer"),
        "helpful_votes": ("helpful_votes", "helpful"),
        "product_id": ("product_id", "asin"),
    }
    records = []
    for row in reader:
        record = {"text": row.get(review_column)}
        for target, candidates in optional_columns.items():
            column = next((normalized_fields[name] for name in candidates if name in normalized_fields), None)
            if column:
                record[target] = row.get(column)
        records.append(record)
    return records


class _NotebookTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _records_from_table_rows(rows):
    if len(rows) < 2 or not rows[0]:
        return []

    headers = rows[0]
    review_column = _pick_review_column(headers)
    if review_column is None:
        return []

    header_indexes = {header: index for index, header in enumerate(headers)}
    review_index = header_indexes[review_column]
    optional_indexes = {}
    for target, names in {
        "review_id": ("review_id", "id"),
        "rating": ("rating", "stars", "star_rating"),
    }.items():
        normalized_headers = {
            _normalize_column_name(header): index
            for index, header in enumerate(headers)
        }
        optional_indexes[target] = next(
            (normalized_headers[name] for name in names if name in normalized_headers),
            None,
        )

    records = []
    for row in rows[1:]:
        if review_index >= len(row):
            continue
        record = {"text": row[review_index]}
        for target, index in optional_indexes.items():
            if index is not None and index < len(row):
                record[target] = row[index]
        records.append(record)
    return records


def _records_from_notebook_table(value):
    if isinstance(value, dict):
        for key in ("reviews", "data"):
            if isinstance(value.get(key), (list, dict)):
                nested_records = _records_from_notebook_table(value[key])
                if nested_records:
                    return nested_records

    if isinstance(value, list):
        if value and all(isinstance(row, dict) for row in value):
            review_column = _pick_review_column(value[0].keys())
            if review_column is None:
                return []
            records = []
            for row in value:
                record = {"text": row.get(review_column)}
                for target, names in {
                    "review_id": ("review_id", "id"),
                    "rating": ("rating", "stars", "star_rating"),
                }.items():
                    normalized = {
                        _normalize_column_name(key): key
                        for key in row
                    }
                    column = next((normalized[name] for name in names if name in normalized), None)
                    if column is not None:
                        record[target] = row[column]
                records.append(record)
            return records
        return []

    if not isinstance(value, dict):
        return []

    columns = value.get("columns")
    data = value.get("data")
    if isinstance(columns, list) and isinstance(data, list):
        return _records_from_table_rows([columns, *data])

    review_column = _pick_review_column(value.keys())
    if review_column is None:
        return []
    review_values = value[review_column]
    if not isinstance(review_values, list):
        review_values = [review_values]

    normalized_keys = {
        _normalize_column_name(key): key
        for key in value
    }
    optional_columns = {}
    for target, names in {
        "review_id": ("review_id", "id"),
        "rating": ("rating", "stars", "star_rating"),
    }.items():
        column = next((normalized_keys[name] for name in names if name in normalized_keys), None)
        if column is not None:
            optional_columns[target] = value[column]

    records = []
    for index, review in enumerate(review_values):
        record = {"text": review}
        for target, column_values in optional_columns.items():
            if isinstance(column_values, list) and index < len(column_values):
                record[target] = column_values[index]
            elif not isinstance(column_values, list):
                record[target] = column_values
        records.append(record)
    return records


def _markdown_cell_reviews(source):
    reviews = []
    has_headings = False
    in_review_section = False
    in_code_fence = False
    paragraph = []
    lines = source.splitlines()

    def flush_paragraph():
        if paragraph and (in_review_section or not has_headings):
            text = " ".join(paragraph).strip()
            text = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", text)
            text = re.sub(r"^(?:review|feedback|comment)\s*:\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
            text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
            text = re.sub(r"[*_`>#]", "", text).strip()
            if text:
                reviews.append({"text": text})
        paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush_paragraph()
            in_code_fence = not in_code_fence
            index += 1
            continue
        if in_code_fence:
            index += 1
            continue

        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*$", stripped)
        if heading:
            flush_paragraph()
            has_headings = True
            in_review_section = bool(
                re.search(r"\b(review|reviews|feedback|comments?)\b", heading.group(1), re.IGNORECASE)
            )
            index += 1
            continue
        if not stripped:
            flush_paragraph()
            index += 1
            continue

        if "|" in stripped and index + 1 < len(lines) and "|" in lines[index + 1]:
            table_lines = [stripped]
            next_index = index + 1
            while next_index < len(lines) and "|" in lines[next_index]:
                table_lines.append(lines[next_index].strip())
                next_index += 1
            table_rows = [
                [cell.strip() for cell in table_line.strip("|").split("|")]
                for table_line in table_lines
            ]
            if len(table_rows) > 1 and all(
                all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)
                for row in table_rows[1:2]
            ):
                flush_paragraph()
                table_rows = [table_rows[0], *table_rows[2:]]
                table_records = _records_from_table_rows(table_rows)
                if table_records:
                    reviews.extend(table_records)
                    index = next_index
                    continue

        if re.match(r"^(?:[-*+]|\d+[.)])\s+", stripped):
            flush_paragraph()
        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    return reviews


def _literal_code_reviews(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    records = []
    review_variable = re.compile(r"(review|feedback|comment|customer_text)", re.IGNORECASE)
    for node in ast.walk(tree):
        value_node = None
        target_names = []
        if isinstance(node, ast.Assign):
            value_node = node.value
            target_nodes = node.targets
        elif isinstance(node, ast.AnnAssign):
            value_node = node.value
            target_nodes = [node.target]
        else:
            continue

        for target in target_nodes:
            if isinstance(target, ast.Name):
                target_names.append(target.id)
        try:
            literal_value = ast.literal_eval(value_node) if value_node is not None else None
        except (ValueError, TypeError, SyntaxError):
            literal_value = None

        table_records = _records_from_notebook_table(literal_value)
        if table_records:
            records.extend(table_records)
        elif any(review_variable.search(name) for name in target_names):
            if isinstance(literal_value, str):
                records.append({"text": literal_value})
            elif isinstance(literal_value, (list, tuple)):
                records.extend({"text": value} for value in literal_value if isinstance(value, str))

    return records


def _extract_notebook_reviews(notebook):
    if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
        raise ValueError("Notebook JSON must contain a cells array.")

    records = []
    for cell in notebook["cells"]:
        if not isinstance(cell, dict):
            continue
        source_value = cell.get("source", "")
        source = "".join(source_value) if isinstance(source_value, list) else str(source_value)
        cell_type = cell.get("cell_type")
        if cell_type == "markdown":
            records.extend(_markdown_cell_reviews(source))
        elif cell_type == "code":
            records.extend(_literal_code_reviews(source))

            for output in cell.get("outputs", []):
                if not isinstance(output, dict):
                    continue
                output_data = output.get("data", {})
                if not isinstance(output_data, dict):
                    continue
                html_output = output_data.get("text/html")
                if isinstance(html_output, list):
                    html_output = "".join(html_output)
                if isinstance(html_output, str):
                    table_parser = _NotebookTableParser()
                    table_parser.feed(html_output)
                    table_parser.close()
                    records.extend(_records_from_table_rows(table_parser.rows))

                for mime_type in ("application/json", "application/vnd.dataresource+json"):
                    json_output = output_data.get(mime_type)
                    if isinstance(json_output, list):
                        json_output = "".join(json_output)
                    if isinstance(json_output, str):
                        try:
                            json_output = json.loads(json_output)
                        except json.JSONDecodeError:
                            continue
                    records.extend(_records_from_notebook_table(json_output))

    return records


@router.post("/summarize")
def summarize_reviews_endpoint(payload: BatchReviewRequest):
    reviews = [review for review in payload.reviews if review and review.strip()]
    if not reviews:
        raise HTTPException(status_code=400, detail="At least one review is required for summarization.")

    analysis = analyze_review_records(reviews, source="Manual")
    return {
        "summary": analysis["summary"],
        "insights": analysis["insights"],
        "review_quality": analysis["review_quality"],
    }


@router.post("/analyze-link")
def analyze_link(payload: LinkRequest):
    raw_url = (payload.url or "").strip()
    if not raw_url:
        raise HTTPException(status_code=400, detail="A valid URL is required.")
    url = _normalize_link_url(raw_url)
    try:
        _validate_public_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    page_data = _extract_page_metadata(url)
    reviews = page_data.get("reviews", [])
    analysis = analyze_review_records(reviews, source=page_data.get("platform", "URL")) if reviews else None
    document_text = page_data.get("text", "")
    if not reviews and document_text.strip():
        sentiment = predict_sentiment(document_text)
        document_analysis = {
            "sentiment": sentiment,
            "emotion": detect_emotion(document_text),
            "aspects": analyze_aspect_sentiment(document_text),
            "content_characters_extracted": page_data.get("document_characters_extracted", len(document_text)),
            "content_characters_analyzed": len(document_text),
            "content_truncated": page_data.get("document_truncated", False),
            "content_preview": document_text[:1200],
            "explanation": generate_explanation(document_text[:10_000]),
        }
        return {
            "status": "ok",
            "analysis_type": "page_document",
            "message": (
                "Analyzed visible page text as one document. This is page-level content, "
                "not an aggregate of customer reviews."
            ),
            "source_url": page_data.get("source_url"),
            "platform": page_data.get("platform"),
            "title": page_data.get("title"),
            "description": page_data.get("description"),
            "content_preview": page_data.get("content_preview"),
            "metadata_extracted": bool(page_data.get("title") or page_data.get("description")),
            "reviews_found": page_data.get("reviews_found", 0),
            "valid_reviews_found": 0,
            "document_analysis": document_analysis,
            "analysis": None,
        }
    valid_reviews_found = analysis["review_quality"]["valid_reviews"] if analysis else 0
    if analysis and analysis["total_reviews"] < 3:
        analysis = None
    if analysis:
        message = None
    elif page_data.get("fetch_error"):
        message = page_data["fetch_error"]
    elif not reviews and not document_text.strip():
        platform = page_data.get("platform") or "This source"
        source_label = (
            "Amazon product page" if platform == "Amazon"
            else "page" if platform == "Web page"
            else "linked CSV export" if platform == "CSV review export"
            else "linked JSON export" if platform == "JSON review export"
            else f"{platform} page"
        )
        message = (
            f"The {source_label} was retrieved, but no visible page text or customer-review "
            "text was available to analyze. The page may require JavaScript, sign-in, or "
            "may block automated access."
        )
    else:
        message = (
            f"The page contained {len(reviews)} structured review record(s), but only "
            f"{valid_reviews_found} passed review validation. At least 3 valid, unique reviews are "
            "required to generate aggregate sentiment statistics."
        )
    return {
        "status": (
            "content_unavailable" if page_data.get("fetch_error")
            else "ok" if analysis
            else "insufficient_reviews"
        ),
        "message": message,
        "source_url": page_data.get("source_url"),
        "platform": page_data.get("platform"),
        "title": page_data.get("title"),
        "description": page_data.get("description"),
        "content_preview": page_data.get("content_preview"),
        "metadata_extracted": bool(page_data.get("title") or page_data.get("description")),
        "reviews_found": page_data.get("reviews_found", 0),
        "valid_reviews_found": valid_reviews_found,
        "analysis": analysis,
    }


@router.post("/explainability")
def explain_review_endpoint(payload: ReviewRequest):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Review text is required for explanations.")
    return generate_explanation(text)


@router.get("/health")
def health_check(request: Request):
    resolved_host = request.url.hostname or HOST
    resolved_port = request.url.port or PORT
    return {
        "status": "ok",
        "host": resolved_host,
        "port": resolved_port,
        "message": "API is running smoothly.",
    }


@router.post("/analyze")
def analyze_review(payload: ReviewRequest):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Review text is required.")

    review_texts = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    if len(review_texts) > 1:
        return analyze_review_records(review_texts, source="Manual")

    analysis = analyze_review_records([text], source="Manual")
    record = analysis["reviews"][0] if analysis["reviews"] else None
    if record is None:
        raise HTTPException(status_code=400, detail="Review text is empty, too short, or invalid after cleaning.")
    sentiment = record["sentiment"]
    aspects = extract_aspects(text)
    aspect_sentiments = record["aspects"]
    emotion = record["emotion"]
    sarcasm = detect_sarcasm(text)
    fake_review = detect_fake_review(text)

    return {
        **analysis,
        "text": text,
        "sentiment": sentiment,
        "aspects": aspects,
        "aspect_sentiments": aspect_sentiments,
        "emotion": emotion,
        "sarcasm": sarcasm,
        "fake_review": fake_review,
        "summary": analysis["summary"],
        "insights": analysis["recommendations"],
        "review_quality": analysis["review_quality"],
    }


@router.post("/aspect-extraction")
def aspect_extraction_endpoint(payload: ReviewRequest):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Review text is required.")
    return {"aspects": extract_aspects(text)}


@router.post("/emotion-detection")
def emotion_detection_endpoint(payload: ReviewRequest):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Review text is required.")
    return detect_emotion(text)


@router.post("/sarcasm-detection")
def sarcasm_detection_endpoint(payload: ReviewRequest):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Review text is required.")
    return detect_sarcasm(text)


@router.post("/fake-review-detection")
def fake_review_detection_endpoint(payload: ReviewRequest):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Review text is required.")
    return detect_fake_review(text)


@router.get("/dashboard")
def dashboard_overview():
    return analyze_review_records([], source="No analysis loaded")["dashboard"]


@router.get("/model-metrics")
def model_metrics_endpoint():
    if SENTIMENT_METRICS_PATH.is_file():
        return json.loads(SENTIMENT_METRICS_PATH.read_text(encoding="utf-8"))
    return {
        "status": "not_evaluated",
        "message": (
            "Sentiment metrics are not available. Prepare and evaluate the independent "
            "dataset with the documented model commands."
        ),
    }


@router.get("/extended-model-metrics")
def extended_model_metrics_endpoint():
    if SENTIMENT_METRICS_PATH.is_file():
        report = json.loads(SENTIMENT_METRICS_PATH.read_text(encoding="utf-8"))
        overall = report["overall"]
        return {
            "status": "partially_evaluated",
            "message": (
                "Sentiment has an independent held-out evaluation. Emotion, sarcasm, and "
                "suspicious-review models have not been independently evaluated."
            ),
            "sentiment": {
                "accuracy": overall["accuracy"],
                "precision": overall["weighted_precision"],
                "recall": overall["weighted_recall"],
                "f1_score": overall["weighted_f1"],
                "dataset_size": report["dataset_size"],
                "dataset": report["dataset"],
            },
        }
    return {
        "status": "not_evaluated",
        "message": (
            "Model performance metrics are not available. Prepare and evaluate the "
            "independent dataset with the documented model commands."
        ),
    }


@router.post("/batch-analyze")
def batch_analyze(payload: BatchReviewRequest):
    analysis = analyze_review_records(payload.reviews, source="Manual")
    analysis["results"] = analysis["reviews"]
    return analysis


@router.post("/csv-analyze")
async def csv_analyze(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="A CSV file is required.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty.")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="CSV file could not be decoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file does not contain a header row.")

    review_column = _pick_review_column(reader.fieldnames)
    if review_column is None:
        raise HTTPException(status_code=400, detail="CSV must contain a review, text, comment, feedback, or content column.")

    optional_columns = {
        "review_id": ("review_id", "id"),
        "rating": ("rating", "stars", "star_rating"),
        "date": ("date", "review_date", "created_at"),
        "verified_purchase": ("verified_purchase", "verified", "purchase_verified"),
        "user_name": ("user_name", "username", "author", "reviewer"),
        "helpful_votes": ("helpful_votes", "helpful"),
        "product_id": ("product_id", "asin"),
    }
    normalized_fields = {
        _normalize_column_name(name): name
        for name in reader.fieldnames
        if name is not None
    }
    records = []
    try:
        for row in reader:
            if row is None:
                continue
            record = {"text": row.get(review_column)}
            for target, candidates in optional_columns.items():
                column = next((normalized_fields[name] for name in candidates if name in normalized_fields), None)
                if column:
                    record[target] = row.get(column)
            records.append(record)
    except csv.Error as exc:
        raise HTTPException(status_code=400, detail="The uploaded CSV file is malformed.") from exc

    if not records:
        raise HTTPException(status_code=400, detail="No review rows were found in the uploaded CSV file.")

    analysis = analyze_review_records(records, source="CSV")
    return {
        **analysis,
        "file_name": file.filename,
        "review_column": review_column,
        "results": analysis["reviews"],
    }


@router.post("/notebook-analyze")
async def notebook_analyze(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".ipynb"):
        raise HTTPException(status_code=400, detail="A Jupyter Notebook (.ipynb) file is required.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded notebook file is empty.")

    try:
        notebook = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Notebook file is not valid UTF-8 Jupyter JSON.") from exc

    try:
        records = _extract_notebook_reviews(notebook)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not records:
        raise HTTPException(
            status_code=400,
            detail=(
                "No review text was found in this notebook. Add a table with a review, text, comment, "
                "feedback, or content column, a Markdown review section, or a literal reviews list in a "
                "code cell. Notebook code is never executed."
            ),
        )

    analysis = analyze_review_records(records, source="Notebook")
    return {
        **analysis,
        "file_name": file.filename,
        "reviews_extracted": len(records),
        "results": analysis["reviews"],
    }


@router.post("/analyze/reviews")
def analyze_review_records_endpoint(payload: BatchReviewRequest):
    return analyze_review_records(payload.reviews, source="Manual")


@router.get("/demo")
def demo_analysis():
    return analyze_review_records(build_demo_reviews(), source="Demo (synthetic sample data)")