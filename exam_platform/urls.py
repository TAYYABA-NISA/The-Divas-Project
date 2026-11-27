from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.forms import RoleAuthenticationForm

handler400 = "exam_platform.error_handlers.bad_request"
handler403 = "exam_platform.error_handlers.permission_denied"
handler404 = "exam_platform.error_handlers.page_not_found"
handler500 = "exam_platform.error_handlers.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(authentication_form=RoleAuthenticationForm),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("accounts.urls")),
    path("", include("examinations.urls")),
    path("", include("proctoring.urls")),
]
