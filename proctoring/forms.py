from django import forms

from .models import ReviewDecision


class ConsentForm(forms.Form):
    consent = forms.BooleanField(
        label="I understand and consent to the advisory monitoring described above."
    )


class ReviewDecisionForm(forms.ModelForm):
    class Meta:
        model = ReviewDecision
        fields = ("decision", "note")
        widgets = {"note": forms.Textarea(attrs={"rows": 4})}

    def clean_note(self):
        note = self.cleaned_data["note"].strip()
        if not note:
            raise forms.ValidationError("Explain why you accepted or dismissed this advisory flag.")
        return note
