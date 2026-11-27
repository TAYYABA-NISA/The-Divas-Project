from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Question(models.Model):
    class Type(models.TextChoices):
        SINGLE_CHOICE = "SINGLE", "Single-answer MCQ"
        MULTIPLE_SELECT = "MULTIPLE", "Multiple-select"
        WRITTEN = "WRITTEN", "Written response"

    class Difficulty(models.TextChoices):
        EASY = "EASY", "Easy"
        MEDIUM = "MEDIUM", "Medium"
        HARD = "HARD", "Hard"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="authored_questions"
    )
    category = models.CharField(max_length=100)
    difficulty = models.CharField(max_length=10, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    question_type = models.CharField(max_length=10, choices=Type.choices)
    prompt = models.TextField()
    default_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("1.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("category", "difficulty", "id")

    def clean(self):
        if self.default_marks <= 0:
            raise ValidationError({"default_marks": "Marks must be greater than zero."})

    def __str__(self):
        return self.prompt[:80]


class QuestionChoice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")

    def __str__(self):
        return self.text


class Examination(models.Model):
    class State(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ONGOING = "ONGOING", "Ongoing"
        COMPLETED = "COMPLETED", "Completed"

    class MultipleSelectScheme(models.TextChoices):
        ALL_OR_NOTHING = "ALL_OR_NOTHING", "All or nothing"
        PARTIAL = "PARTIAL", "Partial credit (wrong choices cancel correct ones)"

    examiner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="examinations"
    )
    title = models.CharField(max_length=200)
    instructions = models.TextField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField()
    total_marks = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    state = models.CharField(max_length=10, choices=State.choices, default=State.DRAFT)
    randomize_questions = models.BooleanField(default=False)
    randomize_choices = models.BooleanField(default=False)
    multiple_select_scheme = models.CharField(
        max_length=14, choices=MultipleSelectScheme.choices, default=MultipleSelectScheme.ALL_OR_NOTHING,
    )
    results_published = models.BooleanField(default=False)
    results_published_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-starts_at", "title")

    def clean(self):
        errors = {}
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "The examination must end after it starts."
        if self.duration_minutes <= 0:
            errors["duration_minutes"] = "Duration must be greater than zero."
        if self.total_marks < 0:
            errors["total_marks"] = "Total marks cannot be negative."
        if errors:
            raise ValidationError(errors)

    def is_available_to(self, candidate, now=None):
        now = now or timezone.now()
        return (
            self.state in {self.State.PUBLISHED, self.State.ONGOING}
            and self.starts_at <= now < self.ends_at
            and self.enrollments.filter(candidate=candidate).exists()
        )

    def current_state(self, now=None):
        now = now or timezone.now()
        if self.state == self.State.PUBLISHED and self.starts_at <= now < self.ends_at:
            return self.State.ONGOING
        if self.state in {self.State.PUBLISHED, self.State.ONGOING} and now >= self.ends_at:
            return self.State.COMPLETED
        return self.state

    def attempt_deadline(self, started_at):
        return min(started_at + timedelta(minutes=self.duration_minutes), self.ends_at)

    def __str__(self):
        return self.title


class ExaminationQuestion(models.Model):
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="exam_questions")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="exam_assignments")
    position = models.PositiveIntegerField(default=0)
    marks = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("examination", "question"), name="unique_question_per_exam"),
        ]

    @property
    def assigned_marks(self):
        return self.marks if self.marks is not None else self.question.default_marks

    def clean(self):
        if self.marks is not None and self.marks <= 0:
            raise ValidationError({"marks": "Marks must be greater than zero."})


class ExamBlueprint(models.Model):
    """Difficulty ratio used to draw a different question set for every candidate."""

    examination = models.OneToOneField(Examination, on_delete=models.CASCADE, related_name="blueprint")
    category = models.CharField(max_length=100, blank=True)
    easy_count = models.PositiveIntegerField(default=0)
    medium_count = models.PositiveIntegerField(default=0)
    hard_count = models.PositiveIntegerField(default=0)
    easy_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("1.00"))
    medium_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("2.00"))
    hard_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("3.00"))
    # Eligible question ids, frozen at publication so later bank edits cannot change the draw pool.
    frozen_pool = models.JSONField(default=list, blank=True)

    def counts(self):
        return {
            Question.Difficulty.EASY: self.easy_count,
            Question.Difficulty.MEDIUM: self.medium_count,
            Question.Difficulty.HARD: self.hard_count,
        }

    def marks_for(self, difficulty):
        return {
            Question.Difficulty.EASY: self.easy_marks,
            Question.Difficulty.MEDIUM: self.medium_marks,
            Question.Difficulty.HARD: self.hard_marks,
        }[difficulty]

    @property
    def total_drawn(self):
        return self.easy_count + self.medium_count + self.hard_count

    @property
    def total_marks(self):
        return sum((self.marks_for(d) * n for d, n in self.counts().items()), Decimal("0.00"))

    def clean(self):
        errors = {}
        for field in ("easy_marks", "medium_marks", "hard_marks"):
            value = getattr(self, field)
            if value is not None and value <= 0:
                errors[field] = "Marks must be greater than zero."
        if errors:
            raise ValidationError(errors)


