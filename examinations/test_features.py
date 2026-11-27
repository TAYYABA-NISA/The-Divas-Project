from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from .models import (
    Attempt, AttemptAnswer, Enrollment, ExamBlueprint, Examination, ExaminationEvent,
    ExaminationQuestion, Question, QuestionChoice,
)
from .services import (
    exam_analytics, finalize_attempt, grade_written_answer, publish_examination,
    publish_results, save_answer, start_attempt,
)


def make_user(name, role):
    return User.objects.create_user(username=name, password="pw-123456", role=role)


def make_question(author, difficulty, qtype=Question.Type.SINGLE_CHOICE, prompt=None, marks="1.00", correct=1):
    q = Question.objects.create(
        author=author, category="Gen", difficulty=difficulty, question_type=qtype,
        prompt=prompt or f"{difficulty} question {Question.objects.count()}", default_marks=Decimal(marks),
    )
    if qtype != Question.Type.WRITTEN:
        for i in range(4):
            QuestionChoice.objects.create(question=q, text=f"opt{i}", is_correct=i < correct, position=i)
    return q


def make_exam(examiner, **kwargs):
    now = timezone.now()
    defaults = dict(
        examiner=examiner, title="Exam", instructions="Go", starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(hours=1), duration_minutes=30, state=Examination.State.DRAFT,
    )
    defaults.update(kwargs)
    return Examination.objects.create(**defaults)


def open_window(exam):
    """Publish a draft exam whose window is currently open."""
    return publish_examination(exam)


class BlueprintTests(TestCase):
    def setUp(self):
        self.examiner = make_user("ex", User.Role.EXAMINER)
        for d, n in (("EASY", 12), ("MEDIUM", 8), ("HARD", 5)):
            for _ in range(n):
                make_question(self.examiner, d)
        self.exam = make_exam(self.examiner)
        ExamBlueprint.objects.create(examination=self.exam, easy_count=3, medium_count=2, hard_count=1)
        self.candidates = []
        for i in range(5):
            c = make_user(f"c{i}", User.Role.CANDIDATE)
            Enrollment.objects.create(examination=self.exam, candidate=c)
            self.candidates.append(c)
        open_window(self.exam)

    def test_exact_counts_marks_and_total(self):
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.total_marks, Decimal("10.00"))  # 3*1 + 2*2 + 1*3
        attempt = start_attempt(examination=self.exam, candidate=self.candidates[0])
        diffs = [q.difficulty for q in attempt.attempt_questions.all()]
        self.assertEqual((diffs.count("EASY"), diffs.count("MEDIUM"), diffs.count("HARD")), (3, 2, 1))
        self.assertEqual(attempt.total_marks, Decimal("10.00"))

    def test_candidates_get_different_draws_and_reopen_is_stable(self):
        draws = []
        for c in self.candidates:
            attempt = start_attempt(examination=self.exam, candidate=c)
            draws.append(tuple(sorted(attempt.attempt_questions.values_list("source_question_id", flat=True))))
        self.assertGreater(len(set(draws)), 1)
        again = start_attempt(examination=self.exam, candidate=self.candidates[0])
        self.assertEqual(
            tuple(sorted(again.attempt_questions.values_list("source_question_id", flat=True))), draws[0]
        )
        self.assertEqual(Attempt.objects.filter(candidate=self.candidates[0]).count(), 1)

    def test_short_pool_is_rejected_at_publication(self):
        exam = make_exam(self.examiner, title="Short")
        ExamBlueprint.objects.create(examination=exam, hard_count=9)
        with self.assertRaises(ValidationError) as ctx:
            publish_examination(exam)
        self.assertIn("hard", ctx.exception.messages[0])

    def test_pool_is_frozen_at_publication(self):
        blueprint = self.exam.blueprint
        blueprint.refresh_from_db()
        count = len(blueprint.frozen_pool)
        make_question(self.examiner, "EASY")
        attempt = start_attempt(examination=self.exam, candidate=self.candidates[1])
        self.assertEqual(len(blueprint.frozen_pool), count)
        self.assertEqual(attempt.attempt_questions.count(), 6)

    def test_question_in_published_pool_cannot_be_edited_or_deleted(self):
        self.client.force_login(self.examiner)
        qid = ExamBlueprint.objects.get(examination=self.exam).frozen_pool[0]
        self.assertEqual(self.client.get(reverse("examinations:question-edit", args=[qid])).status_code, 403)
        self.assertEqual(self.client.post(reverse("examinations:question-delete", args=[qid])).status_code, 403)

    def test_blueprint_view_requires_owning_examiner(self):
        draft = make_exam(self.examiner, title="Draft")
        url = reverse("examinations:exam-blueprint", args=[draft.id])
        self.client.force_login(self.candidates[0])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(make_user("other", User.Role.EXAMINER))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.examiner)
        self.assertEqual(self.client.get(url).status_code, 200)


