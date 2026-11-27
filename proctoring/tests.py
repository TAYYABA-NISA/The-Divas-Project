import hashlib
import json
import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from examinations.models import Attempt, Examination
from proctoring.models import ProctorEvent, ProctorSession, ReviewDecision
from proctoring.services import record_consent


class ProctoringViewsTests(TestCase):
    def setUp(self):
        self.evidence_root = tempfile.mkdtemp()
        self.settings_override = override_settings(PROCTOR_EVIDENCE_ROOT=self.evidence_root)
        self.settings_override.enable()
        now = timezone.now()
        self.examiner = User.objects.create_user(username="examiner", password="password", role=User.Role.EXAMINER)
        self.other_examiner = User.objects.create_user(username="other-examiner", password="password", role=User.Role.EXAMINER)
        self.candidate = User.objects.create_user(username="candidate", password="password", role=User.Role.CANDIDATE)
        self.other_candidate = User.objects.create_user(username="other-candidate", password="password", role=User.Role.CANDIDATE)
        self.exam = Examination.objects.create(
            examiner=self.examiner, title="Secure test", instructions="Read carefully.", starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=2), duration_minutes=60, state=Examination.State.ONGOING,
        )
        self.other_exam = Examination.objects.create(
            examiner=self.other_examiner, title="Other test", instructions="Read carefully.", starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=2), duration_minutes=60, state=Examination.State.ONGOING,
        )
        self.attempt = Attempt.objects.create(
            examination=self.exam, candidate=self.candidate, started_at=now, expires_at=now + timedelta(hours=1)
        )
        self.other_attempt = Attempt.objects.create(
            examination=self.other_exam, candidate=self.other_candidate, started_at=now, expires_at=now + timedelta(hours=1)
        )
        self.session, self.token = record_consent(attempt=self.attempt, candidate=self.candidate)
        self.other_session, self.other_token = record_consent(attempt=self.other_attempt, candidate=self.other_candidate)

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.evidence_root, ignore_errors=True)

    def _agent_post(self, name, payload, token=None):
        return self.client.post(
            reverse(name), data=json.dumps(payload), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token or self.token}",
        )

    def test_consent_creates_only_hashed_token_for_own_active_attempt(self):
        new_attempt = Attempt.objects.create(
            examination=self.exam, candidate=self.other_candidate, started_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        self.client.force_login(self.other_candidate)
        response = self.client.post(reverse("proctoring:consent", args=[new_attempt.id]), {"consent": "on"})
        self.assertEqual(response.status_code, 200)
        session = ProctorSession.objects.get(attempt=new_attempt)
        self.assertEqual(len(session.token_hash), 64)
        self.assertNotEqual(session.token_hash, response.context["agent_token"])
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(reverse("proctoring:consent", args=[new_attempt.id])).status_code, 404)

    def test_agent_event_requires_current_valid_token_and_strips_biometric_payloads(self):
        response = self._agent_post("proctoring:agent-event", {"event_type": "GAZE_AWAY", "severity": "LOW", "details": {"duration_seconds": 7}})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProctorEvent.objects.get().details, {"duration_seconds": 7})
        bad = self._agent_post("proctoring:agent-event", {"event_type": "GAZE_AWAY"}, token="wrong")
        self.assertEqual(bad.status_code, 403)
        raw_biometric = self._agent_post("proctoring:agent-event", {"event_type": "GAZE_AWAY", "details": {"face_embedding": [1, 2]}})
        self.assertEqual(raw_biometric.status_code, 403)
        self.attempt.status = Attempt.Status.SUBMITTED
        self.attempt.save(update_fields=("status",))
        expired = self._agent_post("proctoring:agent-event", {"event_type": "GAZE_AWAY"})
        self.assertEqual(expired.status_code, 403)

    def test_baseline_rejects_raw_bluetooth_identifier(self):
        response = self._agent_post("proctoring:agent-baseline", {"devices": [{"address": "AA:BB:CC:DD:EE:FF"}]})
        self.assertEqual(response.status_code, 403)
        device_hash = hashlib.sha256(b"demo-device").hexdigest()
        response = self._agent_post("proctoring:agent-baseline", {"devices": [{"device_id_hash": device_hash, "rssi": -60}]})
        self.assertEqual(response.status_code, 201)

    def test_clip_is_capped_to_its_own_session_and_private_to_examiner(self):
        event = ProctorEvent.objects.create(session=self.session, event_type="PHONE_DETECTED", severity="MEDIUM", occurred_at=timezone.now())
        other_event = ProctorEvent.objects.create(session=self.other_session, event_type="PHONE_DETECTED", severity="MEDIUM", occurred_at=timezone.now())
        cross_attempt = self.client.post(
            reverse("proctoring:agent-clip"), {"event_id": other_event.id, "clip": SimpleUploadedFile("evidence.jpg", b"data", content_type="image/jpeg")},
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(cross_attempt.status_code, 403)
        response = self.client.post(
            reverse("proctoring:agent-clip"), {"event_id": event.id, "clip": SimpleUploadedFile("evidence.jpg", b"data", content_type="image/jpeg")},
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 201)
        clip_id = response.json()["id"]
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(reverse("proctoring:private-clip", args=[clip_id])).status_code, 403)
        self.client.force_login(self.examiner)
        self.assertEqual(self.client.get(reverse("proctoring:private-clip", args=[clip_id])).status_code, 200)

    def test_candidates_cannot_read_events_and_examiners_cannot_read_other_exam(self):
        ProctorEvent.objects.create(session=self.session, event_type="NO_FACE", severity="LOW", occurred_at=timezone.now())
        timeline = reverse("proctoring:event-timeline", args=[self.attempt.id])
        self.client.force_login(self.candidate)
        self.assertEqual(self.client.get(timeline).status_code, 403)
        self.client.force_login(self.other_examiner)
        self.assertEqual(self.client.get(timeline).status_code, 404)
        self.client.force_login(self.examiner)
        self.assertContains(self.client.get(timeline), "Monitoring review")

    def test_owner_decision_requires_note_and_is_audited(self):
        event = ProctorEvent.objects.create(session=self.session, event_type="NO_FACE", severity="LOW", occurred_at=timezone.now())
        url = reverse("proctoring:decide-event", args=[event.id])
        self.client.force_login(self.examiner)
        self.assertEqual(self.client.post(url, {"decision": "DISMISS", "note": " "}).status_code, 400)
        response = self.client.post(url, {"decision": "DISMISS", "note": "Camera briefly lost focus."})
        self.assertEqual(response.status_code, 200)
        decision = ReviewDecision.objects.get(event=event)
        self.assertEqual(decision.decided_by, self.examiner)
        self.assertEqual(decision.decision, ReviewDecision.Decision.DISMISS)
        self.assertTrue(decision.decided_at)
