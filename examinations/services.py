import random
import statistics
from datetime import timedelta
from collections import Counter, OrderedDict
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    Attempt,
    AttemptAnswer,
    AttemptQuestion,
    Enrollment,
    Examination,
    ExaminationEvent,
    ExaminationQuestion,
    Question,
)

CENT = Decimal("0.01")
MIN_ANALYTICS_SAMPLE = 3


def _money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Publication checks and difficulty-ratio blueprint (3.3, 5.2)
# ---------------------------------------------------------------------------

def question_problem(question):
    """Return a message when a question cannot be used in an examination, else None."""
    choices = list(question.choices.all())
    correct_count = sum(choice.is_correct for choice in choices)
    if question.question_type == Question.Type.SINGLE_CHOICE:
        if len(choices) < 2 or correct_count != 1:
            return "Each single-answer question needs at least two choices and exactly one correct choice."
    elif question.question_type == Question.Type.MULTIPLE_SELECT:
        if len(choices) < 2 or correct_count < 1:
            return "Each multiple-select question needs at least two choices and one or more correct choices."
    elif choices:
        return "Written-response questions cannot contain answer choices."
    return None


def _blueprint_or_none(exam):
    blueprint = getattr(exam, "blueprint", None) if hasattr(exam, "blueprint") else None
    return blueprint if blueprint and blueprint.total_drawn > 0 else None


def blueprint_candidate_pool(exam, blueprint=None):
    """Valid questions the blueprint may draw from, grouped by difficulty (manual picks excluded)."""
    blueprint = blueprint or _blueprint_or_none(exam)
    pool = {difficulty: [] for difficulty in Question.Difficulty.values}
    if not blueprint:
        return pool
    manual_ids = set(exam.exam_questions.values_list("question_id", flat=True))
    questions = Question.objects.filter(author=exam.examiner).prefetch_related("choices").order_by("id")
    if blueprint.category:
        questions = questions.filter(category=blueprint.category)
    for question in questions:
        if question.id in manual_ids or question_problem(question):
            continue
        pool[question.difficulty].append(question.id)
    return pool


def validate_for_publication(exam):
    assignments = list(exam.exam_questions.select_related("question").prefetch_related("question__choices"))
    blueprint = _blueprint_or_none(exam)
    if not assignments and not blueprint:
        raise ValidationError("Add at least one question or a difficulty blueprint before publishing.")

    for assignment in assignments:
        question = assignment.question
        if question.author_id != exam.examiner_id:
            raise ValidationError("An examination may contain only questions from its examiner's question bank.")
        problem = question_problem(question)
        if problem:
            raise ValidationError(problem)

    if blueprint:
        pool = blueprint_candidate_pool(exam, blueprint)
        labels = {"EASY": "easy", "MEDIUM": "medium", "HARD": "hard"}
        for difficulty, needed in blueprint.counts().items():
            available = len(pool[difficulty])
            if needed > available:
                raise ValidationError(
                    f"The blueprint needs {needed} {labels[difficulty]} question(s) but only {available} "
                    f"valid {labels[difficulty]} question(s) are available in the question bank."
                )


def exam_total_marks(exam):
    total = sum((item.assigned_marks for item in exam.exam_questions.select_related("question")), Decimal("0.00"))
    blueprint = _blueprint_or_none(exam)
    if blueprint:
        total += blueprint.total_marks
    return _money(total)


@transaction.atomic
def publish_examination(exam, now=None):
    """Validate, freeze the blueprint pool and move a draft examination to PUBLISHED."""
    now = now or timezone.now()
    exam = Examination.objects.select_for_update().get(pk=exam.pk)
    if exam.state != Examination.State.DRAFT:
        raise ValidationError("Only draft examinations can be published.")
    validate_for_publication(exam)
    blueprint = _blueprint_or_none(exam)
    if blueprint:
        pool = blueprint_candidate_pool(exam, blueprint)
        blueprint.frozen_pool = sorted(qid for ids in pool.values() for qid in ids)
        blueprint.save(update_fields=("frozen_pool",))
    exam.total_marks = exam_total_marks(exam)
    exam.state = Examination.State.PUBLISHED
    exam.published_at = now
    exam.save(update_fields=("total_marks", "state", "published_at", "updated_at"))
    return exam


