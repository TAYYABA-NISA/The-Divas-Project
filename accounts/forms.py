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