class Enrollment(models.Model):
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="enrollments")
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="exam_enrollments"
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("examination", "candidate"), name="unique_exam_enrollment"),
        ]

    def clean(self):
        if not self.candidate.is_candidate:
            raise ValidationError({"candidate": "Only candidate accounts can be enrolled."})


class RealAttemptManager(models.Manager):
    """Default attempt manager for real examination data only."""

    def get_queryset(self):
        return super().get_queryset().filter(is_sandbox=False)


class Attempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        SUBMITTED = "SUBMITTED", "Submitted"
        EXPIRED = "EXPIRED", "Expired"

    examination = models.ForeignKey(Examination, on_delete=models.PROTECT, related_name="attempts")
    candidate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attempts")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    total_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    total_marks = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    draw_seed = models.BigIntegerField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    is_sandbox = models.BooleanField(default=False)
    scratchpad = models.TextField(blank=True)
    scratchpad_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = RealAttemptManager()
    all_objects = models.Manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("examination", "candidate"),
                condition=models.Q(is_sandbox=False),
                name="one_real_attempt_per_candidate_per_exam",
            ),
        ]

    def can_accept_answers(self, now=None):
        now = now or timezone.now()
        # The deadline is exclusive: an answer must reach the server before it.
        return self.status == self.Status.IN_PROGRESS and now < self.expires_at


class AttemptQuestion(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="attempt_questions")
    source_assignment = models.ForeignKey(ExaminationQuestion, on_delete=models.PROTECT, null=True, blank=True)
    source_question = models.ForeignKey(
        Question, on_delete=models.PROTECT, null=True, blank=True, related_name="attempt_uses"
    )
    difficulty = models.CharField(max_length=10, blank=True)
    position = models.PositiveIntegerField()
    prompt = models.TextField()
    question_type = models.CharField(max_length=10, choices=Question.Type.choices)
    marks = models.DecimalField(max_digits=7, decimal_places=2)
    choices_snapshot = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("attempt", "position"), name="unique_attempt_question_position"),
        ]


class AttemptAnswer(models.Model):
    attempt_question = models.OneToOneField(AttemptQuestion, on_delete=models.CASCADE, related_name="answer")
    selected_choice_ids = models.JSONField(default=list, blank=True)
    written_response = models.TextField(blank=True)
    marked_for_review = models.BooleanField(default=False)
    awarded_marks = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    grader_feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="graded_answers"
    )
    graded_at = models.DateTimeField(null=True, blank=True)
    client_seq = models.BigIntegerField(default=0)
    saved_at = models.DateTimeField(auto_now=True)


class UserPreference(models.Model):
    """Candidate-controlled workspace settings, stored per user rather than per device."""

    class FontSize(models.TextChoices):
        SMALL = "SMALL", "Small"
        NORMAL = "NORMAL", "Normal"
        LARGE = "LARGE", "Large"

    class Theme(models.TextChoices):
        STANDARD = "STANDARD", "Standard"
        HIGH_CONTRAST = "HIGH_CONTRAST", "High contrast"

    class PalettePosition(models.TextChoices):
        RIGHT = "RIGHT", "Right side"
        TOP = "TOP", "Above question"

    class Density(models.TextChoices):
        COMFORTABLE = "COMFORTABLE", "Comfortable"
        COMPACT = "COMPACT", "Compact"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_preference")
    font_size = models.CharField(max_length=8, choices=FontSize.choices, default=FontSize.NORMAL)
    theme = models.CharField(max_length=16, choices=Theme.choices, default=Theme.STANDARD)
    palette_position = models.CharField(max_length=8, choices=PalettePosition.choices, default=PalettePosition.RIGHT)
    density = models.CharField(max_length=12, choices=Density.choices, default=Density.COMFORTABLE)
    updated_at = models.DateTimeField(auto_now=True)


class VerifiedReport(models.Model):
    """A short-lived public verification record; PDFs are rendered on demand."""

    class Type(models.TextChoices):
        CANDIDATE_RESULT = "CANDIDATE_RESULT", "Candidate result"
        EXAMINATION_SUMMARY = "EXAMINATION_SUMMARY", "Examination summary"

    class Status(models.TextChoices):
        VALID = "VALID", "Valid"
        REVOKED = "REVOKED", "Revoked"
        SUPERSEDED = "SUPERSEDED", "Superseded"

    public_id = models.CharField(max_length=64, unique=True, db_index=True)
    report_type = models.CharField(max_length=24, choices=Type.choices)
    attempt = models.ForeignKey(Attempt, null=True, blank=True, on_delete=models.CASCADE, related_name="verified_reports")
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="verified_reports")
    data_hash = models.CharField(max_length=64)
    issued_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.VALID)

    class Meta:
        ordering = ("-issued_at",)

    def clean(self):
        if self.report_type == self.Type.CANDIDATE_RESULT and self.attempt_id is None:
            raise ValidationError({"attempt": "Candidate result reports require an attempt."})
        if self.attempt_id and self.attempt.examination_id != self.examination_id:
            raise ValidationError({"attempt": "The attempt must belong to this examination."})


class ExaminationEvent(models.Model):
    class Type(models.TextChoices):
        ANNOUNCEMENT = "ANNOUNCEMENT", "Announcement"
        INCIDENT = "INCIDENT", "Incident"

    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="events")
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="events", null=True, blank=True)
    event_type = models.CharField(max_length=15, choices=Type.choices)
    message = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
