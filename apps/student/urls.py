from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'students'

urlpatterns = [
    # ── Dashboard ────────────────────────────────────────────────────────────
    path('', views.dashboard, name='dashboard'),

    # ── Courses ──────────────────────────────────────────────────────────────
    path('courses/', views.my_courses, name='my_courses'),
    path('courses/catalog/', views.course_catalog, name='course_catalog'),
    path('courses/semester-register-all/', views.register_all_semester_courses, name='register_all_semester_courses'),
    path('courses/<slug:course_slug>/semester-register/', views.register_semester_course, name='register_semester_course'),
    path('courses/<slug:course_slug>/semester-drop/', views.drop_semester_course, name='drop_semester_course'),
    path('courses/<slug:course_slug>/', views.course_detail, name='course_detail'),
    path('courses/<slug:course_slug>/enroll/', views.enroll_course, name='enroll_course'),
    path('courses/<slug:course_slug>/review/', views.submit_review, name='submit_review'),  # NEW
    path('courses/<slug:course_slug>/retry-lms-enrollment/', views.retry_lms_enrollment, name='retry_lms_enrollment'),

    # ── Lessons ──────────────────────────────────────────────────────────────
    path(
        'courses/<slug:course_slug>/lessons/<slug:lesson_slug>/',
        views.lesson_view, name='lesson_view',
    ),
    path(
        'courses/<slug:course_slug>/lessons/<slug:lesson_slug>/complete/',
        views.mark_lesson_complete, name='mark_lesson_complete',
    ),

    # ── Assignments ──────────────────────────────────────────────────────────
    path('assignments/', views.assignments, name='assignments'),
    path(
        'courses/<slug:course_slug>/assignments/<slug:assignment_slug>/',
        views.assignment_detail, name='assignment_detail',
    ),
    path(
        'courses/<slug:course_slug>/assignments/<slug:assignment_slug>/submit/',
        views.submit_assignment, name='submit_assignment',
    ),

    # ── Quizzes ──────────────────────────────────────────────────────────────
    path('quizzes/', views.quiz_list, name='quiz_list'),
    path('exam/', views.exam_list, name='exam_list'),
    path(
        'courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/<slug:quiz_slug>/',
        views.quiz_detail, name='quiz_detail',
    ),
    path(
        'courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/<slug:quiz_slug>/take/',
        views.quiz_take, name='quiz_take',
    ),
    path('quizzes/attempt/<int:attempt_id>/submit/', views.quiz_submit, name='quiz_submit'),
    path('quizzes/attempt/<int:attempt_id>/result/', views.quiz_result, name='quiz_result'),

    # ── Community ────────────────────────────────────────────────────────────
    path('community/', views.community, name='community'),
    path('community/thread/<int:thread_id>/', views.thread_detail, name='thread_detail'),
    path('community/create/', views.create_thread, name='create_thread'),

    # ── Study Groups ─────────────────────────────────────────────────────────
    path('study-groups/', views.study_groups, name='study_groups'),
    path('study-groups/create/', views.create_study_group, name='create_study_group'),  # NEW
    path('study-groups/<int:group_id>/', views.study_group_detail, name='study_group_detail'),
    path('study-groups/<int:group_id>/join/', views.join_study_group, name='join_study_group'),

    # ── Achievements ─────────────────────────────────────────────────────────
    path('achievements/', views.achievements, name='achievements'),

    # ── Grades & Progress ────────────────────────────────────────────────────
    path('grades/', views.grades, name='grades'),
    path('progress/', views.progress, name='progress'),

    # ── Certificates ─────────────────────────────────────────────────────────
    path('certificates/', views.certificates, name='certificates'),
    path('certificates/<str:certificate_id>/print/', views.certificate_print, name='certificate_print'),

    # ── Profile & Settings ───────────────────────────────────────────────────
    # "My Profile", "Settings" and "Help & Support" are now single shared pages
    # for every role — these old URLs redirect there so nothing that still
    # links here breaks.
    path('profile/', RedirectView.as_view(pattern_name='eduweb:profile', permanent=False), name='profile'),
    path('settings/', RedirectView.as_view(pattern_name='eduweb:settings', permanent=False), name='settings'),
    path('help-support/', RedirectView.as_view(pattern_name='support:submit_ticket', permanent=False), name='help_support'),

    # ── Payments ─────────────────────────────────────────────────────────────
    path('payments/', views.my_payments, name='my_payments'),

    path('academic-records/', views.academic_records, name='academic_records'),

    # ── Inbox / Messaging (NEW) ───────────────────────────────────────────────
    path('inbox/', views.inbox, name='inbox'),
    path('inbox/compose/', views.compose_message, name='compose_message'),
    path('inbox/<int:message_id>/', views.message_thread, name='message_thread'),

    # ── Notifications (NEW) ───────────────────────────────────────────────────
    path('notifications/', views.notifications_view, name='notifications_view'),
    path(
        'notifications/<int:notification_id>/read/',
        views.mark_notification_read, name='mark_notification_read', ),


    # ── CBT Examinations ──────────────────────────────────────────────────────
    path('exam/', views.exam_list, name='exam_list'),
    path('exam/<slug:slug>/instructions/', views.exam_instructions, name='exam_instructions'),
    path('exam/<slug:slug>/start/',        views.start_exam,         name='start_exam'),
    path('exam/<slug:slug>/data/',         views.get_exam_data,      name='get_exam_data'),
    path('exam/<slug:slug>/save/',         views.save_answer,        name='save_answer'),
    path('exam/<slug:slug>/flag-tab-switch/', views.flag_tab_switch, name='flag_tab_switch'),
    path('exam/<slug:slug>/submit/',       views.submit_exam,        name='submit_exam'),
]