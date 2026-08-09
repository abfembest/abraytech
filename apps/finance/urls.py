from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [

    # Dashboard
    path('', views.finance_dashboard, name='dashboard'),

    # Payments live under the top-level /payment/ prefix (config/urls.py,
    # namespace 'payments') — the sidebar's {% url 'payments:...' %} links resolve
    # there, not here. Nothing reverses the 'finance' namespace for payment URLs.

    # Subscriptions (institutional — superuser-only)
    path(
        'subscriptions/',
        views.subscription_list,
        name='subscription_list',
    ),
    path(
        'subscriptions/add/',
        views.subscription_create,
        name='subscription_create',
    ),

    # Payroll
    path('payroll/', views.payroll_management, name='payroll_management'),
    path(
        'payroll/<str:payroll_reference>/',
        views.payroll_detail,
        name='payroll_detail',
    ),
    path(
        'payroll/<str:payroll_reference>/delete/',
        views.payroll_delete,
        name='payroll_delete',
    ),
    path(
        'payroll/<str:payroll_reference>/attachment/'
        '<int:attachment_number>/delete/',
        views.payroll_attachment_delete,
        name='payroll_attachment_delete',
    ),
]