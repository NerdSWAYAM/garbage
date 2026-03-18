from transformers import pipeline

# Load the pipeline globally so it is not re-loaded for every request
pipe = pipeline("image-classification", model="watersplash/waste-classification")

def predict_image(image):
    """
    Takes a PIL image and returns the highest scoring label.
    """
    results = pipe(image)
    if results and len(results) > 0:
        # results usually looks like [{'score': 0.99, 'label': 'plastic'}, ...]
        return results[0]['label']
    return "Unknown"