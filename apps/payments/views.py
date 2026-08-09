from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Sum, Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST
from decimal import Decimal
from django.core.paginator import Paginator

from apps.eduweb.decorators import is_finance_manager
from apps.eduweb.models import (
    AcademicSession,
    AllRequiredPayments,
    ApplicationPayment,
    AuditLog,
    Course,
    FeePayment,
    Program,
)

# No institution-wide currency-symbol setting exists yet (SiteConfig and
# SystemConfiguration both lack one) — see AUDIT.md cross-cutting theme #4.
# '$' is an explicit placeholder default, matching finance/views.py's dashboard.
DEFAULT_CURRENCY_SYMBOL = '$'

from .forms import (
    PaymentFilterForm,
    RefundForm,
    InvoiceGenerateForm,
    RequiredPaymentForm,
)


def _has_permission(request, module, action):
    """
    True if the acting user may perform `action` on `module`. Superuser
    always bypasses; otherwise reads the StaffPermissionsMatrix snapshot
    SessionSecurityMiddleware attaches to the request as `request.permissions`.
    Mirrors management/views.py's helper of the same name.
    """
    if request.user.is_superuser:
        return True
    return getattr(request, 'permissions', {}).get(module, {}).get(action, False)


def can_manage_required_payments(user):
    """
    Required-payments management is the one corner of this app admins also
    need direct access to (this used to be a separate management:-only CRUD
    over the same AllRequiredPayments model — collapsed into this single
    surface). Deliberately broader than is_finance_manager, which the rest
    of this app's views stay scoped to.
    """
    return is_finance_manager(user) or (
        user.is_authenticated and (user.is_superuser or getattr(getattr(user, 'profile', None), 'role', None) == 'admin')
    )


# ==================== PAYMENT MANAGEMENT ====================

@login_required
@user_passes_test(is_finance_manager)
def payment_management(request):
    """
    List both payment types — application fees and student required fees —
    each in its own paginated tab, matching templates/finance/payment_management.html
    ('app_page' / 'fee_page' GET params, one Paginator per tab).
    """

    filter_form = PaymentFilterForm(request.GET or None)

    app_qs = ApplicationPayment.objects.select_related(
        'application__program',
        'application__user',
    ).order_by('-created_at')
    fee_qs = FeePayment.objects.select_related(
        'user__profile', 'fee',
    ).order_by('-created_at')

    if filter_form.is_valid():
        cd = filter_form.cleaned_data

        if cd.get('status'):
            app_qs = app_qs.filter(status=cd['status'])
            fee_qs = fee_qs.filter(status=cd['status'])

        if cd.get('payment_method'):
            # FeePayment.PAYMENT_METHOD_CHOICES doesn't share this form's
            # choice set — the method filter only applies to application fees.
            app_qs = app_qs.filter(payment_method=cd['payment_method'])

        if cd.get('date_from'):
            app_qs = app_qs.filter(created_at__date__gte=cd['date_from'])
            fee_qs = fee_qs.filter(created_at__date__gte=cd['date_from'])

        if cd.get('date_to'):
            app_qs = app_qs.filter(created_at__date__lte=cd['date_to'])
            fee_qs = fee_qs.filter(created_at__date__lte=cd['date_to'])

        if cd.get('search'):
            term = cd['search']
            app_qs = app_qs.filter(
                Q(payment_reference__icontains=term)
                | Q(application__user__username__icontains=term)
                | Q(application__user__email__icontains=term)
                | Q(application__user__first_name__icontains=term)
                | Q(application__user__last_name__icontains=term)
            )
            fee_qs = fee_qs.filter(
                Q(payment_reference__icontains=term)
                | Q(user__username__icontains=term)
                | Q(user__email__icontains=term)
                | Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
            )

    app_page = Paginator(app_qs, 20).get_page(request.GET.get('app_page'))
    fee_page = Paginator(fee_qs, 20).get_page(request.GET.get('fee_page'))

    # Combined KPIs — "Application fees & student required fees, all in one place"
    app_revenue = (
        app_qs.filter(status='success').aggregate(Sum('amount'))['amount__sum']
        or Decimal('0.00')
    )
    fee_revenue = (
        fee_qs.filter(status='success').aggregate(Sum('amount'))['amount__sum']
        or Decimal('0.00')
    )

    context = {
        'filter_form': filter_form,
        'app_page': app_page,
        'fee_page': fee_page,
        'total_payments': app_qs.count() + fee_qs.count(),
        'success_count': app_qs.filter(status='success').count() + fee_qs.filter(status='success').count(),
        'pending_count': app_qs.filter(status='pending').count() + fee_qs.filter(status='pending').count(),
        'refunded_count': app_qs.filter(status='refunded').count() + fee_qs.filter(status='refunded').count(),
        'total_revenue': app_revenue + fee_revenue,
        'total_app_payments': app_qs.count(),
        'total_fee_payments': fee_qs.count(),
        'currency_symbol': DEFAULT_CURRENCY_SYMBOL,
    }

    return render(request, 'finance/payment_management.html', context)


