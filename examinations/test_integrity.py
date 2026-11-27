from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from examinations.models import Attempt, Enrollment, Examination, ExaminationQuestion, Question, QuestionChoice
from examinations.services import finalize_attempt, save_answer, start_attempt


class AttemptIntegrityTests(TestCase):
    def setUp(self):
        self.examiner = User.objects.create_user(
            username="integrity-examiner", password="test-password", role=User.Role.EXAMINER
        )
        self.candidate = User.objects.create_user(
            username="integrity-candidate", password="test-password", role=User.Role.CANDIDATE
        )
        self.available_exam = self._create_exam("Available examination")
        self.question = Question.objects.create(
            author=self.examiner,
            category="Integrity",
            difficulty=Question.Difficulty.EASY,
            question_type=Question.Type.SINGLE_CHOICE,
            prompt="Which answer is correct?",
            default_marks=Decimal("1.00"),
        )
        self.correct_choice = QuestionChoice.objects.create(
            question=self.question, text="Correct", is_correct=True, position=1
        )
        QuestionChoice.objects.create(
            question=self.question, text="Incorrect", is_correct=False, position=2
        )
        ExaminationQuestion.objects.create(
            examination=self.available_exam, question=self.question, position=1
        )

    def _create_exam(self, title, starts_at=None, ends_at=None):
        now = timezone.now()
        exam = Examination.objects.create(
            examiner=self.examiner,
            title=title,
            instructions="Read the instructions.",
            starts_at=starts_at or now - timedelta(minutes=5),
            ends_at=ends_at or now + timedelta(hours=1),
            duration_minutes=30,
            state=Examination.State.PUBLISHED,
        )
        Enrollment.objects.create(examination=exam, candidate=self.candidate)
        return exam

    def test_server_rejects_entry_before_the_availability_window(self):
        future_exam = self._create_exam(
            "Future examination",
            starts_at=timezone.now() + timedelta(minutes=10),
            ends_at=timezone.now() + timedelta(hours=1),
        )

        with self.assertRaises(PermissionDenied):
            start_attempt(examination=future_exam, candidate=self.candidate)

        self.client.force_login(self.candidate)
        response = self.client.post(reverse("examinations:candidate-start", args=[future_exam.id]))

        self.assertRedirects(response, reverse("examinations:candidate-dashboard"))
        self.assertFalse(Attempt.objects.filter(examination=future_exam, candidate=self.candidate).exists())

    def test_server_rejects_an_answer_at_the_exact_deadline_and_finalizes(self):
        attempt = start_attempt(examination=self.available_exam, candidate=self.candidate)
        attempt_question = attempt.attempt_questions.get()

        with self.assertRaises(PermissionDenied):
            save_answer(
                attempt=attempt,
                attempt_question_id=attempt_question.id,
                selected_choice_ids=[self.correct_choice.id],
                now=attempt.expires_at,
            )

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.EXPIRED)
        self.assertEqual(attempt.submitted_at, attempt.expires_at)
        self.assertFalse(attempt_question.answer if hasattr(attempt_question, "answer") else None)
        with self.assertRaises(ValidationError):
            start_attempt(examination=self.available_exam, candidate=self.candidate)

    def test_repeated_submit_keeps_the_first_finalization(self):
        attempt = start_attempt(examination=self.available_exam, candidate=self.candidate)
        attempt_question = attempt.attempt_questions.get()
        save_answer(
            attempt=attempt,
            attempt_question_id=attempt_question.id,
            selected_choice_ids=[self.correct_choice.id],
        )
        self.client.force_login(self.candidate)
        url = reverse("examinations:attempt-submit", args=[attempt.id])

        first = self.client.post(url)
        attempt.refresh_from_db()
        first_submitted_at = attempt.submitted_at
        first_score = attempt.total_score
        second = self.client.post(url)
        attempt.refresh_from_db()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Attempt.objects.filter(examination=self.available_exam, candidate=self.candidate).count(), 1)
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)
        self.assertEqual(attempt.total_score, Decimal("1.00"))
        self.assertEqual(attempt.total_score, first_score)
        self.assertEqual(attempt.submitted_at, first_submitted_at)

    def test_workspace_refresh_restores_answer_and_uses_the_original_deadline(self):
        attempt = start_attempt(examination=self.available_exam, candidate=self.candidate)
        attempt_question = attempt.attempt_questions.get()
        attempt.expires_at = timezone.now() + timedelta(seconds=120)
        attempt.save(update_fields=("expires_at",))
        save_answer(
            attempt=attempt,
            attempt_question_id=attempt_question.id,
            selected_choice_ids=[self.correct_choice.id],
        )
        self.client.force_login(self.candidate)

        response = self.client.get(
            reverse("examinations:attempt-workspace", args=[attempt.id, attempt_question.position])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{self.correct_choice.id}" checked')
        self.assertGreater(response.context["remaining_seconds"], 0)
        self.assertLessEqual(response.context["remaining_seconds"], 120)
        self.assertLess(response.context["remaining_seconds"], self.available_exam.duration_minutes * 60)

    def test_dashboard_categories_show_access_statuses_from_server_state(self):
        future_exam = self._create_exam(
            "Upcoming examination",
            starts_at=timezone.now() + timedelta(minutes=10),
            ends_at=timezone.now() + timedelta(hours=1),
        )
        closed_exam = self._create_exam(
            "Closed examination",
            starts_at=timezone.now() - timedelta(hours=2),
            ends_at=timezone.now() - timedelta(minutes=1),
        )
        submitted_exam = self._create_exam("Submitted examination")
        expired_exam = self._create_exam("Timed out examination")

        submitted_attempt = start_attempt(examination=submitted_exam, candidate=self.candidate)
        finalize_attempt(submitted_attempt)
        expired_attempt = start_attempt(examination=expired_exam, candidate=self.candidate)
        expired_attempt.expires_at = timezone.now() - timedelta(seconds=1)
        expired_attempt.save(update_fields=("expires_at",))

        self.client.force_login(self.candidate)
        response = self.client.get(reverse("examinations:candidate-dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["exam"] for item in response.context["available"]}, {self.available_exam})
        self.assertEqual({item["exam"] for item in response.context["upcoming"]}, {future_exam})
        self.assertEqual({item["exam"] for item in response.context["missed"]}, {closed_exam})
        self.assertEqual(
            {item["exam"] for item in response.context["completed"]},
            {submitted_exam, expired_exam},
            msg=(
                f"in_progress={response.context['in_progress']}, "
                f"completed={response.context['completed']}, missed={response.context['missed']}"
            ),
        )
        self.assertContains(response, "Not open yet")
        self.assertContains(response, "Not attempted")
        self.assertContains(response, "Timed out")

    def test_non_candidates_cannot_access_candidate_routes(self):
        attempt = start_attempt(examination=self.available_exam, candidate=self.candidate)
        self.client.force_login(self.examiner)

        self.assertEqual(self.client.get(reverse("examinations:candidate-dashboard")).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("examinations:candidate-start", args=[self.available_exam.id])).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("examinations:attempt-workspace", args=[attempt.id, 1])).status_code,
            403,
        )
