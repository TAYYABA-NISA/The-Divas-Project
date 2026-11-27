from django.urls import path

from . import views

app_name = "examinations"

urlpatterns = [
    path("examiner/examinations/", views.exam_list, name="exam-list"),
    path("examiner/examinations/create/", views.exam_create, name="exam-create"),
    path("examiner/examinations/<int:exam_id>/", views.exam_detail, name="exam-detail"),
    path("examiner/examinations/<int:exam_id>/publish/", views.exam_publish, name="exam-publish"),
    path("examiner/examinations/<int:exam_id>/enroll/", views.enroll_candidate, name="exam-enroll"),
    path("examiner/examinations/<int:exam_id>/questions/", views.assign_questions, name="exam-questions"),
    path("examiner/examinations/<int:exam_id>/blueprint/", views.exam_blueprint, name="exam-blueprint"),
    path("examiner/examinations/<int:exam_id>/monitor/", views.exam_monitor, name="exam-monitor"),
    path("examiner/examinations/<int:exam_id>/announce/", views.exam_announce, name="exam-announce"),
    path("examiner/examinations/<int:exam_id>/incident/", views.exam_incident, name="exam-incident"),
    path("examiner/examinations/<int:exam_id>/grading/", views.exam_grading, name="exam-grading"),
    path("examiner/examinations/<int:exam_id>/grading/<int:attempt_id>/", views.attempt_grading, name="attempt-grading"),
    path("examiner/examinations/<int:exam_id>/publish-results/", views.exam_publish_results, name="exam-publish-results"),
    path("examiner/examinations/<int:exam_id>/analytics/", views.exam_analytics_view, name="exam-analytics"),
    path("examiner/examinations/<int:exam_id>/analytics.csv", views.exam_analytics_csv, name="exam-analytics-csv"),
    path("examiner/examinations/<int:exam_id>/sandbox/", views.sandbox_start, name="sandbox-start"),
    path("examiner/examinations/<int:exam_id>/summary-report/", views.examiner_summary_report, name="examiner-summary-report"),
    path("examiner/import/", views.bulk_import, name="bulk-import"),
    path("examiner/import/template/<str:kind>/", views.import_template, name="import-template"),
    path("examiner/questions/", views.question_list, name="question-list"),
    path("examiner/questions/create/", views.question_create, name="question-create"),
    path("examiner/questions/<int:question_id>/edit/", views.question_edit, name="question-edit"),
    path("examiner/questions/<int:question_id>/delete/", views.question_delete, name="question-delete"),
    path("candidate/examinations/", views.candidate_dashboard, name="candidate-dashboard"),
    path("candidate/examinations/<int:exam_id>/start/", views.candidate_start_attempt, name="candidate-start"),
    path("candidate/attempts/<int:attempt_id>/question/<int:position>/", views.attempt_workspace, name="attempt-workspace"),
    path("candidate/attempts/<int:attempt_id>/question/<int:position>/save/", views.save_attempt_answer, name="attempt-save-answer"),
    path("candidate/attempts/<int:attempt_id>/poll/", views.attempt_poll, name="attempt-poll"),
    path("candidate/results/<int:attempt_id>/", views.candidate_result, name="candidate-result"),
    path("candidate/results/<int:attempt_id>/report/", views.candidate_result_report, name="candidate-result-report"),
    path("candidate/attempts/<int:attempt_id>/preferences/", views.workspace_preferences, name="workspace-preferences"),
    path("candidate/attempts/<int:attempt_id>/scratchpad/", views.save_scratchpad_view, name="scratchpad-save"),
    path("verify/", views.verify_report, name="verify-lookup"),
    path("verify/<str:public_id>/", views.verify_report, name="verify-report"),
    path("candidate/attempts/<int:attempt_id>/review/", views.attempt_review, name="attempt-review"),
    path("candidate/attempts/<int:attempt_id>/submit/", views.submit_attempt, name="attempt-submit"),
]