class MonitoringTests(TestCase):
    def setUp(self):
        self.examiner = make_user("ex", User.Role.EXAMINER)
        self.other = make_user("other", User.Role.EXAMINER)
        self.cand = make_user("ca", User.Role.CANDIDATE)
        self.cand2 = make_user("cb", User.Role.CANDIDATE)
        self.exam = make_exam(self.examiner, state=Examination.State.PUBLISHED)
        self.exam2 = make_exam(self.other, state=Examination.State.PUBLISHED, title="Other exam")
        for exam, user in ((self.exam, self.cand), (self.exam2, self.cand2)):
            q = make_question(exam.examiner, "EASY")
            ExaminationQuestion.objects.create(examination=exam, question=q, position=1)
            Enrollment.objects.create(examination=exam, candidate=user)

    def test_monitor_pages_are_owner_only(self):
        for name in ("exam-monitor",):
            url = reverse(f"examinations:{name}", args=[self.exam.id])
            self.client.force_login(self.cand)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.client.force_login(self.examiner)
            response = self.client.get(url)
            self.assertContains(response, "not conclusive evidence")
        for name in ("exam-announce", "exam-incident"):
            url = reverse(f"examinations:{name}", args=[self.exam.id])
            self.client.force_login(self.cand)
            self.assertEqual(self.client.post(url, {"message": "x"}).status_code, 403)
            self.client.force_login(self.other)
            self.assertEqual(self.client.post(url, {"message": "x"}).status_code, 404)

    def test_announcement_reaches_only_candidates_of_that_exam(self):
        attempt = start_attempt(examination=self.exam, candidate=self.cand)
        attempt2 = start_attempt(examination=self.exam2, candidate=self.cand2)
        self.client.force_login(self.examiner)
        self.client.post(reverse("examinations:exam-announce", args=[self.exam.id]), {"message": "Ten minutes left"})
        self.client.post(reverse("examinations:exam-incident", args=[self.exam.id]), {"message": "Secret note"})

        self.client.force_login(self.cand)
        body = self.client.get(reverse("examinations:attempt-poll", args=[attempt.id])).json()
        self.assertEqual([a["message"] for a in body["announcements"]], ["Ten minutes left"])
        self.assertNotIn("Secret note", str(body))
        self.assertEqual(self.client.get(reverse("examinations:attempt-poll", args=[attempt2.id])).status_code, 404)

        self.client.force_login(self.cand2)
        body2 = self.client.get(reverse("examinations:attempt-poll", args=[attempt2.id])).json()
        self.assertEqual(body2["announcements"], [])
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.last_seen_at)

    def test_monitor_shows_progress(self):
        attempt = start_attempt(examination=self.exam, candidate=self.cand)
        aq = attempt.attempt_questions.get()
        save_answer(attempt=attempt, attempt_question_id=aq.id, selected_choice_ids=[aq.choices_snapshot[0]["id"]])
        self.client.force_login(self.examiner)
        self.assertContains(self.client.get(reverse("examinations:exam-monitor", args=[self.exam.id])), "1 of 1 answered")

    def test_incident_must_belong_to_same_exam(self):
        attempt2 = start_attempt(examination=self.exam2, candidate=self.cand2)
        self.client.force_login(self.examiner)
        response = self.client.post(
            reverse("examinations:exam-incident", args=[self.exam.id]),
            {"message": "x", "attempt": attempt2.id},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExaminationEvent.objects.filter(event_type="INCIDENT").exists())


