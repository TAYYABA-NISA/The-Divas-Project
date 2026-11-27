"""Private PDF rendering and minimal public verification for issued reports."""
import hashlib
import io
import json
import secrets
from decimal import Decimal

import qrcode
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from .models import Attempt, Examination, VerifiedReport
from .services import exam_analytics


def _as_json_value(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return value


def _canonical_hash(data):
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), default=_as_json_value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def masked_name(user):
    name = (user.get_full_name() or user.username or "Candidate").strip()
    return f"{name[0]}***" if name else "C***"


def candidate_report_data(attempt):
    attempt = Attempt.all_objects.select_related("examination", "candidate").get(pk=attempt.pk)
    if attempt.is_sandbox or not attempt.examination.results_published:
        raise PermissionDenied("Only published real results can be issued as reports.")
    total = attempt.total_marks if attempt.total_marks is not None else attempt.examination.total_marks
    return {
        "exam_title": attempt.examination.title,
        "issue_date": attempt.examination.results_published_at.date().isoformat(),
        "candidate_name": masked_name(attempt.candidate),
        "score": _as_json_value(attempt.total_score or Decimal("0.00")),
        "total": _as_json_value(total or Decimal("0.00")),
    }


def summary_report_data(exam):
    if not exam.results_published:
        raise PermissionDenied("Publish results before issuing a summary report.")
    analytics = exam_analytics(exam)
    return {
        "exam_title": exam.title,
        "issue_date": exam.results_published_at.date().isoformat(),
        "attempted": analytics["summary"]["attempted"],
        "mean": _as_json_value(analytics["summary"]["mean"] or Decimal("0.00")),
        "total": _as_json_value(analytics["summary"]["total_marks"] or Decimal("0.00")),
    }


@transaction.atomic
def issue_report(*, report_type, examination, attempt=None):
    if report_type == VerifiedReport.Type.CANDIDATE_RESULT:
        if attempt is None or attempt.examination_id != examination.id:
            raise ValidationError("A result report must match its examination attempt.")
        data = candidate_report_data(attempt)
        current = VerifiedReport.objects.filter(attempt=attempt, report_type=report_type, status=VerifiedReport.Status.VALID, data_hash=_canonical_hash(data)).first()
        if current:
            return current, data
        VerifiedReport.objects.filter(attempt=attempt, report_type=report_type, status=VerifiedReport.Status.VALID).update(status=VerifiedReport.Status.SUPERSEDED)
    elif report_type == VerifiedReport.Type.EXAMINATION_SUMMARY:
        data = summary_report_data(examination)
        current = VerifiedReport.objects.filter(examination=examination, report_type=report_type, status=VerifiedReport.Status.VALID, data_hash=_canonical_hash(data)).first()
        if current:
            return current, data
        VerifiedReport.objects.filter(examination=examination, report_type=report_type, status=VerifiedReport.Status.VALID).update(status=VerifiedReport.Status.SUPERSEDED)
    else:
        raise ValidationError("Unknown report type.")
    return VerifiedReport.objects.create(
        public_id=secrets.token_urlsafe(16), report_type=report_type, attempt=attempt,
        examination=examination, data_hash=_canonical_hash(data),
    ), data

def verification_data(report):
    if report.status != VerifiedReport.Status.VALID:
        return report.status.lower(), None
    try:
        if report.report_type == VerifiedReport.Type.CANDIDATE_RESULT:
            data = candidate_report_data(report.attempt)
        else:
            data = summary_report_data(report.examination)
    except (PermissionDenied, AttributeError):
        return "superseded", None
    if not secrets.compare_digest(report.data_hash, _canonical_hash(data)):
        return "invalid", None
    # Never add answer data, email, enrollment information, or any proctoring data here.
    public = {key: data[key] for key in ("exam_title", "issue_date", "candidate_name", "score", "total") if key in data}
    return "authentic", public


def _line(pdf, text, y, width=170 * mm):
    words = str(text).split()
    line = ""
    for word in words:
        proposal = f"{line} {word}".strip()
        if stringWidth(proposal, "Helvetica", 10) > width:
            pdf.drawString(20 * mm, y, line)
            y -= 6 * mm
            line = word
        else:
            line = proposal
    if line:
        pdf.drawString(20 * mm, y, line)
        y -= 6 * mm
    return y


def build_pdf_response(request, report, data, filename):
    """Render a readable PDF with a QR code pointing at the public verify record."""
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    page_width, page_height = A4
    y = page_height - 22 * mm
    pdf.setTitle("Verified examination report")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(20 * mm, y, "Verified examination report")
    y -= 12 * mm
    pdf.setFont("Helvetica", 10)
    labels = {
        "exam_title": "Examination", "issue_date": "Issued", "candidate_name": "Candidate",
        "score": "Score", "total": "Total marks", "attempted": "Submitted attempts", "mean": "Average score",
    }
    for key in ("exam_title", "candidate_name", "score", "total", "attempted", "mean", "issue_date"):
        if key in data:
            y = _line(pdf, f"{labels[key]}: {data[key]}", y)
    y -= 4 * mm
    verify_url = request.build_absolute_uri(reverse("examinations:verify-report", args=[report.public_id]))
    qr = qrcode.make(verify_url)
    qr_buffer = io.BytesIO()
    qr.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    pdf.drawImage(ImageReader(qr_buffer), 20 * mm, y - 38 * mm, width=34 * mm, height=34 * mm, mask="auto")
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(60 * mm, y - 8 * mm, "Verification ID")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(60 * mm, y - 15 * mm, report.public_id)
    _line(pdf, "Scan the QR code or enter this ID on the report verification page.", y - 23 * mm, width=110 * mm)
    pdf.showPage()
    pdf.save()
    response = HttpResponse(stream.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response