def draw_blueprint_questions(blueprint, rng):
    """Draw the configured number per difficulty from the frozen pool using ``rng``."""
    questions = {
        q.id: q
        for q in Question.objects.filter(id__in=blueprint.frozen_pool).prefetch_related("choices")
    }
    drawn = []
    for difficulty, needed in blueprint.counts().items():
        ids = sorted(qid for qid, q in questions.items() if q.difficulty == difficulty)
        if needed > len(ids):
            raise ValidationError("The question pool for this examination is too small. Contact the examiner.")
        drawn.extend(questions[qid] for qid in rng.sample(ids, needed))
    return drawn


def questions_in_published_pools():
    """Ids of questions frozen into the pool of a non-draft examination."""
    from .models import ExamBlueprint

    ids = set()
    for pool in ExamBlueprint.objects.exclude(examination__state=Examination.State.DRAFT).values_list(
        "frozen_pool", flat=True
    ):
        ids.update(pool or [])
    return ids


# ---------------------------------------------------------------------------
# Attempt lifecycle
# ---------------------------------------------------------------------------

def _snapshot_choices(question, shuffle, rng):
    choices = [
        {"id": choice.id, "text": choice.text, "is_correct": choice.is_correct}
        for choice in question.choices.all()
    ]
    if shuffle:
        rng.shuffle(choices)
    return choices


@transaction.atomic
def start_attempt(*, examination: Examination, candidate, now=None):
    now = now or timezone.now()
    examination = Examination.objects.select_for_update().get(pk=examination.pk)
    existing = Attempt.objects.select_for_update().filter(
        examination=examination, candidate=candidate
    ).first()
    if existing:
        existing = expire_attempt_if_needed(existing, now=now)
        if existing.status == Attempt.Status.IN_PROGRESS:
            return existing
        raise ValidationError("This examination attempt has already been finalized.")

    if not candidate.is_candidate or not examination.is_available_to(candidate, now=now):
        raise PermissionDenied("You are not eligible to start this examination at this time.")

    seed = random.SystemRandom().getrandbits(62)
    rng = random.Random(seed)

    # Each item: (assignment or None, question, marks)
    items = [
        (assignment, assignment.question, assignment.assigned_marks)
        for assignment in ExaminationQuestion.objects.select_related("question")
        .prefetch_related("question__choices")
        .filter(examination=examination)
        .order_by("position", "id")
    ]
    blueprint = _blueprint_or_none(examination)
    if blueprint:
        items.extend(
            (None, question, blueprint.marks_for(question.difficulty))
            for question in draw_blueprint_questions(blueprint, rng)
        )
    if examination.randomize_questions:
        rng.shuffle(items)

    attempt = Attempt.objects.create(
        examination=examination,
        candidate=candidate,
        started_at=now,
        expires_at=examination.attempt_deadline(now),
        draw_seed=seed,
        total_marks=_money(sum((marks for _, _, marks in items), Decimal("0.00"))),
    )
    for position, (assignment, question, marks) in enumerate(items, start=1):
        AttemptQuestion.objects.create(
            attempt=attempt,
            source_assignment=assignment,
            source_question=question,
            position=position,
            prompt=question.prompt,
            question_type=question.question_type,
            difficulty=question.difficulty,
            marks=marks,
            choices_snapshot=_snapshot_choices(question, examination.randomize_choices, rng),
        )
    return attempt


