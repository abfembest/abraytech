from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

app_name = 'eduweb'

urlpatterns = [
    path('contact', views.contact, name='contact'),
    path('activities/', views.activities, name='activities'),
    path('my-profile/', views.profile, name='profile'),
    path('my-settings/', views.account_settings, name='settings'),
    path('auth/', views.auth_page, name='auth_page'),
    path('verify-email/<uuid:token>/', views.verify_email, name='verify_email'),
    path('account/change-password/', views.force_change_password, name='force_change_password'),
    path('logout/', views.user_logout, name='logout'),
    path('resend-verification/', views.resend_verification, name='resend_verification'),

    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/<uuid:token>/', views.reset_password, name='reset_password'),
    
    path('', views.index, name='index'),
    path('about-us/', views.about, name='about'),
    path('admission/apply/', views.apply, name='apply'),
    path('admission/register/', views.signup_page, name='signup_page'),
    path('admission/requirements/', views.admission_requirement, name='admission_requirement'),
    path('contact/submit/', views.contact_submit, name='contact_submit'),
    path('application_status/', views.application_status, name='application_status'),


    path('admission-letter/<str:application_id>/', views.admission_letter, name='admission_letter'),

    path('verify-otp/', views.otp_verify, name='otp_verify'),

    # Faculty Pages
    path('faculty/<slug:slug>/', views.faculty_detail, name='faculty_detail'),
    path('program/<slug:slug>/', views.program_detail, name='program_detail'),

    # Additional Pages
    path('research/', views.research, name='research'),
    path('all-programs/', views.all_programs, name='all_programs'),
    path('campus-life/', views.campus_life, name='campus_life'),
    path('blog/', views.blog, name='blog'),
    path('blog/<slug:slug>/', views.blog_detail, name='blog_detail'),
    path('blog/category/<slug:slug>/', views.blog_category, name='blog_category'),

    path(
        'application/<str:application_id>/submit/', 
        views.submit_application, 
        name='submit_application'
    ),
    path(
        'application/<str:application_id>/accept-admission/', 
        views.accept_admission, 
        name='accept_admission'
    ),

    ############### PAYMENT GATEWAY URLS################

    
    # Payment API endpoints (secure, require login)
     
    # --------------------
    path("payments/", views.payments, name="payments"),


    ################# STUDENT OUTSTANDING PAYMENT BY ID #########
    path('stddebt_by_id/', views.stddebt_by_id, name='stddebt_by_id'),
    path('student/payment_data/<int:payment_id>/', views.payment_data, name='payment_data'),

    # --------------------
    # Payment API (AJAX)
    # --------------------
    path("api/payment/summary/<str:application_id>/", views.get_payment_summary, name="get_payment_summary"),
    path('api/student-fee/summary/<int:student_fee_id>/', views.get_payment_summary),
    path("create-intent/", views.create_payment_intent, name="create_payment_intent"),
    path("application/confirmation", views.confirm_payment, name="confirm_payment"),

    # --------------------
    # Stripe Webhook
    # --------------------
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),

    ################## APPLICATION SUBMISSIONS #######

    # ================= STAGE 4 =================
    # Save application draft (Ajax)
    path("applications/save-draft/", views.save_application_draft, name="save_application_draft"),

    # ================= STAGE 5 =================
    # Preload payment details (Ajax)
    # path("<str:application_id>/payment-details/",views.payment_details, name="payment_details"),

    # Stripe payment handoff (to be implemented later)
   # path("payments/stripe/start/", views.start_stripe_payment, name="start_stripe_payment"),

    # Stripe webhook (future)
  #  path("payments/stripe/webhook/",views.stripe_webhook,name="stripe_webhook"),

    # ================= STAGE 6 =================
    # Upload documents (Ajax)
    path("<str:application_id>/upload-document/", views.upload_application_file, name="upload_application_file"),

    # eduweb/urls.py — add this line alongside the other API paths
    path("api/student-fee/summary/<int:fee_pk>/", views.get_student_fee_summary, name="get_student_fee_summary"),



]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

