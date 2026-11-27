from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from .models import Enrollment, Examination, ExaminationQuestion, Question, QuestionChoice
from .services import finalize_attempt, save_answer, start_attempt


class AttemptServiceTests(TestCase):
    def setUp(self):
        self.examiner = User.objects.create_user(
            username="examiner", password="test-password", role=User.Role.EXAMINER
        )
        self.candidate = User.objects.create_user(
            username="candidate", password="test-password", role=User.Role.CANDIDATE
        )
        now = timezone.now()
        self.exam = Examination.objects.create(
            examiner=self.examiner,
            title="Python basics",
            instructions="Answer every question.",
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=60),
            duration_minutes=30,
            total_marks=Decimal("2.00"),
            state=Examination.State.PUBLISHED,
            randomize_choices=True,
        )
        self.question = Question.objects.create(
            author=self.examiner,
            category="Python",
            difficulty=Question.Difficulty.EASY,
            question_type=Question.Type.SINGLE_CHOICE,
            prompt="Which value is true?",
            default_marks=Decimal("2.00"),
        )
        self.correct_choice = QuestionChoice.objects.create(
            question=self.question, text="True", is_correct=True, position=1
        )
        QuestionChoice.objects.create(question=self.question, text="False", is_correct=False, position=2)
        ExaminationQuestion.objects.create(examination=self.exam, question=self.question, position=1)
        Enrollment.objects.create(examination=self.exam, candidate=self.candidate)

    def test_only_an_enrolled_candidate_can_start_an_available_exam(self):
        attempt = start_attempt(examination=self.exam, candidate=self.candidate)
        self.assertEqual(attempt.status, attempt.Status.IN_PROGRESS)
        self.assertEqual(attempt.attempt_questions.count(), 1)

        outsider = User.objects.create_user(
            username="outsider", password="test-password", role=User.Role.CANDIDATE
        )
        with self.assertRaises(PermissionDenied):
            start_attempt(examination=self.exam, candidate=outsider)

    def test_attempt_uses_an_immutable_question_snapshot_for_grading(self):
        attempt = start_attempt(examination=self.exam, candidate=self.candidate)
        snapshot_question = attempt.attempt_questions.get()
        original_snapshot = snapshot_question.choices_snapshot

        self.question.prompt = "Changed after the candidate entered"
        self.question.save()
        self.correct_choice.is_correct = False
        self.correct_choice.save()

        self.assertEqual(snapshot_question.prompt, "Which value is true?")
        self.assertEqual(snapshot_question.choices_snapshot, original_snapshot)

    def test_exact_objective_answer_is_graded_automatically(self):
        attempt = start_attempt(examination=self.exam, candidate=self.candidate)
        attempt_question = attempt.attempt_questions.get()
        correct_id = next(
            choice["id"] for choice in attempt_question.choices_snapshot if choice["is_correct"]
        )
        save_answer(
            attempt=attempt,
            attempt_question_id=attempt_question.id,
            selected_choice_ids=[correct_id],
        )
        finalized = finalize_attempt(attempt)

        self.assertEqual(finalized.status, finalized.Status.SUBMITTED)
        self.assertEqual(finalized.total_score, Decimal("2.00"))
        self.assertEqual(attempt_question.answer.awarded_marks, Decimal("2.00"))

    def test_answers_are_rejected_after_the_deadline(self):
        attempt = start_attempt(examination=self.exam, candidate=self.candidate)
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=("expires_at",))

        with self.assertRaises(PermissionDenied):
            save_answer(
                attempt=attempt,
                attempt_question_id=attempt.attempt_questions.get().id,
                selected_choice_ids=[],
            )
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, attempt.Status.EXPIRED)


class CandidateWorkflowViewTests(TestCase):
    """End-to-end checks of the candidate pages through the test client."""

    def setUp(self):
        from django.urls import reverse
        self.reverse = reverse
        examiner = User.objects.create_user(username="ex", password="pw-123456", role=User.Role.EXAMINER)
        self.candidate = User.objects.create_user(username="ca", password="pw-123456", role=User.Role.CANDIDATE)
        now = timezone.now()
        self.exam = Examination.objects.create(
            examiner=examiner, title="Nav exam", instructions="Go.",
            starts_at=now - timedelta(minutes=5), ends_at=now + timedelta(hours=1),
            duration_minutes=30, state=Examination.State.PUBLISHED,
        )
        for pos, (prompt, qtype) in enumerate(
            (("Pick one", Question.Type.SINGLE_CHOICE), ("Explain", Question.Type.WRITTEN)), start=1
        ):
            q = Question.objects.create(author=examiner, category="General", question_type=qtype,
                                        prompt=prompt, default_marks=Decimal("1.00"))
            if qtype == Question.Type.SINGLE_CHOICE:
                QuestionChoice.objects.create(question=q, text="A", is_correct=True, position=1)
                QuestionChoice.objects.create(question=q, text="B", is_correct=False, position=2)
            ExaminationQuestion.objects.create(examination=self.exam, question=q, position=pos)
        Enrollment.objects.create(examination=self.exam, candidate=self.candidate)
        self.client.force_login(self.candidate)

    def start(self):
        response = self.client.post(self.reverse("examinations:candidate-start", args=[self.exam.id]))
        return response, self.candidate.attempts.get()

    def test_workspace_shows_navigation_and_palette(self):
        _, attempt = self.start()
        page = self.client.get(self.reverse("examinations:attempt-workspace", args=[attempt.id, 1]))
        self.assertContains(page, "Question 1 of 2")
        self.assertContains(page, 'value="next"')
        self.assertContains(page, 'aria-label="Question 2, unanswered"')

    def test_save_and_next_moves_to_the_following_question(self):
        _, attempt = self.start()
        q1 = attempt.attempt_questions.get(position=1)
        choice_id = q1.choices_snapshot[0]["id"]
        url = self.reverse("examinations:attempt-save-answer", args=[attempt.id, 1])
        response = self.client.post(url, {"choice": [choice_id], "go": "next"})
        self.assertRedirects(response, self.reverse("examinations:attempt-workspace", args=[attempt.id, 2]))
        self.assertEqual(q1.answer.selected_choice_ids, [choice_id])

        back = self.client.post(self.reverse("examinations:attempt-save-answer", args=[attempt.id, 2]),
                                {"written_response": "Because.", "go": "previous"})
        self.assertRedirects(back, self.reverse("examinations:attempt-workspace", args=[attempt.id, 1]))

    def test_background_autosave_returns_json(self):
        _, attempt = self.start()
        url = self.reverse("examinations:attempt-save-answer", args=[attempt.id, 2])
        response = self.client.post(url, {"written_response": "Draft", "marked_for_review": "on"},
                                    HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.json()["status"], "review")

    def test_restarting_a_submitted_exam_redirects_instead_of_crashing(self):
        _, attempt = self.start()
        self.client.post(self.reverse("examinations:attempt-submit", args=[attempt.id]))
        response = self.client.post(self.reverse("examinations:candidate-start", args=[self.exam.id]))
        self.assertRedirects(response, self.reverse("examinations:candidate-dashboard"))
        dashboard = self.client.get(self.reverse("examinations:candidate-dashboard"))
        self.assertContains(dashboard, "Awaiting results")
        self.assertNotContains(dashboard, "Start examination")
