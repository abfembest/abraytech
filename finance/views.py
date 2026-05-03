from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal
from django.core.paginator import Paginator
import json

from eduweb.models import (
    ApplicationPayment,
    Subscription,
    CourseApplication,
    StaffPayroll,
)

from .forms import (
    SubscriptionFilterForm,
    DateRangeForm,
    PayrollCreateForm,
    PayrollFilterForm,
    PayrollStatusForm,
)


def is_finance_manager(user):
    """Allow only authenticated finance-role users"""
    return (
        user.is_authenticated
        and hasattr(user, 'profile')
        and user.profile.role == 'finance'
    )


# ==================== DASHBOARD ====================

@login_required
@user_passes_test(is_finance_manager)
def finance_dashboard(request):
    """Finance dashboard — analytics and summary across all modules"""

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

    # ── Subscriptions ─────────────────────────────────────────────────────
    active_subscriptions = Subscription.objects.filter(status='active').count()
    active_subs_in_range = Subscription.objects.filter(
        status='active',
        start_date__range=[start_date, end_date],
    )
    subscription_revenue = sum(sub.plan.price for sub in active_subs_in_range)

    # ── Fee payments (FeePayment model — guarded import) ──────────────────
    fee_revenue = Decimal('0.00')
    recent_fee_payments = []
    try:
        from eduweb.models import FeePayment
        fee_qs = FeePayment.objects.filter(
            created_at__range=[start_date, end_date]
        )
        fee_revenue = (
            fee_qs.filter(status='success')
            .aggregate(Sum('amount'))['amount__sum']
            or Decimal('0.00')
        )
        recent_fee_payments = (
            fee_qs.select_related('user', 'fee')
            .order_by('-created_at')[:15]
        )
    except (ImportError, Exception):
        pass  # FeePayment model not available — degrade gracefully

    # ── Required / outstanding payments (AllRequiredPayments model) ───────
    required_payments_count = 0
    required_payments_total = Decimal('0.00')
    overdue_required_count = 0
    all_required_payments = []
    try:
        from eduweb.models import AllRequiredPayments
        req_qs = AllRequiredPayments.objects.filter(
            is_active=True
        ).select_related('program', 'course', 'academic_session')

        required_payments_count = req_qs.count()
        required_payments_total = (
            req_qs.aggregate(Sum('amount'))['amount__sum']
            or Decimal('0.00')
        )
        overdue_required_count = req_qs.filter(
            due_date__lt=today
        ).count()
        all_required_payments = req_qs.order_by('due_date')
    except (ImportError, Exception):
        pass  # Model not available — degrade gracefully

    # ── Recent application payments ───────────────────────────────────────
    recent_app_payments = (
        ApplicationPayment.objects.select_related(
            'application__user',
            'application__program',
        )
        .filter(application__isnull=False)
        .order_by('-created_at')[:15]
    )

    # ── Currency symbol from system config ────────────────────────────────
    currency_symbol = '$'
    try:
        from eduweb.models import SystemConfig
        cfg = SystemConfig.objects.first()
        if cfg and hasattr(cfg, 'currency_symbol') and cfg.currency_symbol:
            currency_symbol = cfg.currency_symbol
    except (ImportError, Exception):
        pass

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
        'subscription_revenue': subscription_revenue,

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

        # Subscriptions
        'active_subscriptions': active_subscriptions,

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

@login_required
@user_passes_test(is_finance_manager)
def subscription_list(request):
    """List all subscriptions with filtering"""

    filter_form = SubscriptionFilterForm(request.GET or None)

    subscriptions = Subscription.objects.select_related(
        'user', 'plan'
    ).order_by('-start_date')

    if filter_form.is_valid():
        cd = filter_form.cleaned_data

        if cd.get('status'):
            subscriptions = subscriptions.filter(status=cd['status'])

        if cd.get('plan'):
            subscriptions = subscriptions.filter(plan=cd['plan'])

        if cd.get('search'):
            term = cd['search']
            subscriptions = subscriptions.filter(
                Q(user__username__icontains=term)
                | Q(user__email__icontains=term)
                | Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
            )

    active_subs = subscriptions.filter(status='active')
    mrr = sum(sub.plan.price for sub in active_subs)

    context = {
        'filter_form': filter_form,
        'subscriptions': subscriptions,
        'total_subscriptions': subscriptions.count(),
        'active_subscriptions': active_subs.count(),
        'cancelled_subscriptions': subscriptions.filter(
            status='cancelled'
        ).count(),
        'expired_subscriptions': subscriptions.filter(
            status='expired'
        ).count(),
        'mrr': mrr,
    }

    return render(request, 'finance/subscription_list.html', context)


# ==================== PAYROLL ====================

@login_required
@user_passes_test(is_finance_manager)
def payroll_management(request):
    """Payroll list + create modal"""

    if request.method == 'POST':
        form = PayrollCreateForm(request.POST, request.FILES)
        if form.is_valid():
            payroll = form.save(commit=False)
            payroll.created_by = request.user
            payroll.save()

            for i in range(1, 6):
                file = request.FILES.get(f'attachment_file_{i}')
                name = request.POST.get(f'attachment_name_{i}', '')
                if file:
                    setattr(payroll, f'attachment_{i}', file)
                    if name:
                        setattr(payroll, f'attachment_{i}_name', name)

            payroll.save()

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

    payroll = get_object_or_404(
        StaffPayroll.objects.select_related(
            'staff', 'created_by', 'approved_by'
        ),
        payroll_reference=payroll_reference,
    )

    if request.method == 'POST':
        status_form = PayrollStatusForm(request.POST, instance=payroll)
        if status_form.is_valid():
            updated = status_form.save(commit=False)
            if (
                updated.payment_status == 'paid'
                and payroll.payment_status != 'paid'
            ):
                updated.approved_by = request.user
                updated.approved_at = timezone.now()
            updated.save()
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
        for i in range(1, 6):
            f = getattr(payroll, f'attachment_{i}')
            if f:
                f.delete(save=False)
        payroll.delete()
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