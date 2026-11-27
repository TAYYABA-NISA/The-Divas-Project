from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import User

ROLE_CHOICES = (
    (User.Role.CANDIDATE, "Candidate"),
    (User.Role.EXAMINER, "Examiner"),
    (User.Role.ADMINISTRATOR, "Administrator"),
)


class RoleAuthenticationForm(AuthenticationForm):
    """Sign-in form that also requires the account to hold the selected role.

    A role mismatch gets the same message as a wrong password, so the form
    does not reveal that the username and password were valid.
    """

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        initial=User.Role.CANDIDATE,
        widget=forms.RadioSelect,
        label="Sign in as",
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Please enter a correct username and password for the selected role.",
    }

    def clean(self):
        cleaned = super().clean()
        user = self.get_user()
        role = cleaned.get("role")
        if user is not None and role and not self._has_role(user, role):
            raise self.get_invalid_login_error()
        return cleaned

    @staticmethod
    def _has_role(user, role):
        if role == User.Role.ADMINISTRATOR:
            return user.is_administrator
        if role == User.Role.EXAMINER:
            return user.is_examiner
        return user.is_candidate


class ProfilePhotoForm(forms.ModelForm):
    """Candidate-owned reference photo; used only by the optional local agent."""

    class Meta:
        model = User
        fields = ("profile_photo",)
        widgets = {"profile_photo": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png"})}

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if not photo:
            return photo
        if photo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Reference photos must be 2 MB or smaller.")
        if getattr(photo, "content_type", "") not in {"image/jpeg", "image/png"}:
            raise forms.ValidationError("Upload a JPEG or PNG reference photo.")
        return photo