# ==================== PAYMENT DETAIL ====================

@login_required
@user_passes_test(is_finance_manager)
def payment_detail(request, payment_reference):
    """
    View a single payment's full details — either an application-fee
    payment or a student required-fee payment; templates/finance/payment_detail.html
    branches on `payment_type` ('application' | 'fee') for both.
    """

    payment = ApplicationPayment.objects.select_related(
        'application__user',
        'application__program__department__faculty',
        'application__intake',
    ).filter(payment_reference=payment_reference).first()
    payment_type = 'application'

    if payment is None:
        payment = get_object_or_404(
            FeePayment.objects.select_related(
                'user__profile', 'fee__program__department__faculty', 'fee__academic_session',
            ),
            payment_reference=payment_reference,
        )
        payment_type = 'fee'

    context = {
        'payment': payment,
        'payment_type': payment_type,
        # Refunds are only wired up for application-fee payments (refund_payment
        # only knows ApplicationPayment/Stripe) — fee payments are view-only here.
        'can_refund': payment_type == 'application' and payment.status == 'success',
    }

    return render(request, 'finance/payment_detail.html', context)


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

@login_required
@user_passes_test(can_manage_required_payments)
def required_payments_list(request):
    """List + create/edit-modal data for AllRequiredPayments (fee obligations)."""
    today = timezone.now().date()

    payments = AllRequiredPayments.objects.select_related(
        'program', 'course', 'academic_session'
    ).order_by('-created_at')

    total_value = (
        payments.filter(is_active=True)
        .aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )

    context = {
        'payments': payments,
        'today': today,
        'total_count': payments.count(),
        'active_count': payments.filter(is_active=True).count(),
        'overdue_count': payments.filter(is_active=True, due_date__lt=today).count(),
        'total_value': total_value,
        'all_programs': Program.objects.order_by('name'),
        'all_courses': Course.objects.select_related('program').order_by('code'),
        'all_sessions': AcademicSession.objects.order_by('-created_at'),
        'suggestions': (
            AllRequiredPayments.objects.order_by('purpose')
            .values_list('purpose', flat=True).distinct()
        ),
    }
    return render(request, 'finance/required_payments.html', context)


