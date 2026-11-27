import unittest

from proctor_agent.distance import calibrate_focal_length, estimate_distance_metres
from proctor_agent.gaze import GazeMonitor, face_is_looking_away
from proctor_agent.identity import compare_faces
from proctor_agent.phone import ConsecutivePhoneFilter
from proctor_agent.screen import ScreenRingBuffer


class GazeDurationTests(unittest.TestCase):
    def test_gaze_away_is_duration_based_and_debounced(self):
        monitor = GazeMonitor(threshold_seconds=5)
        self.assertEqual(monitor.update(face_count=1, looking_away=True, now=0), [])
        self.assertEqual(monitor.update(face_count=1, looking_away=True, now=4.99), [])
        event = monitor.update(face_count=1, looking_away=True, now=5)[0]
        self.assertEqual(event.event_type, "GAZE_AWAY")
        self.assertEqual(event.details["duration_seconds"], 5)
        self.assertEqual(monitor.update(face_count=1, looking_away=True, now=9), [])
        monitor.update(face_count=1, looking_away=False, now=10)
        self.assertEqual(monitor.update(face_count=1, looking_away=True, now=11), [])
        self.assertEqual(monitor.update(face_count=1, looking_away=True, now=16)[0].event_type, "GAZE_AWAY")

    def test_absence_and_multiple_faces_have_separate_flags(self):
        monitor = GazeMonitor(threshold_seconds=2)
        monitor.update(face_count=0, looking_away=False, now=0)
        self.assertEqual(monitor.update(face_count=0, looking_away=False, now=2)[0].event_type, "NO_FACE")
        monitor.update(face_count=2, looking_away=False, now=3)
        self.assertEqual(monitor.update(face_count=2, looking_away=False, now=5)[0].event_type, "MULTIPLE_FACES")

    def test_synthetic_landmarks_use_iris_and_head_position(self):
        landmarks = [(0.0, 0.0)] * 474
        landmarks[33], landmarks[133] = (0.40, 0.5), (0.60, 0.5)
        landmarks[362], landmarks[263] = (0.60, 0.5), (0.40, 0.5)
        landmarks[468], landmarks[473] = (0.50, 0.5), (0.50, 0.5)
        landmarks[234], landmarks[454], landmarks[1] = (0.30, 0.5), (0.70, 0.5), (0.50, 0.5)
        self.assertFalse(face_is_looking_away(landmarks))
        landmarks[468] = (0.58, 0.5)
        self.assertTrue(face_is_looking_away(landmarks))


class DistanceTests(unittest.TestCase):
    def test_pinhole_distance_uses_calibration(self):
        focal = calibrate_focal_length(face_width_pixels=200, known_distance_metres=0.60)
        self.assertAlmostEqual(focal, 800)
        self.assertAlmostEqual(estimate_distance_metres(face_width_pixels=200, focal_length_pixels=focal), 0.60)
        self.assertAlmostEqual(estimate_distance_metres(face_width_pixels=100, focal_length_pixels=focal), 1.20)


class PhoneAndScreenTests(unittest.TestCase):
    def test_phone_requires_consecutive_confident_frames_then_debounces(self):
        detector = ConsecutivePhoneFilter(minimum_confidence=0.7, required_frames=3)
        self.assertIsNone(detector.update([0.9]))
        self.assertIsNone(detector.update([0.8]))
        event = detector.update([0.75])
        self.assertEqual(event.event_type, "PHONE_DETECTED")
        self.assertEqual(event.details["frame_count"], 3)
        self.assertIsNone(detector.update([0.95]))
        self.assertIsNone(detector.update([0.2]))
        self.assertIsNone(detector.update([0.9]))
        self.assertIsNone(detector.update([0.9]))
        self.assertIsNotNone(detector.update([0.9]))

    def test_screen_ring_buffer_keeps_only_recent_frames(self):
        buffer = ScreenRingBuffer(max_frames=3)
        for frame in range(5):
            buffer.add(frame)
        self.assertEqual(buffer.snapshot(), [2, 3, 4])


class IdentityTests(unittest.TestCase):
    def test_same_and_different_synthetic_faces(self):
        reference = [[0, 1], [2, 3]]
        self.assertEqual(compare_faces(reference, [[0, 1], [2, 3]])[0], True)
        self.assertEqual(compare_faces(reference, [[3, 2], [1, 0]])[0], False)


if __name__ == "__main__":
    unittest.main()
