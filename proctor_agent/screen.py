"""Bounded local screen-frame ring buffer for event-triggered evidence only."""

from collections import deque
from pathlib import Path


class ScreenRingBuffer:
    def __init__(self, max_frames=75):
        if max_frames < 1:
            raise ValueError("max_frames must be at least one.")
        self._frames = deque(maxlen=max_frames)

    def add(self, frame):
        self._frames.append(frame)

    def snapshot(self):
        return list(self._frames)

    def __len__(self):
        return len(self._frames)

    def write_mp4(self, destination, fps=10):
        """Write the bounded buffer only after a flag; never record continuously."""
        frames = self.snapshot()
        if not frames:
            return None
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError("Install proctor_agent/requirements-hardware.txt for screen clips.") from error
        height, width = frames[0].shape[:2]
        destination = Path(destination)
        writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        try:
            for frame in frames:
                writer.write(frame)
        finally:
            writer.release()
        return destination


def capture_screen_frame():
    """Capture one BGR frame with mss, imported only for live hardware mode."""
    try:
        import mss
        import numpy
    except ImportError as error:
        raise RuntimeError("Install proctor_agent/requirements-hardware.txt for screen capture.") from error
    with mss.mss() as capture:
        monitor = capture.monitors[1]
        return numpy.asarray(capture.grab(monitor))[:, :, :3]
