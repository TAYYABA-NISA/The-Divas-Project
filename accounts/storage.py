import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateProfileStorage(FileSystemStorage):
    """Keep enrolled reference photos outside publicly served media."""

    @property
    def location(self):
        return str(getattr(settings, "PROCTOR_PROFILE_ROOT", Path(settings.BASE_DIR) / "private_profile_photos"))


PRIVATE_PROFILE_STORAGE = PrivateProfileStorage()


def private_profile_photo_path(instance, filename):
    suffix = Path(filename).suffix.lower()[:10] or ".jpg"
    return f"profiles/{instance.pk or 'new'}/{uuid.uuid4().hex}{suffix}"