@transaction.atomic
def start_sandbox_attempt(*, examination: Examination, examiner, now=None):
    """Create an examiner-owned preview without touching real candidate data."""
    now = now or timezone.now()
    examination = Examination.objects.select_for_update().get(pk=examination.pk)
    if not examiner.is_examiner or (not examiner.is_superuser and examination.examiner_id != examiner.id):
        raise PermissionDenied("Only the owning examiner can preview this examination.")

    seed = random.SystemRandom().getrandbits(62)
    rng = random.Random(seed)
    items = [
        (assignment, assignment.question, assignment.assigned_marks)
        for assignment in ExaminationQuestion.objects.select_related("question")
        .prefetch_related("question__choices")
        .filter(examination=examination)
        .order_by("position", "id")
    ]
    blueprint = _blueprint_or_none(examination)
    if blueprint:
        # Draft previews use the currently valid pool. Published previews use its frozen pool.
        if not blueprint.frozen_pool:
            pool = blueprint_candidate_pool(examination, blueprint)
            blueprint.frozen_pool = sorted(question_id for ids in pool.values() for question_id in ids)
        items.extend(
            (None, question, blueprint.marks_for(question.difficulty))
            for question in draw_blueprint_questions(blueprint, rng)
        )
    if not items:
        raise ValidationError("Add valid questions before starting a sandbox preview.")
    if examination.randomize_questions:
        rng.shuffle(items)

    attempt = Attempt.all_objects.create(
        examination=examination,
        candidate=examiner,
        started_at=now,
        expires_at=now + timedelta(minutes=examination.duration_minutes),
        draw_seed=seed,
        total_marks=_money(sum((marks for _, _, marks in items), Decimal("0.00"))),
        is_sandbox=True,
    )
    for position, (assignment, question, marks) in enumerate(items, start=1):
        AttemptQuestion.objects.create(
            attempt=attempt,
            source_assignment=assignment,
            source_question=question,
            position=position,
            prompt=question.prompt,
            question_type=question.question_type,
            difficulty=question.difficulty,
            marks=marks,
            choices_snapshot=_snapshot_choices(question, examination.randomize_choices, rng),
        )
    return attempt


def save_scratchpad(*, attempt: Attempt, owner, text, now=None):
    """Persist private rough work independently of an answer and never grade it."""
    text = (text or "")[:10000]
    now = now or timezone.now()
    with transaction.atomic():
        attempt = Attempt.all_objects.select_for_update().get(pk=attempt.pk)
        if attempt.candidate_id != owner.id:
            raise PermissionDenied("You cannot edit this scratchpad.")
        if not attempt.can_accept_answers(now):
            expire_attempt_if_needed(attempt, now=now)
            raise PermissionDenied("The scratchpad is closed because the attempt has ended.")
        attempt.scratchpad = text
        attempt.scratchpad_updated_at = now
        attempt.save(update_fields=("scratchpad", "scratchpad_updated_at"))
    return attempt


def save_answer(*, attempt: Attempt, attempt_question_id: int, selected_choice_ids=None,
                written_response="", marked_for_review=False, client_seq=None, now=None):
    """Save an answer only while the server-side deadline remains open.

    ``client_seq`` makes queued, replayed or out-of-order requests idempotent: a request
    whose sequence number is not newer than the stored one is acknowledged without
    overwriting. Receipt time is server time, so offline time never extends the deadline.
    """
    now = now or timezone.now()
    expired = False
    answer = None
    with transaction.atomic():
        attempt = Attempt.all_objects.select_for_update().get(pk=attempt.pk)
        if not attempt.can_accept_answers(now):
            expire_attempt_if_needed(attempt, now=now)
            expired = True
        else:
            attempt_question = AttemptQuestion.objects.get(pk=attempt_question_id, attempt=attempt)
            selected_choice_ids = selected_choice_ids or []
            valid_choice_ids = {choice["id"] for choice in attempt_question.choices_snapshot}
            if any(choice_id not in valid_choice_ids for choice_id in selected_choice_ids):
                raise ValidationError("One or more submitted choices are not part of this question.")
            if attempt_question.question_type == "SINGLE" and len(selected_choice_ids) > 1:
                raise ValidationError("A single-answer question accepts one choice.")
            if attempt_question.question_type != "WRITTEN" and written_response:
                raise ValidationError("Objective questions do not accept a written response.")

            existing = AttemptAnswer.objects.select_for_update().filter(attempt_question=attempt_question).first()
            if existing and client_seq is not None and client_seq <= existing.client_seq:
                return existing  # stale or duplicate replay
            defaults = {
                "selected_choice_ids": selected_choice_ids,
                "written_response": written_response,
                "marked_for_review": marked_for_review,
            }
            if client_seq is not None:
                defaults["client_seq"] = client_seq
            answer, _ = AttemptAnswer.objects.update_or_create(
                attempt_question=attempt_question, defaults=defaults
            )
    if expired:
        raise PermissionDenied("The answer deadline has passed.")
    return answer


