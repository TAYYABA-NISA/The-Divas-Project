from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.dashboard_redirect, name="dashboard"),
    path("profile-photo/", views.profile_photo, name="profile-photo"),
]
