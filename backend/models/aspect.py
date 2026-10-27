import re
from collections import defaultdict

ASPECT_KEYWORDS = {
    "Sound Quality": ["sound", "audio quality", "bass", "treble", "vocals", "music", "volume"],
    "Active Noise Cancellation": ["anc", "noise cancellation", "noise cancelling", "noise canceling"],
    "Ambient Mode": ["ambient mode", "transparency mode", "transparency"],
    "Spatial Audio": ["spatial audio", "spatial sound"],
    "Battery Life": ["battery", "battery life", "playtime", "charge lasts"],
    "Charging": ["charging", "charger", "charging case", "fast charging"],
    "Comfort and Fit": ["comfort", "comfortable", "fit", "ear tips", "ears hurt", "secure fit"],
    "Microphone and Calls": ["microphone", "mic", "call quality", "phone calls", "voice calls"],
    "Bluetooth and Pairing": ["bluetooth", "pairing", "disconnect", "connection", "connectivity"],
    "Latency and Gaming": ["latency", "lag", "gaming", "game mode"],
    "Product Quality": ["product quality", "build quality", "durability", "design", "materials", "build", "performance", "screen"],
    "Value for Money": ["value for money", "worth the price", "good value"],
    "Price": ["price", "cost", "expensive", "cheap", "affordable", "budget", "overpriced"],
    "Delivery": ["delivery", "shipping", "late", "arrived", "speed", "arrive", "shipment", "order", "dispatch"],
    "Customer Service": ["customer service", "support", "customer care", "help", "response", "agent", "team", "assistance"],
    "Packaging": ["packaging", "box", "condition", "wrapped", "delivery box", "package", "carton"],
    "Warranty": ["warranty", "replacement", "repair", "return policy"],
    "User Experience": ["experience", "usability", "interface", "setup", "navigation", "ui", "controls"],
}


def _clean_text(text):
    if not text:
        return ""
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", str(text).lower())
    return re.sub(r"\s+", " ", text).strip()


def extract_aspects(review_text: str):
    if not review_text or not review_text.strip():
        return []

    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+|[;\n]+", review_text) if segment.strip()]
    aspect_scores = defaultdict(int)

    for sentence in sentences:
        normalized_sentence = _clean_text(sentence)
        for aspect, keywords in ASPECT_KEYWORDS.items():
            matches = 0
            for keyword in keywords:
                pattern = r"\b" + re.escape(keyword) + r"\b"
                if re.search(pattern, normalized_sentence):
                    matches += 1
            if matches:
                aspect_scores[aspect] += matches

    if not aspect_scores:
        return []

    ranked_aspects = sorted(aspect_scores.items(), key=lambda item: (-item[1], list(ASPECT_KEYWORDS).index(item[0])))
    results = []
    for aspect, score in ranked_aspects[:5]:
        results.append({"aspect": aspect, "score": score})

    return results