@login_required
@user_passes_test(can_manage_required_payments)
@require_POST
def required_payment_create(request):
    if not _has_permission(request, 'finance_payments', 'can_create'):
        messages.error(request, 'You do not have permission to create required payments.')
        return redirect('payments:required_payments_list')

    form = RequiredPaymentForm(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            messages.error(
                request,
                'A required payment with the same programme, session, purpose, '
                'semester and level already exists.'
            )
        else:
            messages.success(request, f'Required payment "{form.cleaned_data["purpose"]}" created.')
    else:
        messages.error(request, 'Could not create required payment: ' + '; '.join(
            f'{field}: {", ".join(errs)}' for field, errs in form.errors.items()
        ))
    return redirect('payments:required_payments_list')


@login_required
@user_passes_test(can_manage_required_payments)
@require_POST
def required_payment_update(request, pk):
    if not _has_permission(request, 'finance_payments', 'can_edit'):
        messages.error(request, 'You do not have permission to edit required payments.')
        return redirect('payments:required_payments_list')

    payment = get_object_or_404(AllRequiredPayments, pk=pk)
    form = RequiredPaymentForm(request.POST, instance=payment)
    if form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            messages.error(
                request,
                'A required payment with the same programme, session, purpose, '
                'semester and level already exists.'
            )
        else:
            messages.success(request, f'Required payment "{payment.purpose}" updated.')
    else:
        messages.error(request, 'Could not update required payment: ' + '; '.join(
            f'{field}: {", ".join(errs)}' for field, errs in form.errors.items()
        ))
    return redirect('payments:required_payments_list')


@login_required
@user_passes_test(can_manage_required_payments)
@require_POST
def required_payment_toggle(request, pk):
    if not _has_permission(request, 'finance_payments', 'can_edit'):
        messages.error(request, 'You do not have permission to edit required payments.')
        return redirect('payments:required_payments_list')

    payment = get_object_or_404(AllRequiredPayments, pk=pk)
    payment.is_active = not payment.is_active
    payment.save(update_fields=['is_active'])
    messages.success(
        request,
        f'"{payment.purpose}" is now {"active" if payment.is_active else "inactive"}.'
    )
    return redirect('payments:required_payments_list')


@login_required
@user_passes_test(can_manage_required_payments)
@require_POST
def required_payment_delete(request, pk):
    if not _has_permission(request, 'finance_payments', 'can_delete'):
        messages.error(request, 'You do not have permission to delete required payments.')
        return redirect('payments:required_payments_list')

    payment = get_object_or_404(AllRequiredPayments, pk=pk)
    purpose = payment.purpose
    payment_pk = payment.pk
    payment.delete()
    AuditLog.objects.create(
        user=request.user,
        action='delete',
        model_name='AllRequiredPayments',
        object_id=str(payment_pk),
        description=f'Deleted required payment "{purpose}".',
    )
    messages.success(request, f'Required payment "{purpose}" deleted.')
    return redirect('payments:required_payments_list')


@login_required
@user_passes_test(can_manage_required_payments)
@require_POST
def required_payment_send_reminders(request):
    """
    Email an overdue-payment reminder to every student with a pending/failed
    FeePayment past its due date. Ported from management's now-collapsed
    required-payments CRUD so admins don't lose this capability.
    """
    if not _has_permission(request, 'finance_payments', 'can_edit'):
        messages.error(request, 'You do not have permission to send payment reminders.')
        return redirect('payments:required_payments_list')

    from apps.eduweb.emailservices import send_overdue_payment_reminder_email
    import logging
    logger = logging.getLogger(__name__)

    today = timezone.now().date()
    overdue_fees = FeePayment.objects.filter(
        fee__due_date__lt=today,
        status__in=['pending', 'failed'],
        user__isnull=False,
    ).select_related('user', 'fee')

    sent, failed = 0, 0
    for fee_payment in overdue_fees:
        try:
            send_overdue_payment_reminder_email(fee_payment.user, fee_payment.fee)
            sent += 1
        except Exception:
            logger.exception('Failed to send overdue reminder for FeePayment %s', fee_payment.pk)
            failed += 1

    if sent:
        messages.success(request, f'Sent {sent} overdue payment reminder(s).' + (f' {failed} failed.' if failed else ''))
    else:
        messages.info(request, 'No overdue payments found.')
    return redirect('payments:required_payments_list')


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

    if not _has_permission(request, 'finance_payments', 'can_export'):
        messages.error(request, 'You do not have permission to export invoices.')
        return redirect('payments:invoice_generation')

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

    AuditLog.objects.create(
        user=request.user,
        action='export',
        model_name='ApplicationPayment',
        object_id=str(payment.pk),
        description=f'Exported invoice PDF for payment {payment.payment_reference}.',
    )

    return response

# ==================== REFUND ====================

@login_required
@user_passes_test(is_finance_manager)
def refund_payment(request, payment_reference):
    """
    View the refund confirmation page (GET) and process a refund (POST)
    for a successful payment.
    - Only 'success' status payments are eligible.
    - Issues an actual Stripe refund if the payment was made via Stripe.
    - Validates refund amount does not exceed the original.
    """
    payment = get_object_or_404(
        ApplicationPayment.objects.select_related('application'),
        payment_reference=payment_reference,
    )

    if request.method == 'POST':
        if not _has_permission(request, 'finance_payments', 'can_edit'):
            messages.error(request, 'You do not have permission to process refunds.')
            return redirect(
                'payments:payment_detail',
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
                    from apps.eduweb.views import get_stripe_secret_key
                    stripe.api_key = get_stripe_secret_key()

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
            with transaction.atomic():
                payment.status = 'refunded'
                payment.failure_reason = (
                    f'Refunded {refund_amount} — Reason: {reason}'
                    + (f' | Notes: {notes}' if notes else '')
                    + f' | By: {request.user.username}'
                    + f' | At: {timezone.now().strftime("%Y-%m-%d %H:%M")}'
                )
                payment.save(update_fields=['status', 'failure_reason'])

                # Keep CourseApplication.payment_status (which is_paid reads)
                # in sync — otherwise a refunded application still reports as
                # fully paid and keeps portal access it should have lost.
                application = payment.application
                if application and application.payment_status == 'success':
                    application.payment_status = 'refunded'
                    application.save(update_fields=['payment_status'])

            AuditLog.objects.create(
                user=request.user,
                action='update',
                model_name='ApplicationPayment',
                object_id=str(payment.pk),
                description=(
                    f'{request.user.username} refunded {refund_amount} for payment '
                    f'{payment_reference}. Reason: {reason}.'
                    + (f' Notes: {notes}' if notes else '')
                ),
            )

            messages.success(
                request,
                f'Refund of {refund_amount} processed successfully '
                f'for payment {payment_reference}.'
            )
            return redirect(
                'payments:payment_detail',
                payment_reference=payment_reference,
            )
    else:
        form = RefundForm(payment=payment)

    return render(request, 'finance/refund.html', {
        'payment': payment,
        'form': form,
        'application': payment.application,
    })