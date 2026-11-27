from django.urls import path

from . import views

app_name = "proctoring"

urlpatterns = [
    path("candidate/attempts/<int:attempt_id>/monitoring-consent/", views.consent, name="consent"),
    path("examiner/attempts/<int:attempt_id>/proctoring/", views.event_timeline, name="event-timeline"),
    path("examiner/proctoring/events/<int:event_id>/decision/", views.decide_event, name="decide-event"),
    path("examiner/proctoring/clips/<int:clip_id>/", views.private_clip, name="private-clip"),
    path("api/proctoring/profile-photo/", views.agent_profile_photo, name="agent-profile-photo"),
    path("api/proctoring/events/", views.agent_event, name="agent-event"),
    path("api/proctoring/baseline/", views.agent_baseline, name="agent-baseline"),
    path("api/proctoring/clips/", views.agent_clip, name="agent-clip"),
]
