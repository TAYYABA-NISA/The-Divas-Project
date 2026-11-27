from django.contrib.auth.models import AbstractUser
from django.db import models

from .storage import PRIVATE_PROFILE_STORAGE, private_profile_photo_path


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMINISTRATOR = "ADMIN", "Administrator"
        EXAMINER = "EXAMINER", "Examiner"
        CANDIDATE = "CANDIDATE", "Candidate"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CANDIDATE)
    profile_photo = models.FileField(
        storage=PRIVATE_PROFILE_STORAGE,
        upload_to=private_profile_photo_path,
        blank=True,
        help_text="Optional reference image for the advisory identity check.",
    )

    @property
    def is_administrator(self):
        return self.role == self.Role.ADMINISTRATOR or self.is_superuser

    @property
    def is_examiner(self):
        return self.role == self.Role.EXAMINER

    @property
    def is_candidate(self):
        return self.role == self.Role.CANDIDATE
