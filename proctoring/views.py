import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import User
from examinations.models import Attempt
from examinations.permissions import role_required

from .forms import ConsentForm, ReviewDecisionForm
from .models import ProctorClip, ProctorEvent, ReviewDecision
from .services import authenticate_agent_token, create_event, record_consent, save_clip, save_device_baseline


def _owned_attempt_or_404(request, attempt_id):
    queryset = Attempt.objects.select_related("examination", "candidate")
    if request.user.is_superuser:
        return get_object_or_404(queryset, pk=attempt_id)
    return get_object_or_404(queryset, pk=attempt_id, examination__examiner=request.user)


def _agent_session(request):
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise PermissionDenied("A bearer agent token is required.")
    return authenticate_agent_token(token)


def _json_payload(request):
    if request.content_type != "application/json":
        raise ValidationError("Use application/json for this endpoint.")
    try:
        return json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError("Request body must be valid JSON.") from error


@role_required(User.Role.CANDIDATE)
def consent(request, attempt_id):
    attempt = get_object_or_404(Attempt, pk=attempt_id, candidate=request.user)
    form = ConsentForm(request.POST or None)
    token = None
    if request.method == "POST" and form.is_valid():
        try:
            _, token = record_consent(attempt=attempt, candidate=request.user)
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "proctoring/consent.html", {"attempt": attempt, "form": form, "agent_token": token})


@csrf_exempt
@require_POST
def agent_event(request):
    try:
        session = _agent_session(request)
        event = create_event(session=session, payload=_json_payload(request))
    except (PermissionDenied, ValidationError) as error:
        return JsonResponse({"detail": str(error)}, status=403)
    return JsonResponse({"id": event.id, "occurred_at": event.occurred_at.isoformat()}, status=201)


@csrf_exempt
@require_POST
def agent_baseline(request):
    try:
        session = _agent_session(request)
        baseline = save_device_baseline(session=session, payload=_json_payload(request))
    except (PermissionDenied, ValidationError) as error:
        return JsonResponse({"detail": str(error)}, status=403)
    return JsonResponse({"id": baseline.id, "captured_at": baseline.captured_at.isoformat()}, status=201)


@csrf_exempt
@require_POST
def agent_clip(request):
    try:
        session = _agent_session(request)
        event_id = int(request.POST.get("event_id", ""))
        uploaded_file = request.FILES.get("clip")
        if uploaded_file is None:
            raise ValidationError("Attach an evidence clip in the clip field.")
        clip = save_clip(session=session, event_id=event_id, uploaded_file=uploaded_file)
    except (TypeError, ValueError, PermissionDenied, ValidationError) as error:
        return JsonResponse({"detail": str(error)}, status=403)
    return JsonResponse({"id": clip.id, "size_bytes": clip.size_bytes}, status=201)


@role_required(User.Role.EXAMINER)
def event_timeline(request, attempt_id):
    attempt = _owned_attempt_or_404(request, attempt_id)
    events = ProctorEvent.objects.filter(session__attempt=attempt).select_related("review_decision", "session")
    return render(request, "proctoring/event_timeline.html", {"attempt": attempt, "events": events})


@role_required(User.Role.EXAMINER)
@require_POST
def decide_event(request, event_id):
    event = get_object_or_404(
        ProctorEvent.objects.select_related("session__attempt__examination"), pk=event_id
    )
    if event.session.attempt.examination.examiner_id != request.user.id:
        raise Http404
    form = ReviewDecisionForm(request.POST, instance=getattr(event, "review_decision", None))
    if not form.is_valid():
        return render(request, "proctoring/decision_form.html", {"event": event, "form": form}, status=400)
    decision = form.save(commit=False)
    decision.event = event
    decision.decided_by = request.user
    decision.save()
    events = ProctorEvent.objects.filter(session__attempt=event.session.attempt).select_related("review_decision")
    return render(request, "proctoring/event_timeline.html", {"attempt": event.session.attempt, "events": events})


@role_required(User.Role.EXAMINER)
def private_clip(request, clip_id):
    clip = get_object_or_404(
        ProctorClip.objects.select_related("event__session__attempt__examination"), pk=clip_id
    )
    if clip.event.session.attempt.examination.examiner_id != request.user.id:
        raise Http404
    return FileResponse(clip.evidence.open("rb"), content_type=clip.content_type, as_attachment=False)
