import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Max
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import User

from .forms import (
    AnnouncementForm,
    BlueprintForm,
    EnrollmentForm,
    ExaminationForm,
    ExamQuestionAssignmentForm,
    GradeForm,
    IncidentForm,
    BulkImportForm,
    WorkspacePreferenceForm,
    QuestionChoiceFormSet,
    QuestionForm,
)
from .models import (
    Attempt,
    AttemptAnswer,
    AttemptQuestion,
    Enrollment,
    ExamBlueprint,
    Examination,
    ExaminationEvent,
    ExaminationQuestion,
    Question,
    UserPreference,
    VerifiedReport,
)
from .permissions import role_required
from .services import (
    announcements_after,
    blueprint_candidate_pool,
    exam_analytics,
    expire_attempt_if_needed,
    finalize_attempt,
    finalized_attempts,
    grade_written_answer,
    log_incident,
    monitor_snapshot,
    pending_written_answers,
    post_announcement,
    publication_problems,
    publish_examination,
    publish_results,
    questions_in_published_pools,
    save_answer,
    save_scratchpad,
    start_attempt,
    start_sandbox_attempt,
    touch_attempt,
)


from .bulk_import import commit_candidates, commit_questions, preview_candidates, preview_questions
from .reporting import build_pdf_response, candidate_report_data, issue_report, summary_report_data, verification_data

def _owned_exam_or_404(request, exam_id):
    if request.user.is_superuser:
        return get_object_or_404(Examination, pk=exam_id)
    return get_object_or_404(Examination, pk=exam_id, examiner=request.user)


def _sync_exam_state(exam, now=None):
    now = now or timezone.now()
    new_state = exam.current_state(now)
    if new_state != exam.state:
        exam.state = new_state
        if new_state == Examination.State.COMPLETED:
            exam.completed_at = now
            exam.save(update_fields=("state", "completed_at", "updated_at"))
        else:
            exam.save(update_fields=("state", "updated_at"))
    return exam


@role_required(User.Role.EXAMINER)
def exam_list(request):
    exams = Examination.objects.filter(examiner=request.user).prefetch_related("exam_questions")
    for exam in exams:
        _sync_exam_state(exam)
    return render(request, "examinations/exam_list.html", {"exams": exams})


@role_required(User.Role.EXAMINER)
def exam_create(request):
    form = ExaminationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        exam = form.save(commit=False)
        exam.examiner = request.user
        exam.full_clean()
        exam.save()
        messages.success(request, "Draft examination created. Add questions and candidates before publication.")
        return redirect("examinations:exam-detail", exam_id=exam.id)
    return render(request, "examinations/exam_form.html", {"form": form})


