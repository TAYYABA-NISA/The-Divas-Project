"""Strict, two-step CSV/JSON import helpers for examiner-owned data."""
import csv
import io
import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from .models import Enrollment, Examination, Question, QuestionChoice

MAX_IMPORT_BYTES = 2 * 1024 * 1024
QUESTION_COLUMNS = {"category", "difficulty", "question_type", "prompt", "default_marks", "choices"}
CANDIDATE_COLUMNS = {"username", "first_name", "last_name", "email"}


def _error(row, message):
    return {"row": row, "message": message}


def _read_upload(upload):
    if upload.size > MAX_IMPORT_BYTES:
        raise ValidationError("Imports are limited to 2 MB.")
    try:
        raw = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("Use UTF-8 encoded CSV or JSON files.")
    if not raw.strip():
        raise ValidationError("The import file is empty.")
    if upload.name.lower().endswith(".json"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON: {exc.msg}.")
        rows = payload.get("records") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValidationError("JSON must be a list of record objects or an object with a records list.")
        return rows
    try:
        return list(csv.DictReader(io.StringIO(raw)))
    except csv.Error as exc:
        raise ValidationError(f"Invalid CSV: {exc}.")


def _choices(value):
    if isinstance(value, list):
        choices = value
    else:
        choices = []
        for item in str(value or "").split(";"):
            if not item.strip():
                continue
            try:
                text, correct = item.rsplit("|", 1)
            except ValueError:
                raise ValueError("choices must use text|true or text|false, separated by semicolons.")
            choices.append({"text": text.strip(), "is_correct": correct.strip().lower() == "true"})
    if not all(isinstance(choice, dict) and choice.get("text") for choice in choices):
        raise ValueError("Each choice needs text.")
    return [{"text": str(choice["text"]).strip(), "is_correct": bool(choice.get("is_correct"))} for choice in choices]


def preview_questions(upload):
    rows, errors, clean = _read_upload(upload), [], []
    seen = set()
    for number, row in enumerate(rows, 2):
        missing = [field for field in QUESTION_COLUMNS if not str(row.get(field, "")).strip()]
        if missing:
            errors.append(_error(number, f"Missing required value(s): {', '.join(sorted(missing))}.")); continue
        try:
            difficulty = str(row["difficulty"]).upper()
            question_type = str(row["question_type"]).upper()
            if difficulty not in Question.Difficulty.values:
                raise ValueError("difficulty must be EASY, MEDIUM or HARD.")
            if question_type not in Question.Type.values:
                raise ValueError("question_type must be SINGLE, MULTIPLE or WRITTEN.")
            marks = Decimal(str(row["default_marks"]))
            if marks <= 0:
                raise ValueError("default_marks must be greater than zero.")
            choices = _choices(row.get("choices"))
            correct = sum(item["is_correct"] for item in choices)
            if question_type == Question.Type.SINGLE_CHOICE and (len(choices) < 2 or correct != 1):
                raise ValueError("SINGLE questions need two choices and exactly one correct choice.")
            if question_type == Question.Type.MULTIPLE_SELECT and (len(choices) < 2 or correct < 1):
                raise ValueError("MULTIPLE questions need two choices and at least one correct choice.")
            if question_type == Question.Type.WRITTEN and choices:
                raise ValueError("WRITTEN questions cannot have choices.")
            key = (str(row["category"]).strip().lower(), str(row["prompt"]).strip().lower())
            if key in seen:
                raise ValueError("Duplicate category and prompt in this import.")
            seen.add(key)
            clean.append({"category": str(row["category"]).strip(), "difficulty": difficulty, "question_type": question_type,
                          "prompt": str(row["prompt"]).strip(), "default_marks": str(marks), "choices": choices})
        except (ValueError, InvalidOperation) as exc:
            errors.append(_error(number, str(exc)))
    return clean, errors


def preview_candidates(upload):
    rows, errors, clean = _read_upload(upload), [], []
    seen = set()
    for number, row in enumerate(rows, 2):
        username = str(row.get("username", "")).strip()
        if not username:
            errors.append(_error(number, "username is required.")); continue
        if username.lower() in seen:
            errors.append(_error(number, "Duplicate username in this import.")); continue
        seen.add(username.lower())
        email = str(row.get("email", "")).strip()
        if email and "@" not in email:
            errors.append(_error(number, "email must be a valid address.")); continue
        clean.append({"username": username, "first_name": str(row.get("first_name", "")).strip(),
                      "last_name": str(row.get("last_name", "")).strip(), "email": email})
    existing = set(User.objects.filter(username__in=[r["username"] for r in clean]).values_list("username", flat=True))
    for row in clean:
        if row["username"] in existing:
            errors.append(_error(row["username"], "That username already exists; use enrollment instead."))
    return clean, errors


@transaction.atomic
def commit_questions(*, examiner, records):
    created = []
    for record in records:
        question = Question.objects.create(author=examiner, **{key: record[key] for key in ("category", "difficulty", "question_type", "prompt", "default_marks")})
        QuestionChoice.objects.bulk_create([QuestionChoice(question=question, position=index, **choice) for index, choice in enumerate(record["choices"], 1)])
        created.append(question)
    return created


@transaction.atomic
def commit_candidates(*, examination, records):
    if examination.state != Examination.State.DRAFT:
        raise ValidationError("Candidates can be bulk-enrolled only while the examination is a draft.")
    candidates = []
    for record in records:
        user = User.objects.create_user(password=None, role=User.Role.CANDIDATE, **record)
        Enrollment.objects.create(examination=examination, candidate=user)
        candidates.append(user)
    return candidates
