"""YOLO cell-phone filtering with a pure-Python consecutive-frame guard."""

from .gaze import AdvisoryEvent


class ConsecutivePhoneFilter:
    def __init__(self, minimum_confidence=0.60, required_frames=3):
        if not 0 < minimum_confidence <= 1 or required_frames < 1:
            raise ValueError("Use a confidence in (0, 1] and at least one frame.")
        self.minimum_confidence = minimum_confidence
        self.required_frames = required_frames
        self._consecutive = 0
        self._emitted = False

    def update(self, confidences):
        confidence = max((float(value) for value in confidences), default=0.0)
        if confidence >= self.minimum_confidence:
            self._consecutive += 1
        else:
            self._consecutive = 0
            self._emitted = False
        if self._consecutive >= self.required_frames and not self._emitted:
            self._emitted = True
            return AdvisoryEvent(
                "PHONE_DETECTED", "MEDIUM",
                {"confidence": round(confidence, 3), "frame_count": self._consecutive, "source": "yolov8n"},
            )
        return None


class YoloPhoneDetector:
    """Lazy YOLO wrapper so simulated mode never imports heavy dependencies."""

    def __init__(self, model_name="yolov8n.pt"):
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError("Install proctor_agent/requirements-hardware.txt for phone detection.") from error
        self.model = YOLO(model_name)

    def phone_confidences(self, frame):
        results = self.model(frame, verbose=False)
        confidences = []
        for result in results:
            names = result.names
            for box in result.boxes:
                class_id = int(box.cls[0])
                if names.get(class_id) == "cell phone":
                    confidences.append(float(box.conf[0]))
        return confidences
