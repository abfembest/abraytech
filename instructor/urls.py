from django.urls import path
from . import views

app_name = 'instructor'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Course Management
    path('courses/', views.course_list, name='course_list'),
    # path('courses/create/', views.course_create, name='course_create'),
    path('courses/<slug:slug>/edit/', views.course_edit, name='course_edit'),
    path('courses/<slug:slug>/objectives/', views.course_objectives, name='course_objectives'),
    path('courses/<slug:slug>/delete/', views.course_delete, name='course_delete'),
    
    # Section Management
    path('courses/<slug:course_slug>/sections/create/', views.section_create, name='section_create'),
    path('courses/<slug:course_slug>/sections/<int:section_id>/edit/', views.section_edit, name='section_edit'),
    path('courses/<slug:course_slug>/sections/<int:section_id>/delete/', views.section_delete, name='section_delete'),
    
    # Lesson Management
    path('courses/<slug:course_slug>/lessons/', views.lesson_list, name='lesson_list'),
    path('courses/<slug:course_slug>/lessons/create/', views.lesson_create, name='lesson_create'),
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/edit/', views.lesson_edit, name='lesson_edit'),
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/delete/', views.lesson_delete, name='lesson_delete'),
    
    # Quiz Management
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/', views.quiz_list, name='quiz_list'),
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/create/', views.quiz_create, name='quiz_create'),
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/<slug:quiz_slug>/edit/', views.quiz_edit, name='quiz_edit'),
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/<slug:quiz_slug>/questions/', views.quiz_questions, name='quiz_questions'),
    
    # Question Management
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/<slug:quiz_slug>/questions/create/', views.question_create, name='question_create'),
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/<slug:quiz_slug>/questions/<int:question_id>/answers/', views.question_answers, name='question_answers'),
    
    # Assignment Management
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/assignments/', views.assignment_list, name='assignment_list'),
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/assignments/create/', views.assignment_create, name='assignment_create'),
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/assignments/<slug:assignment_slug>/edit/', views.assignment_edit, name='assignment_edit'),
    path('courses/<slug:course_slug>/assignments/<slug:assignment_slug>/submissions/', views.assignment_submissions, name='assignment_submissions'),
    path('courses/<slug:course_slug>/submissions/<int:submission_id>/grade/', views.grade_submission, name='grade_submission'),
    
    # Student Management
    path('courses/<slug:course_slug>/students/', views.students_list, name='students_list'),
    path('courses/<slug:course_slug>/students/<int:student_id>/progress/', views.student_progress, name='student_progress'),
    path('courses/<slug:course_slug>/students/enroll/', views.enroll_student, name='enroll_student'),
    
    # Announcements
    path('courses/<slug:course_slug>/announcements/create/', views.announcement_create, name='announcement_create'),

    # ==================== ASSESSMENT OVERVIEWS ====================
    path('assessments/quizzes/', views.all_quizzes, name='all_quizzes'),
    path('assessments/assignments/', views.all_assignments, name='all_assignments'),

    # Quiz Question Answer Delete (add after question_answers line)
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/<slug:quiz_slug>/questions/<int:question_id>/answers/<int:answer_id>/delete/', 
        views.delete_answer, 
        name='delete_answer'),

    # Quiz Question Delete (add after question_create line)
    path('courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/<slug:quiz_slug>/questions/<int:question_id>/delete/', 
        views.delete_question, 
        name='delete_question'),

    # ==================== ANALYTICS & REPORTS ====================
    path('analytics/courses/', 
        views.course_statistics, 
        name='analytics_course_stats'),

    path('analytics/students/', 
        views.student_analytics_progress, 
        name='analytics_student_progress'),

    path('analytics/reviews/', 
        views.reviews_ratings, 
        name='analytics_reviews'),

    path('resources/', views.resources, name='resources'),

    # ==================== PROFILE & SETTINGS ====================
    path('profile/', views.instructor_profile, name='profile'),
    path('settings/', views.instructor_settings, name='settings'),
    path('help-support/', views.help_support, name='help_support'),

    # ------------------------------------------------------------------
    # ANNOUNCEMENTS  (list / edit / delete — create already exists)
    # ------------------------------------------------------------------
    path(
        'courses/<slug:course_slug>/announcements/',
        views.announcement_list,
        name='announcement_list',
    ),
    path(
        'courses/<slug:course_slug>/announcements/<slug:announcement_slug>/edit/',
        views.announcement_edit,
        name='announcement_edit',
    ),
    path(
        'courses/<slug:course_slug>/announcements/<slug:announcement_slug>/delete/',
        views.announcement_delete,
        name='announcement_delete',
    ),

    # ------------------------------------------------------------------
    # QUIZ RESULTS  (attempt list + single attempt breakdown)
    # ------------------------------------------------------------------
    path(
        'courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/<slug:quiz_slug>/results/',
        views.quiz_results,
        name='quiz_results',
    ),
    path(
        'courses/<slug:course_slug>/lessons/<slug:lesson_slug>/quizzes/<slug:quiz_slug>/results/<int:attempt_id>/',
        views.quiz_attempt_detail,
        name='quiz_attempt_detail',
    ),

    # ------------------------------------------------------------------
    # NOTIFICATIONS
    # ------------------------------------------------------------------
    path(
        'notifications/',
        views.instructor_notifications,
        name='notifications',
    ),
    path(
        'notifications/<int:notif_id>/read/',
        views.instructor_notification_read,
        name='notification_read',
    ),

    # ------------------------------------------------------------------
    # MESSAGES  (inbox / sent / thread / compose / reply / mark-all-read)
    # ------------------------------------------------------------------
    path(
        'messages/',
        views.messages_inbox,
        name='messages_inbox',
    ),
    path(
        'messages/sent/',
        views.messages_sent,
        name='messages_sent',
    ),
    path(
        'messages/compose/',
        views.message_compose,
        name='message_compose',
    ),
    path(
        'messages/<int:message_id>/',
        views.message_thread,
        name='message_thread',
    ),
    path(
        'messages/<int:message_id>/reply/',
        views.message_reply,
        name='message_reply',
    ),
    path(
        'messages/mark-all-read/',
        views.messages_mark_all_read,
        name='messages_mark_all_read',
    ),

    # ------------------------------------------------------------------
    # DISCUSSIONS  (list / detail / reply / pin / lock / delete + reply actions)
    # ------------------------------------------------------------------
    path(
        'courses/<slug:course_slug>/discussions/',
        views.discussions,
        name='discussions',
    ),
    path(
        'courses/<slug:course_slug>/discussions/<slug:discussion_slug>/',
        views.discussion_detail,
        name='discussion_detail',
    ),
    path(
        'courses/<slug:course_slug>/discussions/<slug:discussion_slug>/reply/',
        views.discussion_reply,
        name='discussion_reply',
    ),
    path(
        'courses/<slug:course_slug>/discussions/<slug:discussion_slug>/pin/',
        views.discussion_toggle_pin,
        name='discussion_toggle_pin',
    ),
    path(
        'courses/<slug:course_slug>/discussions/<slug:discussion_slug>/lock/',
        views.discussion_toggle_lock,
        name='discussion_toggle_lock',
    ),
    path(
        'courses/<slug:course_slug>/discussions/<slug:discussion_slug>/delete/',
        views.discussion_delete,
        name='discussion_delete',
    ),
    path(
        'courses/<slug:course_slug>/discussions/<slug:discussion_slug>/replies/<int:reply_id>/solution/',
        views.reply_toggle_solution,
        name='reply_toggle_solution',
    ),
    path(
        'courses/<slug:course_slug>/discussions/<slug:discussion_slug>/replies/<int:reply_id>/delete/',
        views.reply_delete,
        name='reply_delete',
    ),

    path(
        'assessments/create/',
        views.create_assessment,
        name='create_assessment',
    ),
 
    # AJAX helpers for the create assessment page
    path(
        'assessments/course-details/',
        views.ajax_course_details,
        name='ajax_course_details',
    ),
    path(
        'assessments/course-lessons/',
        views.ajax_course_lessons,
        name='ajax_course_lessons',
    ),

    # ------------------------------------------------------------------
    # EXAM MANAGEMENT
    # ------------------------------------------------------------------
    path(
        'exams/',
        views.exam_list,
        name='exam_list',
    ),
    path(
        'exams/<slug:slug>/',
        views.exam_detail,
        name='exam_detail',
    ),
    path(
        'exams/<slug:slug>/update/',
        views.exam_update,
        name='exam_update',
    ),
    path(
        'exams/<slug:slug>/submit/',
        views.exam_submit,
        name='exam_submit',
    ),
    path(
        'exams/<slug:slug>/publish/',
        views.exam_publish,
        name='exam_publish',
    ),
    path(
        'exams/<slug:slug>/questions/create/',
        views.exam_question_create,
        name='exam_question_create',
    ),
    path(
        'exams/<slug:slug>/questions/<int:question_id>/edit/',
        views.exam_question_edit,
        name='exam_question_edit',
    ),
    path(
        'exams/<slug:slug>/questions/<int:question_id>/delete/',
        views.exam_question_delete,
        name='exam_question_delete',
    ),
    path(
        'exams/<slug:slug>/questions/import/',
        views.exam_import_questions,
        name='exam_import_questions',
    ),

    path(
        'exams/<slug:slug>/responses/<int:response_id>/grade/',
        views.exam_grade_response,
        name='exam_grade_response',
    ),

    path('courses/<slug:slug>/manage/', views.course_manage, name='course_manage'),
    path('manage/', views.course_manage_default, name='course_manage_default'),


]