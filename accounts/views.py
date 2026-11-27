from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def dashboard_redirect(request):
    if request.user.is_administrator:
        return redirect("admin:index")
    if request.user.is_examiner:
        return redirect("examinations:exam-list")
    return redirect("examinations:candidate-dashboard")