@transaction.atomic
def expire_attempt_if_needed(attempt: Attempt, now=None):
    """Finalize an expired attempt under the same row lock as saves and submits."""
    now = now or timezone.now()
    attempt = Attempt.all_objects.select_for_update().get(pk=attempt.pk)
    if attempt.status == Attempt.Status.IN_PROGRESS and now >= attempt.expires_at:
        return finalize_attempt(attempt, expired=True, now=now)
    return attempt


# ---------------------------------------------------------------------------
# Marking (3.7)
# ---------------------------------------------------------------------------

def score_objective(attempt_question, selected_ids, scheme):
    """Marks for a SINGLE or MULTIPLE question under the examination's marking scheme."""
    selected = set(selected_ids or [])
    correct = {c["id"] for c in attempt_question.choices_snapshot if c["is_correct"]}
    if not selected or not correct:
        return Decimal("0.00")
    marks = attempt_question.marks
    if selected == correct:
        return _money(marks)
    if attempt_question.question_type == "MULTIPLE" and scheme == Examination.MultipleSelectScheme.PARTIAL:
        net = len(selected & correct) - len(selected - correct)
        if net > 0:
            return _money(marks * Decimal(net) / Decimal(len(correct)))
    return Decimal("0.00")


def recompute_attempt_total(attempt):
    """Single place that derives ``Attempt.total_score`` from stored awarded marks."""
    total = sum(
        (
            answer.awarded_marks
            for answer in AttemptAnswer.objects.filter(
                attempt_question__attempt=attempt, awarded_marks__isnull=False
            )
        ),
        Decimal("0.00"),
    )
    attempt.total_score = _money(total)
    attempt.save(update_fields=("total_score",))
    return attempt.total_score


@transaction.atomic
def finalize_attempt(attempt: Attempt, *, expired=False, now=None):
    now = now or timezone.now()
    attempt = Attempt.all_objects.select_for_update().select_related("examination").get(pk=attempt.pk)
    if attempt.status != Attempt.Status.IN_PROGRESS:
        return attempt
    if not expired and now >= attempt.expires_at:
        expired = True

    scheme = attempt.examination.multiple_select_scheme
    for attempt_question in attempt.attempt_questions.select_related("answer"):
        answer = getattr(attempt_question, "answer", None)
        if attempt_question.question_type == "WRITTEN":
            if answer is None or not answer.written_response.strip():
                # Nothing to grade: record zero so the examiner has no empty queue entry.
                if answer is None:
                    answer = AttemptAnswer.objects.create(attempt_question=attempt_question)
                answer.awarded_marks = Decimal("0.00")
                answer.save(update_fields=("awarded_marks", "saved_at"))
            continue
        awarded = score_objective(attempt_question, answer.selected_choice_ids if answer else [], scheme)
        if answer:
            answer.awarded_marks = awarded
            answer.save(update_fields=("awarded_marks", "saved_at"))

    attempt.status = Attempt.Status.EXPIRED if expired else Attempt.Status.SUBMITTED
    attempt.submitted_at = min(now, attempt.expires_at) if expired else now
    attempt.save(update_fields=("status", "submitted_at"))
    recompute_attempt_total(attempt)
    return attempt


