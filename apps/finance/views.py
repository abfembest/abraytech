import json
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import datetime, timedelta

from apps.eduweb.decorators import is_finance_manager
from apps.eduweb.models import (
    AllRequiredPayments,
    ApplicationPayment,
    AuditLog,
    CourseApplication,
    FeePayment,
    InstitutionalSubscription,
    StaffPayroll,
)

from .forms import (
    DateRangeForm,
    InstitutionalSubscriptionForm,
    PayrollCreateForm,
    PayrollFilterForm,
    PayrollStatusForm,
)

logger = logging.getLogger(__name__)


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


# ==================== DASHBOARD ====================

@login_required
@user_passes_test(is_finance_manager)
def finance_dashboard(request):
    """Finance dashboard — analytics and summary across all modules"""

    # Consistent with management/dashboard() and instructor/dashboard(): the
    # portal's own root dashboard isn't a StaffPermissionsMatrix module (see
    # the commented-out 'dashboard' key in ROLE_DEFAULT_PERMISSIONS) — access
    # is gated by is_finance_manager (role) alone, matching every other app.

    # ── Date range resolution ─────────────────────────────────────────────
    range_form = DateRangeForm(request.GET or None)
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)

    if range_form.is_valid():
        range_type = range_form.cleaned_data.get('range_type', 'this_month')

        if range_type == 'today':
            start_date = timezone.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif range_type == 'yesterday':
            start_date = (
                timezone.now() - timedelta(days=1)
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
        elif range_type == 'this_week':
            start_date = (
                timezone.now() - timedelta(days=timezone.now().weekday())
            ).replace(hour=0, minute=0, second=0, microsecond=0)
        elif range_type == 'last_week':
            end_date = (
                timezone.now() - timedelta(days=timezone.now().weekday())
            )
            start_date = end_date - timedelta(days=7)
        elif range_type == 'this_month':
            start_date = timezone.now().replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
        elif range_type == 'last_month':
            end_date = timezone.now().replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            start_date = (end_date - timedelta(days=1)).replace(day=1)
        elif range_type == 'this_year':
            start_date = timezone.now().replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        elif range_type == 'custom':
            if range_form.cleaned_data.get('start_date'):
                start_date = timezone.make_aware(
                    datetime.combine(
                        range_form.cleaned_data['start_date'],
                        datetime.min.time(),
                    )
                )
            if range_form.cleaned_data.get('end_date'):
                end_date = timezone.make_aware(
                    datetime.combine(
                        range_form.cleaned_data['end_date'],
                        datetime.max.time(),
                    )
                )

    today = timezone.now().date()

    # ── Application payments in range ─────────────────────────────────────
    payments = ApplicationPayment.objects.filter(
        created_at__range=[start_date, end_date]
    )

    # ── Revenue KPIs ──────────────────────────────────────────────────────
    total_revenue = (
        payments.filter(status='success')
        .aggregate(Sum('amount'))['amount__sum']
        or Decimal('0.00')
    )
    pending_revenue = (
        payments.filter(status='pending')
        .aggregate(Sum('amount'))['amount__sum']
        or Decimal('0.00')
    )
    refunded_amount = (
        payments.filter(status='refunded')
        .aggregate(Sum('amount'))['amount__sum']
        or Decimal('0.00')
    )

    # Application vs fee revenue split (all successful app payments = app_revenue;
    # fee_revenue comes from FeePayment if available, else zero)
    app_revenue = total_revenue  # ApplicationPayment is the app revenue source

    # ── Transaction counts ────────────────────────────────────────────────
    total_transactions = payments.count()
    successful_transactions = payments.filter(status='success').count()
    failed_transactions = payments.filter(status='failed').count()

    success_rate = (
        round(successful_transactions / total_transactions * 100, 2)
        if total_transactions > 0
        else 0
    )

    # ── Payment methods breakdown ─────────────────────────────────────────
    payment_methods = (
        payments.filter(status='success')
        .values('payment_method')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )

    # ── Daily revenue for line chart ──────────────────────────────────────
    daily_revenue = []
    current = start_date
    while current <= end_date:
        day_total = (
            payments.filter(status='success', created_at__date=current.date())
            .aggregate(Sum('amount'))['amount__sum']
            or Decimal('0.00')
        )
        daily_revenue.append({
            'date': current.strftime('%Y-%m-%d'),
            'revenue': float(day_total),
        })
        current += timedelta(days=1)

    # ── Top programs by revenue ───────────────────────────────────────────
    top_courses = (
        CourseApplication.objects.filter(
            payment__status='success',
            payment__created_at__range=[start_date, end_date],
        )
        .values('program__name')
        .annotate(revenue=Sum('payment__amount'), applications=Count('id'))
        .order_by('-revenue')[:5]
    )

    # ── Fee payments ────────────────────────────────────────────────────────
    fee_qs = FeePayment.objects.filter(created_at__range=[start_date, end_date])
    fee_revenue = (
        fee_qs.filter(status='success')
        .aggregate(Sum('amount'))['amount__sum']
        or Decimal('0.00')
    )
    recent_fee_payments = (
        fee_qs.select_related('user', 'fee')
        .order_by('-created_at')[:15]
    )

    # ── Required / outstanding payments ────────────────────────────────────
    req_qs = AllRequiredPayments.objects.filter(
        is_active=True
    ).select_related('program', 'course', 'academic_session')

    required_payments_count = req_qs.count()
    required_payments_total = (
        req_qs.aggregate(Sum('amount'))['amount__sum']
        or Decimal('0.00')
    )
    overdue_required_count = req_qs.filter(due_date__lt=today).count()
    all_required_payments = req_qs.order_by('due_date')

    # ── Recent application payments ───────────────────────────────────────
    recent_app_payments = (
        ApplicationPayment.objects.select_related(
            'application__user',
            'application__program',
        )
        .filter(application__isnull=False)
        .order_by('-created_at')[:15]
    )

    # No institution-wide currency-symbol setting exists yet (SiteConfig and
    # SystemConfiguration both lack one) — see AUDIT.md cross-cutting theme #4.
    # '$' is an explicit placeholder default, not a lookup that silently fails.
    currency_symbol = '$'

    context = {
        # Date range
        'range_form': range_form,
        'start_date': start_date,
        'end_date': end_date,
        'today': today,

        # Currency
        'currency_symbol': currency_symbol,

        # Revenue KPIs
        'total_revenue': total_revenue,
        'app_revenue': app_revenue,
        'fee_revenue': fee_revenue,
        'pending_revenue': pending_revenue,
        'refunded_amount': refunded_amount,

        # Transaction KPIs
        'total_transactions': total_transactions,
        'successful_transactions': successful_transactions,
        'failed_transactions': failed_transactions,
        'success_rate': success_rate,

        # Charts
        'payment_methods': payment_methods,
        'daily_revenue': json.dumps(daily_revenue),

        # Top programs
        'top_courses': top_courses,

        # Required payments
        'required_payments_count': required_payments_count,
        'required_payments_total': required_payments_total,
        'overdue_required_count': overdue_required_count,
        'all_required_payments': all_required_payments,

        # Recent transactions tables
        'recent_app_payments': recent_app_payments,
        'recent_fee_payments': recent_fee_payments,
    }

    return render(request, 'finance/dashboard.html', context)


# ==================== SUBSCRIPTIONS ====================
# Institutional subscriptions (software/hosting/tools the school itself pays
# for) — superuser-only, unrelated to the student-facing SubscriptionPlan.

def _is_superuser(user):
    return user.is_authenticated and user.is_active and user.is_superuser


def _subscription_list_context(form=None):
    subscriptions = InstitutionalSubscription.objects.all()
    today = timezone.now().date()
    return {
        'subscriptions': subscriptions,
        'total_subscriptions': subscriptions.count(),
        'active_subscriptions': subscriptions.filter(expiry_date__gte=today).count(),
        'expired_subscriptions': subscriptions.filter(expiry_date__lt=today).count(),
        'total_amount': subscriptions.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'),
        'form': form or InstitutionalSubscriptionForm(),
    }


@login_required
@user_passes_test(_is_superuser)
def subscription_list(request):
    """List the institution's own paid subscriptions."""
    return render(request, 'finance/subscription_list.html', _subscription_list_context())


@login_required
@user_passes_test(_is_superuser)
def subscription_create(request):
    """Add a new institutional subscription record."""
    if request.method != 'POST':
        return redirect('finance:subscription_list')

    form = InstitutionalSubscriptionForm(request.POST)
    if form.is_valid():
        subscription = form.save(commit=False)
        subscription.created_by = request.user
        subscription.save()
        AuditLog.objects.create(
            user=request.user,
            action='create',
            model_name='InstitutionalSubscription',
            object_id=str(subscription.pk),
            description=f'Added institutional subscription "{subscription.purpose}" ({subscription.amount}).',
        )
        messages.success(request, f'Subscription "{subscription.purpose}" added.')
        return redirect('finance:subscription_list')

    messages.error(request, 'Please correct the errors below.')
    context = _subscription_list_context(form=form)
    context['show_add_modal'] = True
    return render(request, 'finance/subscription_list.html', context)


# ==================== PAYROLL ====================

@login_required
@user_passes_test(is_finance_manager)
def payroll_management(request):
    """Payroll list + create modal"""

    if not _has_permission(request, 'finance_payroll', 'can_view'):
        messages.error(request, 'You do not have permission to view payroll.')
        return redirect('finance:dashboard')

    if request.method == 'POST':
        if not _has_permission(request, 'finance_payroll', 'can_create'):
            messages.error(request, 'You do not have permission to create payroll records.')
            return redirect('finance:payroll_management')

        form = PayrollCreateForm(request.POST, request.FILES)
        if form.is_valid() and form.cleaned_data['staff'] == request.user:
            messages.error(request, 'You cannot create a payroll record for yourself.')
            return redirect('finance:payroll_management')
        if form.is_valid():
            payroll = form.save(commit=False)
            payroll.created_by = request.user

            for i in range(1, 6):
                file = request.FILES.get(f'attachment_file_{i}')
                name = request.POST.get(f'attachment_name_{i}', '')
                if file:
                    setattr(payroll, f'attachment_{i}', file)
                    if name:
                        setattr(payroll, f'attachment_{i}_name', name)

            try:
                with transaction.atomic():
                    payroll.save()
            except IntegrityError:
                messages.error(
                    request,
                    f'A payroll record for {form.cleaned_data["staff"]} in '
                    f'{form.cleaned_data["month"]}/{form.cleaned_data["year"]} already exists.'
                )
            else:
                AuditLog.objects.create(
                    user=request.user,
                    action='create',
                    model_name='StaffPayroll',
                    object_id=str(payroll.pk),
                    description=(
                        f'Created payroll record {payroll.payroll_reference} for '
                        f'{payroll.staff} ({payroll.month}/{payroll.year}).'
                    ),
                )
                messages.success(
                    request,
                    f'Payroll created: {payroll.payroll_reference}'
                )
            return redirect('finance:payroll_management')
    else:
        form = PayrollCreateForm()

    filter_form = PayrollFilterForm(request.GET or None)

    payrolls = StaffPayroll.objects.select_related(
        'staff', 'created_by', 'approved_by'
    ).order_by('-year', '-month', 'staff__username')

    if filter_form.is_valid():
        cd = filter_form.cleaned_data

        if cd.get('status'):
            payrolls = payrolls.filter(payment_status=cd['status'])
        if cd.get('month'):
            payrolls = payrolls.filter(month=int(cd['month']))
        if cd.get('year'):
            payrolls = payrolls.filter(year=cd['year'])
        if cd.get('search'):
            term = cd['search']
            payrolls = payrolls.filter(
                Q(payroll_reference__icontains=term)
                | Q(staff__username__icontains=term)
                | Q(staff__first_name__icontains=term)
                | Q(staff__last_name__icontains=term)
            )

    paginator = Paginator(payrolls, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    total_amount = (
        payrolls.aggregate(total=Sum('net_salary'))['total']
        or Decimal('0')
    )
    paid_amount = (
        payrolls.filter(payment_status='paid')
        .aggregate(total=Sum('net_salary'))['total']
        or Decimal('0')
    )

    context = {
        'form': form,
        'filter_form': filter_form,
        'page_obj': page_obj,
        'payrolls': page_obj.object_list,
        'total_payrolls': payrolls.count(),
        'pending_count': payrolls.filter(payment_status='pending').count(),
        'paid_count': payrolls.filter(payment_status='paid').count(),
        'total_amount': total_amount,
        'paid_amount': paid_amount,
    }

    return render(request, 'finance/payroll_management.html', context)


@login_required
@user_passes_test(is_finance_manager)
def payroll_detail(request, payroll_reference):
    """View + update a single payroll record"""

    if not _has_permission(request, 'finance_payroll', 'can_view'):
        messages.error(request, 'You do not have permission to view payroll.')
        return redirect('finance:dashboard')

    payroll = get_object_or_404(
        StaffPayroll.objects.select_related(
            'staff', 'created_by', 'approved_by'
        ),
        payroll_reference=payroll_reference,
    )

    if request.method == 'POST':
        if not _has_permission(request, 'finance_payroll', 'can_edit'):
            messages.error(request, 'You do not have permission to update payroll status.')
            return redirect(
                'finance:payroll_detail',
                payroll_reference=payroll_reference,
            )

        if payroll.staff_id == request.user.id:
            messages.error(request, 'You cannot approve or edit your own payroll record.')
            return redirect(
                'finance:payroll_detail',
                payroll_reference=payroll_reference,
            )

        status_form = PayrollStatusForm(request.POST, instance=payroll)
        if status_form.is_valid():
            previous_status = payroll.payment_status
            with transaction.atomic():
                updated = status_form.save(commit=False)
                just_approved = (
                    updated.payment_status == 'paid'
                    and payroll.payment_status != 'paid'
                )
                if just_approved:
                    updated.approved_by = request.user
                    updated.approved_at = timezone.now()
                updated.save()
            AuditLog.objects.create(
                user=request.user,
                action='update',
                model_name='StaffPayroll',
                object_id=str(updated.pk),
                description=(
                    f'Updated payroll {updated.payroll_reference} status from '
                    f'"{previous_status}" to "{updated.payment_status}" for {updated.staff}.'
                    + (' Approved for payment.' if just_approved else '')
                ),
            )
            messages.success(request, 'Payroll status updated.')
            return redirect(
                'finance:payroll_detail',
                payroll_reference=payroll_reference,
            )
    else:
        status_form = PayrollStatusForm(instance=payroll)

    context = {
        'payroll': payroll,
        'status_form': status_form,
        'attachments': payroll.get_attachments(),
    }

    return render(request, 'finance/payroll_detail.html', context)


@login_required
@user_passes_test(is_finance_manager)
def payroll_delete(request, payroll_reference):
    """Delete a payroll record (only if not paid)"""

    if not _has_permission(request, 'finance_payroll', 'can_delete'):
        messages.error(request, 'You do not have permission to delete payroll records.')
        return redirect(
            'finance:payroll_detail',
            payroll_reference=payroll_reference,
        )

    payroll = get_object_or_404(
        StaffPayroll,
        payroll_reference=payroll_reference,
    )

    if not payroll.can_delete():
        messages.error(request, 'Cannot delete a paid payroll record.')
        return redirect(
            'finance:payroll_detail',
            payroll_reference=payroll_reference,
        )

    if request.method == 'POST':
        payroll_pk = payroll.pk
        payroll_staff = str(payroll.staff)
        with transaction.atomic():
            for i in range(1, 6):
                f = getattr(payroll, f'attachment_{i}')
                if f:
                    f.delete(save=False)
            payroll.delete()
        AuditLog.objects.create(
            user=request.user,
            action='delete',
            model_name='StaffPayroll',
            object_id=str(payroll_pk),
            description=f'Deleted payroll record {payroll_reference} for {payroll_staff}.',
        )
        messages.success(
            request,
            f'Payroll {payroll_reference} deleted.'
        )
        return redirect('finance:payroll_management')

    return redirect(
        'finance:payroll_detail',
        payroll_reference=payroll_reference,
    )


@login_required
@user_passes_test(is_finance_manager)
def payroll_attachment_delete(request, payroll_reference, attachment_number):
    """Delete one attachment from a payroll record"""

    if not _has_permission(request, 'finance_payroll', 'can_delete'):
        messages.error(request, 'You do not have permission to delete payroll attachments.')
        return redirect(
            'finance:payroll_detail',
            payroll_reference=payroll_reference,
        )

    payroll = get_object_or_404(
        StaffPayroll,
        payroll_reference=payroll_reference,
    )

    if request.method == 'POST':
        if payroll.delete_attachment(attachment_number):
            messages.success(
                request,
                f'Attachment {attachment_number} deleted.'
            )
        else:
            messages.error(request, 'Failed to delete attachment.')

    return redirect(
        'finance:payroll_detail',
        payroll_reference=payroll_reference,
    )