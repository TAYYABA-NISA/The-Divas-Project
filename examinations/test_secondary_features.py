from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from .bulk_import import commit_questions, preview_questions
from .models import Attempt, Examination, ExaminationQuestion, Question, QuestionChoice, UserPreference, VerifiedReport
from .reporting import issue_report, verification_data
from .services import start_attempt


class SecondaryFeatureTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.examiner = User.objects.create_user(username="examiner", password="pw", role=User.Role.EXAMINER)
        self.candidate = User.objects.create_user(username="candidate", password="pw", role=User.Role.CANDIDATE)
        self.other = User.objects.create_user(username="other", password="pw", role=User.Role.CANDIDATE)
        self.exam = Examination.objects.create(
            examiner=self.examiner, title="Feature exam", instructions="Read.", starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(hours=1), duration_minutes=20, total_marks=Decimal("1.00"), state=Examination.State.PUBLISHED,
        )
        question = Question.objects.create(author=self.examiner, category="General", difficulty="EASY", question_type="SINGLE", prompt="One?", default_marks=Decimal("1.00"))
        QuestionChoice.objects.create(question=question, text="Yes", is_correct=True, position=1)
        QuestionChoice.objects.create(question=question, text="No", is_correct=False, position=2)
        ExaminationQuestion.objects.create(examination=self.exam, question=question, position=1)
        from .models import Enrollment
        Enrollment.objects.create(examination=self.exam, candidate=self.candidate)
        self.attempt = start_attempt(examination=self.exam, candidate=self.candidate)

    def test_preferences_and_scratchpad_are_private_and_persisted(self):
        self.client.force_login(self.candidate)
        pref_url = reverse("examinations:workspace-preferences", args=[self.attempt.id])
        response = self.client.post(pref_url, {"font_size": "LARGE", "theme": "HIGH_CONTRAST", "palette_position": "TOP", "density": "COMPACT"})
        self.assertEqual(response.status_code, 200)
        preference = UserPreference.objects.get(user=self.candidate)
        self.assertEqual(preference.font_size, "LARGE")
        scratch_url = reverse("examinations:scratchpad-save", args=[self.attempt.id])
        self.assertEqual(self.client.post(scratch_url, {"scratchpad": "private calculation"}).status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.scratchpad, "private calculation")
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(scratch_url, {"scratchpad": "steal"}).status_code, 404)

    def test_examiner_sandbox_has_no_real_attempt_record(self):
        self.client.force_login(self.examiner)
        response = self.client.post(reverse("examinations:sandbox-start", args=[self.exam.id]))
        self.assertEqual(response.status_code, 302)
        sandbox = Attempt.all_objects.get(candidate=self.examiner, is_sandbox=True)
        self.assertTrue(sandbox.is_sandbox)
        self.assertFalse(Attempt.objects.filter(pk=sandbox.id).exists())
        self.assertContains(self.client.get(reverse("examinations:attempt-workspace", args=[sandbox.id, 1])), "Question 1 of 1")

    def test_bulk_question_preview_rejects_bad_rows_and_commits_valid_rows(self):
        valid = SimpleUploadedFile("questions.csv", b"category,difficulty,question_type,prompt,default_marks,choices\nMath,EASY,SINGLE,2 plus 2,1,4|true;5|false\n", content_type="text/csv")
        records, errors = preview_questions(valid)
        self.assertFalse(errors)
        commit_questions(examiner=self.examiner, records=records)
        self.assertTrue(Question.objects.filter(author=self.examiner, prompt="2 plus 2").exists())
        invalid = SimpleUploadedFile("bad.csv", b"category,difficulty,question_type,prompt,default_marks,choices\nMath,INVALID,SINGLE,Bad,1,a|true;b|false\n", content_type="text/csv")
        records, errors = preview_questions(invalid)
        self.assertEqual(records, [])
        self.assertTrue(errors)

    def test_result_report_verifies_minimal_data_and_is_not_cross_candidate_readable(self):
        self.attempt.status = Attempt.Status.SUBMITTED
        self.attempt.submitted_at = timezone.now()
        self.attempt.total_score = Decimal("1.00")
        self.attempt.total_marks = Decimal("1.00")
        self.attempt.save()
        self.exam.results_published = True
        self.exam.results_published_at = timezone.now()
        self.exam.save()
        report, _ = issue_report(report_type=VerifiedReport.Type.CANDIDATE_RESULT, examination=self.exam, attempt=self.attempt)
        status, data = verification_data(report)
        self.assertEqual(status, "authentic")
        self.assertEqual(set(data), {"exam_title", "issue_date", "candidate_name", "score", "total"})
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("examinations:candidate-result-report", args=[self.attempt.id])).status_code, 404)
        self.client.force_login(self.candidate)
        response = self.client.get(reverse("examinations:candidate-result-report", args=[self.attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