class GradingTests(TestCase):
    def setUp(self):
        self.examiner = make_user("ex", User.Role.EXAMINER)
        self.cand = make_user("ca", User.Role.CANDIDATE)
        self.cand2 = make_user("cb", User.Role.CANDIDATE)
        self.exam = make_exam(
            self.examiner, multiple_select_scheme=Examination.MultipleSelectScheme.PARTIAL,
        )
        self.single = make_question(self.examiner, "EASY", marks="2.00")
        self.multi = make_question(self.examiner, "MEDIUM", Question.Type.MULTIPLE_SELECT, marks="4.00", correct=2)
        self.written = make_question(self.examiner, "HARD", Question.Type.WRITTEN, marks="5.00")
        for pos, q in enumerate((self.single, self.multi, self.written), start=1):
            ExaminationQuestion.objects.create(examination=self.exam, question=q, position=pos)
        for c in (self.cand, self.cand2):
            Enrollment.objects.create(examination=self.exam, candidate=c)
        self.exam = publish_examination(self.exam)

    def take(self, candidate, single_right=True, multi="partial", text="An answer"):
        attempt = start_attempt(examination=self.exam, candidate=candidate)
        by_type = {aq.question_type: aq for aq in attempt.attempt_questions.all()}
        s = by_type["SINGLE"]
        correct = [c["id"] for c in s.choices_snapshot if c["is_correct"]]
        wrong = [c["id"] for c in s.choices_snapshot if not c["is_correct"]]
        save_answer(attempt=attempt, attempt_question_id=s.id, selected_choice_ids=correct if single_right else wrong[:1])
        m = by_type["MULTIPLE"]
        mc = [c["id"] for c in m.choices_snapshot if c["is_correct"]]
        mw = [c["id"] for c in m.choices_snapshot if not c["is_correct"]]
        picks = {"partial": mc[:1], "all": mc, "wrongmix": mc[:1] + mw[:1], "none": []}[multi]
        save_answer(attempt=attempt, attempt_question_id=m.id, selected_choice_ids=picks)
        if text:
            w = by_type["WRITTEN"]
            save_answer(attempt=attempt, attempt_question_id=w.id, written_response=text)
        return finalize_attempt(attempt)

    def written_answer(self, attempt):
        return AttemptAnswer.objects.get(attempt_question__attempt=attempt, attempt_question__question_type="WRITTEN")

    def test_multiple_select_partial_credit_and_penalty(self):
        self.assertEqual(self.take(self.cand, multi="partial").total_score, Decimal("4.00"))  # 2 + 2 + 0 pending
        other = self.take(self.cand2, multi="wrongmix")  # net 0 on multi
        self.assertEqual(other.total_score, Decimal("2.00"))

    def test_all_or_nothing_scheme(self):
        self.exam.multiple_select_scheme = Examination.MultipleSelectScheme.ALL_OR_NOTHING
        self.exam.save()
        self.assertEqual(self.take(self.cand, multi="partial").total_score, Decimal("2.00"))

    def test_marks_over_limit_rejected_and_total_follows_regrade(self):
        attempt = self.take(self.cand)
        answer = self.written_answer(attempt)
        with self.assertRaises(ValidationError):
            grade_written_answer(answer_id=answer.id, grader=self.examiner, marks="5.01")
        with self.assertRaises(ValidationError):
            grade_written_answer(answer_id=answer.id, grader=self.examiner, marks="-1")
        grade_written_answer(answer_id=answer.id, grader=self.examiner, marks="3.5", feedback="Good")
        attempt.refresh_from_db()
        self.assertEqual(attempt.total_score, Decimal("7.50"))
        grade_written_answer(answer_id=answer.id, grader=self.examiner, marks="1")
        attempt.refresh_from_db()
        self.assertEqual(attempt.total_score, Decimal("5.00"))

    def test_other_examiner_cannot_grade(self):
        attempt = self.take(self.cand)
        with self.assertRaises(PermissionDenied):
            grade_written_answer(
                answer_id=self.written_answer(attempt).id, grader=make_user("o", User.Role.EXAMINER), marks="1"
            )

    def test_blank_written_answer_needs_no_marking(self):
        attempt = self.take(self.cand, text="")
        self.assertEqual(self.written_answer(attempt).awarded_marks, Decimal("0.00"))

    def test_publish_blocked_until_graded_and_window_closed(self):
        attempt = self.take(self.cand)
        with self.assertRaises(ValidationError):
            publish_results(self.exam)  # window open
        self.exam.ends_at = timezone.now() - timedelta(seconds=1)
        self.exam.save()
        with self.assertRaises(ValidationError) as ctx:
            publish_results(self.exam)
        self.assertIn("written", " ".join(ctx.exception.messages))
        grade_written_answer(answer_id=self.written_answer(attempt).id, grader=self.examiner, marks="4")
        publish_results(self.exam)
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.results_published)

    def publish_all(self):
        a1 = self.take(self.cand)
        a2 = self.take(self.cand2, single_right=False)
        for a in (a1, a2):
            grade_written_answer(answer_id=self.written_answer(a).id, grader=self.examiner, marks="2")
        self.exam.ends_at = timezone.now() - timedelta(seconds=1)
        self.exam.save()
        return a1, a2

    def test_candidate_sees_only_own_published_result(self):
        a1, a2 = self.publish_all()
        self.client.force_login(self.cand)
        url1 = reverse("examinations:candidate-result", args=[a1.id])
        self.assertEqual(self.client.get(url1).status_code, 404)  # unpublished
        publish_results(self.exam)
        response = self.client.get(url1)
        self.assertContains(response, "8")
        self.assertNotContains(response, "is_correct")
        self.assertEqual(self.client.get(reverse("examinations:candidate-result", args=[a2.id])).status_code, 404)

    def test_grading_views_are_owner_only(self):
        a1, _ = self.publish_all()
        urls = [
            reverse("examinations:exam-grading", args=[self.exam.id]),
            reverse("examinations:attempt-grading", args=[self.exam.id, a1.id]),
        ]
        for url in urls:
            self.client.force_login(self.cand)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.force_login(make_user(f"o{urls.index(url)}", User.Role.EXAMINER))
            self.assertEqual(self.client.get(url).status_code, 404)
            self.client.force_login(self.examiner)
            self.assertEqual(self.client.get(url).status_code, 200)
        pub = reverse("examinations:exam-publish-results", args=[self.exam.id])
        self.client.force_login(self.cand)
        self.assertEqual(self.client.post(pub, {"confirm": "yes"}).status_code, 403)

    def test_publish_requires_confirmation_and_grade_view_validates(self):
        a1, _ = self.publish_all()
        self.client.force_login(self.examiner)
        pub = reverse("examinations:exam-publish-results", args=[self.exam.id])
        self.client.post(pub)
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.results_published)
        answer = self.written_answer(a1)
        self.client.post(
            reverse("examinations:attempt-grading", args=[self.exam.id, a1.id]),
            {"answer_id": answer.id, "marks": "99"},
        )
        answer.refresh_from_db()
        self.assertEqual(answer.awarded_marks, Decimal("2.00"))
        self.client.post(pub, {"confirm": "yes"})
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.results_published)


