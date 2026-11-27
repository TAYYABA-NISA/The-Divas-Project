from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.forms import RoleAuthenticationForm

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(authentication_form=RoleAuthenticationForm), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("accounts.urls")),
    path("", include("examinations.urls")),
    path("", include("proctoring.urls")),
]
