from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from examinations.permissions import role_required

from .forms import ProfilePhotoForm
from .models import User


@login_required
def dashboard_redirect(request):
    if request.user.is_administrator:
        return redirect("admin:index")
    if request.user.is_examiner:
        return redirect("examinations:exam-list")
    return redirect("examinations:candidate-dashboard")


@role_required(User.Role.CANDIDATE)
def profile_photo(request):
    form = ProfilePhotoForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your private reference photo was updated.")
        return redirect("accounts:profile-photo")
    return render(request, "accounts/profile_photo.html", {"form": form})
