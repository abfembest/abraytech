from django.urls import path, include
from . import views

app_name = 'finance'

urlpatterns = [

    # Dashboard
    path('', views.finance_dashboard, name='dashboard'),

    # Payments — delegated to the payments app
    # All payment URLs are now under payments/ namespace
    path('payments/', include('payment.urls', namespace='payment')),

    # Subscriptions
    path(
        'subscriptions/',
        views.subscription_list,
        name='subscription_list',
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