@role_required(User.Role.EXAMINER)
def exam_detail(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    _sync_exam_state(exam)
    blueprint = ExamBlueprint.objects.filter(examination=exam).first()
    pool_counts = None
    if blueprint and exam.state == Examination.State.DRAFT:
        pool = blueprint_candidate_pool(exam, blueprint)
        pool_counts = {key: len(ids) for key, ids in pool.items()}
    return render(
        request,
        "examinations/exam_detail.html",
        {
            "exam": exam,
            "assignments": exam.exam_questions.select_related("question"),
            "enrollments": exam.enrollments.select_related("candidate"),
            "blueprint": blueprint,
            "pool_counts": pool_counts,
            "attempt_count": finalized_attempts(exam).count(),
        },
    )


@role_required(User.Role.EXAMINER)
@require_POST
def exam_publish(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    try:
        publish_examination(exam)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("examinations:exam-detail", exam_id=exam.id)
    messages.success(request, "Examination published. Candidates can enter only during its scheduled window.")
    return redirect("examinations:exam-detail", exam_id=exam.id)


@role_required(User.Role.EXAMINER)
def exam_blueprint(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    if exam.state != Examination.State.DRAFT:
        raise PermissionDenied("The blueprint cannot be changed after publication.")
    blueprint = ExamBlueprint.objects.filter(examination=exam).first()
    if request.method == "POST" and "remove" in request.POST:
        if blueprint:
            blueprint.delete()
        messages.success(request, "Blueprint removed.")
        return redirect("examinations:exam-detail", exam_id=exam.id)
    form = BlueprintForm(request.POST or None, instance=blueprint)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.examination = exam
        saved.full_clean()
        saved.save()
        messages.success(request, "Blueprint saved. Each candidate will receive their own random draw.")
        return redirect("examinations:exam-detail", exam_id=exam.id)
    pool = blueprint_candidate_pool(exam, blueprint) if blueprint else None
    return render(request, "examinations/exam_blueprint.html", {"exam": exam, "form": form, "blueprint": blueprint, "pool": pool})


@role_required(User.Role.EXAMINER)
def assign_questions(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    if exam.state != Examination.State.DRAFT:
        raise PermissionDenied("Questions cannot be changed after publication.")
    form = ExamQuestionAssignmentForm(request.POST or None, examiner=request.user)
    if request.method == "POST" and form.is_valid():
        next_position = (exam.exam_questions.aggregate(max_position=Max("position"))["max_position"] or 0) + 1
        existing_ids = set(exam.exam_questions.values_list("question_id", flat=True))
        for question in form.cleaned_data["questions"]:
            if question.id not in existing_ids:
                ExaminationQuestion.objects.create(
                    examination=exam, question=question, position=next_position
                )
                next_position += 1
        messages.success(request, "Selected questions were assigned to the draft examination.")
        return redirect("examinations:exam-detail", exam_id=exam.id)
    return render(request, "examinations/assign_questions.html", {"form": form, "exam": exam})


@role_required(User.Role.EXAMINER)
def enroll_candidate(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    if exam.state != Examination.State.DRAFT:
        raise PermissionDenied("Candidates cannot be changed after publication.")
    form = EnrollmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        enrollment = form.save(commit=False)
        enrollment.examination = exam
        try:
            enrollment.full_clean()
            enrollment.save()
            messages.success(request, "Candidate enrolled.")
            return redirect("examinations:exam-detail", exam_id=exam.id)
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "examinations/enroll_candidate.html", {"form": form, "exam": exam})


@role_required(User.Role.EXAMINER)
def question_list(request):
    questions = Question.objects.filter(author=request.user).prefetch_related("choices")
    return render(request, "examinations/question_list.html", {"questions": questions})


@role_required(User.Role.EXAMINER)
def question_create(request):
    question_form = QuestionForm(request.POST or None)
    formset = QuestionChoiceFormSet(request.POST or None, prefix="choices")
    if request.method == "POST" and question_form.is_valid() and formset.is_valid():
        question = question_form.save(commit=False)
        question.author = request.user
        question.full_clean()
        question.save()
        formset.instance = question
        formset.save()
        messages.success(request, "Question saved to your question bank.")
        return redirect("examinations:question-list")
    return render(
        request,
        "examinations/question_form.html",
        {"question_form": question_form, "formset": formset},
    )


def _question_locked(question):
    return (
        question.exam_assignments.exclude(examination__state=Examination.State.DRAFT).exists()
        or question.id in questions_in_published_pools()
    )


@role_required(User.Role.EXAMINER)
def question_edit(request, question_id):
    question = get_object_or_404(Question, pk=question_id, author=request.user)
    if _question_locked(question):
        raise PermissionDenied("Questions used by published examinations cannot be changed.")
    question_form = QuestionForm(request.POST or None, instance=question)
    formset = QuestionChoiceFormSet(request.POST or None, instance=question, prefix="choices")
    if request.method == "POST" and question_form.is_valid() and formset.is_valid():
        question = question_form.save()
        formset.save()
        messages.success(request, "Question updated.")
        return redirect("examinations:question-list")
    return render(
        request,
        "examinations/question_form.html",
        {"question_form": question_form, "formset": formset, "question": question},
    )


@role_required(User.Role.EXAMINER)
@require_POST
def question_delete(request, question_id):
    question = get_object_or_404(Question, pk=question_id, author=request.user)
    if (
        question.exam_assignments.exists()
        or question.attempt_uses.exists()
        or question.id in questions_in_published_pools()
    ):
        raise PermissionDenied("Remove this question from draft examinations before deleting it.")
    question.delete()
    messages.success(request, "Question deleted.")
    return redirect("examinations:question-list")


# ---------------------------------------------------------------------------
# Monitoring and announcements (3.6)
# ---------------------------------------------------------------------------

@role_required(User.Role.EXAMINER)
def exam_monitor(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    _sync_exam_state(exam)
    events = exam.events.select_related("created_by", "attempt__candidate")[:50]
    return render(
        request,
        "examinations/exam_monitor.html",
        {
            "exam": exam,
            "rows": monitor_snapshot(exam),
            "events": events,
            "announcement_form": AnnouncementForm(),
            "incident_form": IncidentForm(exam=exam),
        },
    )


@role_required(User.Role.EXAMINER)
@require_POST
def exam_announce(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    form = AnnouncementForm(request.POST)
    if form.is_valid():
        try:
            post_announcement(exam=exam, user=request.user, message=form.cleaned_data["message"])
            messages.success(request, "Announcement sent. Candidates see it within a few seconds.")
        except ValidationError as error:
            messages.error(request, error.messages[0])
    else:
        messages.error(request, "Write a message of up to 1000 characters before sending.")
    return redirect("examinations:exam-monitor", exam_id=exam.id)


@role_required(User.Role.EXAMINER)
@require_POST
def exam_incident(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    form = IncidentForm(request.POST, exam=exam)
    if form.is_valid():
        try:
            log_incident(
                exam=exam, user=request.user, message=form.cleaned_data["message"],
                attempt=form.cleaned_data["attempt"],
            )
            messages.success(request, "Observation recorded for review.")
        except ValidationError as error:
            messages.error(request, error.messages[0])
    else:
        messages.error(request, "Choose a candidate from this examination and describe what was observed.")
    return redirect("examinations:exam-monitor", exam_id=exam.id)


# ---------------------------------------------------------------------------
# Grading, review and publication (3.7, 3.8)
# ---------------------------------------------------------------------------

@role_required(User.Role.EXAMINER)
def exam_grading(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    _sync_exam_state(exam)
    attempts = list(finalized_attempts(exam).select_related("candidate").order_by("candidate__last_name", "id"))
    pending = {}
    for answer in pending_written_answers(finalized_attempts(exam)):
        pending[answer.attempt_question.attempt_id] = pending.get(answer.attempt_question.attempt_id, 0) + 1
    rows = [{"attempt": a, "pending": pending.get(a.id, 0)} for a in attempts]
    return render(
        request,
        "examinations/exam_grading.html",
        {"exam": exam, "rows": rows, "problems": publication_problems(exam)},
    )


@role_required(User.Role.EXAMINER)
def attempt_grading(request, exam_id, attempt_id):
    exam = _owned_exam_or_404(request, exam_id)
    attempt = get_object_or_404(
        finalized_attempts(exam).select_related("candidate"), pk=attempt_id
    )
    if request.method == "POST":
        answer_id = request.POST.get("answer_id", "")
        answer = get_object_or_404(
            AttemptAnswer, pk=answer_id if answer_id.isdigit() else 0, attempt_question__attempt=attempt
        )
        form = GradeForm(request.POST)
        if form.is_valid():
            try:
                grade_written_answer(
                    answer_id=answer.id, grader=request.user,
                    marks=form.cleaned_data["marks"], feedback=form.cleaned_data["feedback"],
                )
                messages.success(request, "Marks saved and total recalculated.")
            except ValidationError as error:
                messages.error(request, error.messages[0])
        else:
            messages.error(request, "Enter marks as a number between 0 and the question's marks.")
        return redirect("examinations:attempt-grading", exam_id=exam.id, attempt_id=attempt.id)

    items = []
    for aq in attempt.attempt_questions.select_related("answer"):
        answer = getattr(aq, "answer", None)
        selected = set(answer.selected_choice_ids) if answer else set()
        items.append({
            "question": aq,
            "answer": answer,
            "choices": [
                {"text": c["text"], "correct": c["is_correct"], "selected": c["id"] in selected}
                for c in aq.choices_snapshot
            ],
            "needs_marks": bool(
                aq.question_type == "WRITTEN" and answer and answer.awarded_marks is None
            ),
        })
    return render(
        request,
        "examinations/attempt_grading.html",
        {"exam": exam, "attempt": attempt, "items": items, "form": GradeForm()},
    )


@role_required(User.Role.EXAMINER)
@require_POST
def exam_publish_results(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    if request.POST.get("confirm") != "yes":
        messages.error(request, "Confirm that you have reviewed the results before publishing.")
        return redirect("examinations:exam-grading", exam_id=exam.id)
    try:
        publish_results(exam)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("examinations:exam-grading", exam_id=exam.id)
    messages.success(request, "Results published. Each candidate can see only their own result.")
    return redirect("examinations:exam-grading", exam_id=exam.id)


@role_required(User.Role.EXAMINER)
def exam_analytics_view(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    return render(request, "examinations/exam_analytics.html", {"exam": exam, **exam_analytics(exam)})


def _safe_cell(value):
    """Neutralise spreadsheet formulas in exported text."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@role_required(User.Role.EXAMINER)
def exam_analytics_csv(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    kind = request.GET.get("kind", "questions")
    if kind not in ("questions", "scores"):
        raise Http404("Unknown export.")
    data = exam_analytics(exam)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="exam-{exam.id}-{kind}.csv"'
    writer = csv.writer(response)
    if kind == "scores":
        writer.writerow(["Candidate", "Status", "Score", "Total marks"])
        for attempt in data["attempts"]:
            writer.writerow([
                _safe_cell(attempt.candidate.get_full_name() or attempt.candidate.username),
                attempt.status, attempt.total_score, attempt.total_marks or exam.total_marks,
            ])
    else:
        writer.writerow([
            "Question", "Type", "Labelled difficulty", "Shown", "Answered", "Skipped", "Skip rate %",
            "Correct rate %", "Observed difficulty", "Most chosen wrong option",
        ])
        for row in data["questions"]:
            writer.writerow([
                _safe_cell(row["prompt"]), row["type"], row["labelled"], row["shown"], row["answered"],
                row["skipped"], round(row["skip_rate"] * 100, 1),
                "" if row["correct_rate"] is None else round(row["correct_rate"] * 100, 1),
                row["observed"] or "",
                _safe_cell(row["top_wrong"]["text"]) if row["top_wrong"] else "",
            ])
    return response


# ---------------------------------------------------------------------------
# Candidate pages
# ---------------------------------------------------------------------------

@login_required
def candidate_dashboard(request):
    if not request.user.is_candidate:
        raise PermissionDenied("Only candidates can access this dashboard.")
    now = timezone.now()
    enrollments = Enrollment.objects.filter(candidate=request.user).select_related("examination")
    attempts = {
        attempt.examination_id: attempt
        for attempt in Attempt.objects.filter(candidate=request.user)
    }
    in_progress, available, upcoming, completed, missed = [], [], [], [], []
    for enrollment in enrollments:
        exam = _sync_exam_state(enrollment.examination, now)
        if exam.state == Examination.State.DRAFT:
            continue  # Draft examinations are never shown to candidates.
        attempt = attempts.get(exam.id)
        if attempt:
            attempt = expire_attempt_if_needed(attempt, now=now)
        entry = {"exam": exam, "attempt": attempt}
        if attempt and attempt.status == Attempt.Status.IN_PROGRESS:
            in_progress.append(entry)
        elif attempt:
            completed.append(entry)
        elif exam.is_available_to(request.user, now=now):
            available.append(entry)
        elif now < exam.starts_at:
            upcoming.append(entry)
        else:
            missed.append(entry)
    return render(
        request,
        "examinations/candidate_dashboard.html",
        {
            "in_progress": in_progress,
            "available": available,
            "upcoming": upcoming,
            "completed": completed,
            "missed": missed,
        },
    )


@login_required
def candidate_result(request, attempt_id):
    """A candidate's own published result. Anything else is a 404."""
    if not request.user.is_candidate:
        raise PermissionDenied("Only candidates can view results.")
    attempt = get_object_or_404(
        Attempt.objects.select_related("examination"),
        pk=attempt_id,
        candidate=request.user,
        examination__results_published=True,
        status__in=(Attempt.Status.SUBMITTED, Attempt.Status.EXPIRED),
    )
    items = [
        {"question": aq, "answer": getattr(aq, "answer", None)}
        for aq in attempt.attempt_questions.select_related("answer")
    ]
    return render(request, "examinations/candidate_result.html", {"attempt": attempt, "items": items})


@login_required
@require_POST
def candidate_start_attempt(request, exam_id):
    if not request.user.is_candidate:
        raise PermissionDenied("Only candidates can start an examination.")
    exam = get_object_or_404(Examination, pk=exam_id)
    _sync_exam_state(exam)
    try:
        attempt = start_attempt(examination=exam, candidate=request.user)
    except ValidationError:
        messages.info(request, "You have already submitted this examination.")
        return redirect("examinations:candidate-dashboard")
    except PermissionDenied as error:
        messages.error(request, str(error))
        return redirect("examinations:candidate-dashboard")
    return redirect("examinations:attempt-workspace", attempt_id=attempt.id, position=1)


def _candidate_attempt_or_404(request, attempt_id):
    if request.user.is_candidate:
        attempt = get_object_or_404(
            Attempt.all_objects.select_related("examination"), pk=attempt_id, candidate=request.user
        )
    else:
        # Examiners may only open sandbox attempts they own. All other
        # candidate-route requests are rejected before disclosing attempt data.
        attempt = Attempt.all_objects.select_related("examination").filter(
            pk=attempt_id, candidate=request.user, is_sandbox=True
        ).first()
        if attempt is None:
            raise PermissionDenied("Only candidates can access an attempt.")
        if not request.user.is_examiner or (not request.user.is_superuser and attempt.examination.examiner_id != request.user.id):
            raise PermissionDenied("Only the owning examiner can access this sandbox preview.")
    return expire_attempt_if_needed(attempt)

def _question_status(question):
    """Return 'review', 'answered' or 'unanswered' for the question palette."""
    answer = getattr(question, "answer", None)
    if answer and answer.marked_for_review:
        return "review"
    if answer and (answer.selected_choice_ids or answer.written_response.strip()):
        return "answered"
    return "unanswered"


def _palette(attempt):
    questions = list(attempt.attempt_questions.select_related("answer"))
    items = [{"question": q, "status": _question_status(q)} for q in questions]
    counts = {
        "answered": sum(item["status"] == "answered" for item in items),
        "review": sum(item["status"] == "review" for item in items),
        "unanswered": sum(item["status"] == "unanswered" for item in items),
    }
    return items, counts


def _remaining_seconds(attempt):
    return max(0, int((attempt.expires_at - timezone.now()).total_seconds()))


@login_required
def attempt_workspace(request, attempt_id, position):
    attempt = _candidate_attempt_or_404(request, attempt_id)
    if attempt.status != Attempt.Status.IN_PROGRESS:
        return render(request, "examinations/attempt_finished.html", {"attempt": attempt})
    touch_attempt(attempt)
    question = get_object_or_404(AttemptQuestion, attempt=attempt, position=position)
    answer = getattr(question, "answer", None)
    palette, counts = _palette(attempt)
    total = len(palette)
    return render(
        request,
        "examinations/attempt_workspace.html",
        {
            "attempt": attempt,
            "question": question,
            "choices": [{"id": c["id"], "text": c["text"]} for c in question.choices_snapshot],
            "answer": answer,
            "selected_ids": answer.selected_choice_ids if answer else [],
            "palette": palette,
            "counts": counts,
            "total": total,
            "has_previous": position > 1,
            "has_next": position < total,
            "remaining_seconds": _remaining_seconds(attempt),
            "workspace_preference": UserPreference.objects.get_or_create(user=request.user)[0],
            "scratchpad": attempt.scratchpad,
            "announcements": announcements_after(attempt.examination),
        },
    )


@login_required
@require_POST
def save_attempt_answer(request, attempt_id, position):
    """Save the current answer, then move where the candidate asked to go.

    Requests sent by the page's background auto-save (X-Requested-With) get a
    JSON reply instead of a redirect. ``client_seq`` makes queued replays idempotent.
    """
    attempt = _candidate_attempt_or_404(request, attempt_id)
    question = get_object_or_404(AttemptQuestion, attempt=attempt, position=position)
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    try:
        selected_choices = [int(value) for value in request.POST.getlist("choice")]
        raw_seq = request.POST.get("client_seq", "")
        client_seq = int(raw_seq) if raw_seq.isdigit() else None
        save_answer(
            attempt=attempt,
            attempt_question_id=question.id,
            selected_choice_ids=selected_choices,
            written_response=request.POST.get("written_response", ""),
            marked_for_review=request.POST.get("marked_for_review") == "on",
            client_seq=client_seq,
        )
    except (PermissionDenied, ValidationError, ValueError) as error:
        message = error.messages[0] if isinstance(error, ValidationError) else str(error)
        if is_ajax:
            # 403 marks a closed deadline so the client drops its queue instead of retrying.
            code = 403 if isinstance(error, PermissionDenied) else 400
            return JsonResponse({"ok": False, "error": message, "expired": code == 403}, status=code)
        messages.error(request, message)
        return redirect("examinations:attempt-workspace", attempt_id=attempt.id, position=position)

    if is_ajax:
        question = AttemptQuestion.objects.select_related("answer").get(pk=question.pk)
        return JsonResponse({
            "ok": True,
            "status": _question_status(question),
            "saved_at": timezone.localtime().strftime("%H:%M:%S"),
        })

    total = attempt.attempt_questions.count()
    target = request.POST.get("go", "")
    if target == "review":
        return redirect("examinations:attempt-review", attempt_id=attempt.id)
    if target == "next":
        position = min(position + 1, total)
    elif target == "previous":
        position = max(position - 1, 1)
    elif target.isdigit() and 1 <= int(target) <= total:
        position = int(target)
    return redirect("examinations:attempt-workspace", attempt_id=attempt.id, position=position)


@login_required
@require_GET
def attempt_poll(request, attempt_id):
    """Heartbeat: server time left, attempt status and announcements newer than ``after``."""
    attempt = _candidate_attempt_or_404(request, attempt_id)
    after = request.GET.get("after", "0")
    after_id = int(after) if after.isdigit() else 0
    if attempt.status == Attempt.Status.IN_PROGRESS:
        touch_attempt(attempt)
    return JsonResponse({
        "ok": True,
        "status": attempt.status,
        "remaining_seconds": _remaining_seconds(attempt) if attempt.status == Attempt.Status.IN_PROGRESS else 0,
        "announcements": [
            {"id": event.id, "message": event.message,
             "at": timezone.localtime(event.created_at).strftime("%H:%M")}
            for event in announcements_after(attempt.examination, after_id)
        ],
    })


@login_required
def attempt_review(request, attempt_id):
    attempt = _candidate_attempt_or_404(request, attempt_id)
    if attempt.status != Attempt.Status.IN_PROGRESS:
        return render(request, "examinations/attempt_finished.html", {"attempt": attempt})
    palette, counts = _palette(attempt)
    return render(
        request,
        "examinations/attempt_review.html",
        {
            "attempt": attempt,
            "palette": palette,
            "counts": counts,
            "total": len(palette),
            "remaining_seconds": _remaining_seconds(attempt),
            "workspace_preference": UserPreference.objects.get_or_create(user=request.user)[0],
            "scratchpad": attempt.scratchpad,
        },
    )


@login_required
@require_POST
def submit_attempt(request, attempt_id):
    attempt = _candidate_attempt_or_404(request, attempt_id)
    finalize_attempt(attempt)
    attempt.refresh_from_db()
    return render(request, "examinations/attempt_finished.html", {"attempt": attempt})

@role_required(User.Role.EXAMINER)
@require_POST
def sandbox_start(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    try:
        attempt = start_sandbox_attempt(examination=exam, examiner=request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("examinations:exam-detail", exam_id=exam.id)
    messages.info(request, "Sandbox preview started. It is excluded from candidates, results, monitoring, analytics and reports.")
    return redirect("examinations:attempt-workspace", attempt_id=attempt.id, position=1)


@login_required
@require_POST
def workspace_preferences(request, attempt_id):
    attempt = _candidate_attempt_or_404(request, attempt_id)
    preference, _ = UserPreference.objects.get_or_create(user=request.user)
    form = WorkspacePreferenceForm(request.POST, instance=preference)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)
    form.save()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def save_scratchpad_view(request, attempt_id):
    attempt = _candidate_attempt_or_404(request, attempt_id)
    try:
        save_scratchpad(attempt=attempt, owner=request.user, text=request.POST.get("scratchpad", ""))
    except PermissionDenied as error:
        return JsonResponse({"ok": False, "error": str(error)}, status=403)
    return JsonResponse({"ok": True, "saved_at": timezone.localtime().strftime("%H:%M:%S")})


@role_required(User.Role.EXAMINER)
def bulk_import(request):
    preview = request.session.get("bulk_import_preview")
    form = BulkImportForm(request.POST or None, request.FILES or None, examiner=request.user)
    if request.method == "POST" and request.POST.get("action") == "commit":
        if not preview or preview.get("examiner_id") != request.user.id:
            messages.error(request, "The import preview expired. Upload the file again.")
        elif preview.get("errors"):
            messages.error(request, "Fix every row error before committing the import.")
        else:
            try:
                if preview["kind"] == "questions":
                    commit_questions(examiner=request.user, records=preview["records"])
                else:
                    exam = _owned_exam_or_404(request, preview["examination_id"])
                    commit_candidates(examination=exam, records=preview["records"])
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                request.session.pop("bulk_import_preview", None)
                messages.success(request, f"Imported {len(preview['records'])} {preview['kind']} atomically.")
                return redirect("examinations:bulk-import")
    elif request.method == "POST" and form.is_valid():
        kind = form.cleaned_data["kind"]
        records, errors = (preview_questions(form.cleaned_data["file"]) if kind == "questions" else preview_candidates(form.cleaned_data["file"]))
        preview = {
            "examiner_id": request.user.id, "kind": kind, "records": records, "errors": errors,
            "examination_id": form.cleaned_data["examination"].id if form.cleaned_data.get("examination") else None,
        }
        request.session["bulk_import_preview"] = preview
    return render(request, "examinations/bulk_import.html", {"form": form, "preview": preview})


@role_required(User.Role.EXAMINER)
@require_GET
def import_template(request, kind):
    if kind == "questions":
        body = "category,difficulty,question_type,prompt,default_marks,choices\\nMathematics,EASY,SINGLE,2 + 2 = ?,1.00,4|true;3|false\\n"
    elif kind == "candidates":
        body = "username,first_name,last_name,email\\ncandidate_001,Amina,Khan,amina@example.test\\n"
    else:
        raise Http404
    response = HttpResponse(body, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{kind}_import_template.csv"'
    return response


@login_required
def candidate_result_report(request, attempt_id):
    if not request.user.is_candidate:
        raise PermissionDenied("Only candidates can download result reports.")
    attempt = get_object_or_404(Attempt.objects.select_related("examination", "candidate"), pk=attempt_id, candidate=request.user)
    report, data = issue_report(report_type=VerifiedReport.Type.CANDIDATE_RESULT, examination=attempt.examination, attempt=attempt)
    return build_pdf_response(request, report, data, f"result-{attempt.id}.pdf")


@role_required(User.Role.EXAMINER)
def examiner_summary_report(request, exam_id):
    exam = _owned_exam_or_404(request, exam_id)
    report, data = issue_report(report_type=VerifiedReport.Type.EXAMINATION_SUMMARY, examination=exam)
    return build_pdf_response(request, report, data, f"exam-summary-{exam.id}.pdf")


def _verify_rate_limited(request):
    from django.core.cache import cache
    key = f"verify-rate:{request.META.get('REMOTE_ADDR', 'unknown')}"
    if cache.add(key, 1, 60):
        return False
    try:
        count = cache.incr(key)
    except ValueError:
        count = 1
    return count > 30


def verify_report(request, public_id=None):
    if _verify_rate_limited(request):
        return render(request, "examinations/verify_report.html", {"rate_limited": True}, status=429)
    if request.method == "POST":
        submitted_id = request.POST.get("public_id", "").strip()
        if submitted_id:
            return redirect("examinations:verify-report", public_id=submitted_id)
    report = (VerifiedReport.objects.select_related("attempt__candidate", "examination").filter(public_id=public_id).first() if public_id else None)
    status, data = verification_data(report) if report else (None, None)
    context = {"report": report, "public_id": public_id, "verification_status": status, "data": data}
    return render(request, "examinations/verify_report.html", context, status=404 if public_id and report is None else 200)