def pending_written_answers(attempt_qs):
    """Written answers with a response that still await a mark, for finalized attempts."""
    return (
        AttemptAnswer.objects.filter(
            attempt_question__attempt__in=attempt_qs,
            attempt_question__question_type="WRITTEN",
            awarded_marks__isnull=True,
        )
        .exclude(written_response__regex=r"^\s*$")
        .select_related("attempt_question", "attempt_question__attempt", "attempt_question__attempt__candidate")
        .order_by("attempt_question__attempt_id", "attempt_question__position")
    )


def finalized_attempts(exam):
    """Real, finalized attempts of an examination. Every result and analytic goes through here."""
    return Attempt.objects.filter(
        examination=exam, status__in=(Attempt.Status.SUBMITTED, Attempt.Status.EXPIRED)
    )


@transaction.atomic
def grade_written_answer(*, answer_id, grader, marks, feedback=""):
    """Award marks to a written answer. ``marks`` must be within 0..assigned marks."""
    answer = (
        AttemptAnswer.objects.select_for_update()
        .select_related("attempt_question__attempt__examination")
        .get(pk=answer_id)
    )
    attempt_question = answer.attempt_question
    attempt = attempt_question.attempt
    exam = attempt.examination
    if not grader.is_superuser and exam.examiner_id != grader.id:
        raise PermissionDenied("You can grade only your own examinations.")
    if attempt.status == Attempt.Status.IN_PROGRESS:
        raise ValidationError("This attempt is still in progress and cannot be graded yet.")
    if attempt_question.question_type != "WRITTEN":
        raise ValidationError("Only written responses are graded manually.")
    try:
        marks = _money(Decimal(str(marks)))
    except Exception:
        raise ValidationError("Enter the marks as a number.")
    if marks < 0 or marks > attempt_question.marks:
        raise ValidationError(f"Marks must be between 0 and {attempt_question.marks.normalize():f}.")

    answer.awarded_marks = marks
    answer.grader_feedback = feedback.strip()
    answer.graded_by = grader
    answer.graded_at = timezone.now()
    answer.save(update_fields=("awarded_marks", "grader_feedback", "graded_by", "graded_at", "saved_at"))
    # A revised mark invalidates any previously issued candidate result report.
    from .models import VerifiedReport
    VerifiedReport.objects.filter(
        attempt=attempt, report_type=VerifiedReport.Type.CANDIDATE_RESULT,
        status=VerifiedReport.Status.VALID,
    ).update(status=VerifiedReport.Status.SUPERSEDED)
    recompute_attempt_total(Attempt.all_objects.select_for_update().get(pk=attempt.pk))
    return answer


def publication_problems(exam, now=None):
    """Reasons results cannot be published yet; an empty list means they can."""
    now = now or timezone.now()
    problems = []
    for attempt in Attempt.objects.filter(examination=exam, status=Attempt.Status.IN_PROGRESS):
        expire_attempt_if_needed(attempt, now=now)
    if now < exam.ends_at:
        problems.append("The examination window is still open.")
    if Attempt.objects.filter(examination=exam, status=Attempt.Status.IN_PROGRESS).exists():
        problems.append("Some attempts are still in progress.")
    pending = pending_written_answers(finalized_attempts(exam)).count()
    if pending:
        problems.append(f"{pending} written response(s) still need marks.")
    if not finalized_attempts(exam).exists():
        problems.append("There are no submitted attempts to publish.")
    return problems


