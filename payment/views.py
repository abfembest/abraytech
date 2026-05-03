from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum, Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from decimal import Decimal
from django.core.paginator import Paginator

from eduweb.models import ApplicationPayment

from .forms import (
    PaymentFilterForm,
    RefundForm,
    InvoiceGenerateForm,
)


def is_finance_manager(user):
    """Allow only authenticated finance-role users"""
    return (
        user.is_authenticated
        and hasattr(user, 'profile')
        and user.profile.role == 'finance'
    )


# ==================== PAYMENT MANAGEMENT ====================

@login_required
@user_passes_test(is_finance_manager)
def payment_management(request):
    """List all payments with filtering and summary stats"""

    filter_form = PaymentFilterForm(request.GET or None)

    payments = ApplicationPayment.objects.select_related(
        'application__program',
        'application__user',
    ).order_by('-created_at')

    if filter_form.is_valid():
        cd = filter_form.cleaned_data

        if cd.get('status'):
            payments = payments.filter(status=cd['status'])

        if cd.get('payment_method'):
            payments = payments.filter(
                payment_method=cd['payment_method']
            )

        if cd.get('date_from'):
            payments = payments.filter(
                created_at__date__gte=cd['date_from']
            )

        if cd.get('date_to'):
            payments = payments.filter(
                created_at__date__lte=cd['date_to']
            )

        if cd.get('search'):
            term = cd['search']
            payments = payments.filter(
                Q(payment_reference__icontains=term)
                | Q(application__user__username__icontains=term)
                | Q(application__user__email__icontains=term)
                | Q(application__user__first_name__icontains=term)
                | Q(application__user__last_name__icontains=term)
            )

    # Summary stats
    total_amount = (
        payments.filter(status='success')
        .aggregate(Sum('amount'))['amount__sum']
        or Decimal('0.00')
    )

    context = {
        'filter_form': filter_form,
        'payments': payments,
        'total_payments': payments.count(),
        'completed_payments': payments.filter(status='success').count(),
        'pending_payments': payments.filter(status='pending').count(),
        'failed_payments': payments.filter(status='failed').count(),
        'total_amount': total_amount,
    }

    return render(request, 'finance/payment_management.html', context)


# ==================== PAYMENT DETAIL ====================

@login_required
@user_passes_test(is_finance_manager)
def payment_detail(request, payment_reference):
    """View a single payment's full details"""

    payment = get_object_or_404(
        ApplicationPayment.objects.select_related(
            'application__user',
            'application__program'
        ),
        payment_reference=payment_reference,
    )

    refund_form = RefundForm(payment=payment)

    context = {
        'payment': payment,
        'refund_form': refund_form,
        'can_refund': payment.status == 'success',
    }

    return render(request, 'finance/payment_detail.html', context)


# ==================== REFUND ====================

@login_required
@user_passes_test(is_finance_manager)
def refund_payment(request, payment_reference):
    """
    Process a refund for a successful payment.
    - Only 'success' status payments are eligible.
    - Validates refund amount does not exceed original.
    - POST-only; redirects GET back to detail page.
    """

    if request.method != 'POST':
        return redirect(
            'payments:payment_detail',
            payment_reference=payment_reference,
        )

    payment = get_object_or_404(
        ApplicationPayment,
        payment_reference=payment_reference,
    )

    # Guard: only successful payments can be refunded
    if payment.status != 'success':
        messages.error(
            request,
            f'Payment {payment_reference} cannot be refunded '
            f'because its status is "{payment.get_status_display()}", '
            f'not "Success".'
        )
        return redirect(
            'payments:payment_detail',
            payment_reference=payment_reference,
        )

    form = RefundForm(request.POST, payment=payment)

    if form.is_valid():
        reason = form.cleaned_data['reason']
        notes = form.cleaned_data.get('notes', '')
        refund_amount = form.cleaned_data['refund_amount']

        # Mark as refunded and store audit trail
        payment.status = 'refunded'
        payment.failure_reason = (
            f'Refunded ₦{refund_amount} — Reason: {reason}'
            + (f' | Notes: {notes}' if notes else '')
            + f' | By: {request.user.username}'
            + f' | At: {timezone.now().strftime("%Y-%m-%d %H:%M")}'
        )
        payment.save(update_fields=['status', 'failure_reason'])

        messages.success(
            request,
            f'Refund of ₦{refund_amount} processed successfully '
            f'for payment {payment_reference}.'
        )
    else:
        # Put errors back via session-like message
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')

    return redirect(
        'payments:payment_detail',
        payment_reference=payment_reference,
    )


# ==================== TRANSACTION REPORTS ====================