class AnalyticsTests(TestCase):
    def setUp(self):
        self.examiner = make_user("ex", User.Role.EXAMINER)
        self.exam = make_exam(self.examiner)
        self.q1 = make_question(self.examiner, "EASY", prompt="=cmd() Q1", marks="1.00")
        self.q2 = make_question(self.examiner, "HARD", prompt="Q2", marks="1.00")
        for pos, q in enumerate((self.q1, self.q2), start=1):
            ExaminationQuestion.objects.create(examination=self.exam, question=q, position=pos)
        self.cands = [make_user(f"c{i}", User.Role.CANDIDATE) for i in range(4)]
        for c in self.cands:
            Enrollment.objects.create(examination=self.exam, candidate=c)
        publish_examination(self.exam)
        # c0: both right. c1: Q1 right, Q2 wrong. c2: Q1 wrong, Q2 skipped. c3: never starts.
        plan = {0: ("right", "right"), 1: ("right", "wrong"), 2: ("wrong", None)}
        for i, (a, b) in plan.items():
            attempt = start_attempt(examination=self.exam, candidate=self.cands[i])
            for aq, how in zip(attempt.attempt_questions.order_by("position"), (a, b)):
                if how is None:
                    continue
                ids = [c["id"] for c in aq.choices_snapshot if c["is_correct"] == (how == "right")][:1]
                save_answer(attempt=attempt, attempt_question_id=aq.id, selected_choice_ids=ids)
            finalize_attempt(attempt)

    def test_summary_values(self):
        data = exam_analytics(self.exam)
        s = data["summary"]
        self.assertEqual((s["attempted"], s["enrolled"]), (3, 4))
        self.assertEqual(s["highest"], Decimal("2.00"))
        self.assertEqual(s["lowest"], Decimal("0.00"))
        self.assertEqual(s["median"], Decimal("1.00"))
        self.assertEqual(s["mean"], Decimal("1.00"))
        self.assertEqual(sum(b["count"] for b in data["distribution"]), 3)

    def test_per_question_stats(self):
        rows = {r["prompt"]: r for r in exam_analytics(self.exam)["questions"]}
        q1, q2 = rows["=cmd() Q1"], rows["Q2"]
        self.assertAlmostEqual(q1["correct_rate"], 2 / 3)
        self.assertEqual(q1["observed"], "MEDIUM")  # 0.67 is between 0.4 and 0.7
        self.assertTrue(q1["mismatch"])  # labelled easy
        self.assertEqual(q1["top_wrong"]["count"], 1)
        self.assertEqual(q2["skipped"], 1)
        self.assertAlmostEqual(q2["skip_rate"], 1 / 3)
        self.assertAlmostEqual(q2["correct_rate"], 1 / 3)
        self.assertEqual(q2["observed"], "HARD")

    def test_in_progress_attempts_are_excluded(self):
        start_attempt(examination=self.exam, candidate=self.cands[3])
        self.assertEqual(exam_analytics(self.exam)["summary"]["attempted"], 3)

    def test_views_and_csv_access(self):
        urls = [
            reverse("examinations:exam-analytics", args=[self.exam.id]),
            reverse("examinations:exam-analytics-csv", args=[self.exam.id]) + "?kind=questions",
            reverse("examinations:exam-analytics-csv", args=[self.exam.id]) + "?kind=scores",
        ]
        for url in urls:
            self.client.force_login(self.cands[0])
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.force_login(make_user(f"o{len(url)}", User.Role.EXAMINER))
            self.assertEqual(self.client.get(url).status_code, 404)
            self.client.force_login(self.examiner)
            self.assertEqual(self.client.get(url).status_code, 200)
        csv_text = self.client.get(urls[1]).content.decode()
        self.assertIn("'=cmd() Q1", csv_text)  # formula neutralised
        self.assertEqual(
            self.client.get(reverse("examinations:exam-analytics-csv", args=[self.exam.id]) + "?kind=x").status_code, 404
        )


