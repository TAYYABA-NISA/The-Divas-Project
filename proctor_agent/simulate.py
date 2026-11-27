"""Safe, hardware-free advisory event simulation for demonstrations and tests."""

import hashlib


def hash_device_identifier(identifier):
    """Hash a local device identifier before it ever reaches the uplink."""
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()


def simulated_baseline():
    return [{"device_id_hash": hash_device_identifier("demo-keyboard"), "rssi": -68}]


def simulated_events():
    """Yield non-biometric, advisory-only events without touching hardware."""
    yield "GAZE_AWAY", "LOW", {"duration_seconds": 8, "source": "simulated"}
    yield "PHONE_DETECTED", "MEDIUM", {"confidence": 0.91, "frame_count": 3, "source": "simulated"}
