from django.contrib import admin

from .models import (
    Attempt,
    AttemptAnswer,
    AttemptQuestion,
    Enrollment,
    Examination,
    ExaminationEvent,
    ExaminationQuestion,
    Question,
    QuestionChoice,
)


class QuestionChoiceInline(admin.TabularInline):
    model = QuestionChoice
    extra = 2


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "difficulty", "question_type", "default_marks", "author")
    list_filter = ("category", "difficulty", "question_type")
    search_fields = ("prompt",)
    inlines = (QuestionChoiceInline,)


class ExaminationQuestionInline(admin.TabularInline):
    model = ExaminationQuestion
    extra = 1


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0


@admin.register(Examination)
class ExaminationAdmin(admin.ModelAdmin):
    list_display = ("title", "examiner", "state", "starts_at", "ends_at", "results_published")
    list_filter = ("state", "results_published")
    search_fields = ("title", "examiner__username")
    inlines = (ExaminationQuestionInline, EnrollmentInline)


class AttemptQuestionInline(admin.TabularInline):
    model = AttemptQuestion
    extra = 0
    readonly_fields = ("position", "prompt", "question_type", "marks", "choices_snapshot")
    can_delete = False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("examination", "candidate", "status", "started_at", "expires_at", "total_score")
    list_filter = ("status", "examination")
    readonly_fields = ("started_at", "expires_at", "submitted_at", "total_score")
    inlines = (AttemptQuestionInline,)


admin.site.register(AttemptAnswer)
admin.site.register(ExaminationEvent)
