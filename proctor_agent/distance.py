"""Pinhole face-distance estimates used locally for optional advisory signals."""

FACE_WIDTH_METRES = 0.15


def calibrate_focal_length(*, face_width_pixels, known_distance_metres, face_width_metres=FACE_WIDTH_METRES):
    """Return a focal length from one explicit, known-distance calibration."""
    if face_width_pixels <= 0 or known_distance_metres <= 0 or face_width_metres <= 0:
        raise ValueError("Face width and calibration distance must be positive.")
    return face_width_pixels * known_distance_metres / face_width_metres


def estimate_distance_metres(*, face_width_pixels, focal_length_pixels, face_width_metres=FACE_WIDTH_METRES):
    """Estimate distance with d = f_px * W_face / w_px."""
    if face_width_pixels <= 0 or focal_length_pixels <= 0 or face_width_metres <= 0:
        raise ValueError("Face width and focal length must be positive.")
    return focal_length_pixels * face_width_metres / face_width_pixels


def face_width_pixels(landmarks, frame_width):
    """Measure MediaPipe cheek-to-cheek width (landmarks 234 and 454)."""
    if frame_width <= 0 or len(landmarks) <= 454:
        raise ValueError("A full Face Mesh and positive frame width are required.")
    left, right = landmarks[234], landmarks[454]
    left_x = float(left.x if hasattr(left, "x") else left[0])
    right_x = float(right.x if hasattr(right, "x") else right[0])
    width = abs(right_x - left_x) * frame_width
    if width <= 0:
        raise ValueError("Face landmarks have zero width.")
    return width
