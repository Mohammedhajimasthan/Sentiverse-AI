import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.aspect import extract_aspects
from backend.models.emotion import detect_emotion
from backend.models.fake_review import detect_fake_review
from backend.models.sarcasm import detect_sarcasm

aspects = extract_aspects("The product quality is excellent and the delivery was quick, but the price was expensive.")
assert any(item["aspect"] == "Product Quality" for item in aspects)
assert any(item["aspect"] == "Delivery" for item in aspects)
assert any(item["aspect"] == "Price" for item in aspects)
assert detect_emotion("I am so happy and loved the product")['emotion'] in {"Joy", "Love"}
assert detect_sarcasm("Great job, the product broke after one day")['sarcasm'] == "Sarcastic"
assert detect_fake_review("Amazing product! Great! Love it! Best ever!")['review_type'] == "Suspicious"

print("Heuristic analysis tests passed.")
