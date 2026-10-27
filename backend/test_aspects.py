from backend.models.aspect import extract_aspects
from backend.models.aspect_sentiment import analyze_aspect_sentiment

sample_review = "The product quality is excellent but delivery was very late."

print("Testing Aspect Extraction:")
aspects = extract_aspects(sample_review)
print("Extracted Aspects:", aspects)

print("\nTesting Aspect-Based Sentiment Analysis:")
aspect_sentiments = analyze_aspect_sentiment(sample_review)
print("Aspect Sentiments:", aspect_sentiments)
