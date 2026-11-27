"""Optional live webcam agent. Heavy imports stay inside this module's runner."""

import os
import tempfile
import time

from .distance import calibrate_focal_length, estimate_distance_metres, face_width_pixels
from .gaze import GazeMonitor, face_is_looking_away
from .identity import compare_faces
from .phone import ConsecutivePhoneFilter, YoloPhoneDetector
from .screen import ScreenRingBuffer, capture_screen_frame
from .uplink import UplinkError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _load_reference_image(client, cv2):
    try:
        raw = client.fetch_profile_photo()
    except UplinkError:
        return None
    import numpy

    return cv2.imdecode(numpy.frombuffer(raw, dtype=numpy.uint8), cv2.IMREAD_COLOR)


def _upload_event(client, event, screen_buffer):
    response = client.post_event(event.event_type, event.severity, event.details)
    if event.event_type != "PHONE_DETECTED" or not screen_buffer:
        return
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temporary:
        clip_path = temporary.name
    try:
        screen_buffer.write_mp4(clip_path)
        if os.path.getsize(clip_path) <= MAX_UPLOAD_BYTES:
            client.post_clip(response["id"], clip_path)
    finally:
        if os.path.exists(clip_path):
            os.unlink(clip_path)


def run_live(args, client):
    """Run detectors locally and upload only minimized advisory events."""
    try:
        import cv2
        import mediapipe as mp
    except ImportError as error:
        raise RuntimeError("Install proctor_agent/requirements-hardware.txt for live monitoring.") from error

    capture_source = args.video if args.video else args.camera
    camera = cv2.VideoCapture(capture_source)
    if not camera.isOpened():
        raise RuntimeError("The selected camera or sample video could not be opened.")

    mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False, max_num_faces=3, refine_landmarks=True,
        min_detection_confidence=0.5, min_tracking_confidence=0.5,
    )
    monitor = GazeMonitor(args.gaze_seconds)
    phone_filter = ConsecutivePhoneFilter(args.phone_confidence, args.phone_frames)
    phone_detector = YoloPhoneDetector() if args.phone_detection else None
    screen_buffer = ScreenRingBuffer(max_frames=args.screen_frames) if args.screen_capture else None
    reference_image = _load_reference_image(client, cv2) if args.identity_check else None
    identity_reported = False
    focal_length = None
    processed_frames = 0

    try:
        while args.max_frames is None or processed_frames < args.max_frames:
            success, frame = camera.read()
            if not success:
                break
            processed_frames += 1
            result = mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            faces = list(result.multi_face_landmarks or [])
            looking_away = face_is_looking_away(faces[0].landmark) if len(faces) == 1 else False
            for event in monitor.update(face_count=len(faces), looking_away=looking_away, now=time.monotonic()):
                _upload_event(client, event, screen_buffer)

            if len(faces) == 1:
                landmarks = faces[0].landmark
                width = face_width_pixels(landmarks, frame.shape[1])
                if focal_length is None and args.calibration_distance:
                    focal_length = calibrate_focal_length(
                        face_width_pixels=width, known_distance_metres=args.calibration_distance
                    )
                if focal_length:
                    # The estimate is local-only; it is useful for future optional Bluetooth scope.
                    estimate_distance_metres(face_width_pixels=width, focal_length_pixels=focal_length)
                if reference_image is not None and not identity_reported:
                    matched, confidence = compare_faces(reference_image, frame, args.identity_threshold)
                    if not matched:
                        client.post_event("ID_MISMATCH", "LOW", {"confidence": confidence, "source": "local-reference"})
                        identity_reported = True

            if phone_detector:
                event = phone_filter.update(phone_detector.phone_confidences(frame))
                if event:
                    _upload_event(client, event, screen_buffer)
            if screen_buffer:
                screen_buffer.add(capture_screen_frame())
    finally:
        mesh.close()
        camera.release()

    return processed_frames
