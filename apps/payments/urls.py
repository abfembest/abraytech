from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [

    # List + filter
    path(
        '',
        views.payment_management,
        name='payment_management',
    ),

    # Transaction reports
    path(
        'reports/transactions/',
        views.transaction_reports,
        name='transaction_reports',
    ),

    path("required", views.required_payments_list, name="required_payments_list"),
    path("required/create/", views.required_payment_create, name="required_payment_create"),
    path("required/<int:pk>/update/", views.required_payment_update, name="required_payment_update"),
    path("required/<int:pk>/toggle/", views.required_payment_toggle, name="required_payment_toggle"),
    path("required/<int:pk>/delete/", views.required_payment_delete, name="required_payment_delete"),
    path("required/send-reminders/", views.required_payment_send_reminders, name="required_payment_send_reminders"),

    # Invoice pages
    path(
        'invoices/',
        views.invoice_generation,
        name='invoice_generation',
    ),
    path(
        'invoices/<str:payment_reference>/pdf/',
        views.generate_invoice_pdf,
        name='generate_invoice_pdf',
    ),

    # Detail + refund — single-segment catch-all patterns MUST come last,
    # otherwise they shadow every literal route above (e.g. '/invoices/'
    # would resolve to payment_detail(payment_reference='invoices') and
    # 404 instead of reaching invoice_generation).
    path(
        '<str:payment_reference>/',
        views.payment_detail,
        name='payment_detail',
    ),
    path(
        '<str:payment_reference>/refund/',
        views.refund_payment,
        name='refund_payment',
    ),
]