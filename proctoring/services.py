import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from examinations.models import Attempt

from .models import DeviceBaseline, ProctorClip, ProctorEvent, ProctorSession


MAX_CLIP_BYTES = 5 * 1024 * 1024
ALLOWED_CLIP_TYPES = {"image/jpeg", "image/png", "video/mp4"}
ALLOWED_DETAIL_KEYS = {
    "confidence", "duration_seconds", "frame_count", "rssi", "device_id_hash", "source", "message",
}
PROHIBITED_DETAIL_KEYS = {
    "biometric", "embedding", "face", "face_image", "image", "landmarks", "photo", "raw_address",
    "address", "bluetooth_address", "mac", "token",
}


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _has_prohibited_key(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in PROHIBITED_DETAIL_KEYS or "face" in normalized or "biometric" in normalized:
                return True
            if _has_prohibited_key(child):
                return True
    elif isinstance(value, list):
        return any(_has_prohibited_key(item) for item in value)
    return False


def _contains_raw_bluetooth_address(value):
    if isinstance(value, str):
        return bool(re.search(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", value))
    if isinstance(value, dict):
        return any(_contains_raw_bluetooth_address(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_raw_bluetooth_address(item) for item in value)
    return False


def _validate_details(value):
    if not isinstance(value, dict):
        raise ValidationError("Event details must be an object.")
    if _has_prohibited_key(value) or _contains_raw_bluetooth_address(value):
        raise ValidationError("Raw biometric data and device addresses are not accepted.")
    unknown = set(value) - ALLOWED_DETAIL_KEYS
    if unknown:
        raise ValidationError("Event details contain unsupported fields.")
    if "device_id_hash" in value and not _is_sha256(value["device_id_hash"]):
        raise ValidationError("device_id_hash must be a SHA-256 digest.")
    if len(json.dumps(value)) > 2000:
        raise ValidationError("Event details are too large.")
    return value


def _is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


@transaction.atomic
def record_consent(*, attempt, candidate, now=None):
    """Create a session and return its one-time plaintext token after consent."""
    now = now or timezone.now()
    locked_attempt = Attempt.objects.select_for_update().get(pk=attempt.pk)
    if locked_attempt.candidate_id != candidate.id or not candidate.is_candidate:
        raise PermissionDenied("Only the candidate who owns this attempt may consent.")
    if locked_attempt.status != Attempt.Status.IN_PROGRESS or now > locked_attempt.expires_at:
        raise ValidationError("Monitoring consent is available only during an active attempt.")
    if ProctorSession.objects.select_for_update().filter(attempt=locked_attempt).exists():
        raise ValidationError("Monitoring consent has already been recorded for this attempt.")

    token = secrets.token_urlsafe(32)
    session = ProctorSession.objects.create(
        attempt=locked_attempt,
        consent_at=now,
        token_hash=_digest(token),
        token_issued_at=now,
    )
    return session, token


def authenticate_agent_token(raw_token, now=None):
    now = now or timezone.now()
    if not raw_token or len(raw_token) > 512:
        raise PermissionDenied("A valid agent token is required.")
    digest = _digest(raw_token)
    session = ProctorSession.objects.select_related("attempt").filter(token_hash=digest).first()
    if not session or not hmac.compare_digest(session.token_hash, digest):
        raise PermissionDenied("A valid agent token is required.")
    if session.attempt.status != Attempt.Status.IN_PROGRESS or now > session.attempt.expires_at:
        raise PermissionDenied("This agent token is no longer active.")
    ProctorSession.objects.filter(pk=session.pk).update(last_seen=now)
    session.last_seen = now
    return session


def create_event(*, session, payload, now=None):
    now = now or timezone.now()
    event_type = payload.get("event_type")
    severity = payload.get("severity", ProctorEvent.Severity.LOW)
    if event_type not in ProctorEvent.Type.values or severity not in ProctorEvent.Severity.values:
        raise ValidationError("Event type or severity is invalid.")
    details = _validate_details(payload.get("details", {}))
    return ProctorEvent.objects.create(
        session=session, event_type=event_type, severity=severity, details=details, occurred_at=now
    )


def save_device_baseline(*, session, payload, now=None):
    now = now or timezone.now()
    devices = payload.get("devices")
    if not isinstance(devices, list) or len(devices) > 100:
        raise ValidationError("devices must contain at most 100 hashed identifiers.")
    sanitized = []
    for item in devices:
        if not isinstance(item, dict) or set(item) - {"device_id_hash", "rssi"}:
            raise ValidationError("Each baseline device may contain only device_id_hash and rssi.")
        device_hash = item.get("device_id_hash")
        if not _is_sha256(device_hash):
            raise ValidationError("Bluetooth identifiers must be SHA-256 digests.")
        rssi = item.get("rssi")
        if rssi is not None and (not isinstance(rssi, int) or not -127 <= rssi <= 20):
            raise ValidationError("RSSI must be an integer between -127 and 20.")
        sanitized.append({"device_id_hash": device_hash, "rssi": rssi})
    return DeviceBaseline.objects.update_or_create(
        session=session, defaults={"devices": sanitized, "captured_at": now}
    )[0]


def save_clip(*, session, event_id, uploaded_file):
    if uploaded_file.size > MAX_CLIP_BYTES:
        raise ValidationError("Evidence clips must be 5 MB or smaller.")
    if uploaded_file.content_type not in ALLOWED_CLIP_TYPES:
        raise ValidationError("Only JPEG, PNG, and MP4 evidence clips are accepted.")
    event = ProctorEvent.objects.filter(pk=event_id, session=session).first()
    if not event:
        raise PermissionDenied("The event does not belong to this proctor session.")
    return ProctorClip.objects.create(
        event=event,
        evidence=uploaded_file,
        content_type=uploaded_file.content_type,
        size_bytes=uploaded_file.size,
    )


def delete_expired_evidence(*, retention_days, now=None):
    if retention_days < 1:
        raise ValidationError("Retention days must be at least one.")
    now = now or timezone.now()
    cutoff = now - timedelta(days=retention_days)
    clips = list(ProctorClip.objects.filter(created_at__lt=cutoff))
    for clip in clips:
        clip.evidence.delete(save=False)
        clip.delete()
    return len(clips)