class ResilienceTests(TestCase):
    def setUp(self):
        self.examiner = make_user("ex", User.Role.EXAMINER)
        self.cand = make_user("ca", User.Role.CANDIDATE)
        self.exam = make_exam(self.examiner, state=Examination.State.PUBLISHED)
        self.questions = []
        for pos in (1, 2):
            q = make_question(self.examiner, "EASY")
            ExaminationQuestion.objects.create(examination=self.exam, question=q, position=pos)
        Enrollment.objects.create(examination=self.exam, candidate=self.cand)
        self.attempt = start_attempt(examination=self.exam, candidate=self.cand)
        self.aq = self.attempt.attempt_questions.get(position=1)
        self.ids = [c["id"] for c in self.aq.choices_snapshot]

    def selected(self):
        return AttemptAnswer.objects.get(attempt_question=self.aq).selected_choice_ids

    def test_replayed_queue_in_order_keeps_latest(self):
        save_answer(attempt=self.attempt, attempt_question_id=self.aq.id, selected_choice_ids=[self.ids[0]], client_seq=1)
        save_answer(attempt=self.attempt, attempt_question_id=self.aq.id, selected_choice_ids=[self.ids[1]], client_seq=2)
        self.assertEqual(self.selected(), [self.ids[1]])

    def test_stale_or_duplicate_sequence_is_ignored(self):
        save_answer(attempt=self.attempt, attempt_question_id=self.aq.id, selected_choice_ids=[self.ids[1]], client_seq=5)
        save_answer(attempt=self.attempt, attempt_question_id=self.aq.id, selected_choice_ids=[self.ids[0]], client_seq=3)
        save_answer(attempt=self.attempt, attempt_question_id=self.aq.id, selected_choice_ids=[self.ids[2]], client_seq=5)
        self.assertEqual(self.selected(), [self.ids[1]])

    def test_queued_answer_after_deadline_is_rejected_over_http(self):
        self.client.force_login(self.cand)
        url = reverse("examinations:attempt-save-answer", args=[self.attempt.id, 1])
        ok = self.client.post(url, {"choice": [self.ids[0]], "client_seq": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(ok.status_code, 200)
        self.attempt.expires_at = timezone.now() - timedelta(seconds=1)
        self.attempt.save()
        late = self.client.post(url, {"choice": [self.ids[1]], "client_seq": "2"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(late.status_code, 403)
        self.assertTrue(late.json()["expired"])
        self.assertEqual(self.selected(), [self.ids[0]])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, Attempt.Status.EXPIRED)

    def test_invalid_queued_data_returns_400_not_403(self):
        self.client.force_login(self.cand)
        url = reverse("examinations:attempt-save-answer", args=[self.attempt.id, 1])
        bad = self.client.post(url, {"choice": ["999999"], "client_seq": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(bad.status_code, 400)
        self.assertFalse(bad.json()["expired"])

    def test_poll_reports_server_time_and_is_private(self):
        self.client.force_login(self.cand)
        body = self.client.get(reverse("examinations:attempt-poll", args=[self.attempt.id])).json()
        self.assertGreater(body["remaining_seconds"], 0)
        self.assertLessEqual(body["remaining_seconds"], 30 * 60)
        self.client.force_login(self.examiner)
        self.assertEqual(self.client.get(reverse("examinations:attempt-poll", args=[self.attempt.id])).status_code, 403)

    def test_workspace_has_network_status_region(self):
        self.client.force_login(self.cand)
        page = self.client.get(reverse("examinations:attempt-workspace", args=[self.attempt.id, 1]))
        self.assertContains(page, 'id="net-status"')
        self.assertContains(page, "exam-net.js")
        self.assertNotContains(page, "is_correct")