@transaction.atomic
def publish_results(exam, now=None):
    now = now or timezone.now()
    exam = Examination.objects.select_for_update().get(pk=exam.pk)
    if exam.results_published:
        return exam  # idempotent
    problems = publication_problems(exam, now=now)
    if problems:
        raise ValidationError(problems)
    exam.results_published = True
    exam.results_published_at = now
    if exam.state != Examination.State.COMPLETED:
        exam.state = Examination.State.COMPLETED
        exam.completed_at = exam.completed_at or now
    exam.save(update_fields=("results_published", "results_published_at", "state", "completed_at", "updated_at"))
    return exam


# ---------------------------------------------------------------------------
# Monitoring and announcements (3.6)
# ---------------------------------------------------------------------------

def answered_count(attempt):
    count = 0
    for answer in AttemptAnswer.objects.filter(attempt_question__attempt=attempt):
        if answer.selected_choice_ids or answer.written_response.strip():
            count += 1
    return count


def monitor_snapshot(exam, now=None):
    now = now or timezone.now()
    attempts = {a.candidate_id: a for a in Attempt.objects.filter(examination=exam)}
    rows = []
    for enrollment in Enrollment.objects.filter(examination=exam).select_related("candidate"):
        attempt = attempts.get(enrollment.candidate_id)
        row = {"candidate": enrollment.candidate, "attempt": attempt, "status": "NOT_STARTED",
               "answered": 0, "total": 0, "connection": ""}
        if attempt:
            attempt = expire_attempt_if_needed(attempt, now=now)
            row["attempt"] = attempt
            row["status"] = attempt.status
            row["answered"] = answered_count(attempt)
            row["total"] = attempt.attempt_questions.count()
            if attempt.status == Attempt.Status.IN_PROGRESS:
                seen = attempt.last_seen_at
                row["connection"] = "Connected" if seen and (now - seen).total_seconds() <= 45 else "No recent signal"
        rows.append(row)
    return rows


def post_announcement(*, exam, user, message):
    message = (message or "").strip()
    if not message:
        raise ValidationError("Write a message before sending.")
    if len(message) > 1000:
        raise ValidationError("Announcements are limited to 1000 characters.")
    return ExaminationEvent.objects.create(
        examination=exam, event_type=ExaminationEvent.Type.ANNOUNCEMENT, message=message, created_by=user
    )


def log_incident(*, exam, user, message, attempt=None):
    message = (message or "").strip()
    if not message:
        raise ValidationError("Describe what was observed.")
    if len(message) > 1000:
        raise ValidationError("Incident notes are limited to 1000 characters.")
    if attempt is not None and attempt.examination_id != exam.id:
        raise ValidationError("That attempt does not belong to this examination.")
    return ExaminationEvent.objects.create(
        examination=exam, attempt=attempt, event_type=ExaminationEvent.Type.INCIDENT,
        message=message, created_by=user,
    )


def announcements_after(exam, after_id=0):
    return list(
        ExaminationEvent.objects.filter(
            examination=exam, event_type=ExaminationEvent.Type.ANNOUNCEMENT, id__gt=after_id
        ).order_by("id")
    )


def touch_attempt(attempt, now=None):
    Attempt.objects.filter(pk=attempt.pk).update(last_seen_at=now or timezone.now())


# ---------------------------------------------------------------------------
# Analytics (3.8, 4.5)
# ---------------------------------------------------------------------------

def _observed_difficulty(rate):
    if rate is None:
        return None
    if rate >= 0.7:
        return Question.Difficulty.EASY
    if rate >= 0.4:
        return Question.Difficulty.MEDIUM
    return Question.Difficulty.HARD


