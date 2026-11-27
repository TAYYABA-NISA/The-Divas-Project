"""Privacy-preserving face-presence and gaze state machines.

Landmarks are used in memory to make an advisory decision and are never sent to
the server.  The public helpers accept simple point mappings so they can be
unit-tested without MediaPipe or a webcam.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AdvisoryEvent:
    event_type: str
    severity: str
    details: dict


class DurationFlag:
    """Emit once after a condition lasts long enough, then debounce until clear."""

    def __init__(self, event_type, threshold_seconds, severity="LOW"):
        self.event_type = event_type
        self.threshold_seconds = threshold_seconds
        self.severity = severity
        self._started_at = None
        self._emitted = False

    def update(self, active, now):
        if not active:
            self._started_at = None
            self._emitted = False
            return None
        if self._started_at is None:
            self._started_at = now
            return None
        duration = now - self._started_at
        if not self._emitted and duration >= self.threshold_seconds:
            self._emitted = True
            return AdvisoryEvent(
                self.event_type,
                self.severity,
                {"duration_seconds": round(duration, 2), "source": "face-mesh"},
            )
        return None


class GazeMonitor:
    """Debounced monitor for prolonged gaze away, no face, and multiple faces."""

    def __init__(self, threshold_seconds=5.0):
        self.gaze_away = DurationFlag("GAZE_AWAY", threshold_seconds)
        self.no_face = DurationFlag("NO_FACE", threshold_seconds)
        self.multiple_faces = DurationFlag("MULTIPLE_FACES", threshold_seconds, severity="MEDIUM")

    def update(self, *, face_count, looking_away, now):
        events = []
        checks = (
            (self.no_face, face_count == 0),
            (self.multiple_faces, face_count > 1),
            (self.gaze_away, face_count == 1 and looking_away),
        )
        for flag, active in checks:
            event = flag.update(active, now)
            if event:
                events.append(event)
        return events


def _point(landmarks, index):
    point = landmarks[index]
    if hasattr(point, "x"):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


def face_is_looking_away(landmarks, *, iris_limit=0.30, head_limit=0.20):
    """Combine MediaPipe iris offset and a small head-yaw estimate.

    The result is intentionally conservative.  One signal from either eye or
    the nose position must cross its threshold; callers still debounce it for
    several seconds before reporting an event.
    """
    required = (33, 133, 362, 263, 468, 473, 234, 454, 1)
    try:
        if len(landmarks) <= max(required):
            return False
        left_outer, left_inner = _point(landmarks, 33), _point(landmarks, 133)
        right_inner, right_outer = _point(landmarks, 362), _point(landmarks, 263)
        left_iris, right_iris = _point(landmarks, 468), _point(landmarks, 473)
        left_cheek, right_cheek, nose = _point(landmarks, 234), _point(landmarks, 454), _point(landmarks, 1)
    except (IndexError, TypeError, ValueError):
        return False

    def normalized_offset(value, start, end):
        width = abs(end[0] - start[0])
        if width < 1e-6:
            return 0.0
        return (value[0] - ((start[0] + end[0]) / 2)) / width

    iris_offset = max(
        abs(normalized_offset(left_iris, left_outer, left_inner)),
        abs(normalized_offset(right_iris, right_inner, right_outer)),
    )
    head_yaw = abs(normalized_offset(nose, left_cheek, right_cheek))
    return iris_offset > iris_limit or head_yaw > head_limit
