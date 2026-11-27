"""Safe, consistent responses for errors that reach Django's request boundary."""

from http import HTTPStatus

from django.http import JsonResponse
from django.shortcuts import render


_ERROR_DETAILS = {
    400: {
        "code": "bad_request",
        "title": "We could not process that request",
        "message": "Check the submitted information and try again.",
    },
    403: {
        "code": "permission_denied",
        "title": "You do not have access to this page",
        "message": "Sign in with an authorized account or return to your dashboard.",
    },
    404: {
        "code": "not_found",
        "title": "We could not find that page",
        "message": "The link may be outdated, or the record may no longer be available.",
    },
    500: {
        "code": "server_error",
        "title": "Something went wrong",
        "message": "Please try again. Work that was already confirmed as saved is still available.",
    },
}


def _wants_json(request):
    """Return JSON for API and background requests, HTML otherwise."""
    accepted = request.headers.get("Accept", "").lower()
    return (
        request.path.startswith("/api/")
        or request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in accepted
    )


def _safe_exception_message(exception, fallback):
    """Expose deliberate permission messages, never internal server details."""
    message = str(exception).strip() if exception is not None else ""
    return message or fallback


def error_response(request, status, exception=None):
    details = _ERROR_DETAILS[status].copy()
    if status == 403:
        details["message"] = _safe_exception_message(exception, details["message"])

    reference = getattr(request, "request_id", "")
    if _wants_json(request):
        payload = {
            "ok": False,
            "code": details["code"],
            "error": details["message"],
            "detail": details["message"],
        }
        if status == 500 and reference:
            payload["reference"] = reference
        return JsonResponse(payload, status=status)

    return render(
        request,
        "errors/error.html",
        {
            **details,
            "status_code": status,
            "status_phrase": HTTPStatus(status).phrase,
            "reference": reference if status == 500 else "",
        },
        status=status,
    )


def bad_request(request, exception):
    return error_response(request, 400, exception)


def permission_denied(request, exception):
    return error_response(request, 403, exception)


def page_not_found(request, exception):
    return error_response(request, 404, exception)


def server_error(request):
    return error_response(request, 500)