@login_required
@user_passes_test(is_finance_manager)
def transaction_reports(request):
    """All-payments report. Filtering handled client-side via DataTables."""

    payments = ApplicationPayment.objects.select_related(
        'application__user',
        'application__program'
    ).order_by('-created_at')

    total_count = payments.count()
    successful_count = payments.filter(status='success').count()
    total_revenue = (
        payments.filter(status='success')
        .aggregate(total=Sum('amount'))['total']
        or 0
    )
    success_rate = (
        round(successful_count / total_count * 100, 2)
        if total_count > 0
        else 0
    )

    context = {
        'payments': payments,
        'total_count': total_count,
        'successful_count': successful_count,
        'total_revenue': total_revenue,
        'success_rate': success_rate,
    }

    return render(
        request,
        'finance/transaction_reports.html',
        context,
    )

def required_payments_list(request):
    return render(request, 'finance/required_payments.html')


# ==================== INVOICES ====================

@login_required
@user_passes_test(is_finance_manager)
def invoice_generation(request):
    """Invoice selection page"""

    invoice_form = InvoiceGenerateForm(request.GET or None)

    recent_payments = ApplicationPayment.objects.select_related(
        'application__user',
    ).filter(
        status='success',
        application__isnull=False,
    ).order_by('-created_at')[:10]

    context = {
        'invoice_form': invoice_form,
        'recent_payments': recent_payments,
    }

    return render(
        request,
        'finance/invoice_generation.html',
        context,
    )


@login_required
@user_passes_test(is_finance_manager)
def generate_invoice_pdf(request, payment_reference):
    """Generate and stream a PDF invoice for a successful payment"""

    try:
        from xhtml2pdf import pisa
    except ImportError:
        messages.error(
            request,
            'PDF library not installed. Run: pip install xhtml2pdf'
        )
        return redirect('payments:invoice_generation')

    payment = get_object_or_404(
        ApplicationPayment.objects.select_related(
            'application__user',
            'application__program'
        ),
        payment_reference=payment_reference,
        status='success',
    )

    invoice_context = {
        'payment': payment,
        'invoice_number': f'INV-{payment.payment_reference}',
        'invoice_date': timezone.now(),
        'company_name': 'MIU Education',
        'company_address': '123 Education Street',
        'company_city': 'Learning City, LC 12345',
        'company_email': 'billing@miuedu.com',
        'company_phone': '+1 (555) 123-4567',
    }

    html = render_to_string('finance/invoice.html', invoice_context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; '
        f'filename="invoice_{payment.payment_reference}.pdf"'
    )

    result = pisa.CreatePDF(html, dest=response)

    if result.err:
        messages.error(request, 'Error generating PDF invoice.')
        return redirect('payments:invoice_generation')

    return response

# ==================== REFUND ====================

@login_required
@user_passes_test(is_finance_manager)
def refund_payment(request, payment_reference):
    """
    Process a refund for a successful payment.
    - Only 'success' status payments are eligible.
    - Issues actual Stripe refund if payment was via Stripe.
    - Validates refund amount does not exceed original.
    - POST-only; redirects GET back to detail page.
    """

    if request.method != 'POST':
        return redirect(
            'payments:payment_detail',
            payment_reference=payment_reference,
        )

    payment = get_object_or_404(
        ApplicationPayment,
        payment_reference=payment_reference,
    )

    # Guard: only successful payments can be refunded
    if payment.status != 'success':
        messages.error(
            request,
            f'Payment {payment_reference} cannot be refunded '
            f'because its status is '
            f'"{payment.get_status_display()}", not "Success".'
        )
        return redirect(
            'payments:payment_detail',
            payment_reference=payment_reference,
        )

    form = RefundForm(request.POST, payment=payment)

    if form.is_valid():
        reason = form.cleaned_data['reason']
        notes = form.cleaned_data.get('notes', '')
        refund_amount = form.cleaned_data['refund_amount']

        # If paid via Stripe, issue the actual refund on Stripe first
        if payment.gateway_payment_id:
            try:
                import stripe
                from django.conf import settings
                stripe.api_key = settings.STRIPE_SECRET_KEY

                stripe.Refund.create(
                    payment_intent=payment.gateway_payment_id,
                    amount=int(refund_amount * 100),  # convert to pence/cents
                )
            except Exception as e:
                messages.error(
                    request,
                    f'Stripe refund failed: {e}. '
                    f'Record not updated.'
                )
                return redirect(
                    'payments:payment_detail',
                    payment_reference=payment_reference,
                )

        # Update record only after Stripe succeeds (or no Stripe)
        payment.status = 'refunded'
        payment.failure_reason = (
            f'Refunded {refund_amount} — Reason: {reason}'
            + (f' | Notes: {notes}' if notes else '')
            + f' | By: {request.user.username}'
            + f' | At: {timezone.now().strftime("%Y-%m-%d %H:%M")}'
        )
        payment.save(update_fields=['status', 'failure_reason'])

        messages.success(
            request,
            f'Refund of {refund_amount} processed successfully'
            f'for payment {payment_reference}.'
        )

    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')

    return redirect(
        'payments:payment_detail',
        payment_reference=payment_reference,
    )