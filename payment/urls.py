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

    # Detail view
    path(
        '<str:payment_reference>/',
        views.payment_detail,
        name='payment_detail',
    ),

    # Refund action (POST only)
    path(
        '<str:payment_reference>/refund/',
        views.refund_payment,
        name='refund_payment',
    ),

    # Transaction reports
    path(
        'reports/transactions/',
        views.transaction_reports,
        name='transaction_reports',
    ),

    path("required", views.required_payments_list, name="required_payments_list"),

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
    path("refund/<str:payment_reference>/", views.refund_payment, name="refund_payment"),
]