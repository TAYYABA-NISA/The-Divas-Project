from django import forms
from django.forms import inlineformset_factory

from .models import (
    Attempt, Enrollment, ExamBlueprint, Examination, ExaminationQuestion, Question, QuestionChoice,
    UserPreference,
)


class ExaminationForm(forms.ModelForm):
    class Meta:
        model = Examination
        fields = (
            "title", "instructions", "starts_at", "ends_at", "duration_minutes", "total_marks",
            "randomize_questions", "randomize_choices", "multiple_select_scheme",
        )
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "instructions": forms.Textarea(attrs={"rows": 6}),
        }


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ("category", "difficulty", "question_type", "prompt", "default_marks")
        widgets = {"prompt": forms.Textarea(attrs={"rows": 5})}


QuestionChoiceFormSet = inlineformset_factory(
    Question, QuestionChoice, fields=("text", "is_correct", "position"), extra=4, can_delete=True,
)


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ("candidate",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["candidate"].queryset = self.fields["candidate"].queryset.filter(role="CANDIDATE")


class ExamQuestionAssignmentForm(forms.Form):
    questions = forms.ModelMultipleChoiceField(queryset=Question.objects.none(), widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, examiner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["questions"].queryset = Question.objects.filter(author=examiner).order_by("category", "id")


class BlueprintForm(forms.ModelForm):
    class Meta:
        model = ExamBlueprint
        fields = ("category", "easy_count", "medium_count", "hard_count", "easy_marks", "medium_marks", "hard_marks")

    def clean(self):
        cleaned = super().clean()
        if sum(cleaned.get(field) or 0 for field in ("easy_count", "medium_count", "hard_count")) == 0:
            raise forms.ValidationError("Request at least one question in the blueprint, or remove it.")
        return cleaned


class GradeForm(forms.Form):
    marks = forms.DecimalField(min_value=0, max_digits=7, decimal_places=2)
    feedback = forms.CharField(required=False, max_length=1000, widget=forms.Textarea(attrs={"rows": 2}))


class AnnouncementForm(forms.Form):
    message = forms.CharField(label="Announcement", max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


class IncidentForm(forms.Form):
    attempt = forms.ModelChoiceField(queryset=Attempt.objects.none(), required=False, label="Candidate (optional)", empty_label="Whole examination")
    message = forms.CharField(label="Observation", max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, exam, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attempt"].queryset = Attempt.objects.filter(examination=exam).select_related("candidate")
        self.fields["attempt"].label_from_instance = lambda a: a.candidate.get_full_name() or a.candidate.username


class WorkspacePreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = ("font_size", "theme", "palette_position", "density")


class BulkImportForm(forms.Form):
    kind = forms.ChoiceField(choices=(("questions", "Questions"), ("candidates", "Candidates")))
    examination = forms.ModelChoiceField(queryset=Examination.objects.none(), required=False)
    file = forms.FileField(help_text="Upload UTF-8 CSV or JSON, up to 2 MB.")

    def __init__(self, *args, examiner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["examination"].queryset = Examination.objects.filter(examiner=examiner, state=Examination.State.DRAFT)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == "candidates" and not cleaned.get("examination"):
            self.add_error("examination", "Choose the draft examination to enroll imported candidates into.")
        return cleaned
