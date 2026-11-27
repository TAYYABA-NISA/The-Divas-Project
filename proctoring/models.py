import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateEvidenceStorage(FileSystemStorage):
    """Store evidence outside public media using a deployment-configurable location."""

    @property
    def location(self):
        return str(
            getattr(settings, "PROCTOR_EVIDENCE_ROOT", Path(settings.BASE_DIR) / "private_proctor_evidence")
        )


PRIVATE_EVIDENCE_STORAGE = PrivateEvidenceStorage()


def private_clip_path(instance, filename):
    suffix = Path(filename).suffix.lower()[:10] or ".bin"
    return f"proctoring/{instance.event.session_id}/{uuid.uuid4().hex}{suffix}"


class ProctorSession(models.Model):
    """The candidate's consent and the hashed agent credential for one attempt."""

    attempt = models.OneToOneField(
        "examinations.Attempt", on_delete=models.CASCADE, related_name="proctor_session"
    )
    consent_at = models.DateTimeField()
    token_hash = models.CharField(max_length=64, unique=True)
    token_issued_at = models.DateTimeField()
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-consent_at",)


class ProctorEvent(models.Model):
    class Type(models.TextChoices):
        GAZE_AWAY = "GAZE_AWAY", "Gaze away"
        NO_FACE = "NO_FACE", "No face detected"
        MULTIPLE_FACES = "MULTIPLE_FACES", "Multiple faces"
        PHONE_DETECTED = "PHONE_DETECTED", "Phone detected"
        BT_DEVICE_NEARBY = "BT_DEVICE_NEARBY", "Nearby Bluetooth device"
        ID_MISMATCH = "ID_MISMATCH", "Identity mismatch"
        AGENT_OFFLINE = "AGENT_OFFLINE", "Agent offline"

    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    session = models.ForeignKey(ProctorSession, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=24, choices=Type.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.LOW)
    occurred_at = models.DateTimeField()
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-occurred_at", "-id")


class ProctorClip(models.Model):
    event = models.ForeignKey(ProctorEvent, on_delete=models.CASCADE, related_name="clips")
    evidence = models.FileField(storage=PRIVATE_EVIDENCE_STORAGE, upload_to=private_clip_path)
    content_type = models.CharField(max_length=64)
    size_bytes = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class DeviceBaseline(models.Model):
    """Hashed Bluetooth identifiers and optional RSSI values captured before the exam."""

    session = models.OneToOneField(ProctorSession, on_delete=models.CASCADE, related_name="device_baseline")
    devices = models.JSONField(default=list)
    captured_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class AIReview(models.Model):
    class Source(models.TextChoices):
        LOCAL = "LOCAL", "Local rules"
        GEMINI = "GEMINI", "Gemini"

    session = models.ForeignKey(ProctorSession, on_delete=models.CASCADE, related_name="ai_reviews")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.LOCAL)
    summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class ReviewDecision(models.Model):
    class Decision(models.TextChoices):
        ACCEPT = "ACCEPT", "Accept for review"
        DISMISS = "DISMISS", "Dismiss"

    event = models.OneToOneField(ProctorEvent, on_delete=models.CASCADE, related_name="review_decision")
    decision = models.CharField(max_length=10, choices=Decision.choices)
    note = models.TextField()
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    decided_at = models.DateTimeField(auto_now_add=True)
