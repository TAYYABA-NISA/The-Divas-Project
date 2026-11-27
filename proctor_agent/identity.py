"""Optional local-only reference-photo comparison.

This intentionally lightweight comparison keeps numerical embeddings in memory,
discards them after each check, and sends only a confidence score on mismatch.
"""

import math


def _pixel_values(image):
    """Return a flattened grayscale image without requiring OpenCV in unit tests."""
    if hasattr(image, "shape"):
        if len(image.shape) == 3:
            image = image.mean(axis=2)
        height, width = image.shape[:2]
        target_h, target_w = min(32, height), min(32, width)
        rows = [int(index * height / target_h) for index in range(target_h)]
        cols = [int(index * width / target_w) for index in range(target_w)]
        return [float(image[row, col]) for row in rows for col in cols]
    return [float(value) for row in image for value in row]


def face_embedding(image):
    values = _pixel_values(image)
    if not values:
        raise ValueError("An image is required for identity comparison.")
    mean = sum(values) / len(values)
    centred = [value - mean for value in values]
    magnitude = math.sqrt(sum(value * value for value in centred))
    if magnitude < 1e-9:
        # A flat synthetic image is still deterministic but uninformative.
        return tuple(0.0 for _ in centred)
    return tuple(value / magnitude for value in centred)


def similarity(reference_embedding, current_embedding):
    if len(reference_embedding) != len(current_embedding) or not reference_embedding:
        return 0.0
    return sum(left * right for left, right in zip(reference_embedding, current_embedding))


def compare_faces(reference_image, current_image, threshold=0.82):
    """Return (matched, confidence) without persisting a biometric embedding."""
    score = max(0.0, min(1.0, similarity(face_embedding(reference_image), face_embedding(current_image))))
    return score >= threshold, round(score, 3)
