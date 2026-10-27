import json
import urllib.request

sample = {"text": "The product quality is excellent but delivery was very late."}

request = urllib.request.Request(
    "http://127.0.0.1:8000/api/analyze",
    data=json.dumps(sample).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

response = urllib.request.urlopen(request, timeout=20)
body = response.read().decode("utf-8")
parsed = json.loads(body)

assert parsed["sentiment"]["label"] in {"Positive", "Negative", "Neutral", "Mixed"}
assert "Product Quality" in [item["aspect"] for item in parsed["aspects"]]
assert "Delivery" in [item["aspect"] for item in parsed["aspects"]]
print("Smoke test passed:", parsed["sentiment"]["label"], parsed["aspects"])