def exam_analytics(exam):
    attempts = list(finalized_attempts(exam).select_related("candidate"))
    scores = [a.total_score or Decimal("0.00") for a in attempts]
    max_marks = exam.total_marks
    for attempt in attempts:
        if attempt.total_marks:
            max_marks = max(max_marks, attempt.total_marks)

    summary = {
        "enrolled": exam.enrollments.count(),
        "attempted": len(attempts),
        "mean": _money(sum(scores, Decimal("0.00")) / len(scores)) if scores else None,
        "median": _money(statistics.median(scores)) if scores else None,
        "highest": max(scores) if scores else None,
        "lowest": min(scores) if scores else None,
        "total_marks": max_marks,
    }

    distribution = [{"label": f"{i * 10}-{i * 10 + 10}%", "count": 0} for i in range(10)]
    for attempt in attempts:
        total = attempt.total_marks or exam.total_marks
        pct = float((attempt.total_score or 0) / total * 100) if total else 0
        distribution[min(int(pct // 10), 9)]["count"] += 1
    peak = max((d["count"] for d in distribution), default=0)
    for bucket in distribution:
        bucket["width"] = int(bucket["count"] / peak * 100) if peak else 0

    questions = OrderedDict()
    answers = {
        a.attempt_question_id: a
        for a in AttemptAnswer.objects.filter(attempt_question__attempt__in=attempts)
    }
    for aq in AttemptQuestion.objects.filter(attempt__in=attempts).select_related("source_question").order_by(
        "attempt_id", "position"
    ):
        key = aq.source_question_id or f"prompt:{aq.prompt}"
        entry = questions.setdefault(key, {
            "prompt": aq.prompt, "type": aq.question_type,
            "labelled": aq.difficulty or (aq.source_question.difficulty if aq.source_question else ""),
            "shown": 0, "answered": 0, "skipped": 0, "scored": 0, "correct": 0, "pct_sum": Decimal("0"),
            "ungraded": 0, "wrong": Counter(), "texts": {},
        })
        entry["shown"] += 1
        answer = answers.get(aq.id)
        has_response = bool(answer and (answer.selected_choice_ids or answer.written_response.strip()))
        if not has_response:
            entry["skipped"] += 1
        else:
            entry["answered"] += 1
        if aq.question_type != "WRITTEN":
            correct_ids = {c["id"] for c in aq.choices_snapshot if c["is_correct"]}
            entry["texts"].update({c["id"]: c["text"] for c in aq.choices_snapshot})
            if answer:
                for cid in answer.selected_choice_ids:
                    if cid not in correct_ids:
                        entry["wrong"][cid] += 1
        if answer is not None and answer.awarded_marks is not None:
            entry["scored"] += 1
            entry["pct_sum"] += (answer.awarded_marks / aq.marks) if aq.marks else Decimal("0")
            if answer.awarded_marks == aq.marks:
                entry["correct"] += 1
        elif has_response:
            entry["ungraded"] += 1
        elif not has_response:
            entry["scored"] += 1  # unanswered counts as zero marks

    rows = []
    for entry in questions.values():
        shown, scored = entry["shown"], entry["scored"]
        correct_rate = entry["correct"] / scored if scored else None
        enough = scored >= MIN_ANALYTICS_SAMPLE
        observed = _observed_difficulty(correct_rate) if enough else None
        top_wrong = None
        if entry["wrong"]:
            cid, count = entry["wrong"].most_common(1)[0]
            top_wrong = {"text": entry["texts"].get(cid, "Unknown choice"), "count": count}
        rows.append({
            "prompt": entry["prompt"],
            "type": entry["type"],
            "labelled": entry["labelled"],
            "shown": shown,
            "answered": entry["answered"],
            "skipped": entry["skipped"],
            "skip_rate": entry["skipped"] / shown if shown else 0,
            "correct_rate": correct_rate,
            "avg_score_pct": float(entry["pct_sum"] / scored) if scored else None,
            "ungraded": entry["ungraded"],
            "top_wrong": top_wrong,
            "observed": observed,
            "mismatch": bool(observed and entry["labelled"] and observed != entry["labelled"]),
            "enough_data": enough,
        })
    return {"summary": summary, "distribution": distribution, "questions": rows, "attempts": attempts}
