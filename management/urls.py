from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

app_name = 'management'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Applications
    path('applications/', views.applications_list, name='applications_list'),
    path('applications/<str:application_id>/', views.application_detail, name='application_detail'),
    
    path('applications/<int:pk>/make-decision/', views.make_decision, name='make_decision'),
    path('applications/<int:pk>/approve-department/', views.approve_department, name='approve_department'),
    path('applications/<int:pk>/issue-transcript/', views.issue_transcript, name='issue_transcript'),

    # Faculties
    path('faculties/', views.faculties_list, name='faculties_list'),
    path('faculties/create/', views.faculty_create, name='faculty_create'),
    path('faculties/<int:pk>/edit/', views.faculty_edit, name='faculty_edit'),
    path('faculties/<int:pk>/delete/', views.faculty_delete, name='faculty_delete'),

    # Departments
    path('departments/', views.departments_list, name='departments_list'),
    path('departments/create/', views.department_create, name='department_create'),
    path('departments/<int:pk>/edit/', views.department_edit, name='department_edit'),
    path('departments/<int:pk>/delete/', views.department_delete, name='department_delete'),

    # Programs
    path('programs/', views.programs_list, name='programs_list'),
    path('programs/create/', views.program_create, name='program_create'),
    path('programs/<int:pk>/', views.program_detail, name='program_detail'),
    path('programs/<int:pk>/edit/', views.program_edit, name='program_edit'),
    path('programs/<int:pk>/delete/', views.program_delete, name='program_delete'),

    # Academic Sessions
    path('academic-sessions/', views.academic_sessions_list, name='academic_sessions_list'),
    path('academic-sessions/<int:pk>/set-current/', views.academic_session_set_current, name='academic_session_set_current'),

    path('courses/', views.courses_list, name='courses_list'),
    path('exams/<slug:slug>/toggle-active/', views.admin_exam_toggle_active, name='admin_exam_toggle_active'),

    # Intakes
    path('intakes/', views.intakes_list, name='intakes_list'),
    path('intakes/create/', views.intake_create, name='intake_create'),
    path('intakes/<int:pk>/edit/', views.intake_edit, name='intake_edit'),
    path('intakes/<int:pk>/delete/', views.intake_delete, name='intake_delete'),

    # Courses (academic)
    # path('courses/', views.courses, name='courses'),
    # path('courses/create/', views.course_create, name='course_create'),
    # path('courses/<int:pk>/', views.course_detail, name='course_detail'),
    # path('courses/<int:pk>/edit/', views.course_edit, name='course_edit'),
    # path('courses/<int:pk>/delete/', views.course_delete, name='course_delete'),

    # Course categories
    path('categories/', views.course_categories_list, name='course_categories_list'),
    # path('categories/create/', views.course_category_create, name='course_category_create'),
    # path('categories/<int:pk>/edit/', views.course_category_edit, name='course_category_edit'),
    # path('categories/<int:pk>/delete/', views.course_category_delete, name='course_category_delete'),

    path('lms-courses/', views.lms_courses_list, name='lms_courses_list'),
    path('lms-courses/save/', views.lms_course_save, name='lms_course_save'),
    path('lms-courses/academic-course-data/<int:pk>/', views.lms_academic_course_data, name='lms_academic_course_data'),
    path('lms-courses/<int:pk>/', views.lms_course_detail, name='lms_course_detail'),
    path('lms-courses/<int:pk>/delete/', views.lms_course_delete, name='lms_course_delete'),

    # Blog
    path('blog/posts/', views.blog_posts_list, name='blog_posts_list'),
    path('blog/posts/create/', views.blog_post_create, name='blog_post_create'),
    path('blog/posts/<int:pk>/edit/', views.blog_post_edit, name='blog_post_edit'),
    path('blog/posts/<int:pk>/delete/', views.blog_post_delete, name='blog_post_delete'),
    path('blog/categories/', views.blog_categories_list, name='blog_categories_list'),
    path('blog/categories/create/', views.blog_category_create, name='blog_category_create'),
    path('blog/categories/<int:pk>/edit/', views.blog_category_edit, name='blog_category_edit'),
    path('blog/categories/<int:pk>/delete/', views.blog_category_delete, name='blog_category_delete'),

    # Users
    path('users/', views.users_list, name='users_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/bulk-action/', views.bulk_user_action, name='bulk_user_action'),
    # path('users/<int:pk>/', views.user_detail, name='user_detail'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    path('users/<int:pk>/change-role/', views.user_change_role, name='user_change_role'),
    path('users/<int:pk>/quick-info/', views.user_quick_info, name='user_quick_info'),

    # System Config
    path('config/', views.system_config_list, name='system_config_list'),
    path('config/create/', views.system_config_create, name='system_config_create'),
    path('config/<int:pk>/edit/', views.system_config_edit, name='system_config_edit'),
    path('config/<int:pk>/delete/', views.system_config_delete, name='system_config_delete'),
    path('config/branding/', views.branding_config, name='branding_config'),
    path('config/email/', views.email_config, name='email_config'),
    path('config/notifications/', views.notification_config, name='notification_config'),

    # Notifications — admin/staff
    path('notifications/', views.notifications_view, name='notifications_view'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),

    # Inbox / Messaging — admin/staff
    path('inbox/', views.admin_inbox, name='admin_inbox'),
    path('inbox/compose/', views.admin_compose_message, name='admin_compose_message'),
    path('inbox/<int:message_id>/', views.admin_message_thread, name='admin_message_thread'),

    # Audit / Security
    path('audit-logs/', views.audit_logs_list, name='audit_logs_list'),
    path('audit-logs/<int:pk>/', views.audit_log_detail, name='audit_log_detail'),
    path('audit-logs/export/', views.audit_logs_export, name='audit_logs_export'),
    path('security/', views.security_dashboard, name='security_dashboard'),

    # Broadcast
    path('broadcast/', views.broadcast_center, name='broadcast_center'),
    path('broadcast/create/', views.broadcast_create, name='broadcast_create'),
    path('broadcast/<slug:slug>/edit/', views.broadcast_edit, name='broadcast_edit'),
    path('broadcast/<slug:slug>/send/', views.broadcast_send, name='broadcast_send'),
    path('broadcast/<slug:slug>/delete/', views.broadcast_delete, name='broadcast_delete'),

    # Tickets
    path('tickets/', views.tickets_list, name='tickets_list'),
    path('tickets/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/<int:pk>/reply/', views.ticket_reply, name='ticket_reply'),
    path('tickets/<int:pk>/change-status/', views.ticket_change_status, name='ticket_change_status'),
    path('tickets/<int:pk>/assign/', views.ticket_assign, name='ticket_assign'),

    # Contact Messages
    path('contact-messages/', views.contact_messages_list, name='contact_messages_list'),
    path('contact-messages/<int:pk>/', views.contact_message_detail, name='contact_message_detail'),
    path('contact-messages/<int:pk>/mark-read/', views.contact_message_mark_read, name='contact_message_mark_read'),
    path('contact-messages/<int:pk>/respond/', views.contact_message_respond, name='contact_message_respond'),

    # Announcements
    path('announcements/', views.announcements_list, name='announcements_list'),
    path('announcements/create/', views.announcement_create, name='announcement_create'),
    path('announcements/<int:pk>/edit/', views.announcement_edit, name='announcement_edit'),
    path('announcements/<int:pk>/delete/', views.announcement_delete, name='announcement_delete'),

    # Enrollments
    path('enrollments/', views.enrollments_list, name='enrollments_list'),
    path('enrollments/create/', views.enrollment_create, name='enrollment_create'),
    path('enrollments/<int:pk>/edit/', views.enrollment_edit, name='enrollment_edit'),
    path('enrollments/<int:pk>/delete/', views.enrollment_delete, name='enrollment_delete'),

    # Reviews
    path('reviews/', views.reviews_list, name='reviews_list'),
    path('reviews/create/', views.review_create, name='review_create'),
    path('reviews/<int:pk>/edit/', views.review_edit, name='review_edit'),
    path('reviews/<int:pk>/delete/', views.review_delete, name='review_delete'),

    # Certificates — use certificate_id (string) not pk
    path('certificates/', views.certificates_list, name='certificates_list'),
    path('certificates/create/', views.certificate_create, name='certificate_create'),
    path('certificates/<str:certificate_id>/edit/', views.certificate_edit, name='certificate_edit'),
    path('certificates/<str:certificate_id>/delete/', views.certificate_delete, name='certificate_delete'),

    # Badges — use slug
    path('badges/', views.badges_list, name='badges_list'),
    path('badges/create/', views.badge_create, name='badge_create'),
    path('badges/<slug:slug>/edit/', views.badge_edit, name='badge_edit'),
    path('badges/<slug:slug>/delete/', views.badge_delete, name='badge_delete'),

    # Student Badges
    path('student-badges/', views.student_badges_list, name='student_badges_list'),
    path('student-badges/assign/', views.student_badge_assign, name='student_badge_assign'),
    path('student-badges/<int:pk>/delete/', views.student_badge_delete, name='student_badge_delete'),

    # ── FINANCE ──────────────────────────────────────────────────────────────

    # Payment Gateways — use slug (model has slug field, auto-generated from name)
    path('payment-gateways/', views.payment_gateways_list, name='payment_gateways_list'),
    path('payment-gateways/create/', views.payment_gateway_create, name='payment_gateway_create'),
    path('payment-gateways/<slug:slug>/edit/', views.payment_gateway_edit, name='payment_gateway_edit'),
    path('payment-gateways/<slug:slug>/delete/', views.payment_gateway_delete, name='payment_gateway_delete'),

    # Transactions — use transaction_id (UUID-based string, unique)
    path('transactions/', views.transactions_list, name='transactions_list'),
    path('transactions/<str:transaction_id>/', views.transaction_detail, name='transaction_detail'),

    # Required Payments — pk kept (no natural unique identifier on model)
    path('required-payments/', views.required_payments_list, name='required_payments_list'),
    path('required-payments/create/', views.required_payment_create, name='required_payment_create'),
    path('required-payments/<int:pk>/edit/', views.required_payment_edit, name='required_payment_edit'),
    path('required-payments/<int:pk>/delete/', views.required_payment_delete, name='required_payment_delete'),
    path('required-payments/send-overdue-reminders/', views.send_overdue_payment_reminders, name='send_overdue_payment_reminders'),

    # Financial Analytics Dashboard
    path('analytics/financial/', views.financial_analytics, name='financial_analytics'),

    # Staff Payroll — use payroll_reference (unique, auto-generated string)
    path('payroll/', views.staff_payroll_list, name='staff_payroll_list'),
    path('payroll/create/', views.staff_payroll_create, name='staff_payroll_create'),
    path('payroll/<str:payroll_reference>/edit/', views.staff_payroll_edit, name='staff_payroll_edit'),
    path('payroll/<str:payroll_reference>/delete/', views.staff_payroll_delete, name='staff_payroll_delete'),

    # Site Configuration
    path('site-config/general/', views.site_config_general, name='site_config_general'),
    path('site-config/index/', views.site_config_index, name='site_config_index'),
    path('site-config/about/', views.site_config_about, name='site_config_about'),

    # History Milestones
    path('site-config/milestones/', views.site_milestones_list, name='site_milestones_list'),
    path('site-config/milestones/create/', views.site_milestone_create, name='site_milestone_create'),
    path('site-config/milestones/<int:pk>/edit/', views.site_milestone_edit, name='site_milestone_edit'),
    path('site-config/milestones/<int:pk>/delete/', views.site_milestone_delete, name='site_milestone_delete'),

    # Testimonials
    path('site-config/testimonials/', views.testimonials_list, name='testimonials_list'),
    path('site-config/testimonials/create/', views.testimonial_create, name='testimonial_create'),
    path('site-config/testimonials/<int:pk>/edit/', views.testimonial_edit, name='testimonial_edit'),
    path('site-config/testimonials/<int:pk>/delete/', views.testimonial_delete, name='testimonial_delete'),

    # Institution Members
    path('site-config/members/', views.institution_members_list, name='institution_members_list'),
    path('site-config/members/create/', views.institution_member_create, name='institution_member_create'),
    path('site-config/members/<int:pk>/edit/', views.institution_member_edit, name='institution_member_edit'),
    path('site-config/members/<int:pk>/delete/', views.institution_member_delete, name='institution_member_delete'),

    # ── Exams (Superadmin) ────────────────────────────────────────────────────
    path('exams/', views.admin_exam_list, name='admin_exam_list'),
    path('exams/<slug:slug>/', views.admin_exam_detail, name='admin_exam_detail'),
    path('exams/<slug:slug>/approve/', views.admin_exam_approve, name='admin_exam_approve'),
    path('exams/<slug:slug>/reject/', views.admin_exam_reject, name='admin_exam_reject'),
    path('exams/<slug:slug>/publish/', views.admin_exam_publish, name='admin_exam_publish'),
    path('exams/<slug:slug>/questions/', views.admin_question_moderation, name='admin_question_moderation'),
    path('exams/<slug:slug>/timetable/', views.admin_exam_timetable_update, name='admin_exam_timetable_update'),
    path('exams/<slug:slug>/responses/', views.admin_exam_responses, name='admin_exam_responses'),
    path('exams/<slug:slug>/release-results/', views.admin_exam_release_results, name='admin_exam_release_results'),

    # ── Library ──────────────────────────────────────────────────────────────
    path('library/',                             views.library_items_list,         name='library_items_list'),
    path('library/create/',                      views.library_item_create,        name='library_item_create'),
    path('library/<uuid:pk>/edit/',              views.library_item_edit,          name='library_item_edit'),
    path('library/<uuid:pk>/delete/',            views.library_item_delete,        name='library_item_delete'),
    path('library/<uuid:pk>/toggle-active/',     views.library_item_toggle_active, name='library_item_toggle_active'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)