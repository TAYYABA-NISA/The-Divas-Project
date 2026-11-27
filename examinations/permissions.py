from functools import wraps

from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required


def role_required(*roles):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.is_superuser or request.user.role in roles:
                return view(request, *args, **kwargs)
            raise PermissionDenied("You do not have permission to perform this action.")

        return wrapped

    return decorator
