"""
support/views.py — uses eduweb.SupportTicket as the ticket model.

Field mapping from old support.Ticket → eduweb.SupportTicket:
  title        → subject
  created_by   → user
  status values: open, in_progress, waiting_response, resolved, closed
  priority values: low, normal, high, urgent  (no 'medium' / 'critical')
  category values: technical, account, course, payment, other
"""
from functools import wraps

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
import json
from django.db.models import Q, Count, Avg, F
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.paginator import Paginator
from datetime import timedelta

from apps.eduweb.models import SupportTicket, TicketReply, Notification
from .models import (
    SupportTicketExtra, SupportDepartment, SLAPolicy,
    TicketAttachment, TicketHistory, TicketEscalation, TicketFeedback,
    KBCategory, KBArticle, FAQCategory, FAQ, CannedResponse,
    ChatSession, AgentProfile, SupportAnnouncement, SupportAuditLog,
    CHAT_STATUS_CHOICES,
)
from .permissions import support_required, support_admin_required, get_client_ip


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

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


def require_permission(module, action, redirect_to='support:dashboard', skip_get=True):
    """
    Decorator mirroring management/instructor's helper of the same name.
    Denies the request unless _has_permission(request, module, action) is
    True. skip_get=True (default) only guards non-GET requests — pass
    skip_get=False for a read-only list/detail page whose sidebar link is
    already hidden by permissions.<module>.can_view, so the page itself
    must enforce it too rather than being reachable by direct URL.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            guarded = not skip_get or request.method != 'GET'
            if guarded and not _has_permission(request, module, action):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
                messages.error(request, 'You do not have permission to view this page.')
                if callable(redirect_to):
                    return redirect_to(request, *args, **kwargs)
                return redirect(redirect_to)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def _log(request, action, target_type='', target_id='', description=''):
    SupportAuditLog.objects.create(
        actor=request.user,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        description=description,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:300],
    )


def _get_or_create_extra(ticket):
    extra, _ = SupportTicketExtra.objects.get_or_create(ticket=ticket)
    return extra


def _parse_pk(value):
    """
    Safely coerce a POSTed id to int for use as a queryset pk lookup.
    Returns None on missing/non-numeric input instead of letting a raw
    ValueError from the ORM's pk-type coercion bubble up as a 500.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


OPEN_STATUSES = ['open', 'in_progress', 'waiting_response']
CLOSED_STATUSES = ['resolved', 'closed']

# Self-service ticket form (student.forms.StudentSupportTicketForm) offers finer-grained
# category/priority options than eduweb.SupportTicket itself supports — map them down.
SELF_SERVICE_CATEGORY_MAP = {
    'technical': 'technical', 'course': 'course', 'enrollment': 'course',
    'payment': 'payment', 'account': 'account', 'assignment': 'course',
    'quiz': 'course', 'certificate': 'other', 'other': 'other',
}
SELF_SERVICE_PRIORITY_MAP = {'low': 'low', 'medium': 'normal', 'high': 'high'}


# ─────────────────────────────────────────────────────────────────────────────
# Self-service ticket submission — the single "Help & Support" page shared by
# every role (student, instructor, finance, admin). Staff get the full console
# via the rest of this module; this is the one place any user lodges a ticket.
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def submit_ticket(request):
    from apps.student.forms import StudentSupportTicketForm

    if request.method == 'POST':
        action = request.POST.get('action', 'new_ticket')

        if action == 'reply':
            # A user replying to their own ticket's thread, from the modal on this same page.
            ticket = get_object_or_404(SupportTicket, ticket_id=request.POST.get('ticket_id'), user=request.user)
            body = request.POST.get('body', '').strip()
            if body and ticket.status not in CLOSED_STATUSES:
                reply = TicketReply.objects.create(ticket=ticket, author=request.user, message=body, is_internal_note=False)
                for f in request.FILES.getlist('attachments'):
                    if f.size <= 10 * 1024 * 1024:
                        TicketAttachment.objects.create(
                            ticket=ticket, reply=reply, uploaded_by=request.user,
                            file=f, original_name=f.name, file_size=f.size,
                        )
                if ticket.status == 'waiting_response':
                    ticket.status = 'in_progress'
                    ticket.save(update_fields=['status'])
                if ticket.assigned_to:
                    Notification.objects.create(
                        user=ticket.assigned_to, notification_type='system',
                        title='New reply on assigned ticket',
                        message=f'{request.user.get_full_name() or request.user.username} replied on "{ticket.subject}" ({ticket.ticket_id}).',
                        link='/support/tickets/%s/' % ticket.ticket_id,
                    )
                messages.success(request, 'Your reply has been sent.')
            return redirect(f"{reverse('support:submit_ticket')}#ticket-{ticket.pk}")

        form = StudentSupportTicketForm(request.POST, request.FILES)
        if form.is_valid():
            ticket = SupportTicket.objects.create(
                user=request.user,
                subject=form.cleaned_data['subject'],
                description=form.cleaned_data['message'],
                category=SELF_SERVICE_CATEGORY_MAP.get(form.cleaned_data['category'], 'other'),
                priority=SELF_SERVICE_PRIORITY_MAP.get(form.cleaned_data['priority'], 'normal'),
            )
            role = getattr(getattr(request.user, 'profile', None), 'role', '') or 'portal'
            SupportTicketExtra.objects.create(ticket=ticket, source='portal', tags=role)
            attachment = form.cleaned_data.get('attachment')
            if attachment:
                TicketAttachment.objects.create(
                    ticket=ticket, uploaded_by=request.user, file=attachment,
                    original_name=attachment.name, file_size=attachment.size,
                )
            messages.success(
                request,
                f'Your support ticket ({ticket.ticket_id}) has been submitted! '
                'Our team will get back to you within 24-48 hours.'
            )
            return redirect('support:submit_ticket')
    else:
        form = StudentSupportTicketForm()

    my_tickets = SupportTicket.objects.filter(user=request.user).select_related('assigned_to').prefetch_related(
        'replies__author', 'replies__attachments'
    ).order_by('-created_at')[:20]
    faqs = FAQ.objects.filter(is_published=True).select_related('category').order_by('category__order', 'order')

    return render(request, 'support/submit_ticket.html', {
        'form': form,
        'my_tickets': my_tickets,
        'faqs': faqs,
        'page_title': 'Help & Support',
    })


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
def dashboard(request):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    all_tickets = SupportTicket.objects.all()
    open_qs = all_tickets.filter(status__in=OPEN_STATUSES)

    total_open = open_qs.count()
    urgent_count = open_qs.filter(priority='urgent').count()
    resolved_today = all_tickets.filter(status='resolved', resolved_at__gte=today_start).count()

    # SLA — tickets with due_at in the past and still open
    sla_breached = SupportTicketExtra.objects.filter(
        due_at__lt=now, ticket__status__in=OPEN_STATUSES
    ).count()
    sla_at_risk = SupportTicketExtra.objects.filter(
        due_at__gt=now,
        due_at__lt=now + timedelta(hours=2),
        ticket__status__in=OPEN_STATUSES
    ).select_related('ticket').order_by('due_at')[:5]

    waiting_user = all_tickets.filter(status='waiting_response').count()
    unassigned = open_qs.filter(assigned_to__isnull=True).count()
    escalated = SupportTicketExtra.objects.filter(
        is_escalated=True, ticket__status__in=OPEN_STATUSES
    ).count()

    # 14-day volume
    fourteen_days = [now - timedelta(days=i) for i in range(13, -1, -1)]
    chart_labels = [d.strftime('%b %d') for d in fourteen_days]
    chart_created = []
    chart_resolved = []
    daily_data = []
    for day in fourteen_days:
        day_end = day.replace(hour=23, minute=59, second=59)
        day_start = day.replace(hour=0, minute=0, second=0)
        created_count = all_tickets.filter(created_at__range=(day_start, day_end)).count()
        resolved_count = all_tickets.filter(status='resolved', resolved_at__range=(day_start, day_end)).count()
        chart_created.append(created_count)
        chart_resolved.append(resolved_count)
        daily_data.append({
            'date': day.strftime('%b %d'),
            'created': created_count,
            'resolved': resolved_count,
        })

    # Priority breakdown
    priority_counts = {p: open_qs.filter(priority=p).count() for p in ['low', 'normal', 'high', 'urgent']}
    priority_data = [
        {'priority': p, 'count': priority_counts[p]}
        for p in ['low', 'normal', 'high', 'urgent']
    ]

    # Recent tickets
    recent_tickets = all_tickets.select_related('user', 'assigned_to', 'extra').order_by('-created_at')[:10]
    my_tickets = all_tickets.filter(
        assigned_to=request.user, status__in=OPEN_STATUSES
    ).select_related('user', 'extra').order_by('-created_at')[:8]

    # CSAT
    avg_csat = TicketFeedback.objects.aggregate(avg=Avg('rating'))['avg']

    # Agent leaderboard
    agents = (
        User.objects.filter(
            assigned_tickets__status='resolved',
            assigned_tickets__resolved_at__gte=now - timedelta(days=30)
        )
        .annotate(resolved_count=Count('assigned_tickets'))
        .annotate(avg_csat=Avg('assigned_tickets__feedback__rating'))
        .order_by('-resolved_count')[:5]
    )

    recent_feedback = TicketFeedback.objects.select_related('ticket', 'submitted_by').order_by('-created_at')[:5]
    kb_count = KBArticle.objects.filter(status='published').count()
    resolved_week = all_tickets.filter(
        status='resolved',
        resolved_at__gte=now - timedelta(days=7)
    ).count()
    stats = {
        'total_open': total_open,
        'urgent': urgent_count,
        'resolved_today': resolved_today,
        'new_today': all_tickets.filter(created_at__gte=today_start).count(),
        'avg_rating': round(avg_csat, 1) if avg_csat else 0,
        'agents_online': AgentProfile.objects.filter(is_available=True).count(),
        'waiting_response': waiting_user,
        'unassigned': unassigned,
        'escalated': escalated,
        'sla_breached': sla_breached,
        'resolved_week': resolved_week,
        'kb_articles': kb_count,
    }

    return render(request, 'support/dashboard.html', {
        'stats': stats,
        'sla_at_risk': sla_at_risk,
        'chart_labels': chart_labels,
        'chart_created': chart_created,
        'chart_resolved': chart_resolved,
        'daily_data': json.dumps(daily_data),
        'priority_data': json.dumps(priority_data),
        'priority_counts': priority_counts,
        'recent_tickets': recent_tickets,
        'my_tickets': my_tickets,
        'agents': agents,
        'recent_feedback': recent_feedback,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Ticket List
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
@require_permission('support_tickets', 'can_view', skip_get=False)
def ticket_list(request):
    qs = SupportTicket.objects.select_related('user', 'assigned_to', 'extra').order_by('-created_at')

    # Filters
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    category_filter = request.GET.get('category', '')
    quick = request.GET.get('quick', '')

    if search:
        qs = qs.filter(
            Q(ticket_id__icontains=search) |
            Q(subject__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__email__icontains=search)
        )
    if status_filter:
        if status_filter == 'escalated':
            qs = qs.filter(extra__is_escalated=True)
        elif status_filter == 'pending_user':
            qs = qs.filter(status='waiting_response')
        else:
            qs = qs.filter(status=status_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    if category_filter:
        qs = qs.filter(category=category_filter)

    if quick == 'mine':
        qs = qs.filter(assigned_to=request.user)
    elif quick == 'open':
        qs = qs.filter(status__in=OPEN_STATUSES)
    elif quick == 'escalated':
        qs = qs.filter(extra__is_escalated=True)
    elif quick == 'sla':
        qs = qs.filter(extra__due_at__lt=timezone.now(), status__in=OPEN_STATUSES)
    elif quick == 'urgent':
        qs = qs.filter(priority='urgent')
    elif quick == 'waiting':
        qs = qs.filter(status='waiting_response')
    elif quick == 'unassigned':
        qs = qs.filter(assigned_to__isnull=True, status__in=OPEN_STATUSES)

    paginator = Paginator(qs, 25)
    tickets = paginator.get_page(request.GET.get('page'))
    filters = {
        'search': search,
        'status': status_filter or ('open' if quick == 'open' else 'escalated' if quick == 'escalated' else ''),
        'priority': priority_filter,
        'category': category_filter,
        'mine': quick == 'mine',
        'sla': 'breached' if quick == 'sla' else '',
    }

    return render(request, 'support/ticket_list.html', {
        'tickets': tickets,
        'search': search,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'category_filter': category_filter,
        'quick': quick,
        'filters': filters,
        'from_models': {
            'status_choices': SupportTicket.STATUS_CHOICES,
            'priority_choices': SupportTicket.PRIORITY_CHOICES,
            'category_choices': SupportTicket.CATEGORY_CHOICES,
        },
        'status_choices': SupportTicket.STATUS_CHOICES,
        'priority_choices': SupportTicket.PRIORITY_CHOICES,
        'category_choices': SupportTicket.CATEGORY_CHOICES,
        'total_count': qs.count(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Ticket Detail
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
@require_permission('support_tickets', 'can_view', skip_get=False)
def ticket_detail(request, ticket_id):
    ticket = get_object_or_404(SupportTicket.objects.select_related('user', 'assigned_to'), ticket_id=ticket_id)
    extra = _get_or_create_extra(ticket)

    # Increment view count
    SupportTicketExtra.objects.filter(pk=extra.pk).update(view_count=extra.view_count + 1)

    if request.method == 'POST':
        action = request.POST.get('action')

        # Reply is a "create" action, everything else here mutates the
        # ticket's own fields ("edit") — matches ticket_detail.html's
        # permissions.support_tickets.can_create/can_edit button gating.
        required_action = 'can_create' if action == 'reply' else 'can_edit'
        if not _has_permission(request, 'support_tickets', required_action):
            messages.error(request, 'You do not have permission to perform that action on this ticket.')
            return redirect('support:ticket_detail', ticket_id=ticket_id)

        if action == 'reply':
            body = request.POST.get('body', '').strip()
            is_internal = request.POST.get('is_internal') == '1'
            if body:
                reply = TicketReply.objects.create(
                    ticket=ticket,
                    author=request.user,
                    message=body,
                    is_internal_note=is_internal,
                )
                # Mark first response
                if not extra.first_response_at and not is_internal:
                    extra.first_response_at = timezone.now()
                    extra.save(update_fields=['first_response_at'])

                # Handle attachments
                for f in request.FILES.getlist('attachments'):
                    if f.size <= 10 * 1024 * 1024:
                        TicketAttachment.objects.create(
                            ticket=ticket,
                            reply=reply,
                            uploaded_by=request.user,
                            file=f,
                            original_name=f.name,
                            file_size=f.size,
                        )
                # Auto-move to in_progress if open
                if ticket.status == 'open':
                    ticket.status = 'in_progress'
                    ticket.save(update_fields=['status'])
                TicketHistory.objects.create(
                    ticket=ticket, changed_by=request.user,
                    field_name='reply', new_value='Reply added',
                    note='Internal' if is_internal else ''
                )
                if not is_internal and ticket.user_id != request.user.id:
                    Notification.objects.create(
                        user=ticket.user, notification_type='system',
                        title='Support team replied to your ticket',
                        message=f'Your ticket "{ticket.subject}" ({ticket.ticket_id}) has a new reply.',
                        link=f"{reverse('support:submit_ticket')}#ticket-{ticket.pk}",
                    )
                _log(request, 'ticket_reply', 'SupportTicket', ticket.ticket_id, f'{"Internal note" if is_internal else "Reply"} added')
                messages.success(request, 'Reply posted successfully.')
            return redirect('support:ticket_detail', ticket_id=ticket_id)

        elif action == 'update_status':
            old_status = ticket.status
            new_status = request.POST.get('status')
            valid = [s[0] for s in SupportTicket.STATUS_CHOICES]
            if new_status in valid:
                ticket.status = new_status
                if new_status == 'resolved':
                    ticket.resolved_at = timezone.now()
                ticket.save()
                TicketHistory.objects.create(
                    ticket=ticket, changed_by=request.user,
                    field_name='status', old_value=old_status, new_value=new_status
                )
                if ticket.user_id != request.user.id:
                    Notification.objects.create(
                        user=ticket.user, notification_type='system',
                        title='Your support ticket status changed',
                        message=f'"{ticket.subject}" ({ticket.ticket_id}) is now {ticket.get_status_display()}.',
                        link=f"{reverse('support:submit_ticket')}#ticket-{ticket.pk}",
                    )
                _log(request, 'status_change', 'SupportTicket', ticket.ticket_id, f'{old_status} → {new_status}')
                messages.success(request, f'Status updated to {new_status}.')
            return redirect('support:ticket_detail', ticket_id=ticket_id)

        elif action == 'assign':
            agent_pk = _parse_pk(request.POST.get('agent_id'))
            old_agent = ticket.assigned_to
            if agent_pk is not None:
                agent = get_object_or_404(User, pk=agent_pk)
                ticket.assigned_to = agent
                if ticket.status == 'open':
                    ticket.status = 'in_progress'
            else:
                ticket.assigned_to = None
            ticket.save()
            TicketHistory.objects.create(
                ticket=ticket, changed_by=request.user,
                field_name='assigned_to',
                old_value=str(old_agent) if old_agent else '',
                new_value=str(ticket.assigned_to) if ticket.assigned_to else 'Unassigned',
            )
            _log(request, 'assign', 'SupportTicket', ticket.ticket_id)
            messages.success(request, 'Ticket assignment updated.')
            return redirect('support:ticket_detail', ticket_id=ticket_id)

        elif action == 'escalate':
            reason = request.POST.get('reason', 'other')
            notes = request.POST.get('notes', '')
            escalated_to_pk = _parse_pk(request.POST.get('escalated_to_id'))
            escalated_to = User.objects.filter(pk=escalated_to_pk).first() if escalated_to_pk is not None else None
            TicketEscalation.objects.create(
                ticket=ticket, escalated_by=request.user,
                escalated_to=escalated_to,
                reason=reason, notes=notes,
                level=extra.escalation_level + 1,
            )
            extra.is_escalated = True
            extra.escalation_level += 1
            extra.save(update_fields=['is_escalated', 'escalation_level'])
            ticket.status = 'in_progress'
            ticket.save(update_fields=['status'])
            TicketHistory.objects.create(
                ticket=ticket, changed_by=request.user,
                field_name='escalated', new_value='true', note=notes
            )
            _log(request, 'escalate', 'SupportTicket', ticket.ticket_id, notes)
            messages.warning(request, 'Ticket escalated.')
            return redirect('support:ticket_detail', ticket_id=ticket_id)

        elif action == 'update_priority':
            old_priority = ticket.priority
            new_priority = request.POST.get('priority')
            valid_priorities = [p[0] for p in SupportTicket.PRIORITY_CHOICES]
            if new_priority in valid_priorities:
                ticket.priority = new_priority
                ticket.save(update_fields=['priority'])
                TicketHistory.objects.create(
                    ticket=ticket, changed_by=request.user,
                    field_name='priority', old_value=old_priority, new_value=new_priority
                )
                messages.success(request, f'Priority updated to {new_priority}.')
            return redirect('support:ticket_detail', ticket_id=ticket_id)

        elif action == 'reopen':
            ticket.status = 'open'
            ticket.save(update_fields=['status'])
            extra.reopen_count += 1
            extra.save(update_fields=['reopen_count'])
            TicketHistory.objects.create(
                ticket=ticket, changed_by=request.user,
                field_name='status', old_value='closed', new_value='open', note='Reopened'
            )
            messages.info(request, 'Ticket reopened.')
            return redirect('support:ticket_detail', ticket_id=ticket_id)

    replies = ticket.replies.select_related('author').all()
    attachments = ticket.attachments.select_related('uploaded_by').all()
    history = ticket.history.select_related('changed_by').all()
    escalations = ticket.escalations.select_related('escalated_by', 'escalated_to').all()
    feedback = TicketFeedback.objects.filter(ticket=ticket).first()
    agents = User.objects.filter(
        Q(is_staff=True) | Q(profile__role__in=['admin', 'support'])
    ).select_related('profile').order_by('first_name')
    canned_responses = CannedResponse.objects.filter(is_active=True).order_by('title')
    escalation_reasons = TicketEscalation._meta.get_field('reason').choices
    admin_agents = agents.filter(profile__role='admin')
    response_time_hours = None
    if extra.first_response_at:
        response_time_hours = round((extra.first_response_at - ticket.created_at).total_seconds() / 3600, 1)
    resolution_time_hours = None
    if ticket.resolved_at:
        resolution_time_hours = round((ticket.resolved_at - ticket.created_at).total_seconds() / 3600, 1)

    return render(request, 'support/ticket_detail.html', {
        'ticket': ticket,
        'extra': extra,
        'replies': replies,
        'attachments': attachments,
        'history': history,
        'escalations': escalations,
        'feedback': feedback,
        'agents': agents,
        'admin_agents': admin_agents,
        'canned_responses': canned_responses,
        'status_choices': SupportTicket.STATUS_CHOICES,
        'priority_choices': SupportTicket.PRIORITY_CHOICES,
        'escalation_reasons': escalation_reasons,
        'response_time_hours': response_time_hours,
        'resolution_time_hours': resolution_time_hours,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Ticket Create
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
def ticket_create(request):
    if request.method == 'POST':
        if not _has_permission(request, 'support_tickets', 'can_create'):
            messages.error(request, 'You do not have permission to create tickets.')
            return redirect('support:ticket_create')

        user_id = request.POST.get('user_id')
        subject = request.POST.get('subject', '').strip()
        description = request.POST.get('description', '').strip()
        category = request.POST.get('category', 'other')
        priority = request.POST.get('priority', 'normal')
        source = request.POST.get('source', 'portal')
        assigned_to_id = request.POST.get('assigned_to_id')
        department_id = request.POST.get('department_id')

        if not subject or not description:
            messages.error(request, 'Subject and description are required.')
        else:
            created_user = request.user
            user_pk = _parse_pk(user_id)
            if user_pk is not None:
                created_user = get_object_or_404(User, pk=user_pk)

            assigned_to = None
            assigned_pk = _parse_pk(assigned_to_id)
            if assigned_pk is not None:
                assigned_to = User.objects.filter(pk=assigned_pk).first()

            ticket = SupportTicket.objects.create(
                user=created_user,
                subject=subject,
                description=description,
                category=category,
                priority=priority,
                status='open' if not assigned_to else 'in_progress',
                assigned_to=assigned_to,
            )
            extra = SupportTicketExtra.objects.create(
                ticket=ticket,
                source=source,
                tags=request.POST.get('tags', ''),
            )
            department_pk = _parse_pk(department_id)
            if department_pk is not None:
                dept = SupportDepartment.objects.filter(pk=department_pk).first()
                if dept:
                    extra.department = dept
                    extra.save(update_fields=['department'])

            for f in request.FILES.getlist('attachments'):
                if f.size <= 10 * 1024 * 1024:
                    TicketAttachment.objects.create(
                        ticket=ticket, uploaded_by=request.user,
                        file=f, original_name=f.name, file_size=f.size,
                    )

            _log(request, 'ticket_create', 'SupportTicket', ticket.ticket_id, subject)
            messages.success(request, f'Ticket {ticket.ticket_id} created.')
            return redirect('support:ticket_detail', ticket_id=ticket.ticket_id)

    students = User.objects.all().order_by('first_name', 'last_name')
    agents = User.objects.filter(
        Q(is_staff=True) | Q(profile__role__in=['admin', 'support'])
    ).order_by('first_name')
    departments = SupportDepartment.objects.filter(is_active=True)

    return render(request, 'support/ticket_create.html', {
        'students': students,
        'agents': agents,
        'departments': departments,
        'category_choices': SupportTicket.CATEGORY_CHOICES,
        'priority_choices': SupportTicket.PRIORITY_CHOICES,
        'source_choices': SupportTicketExtra.SOURCE_CHOICES,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Base
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
@require_permission('support_knowledge_base', 'can_view', skip_get=False)
def kb_list(request):
    qs = KBArticle.objects.select_related('category', 'author').all()
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    cat_filter = request.GET.get('category', '')
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(tags__icontains=search))
    if status_filter:
        qs = qs.filter(status=status_filter)
    if cat_filter:
        qs = qs.filter(category_id=cat_filter)
    paginator = Paginator(qs, 18)
    articles = paginator.get_page(request.GET.get('page'))
    return render(request, 'support/kb_list.html', {
        'articles': articles,
        'categories': KBCategory.objects.filter(is_active=True),
        'search': search,
        'status_filter': status_filter,
        'cat_filter': cat_filter,
        'total_published': KBArticle.objects.filter(status='published').count(),
        'total_draft': KBArticle.objects.filter(status='draft').count(),
    })


@login_required
@support_required
@require_permission('support_knowledge_base', 'can_view', skip_get=False)
def kb_article_detail(request, slug):
    article = get_object_or_404(KBArticle, slug=slug)
    KBArticle.objects.filter(pk=article.pk).update(view_count=article.view_count + 1)
    related = article.related_articles.filter(status='published')[:4]
    return render(request, 'support/kb_article_detail.html', {'article': article, 'related': related})


@login_required
@support_required
def kb_article_create(request):
    """Created via the 'New Article' modal on kb_list.html (POST-only)."""
    if request.method == 'POST':
        if not _has_permission(request, 'support_knowledge_base', 'can_create'):
            messages.error(request, 'You do not have permission to create knowledge base articles.')
            return redirect('support:kb_list')

        title = request.POST.get('title', '').strip()
        cat_pk = _parse_pk(request.POST.get('category_id'))
        if not title or cat_pk is None:
            messages.error(request, 'A title and a valid category are required.')
            return redirect('support:kb_list')
        cat = get_object_or_404(KBCategory, pk=cat_pk)

        article = KBArticle.objects.create(
            category=cat,
            title=title,
            summary=request.POST.get('summary', '').strip(),
            body=request.POST.get('body', '').strip(),
            status=request.POST.get('status', 'draft'),
            tags=request.POST.get('tags', '').strip(),
            is_featured='is_featured' in request.POST,
            is_pinned='is_pinned' in request.POST,
            author=request.user,
        )
        messages.success(request, 'Article created.')
        return redirect('support:kb_article_detail', slug=article.slug)
    return redirect('support:kb_list')


@login_required
@support_required
def kb_article_edit(request, slug):
    if request.method == 'GET' and not _has_permission(request, 'support_knowledge_base', 'can_view'):
        messages.error(request, 'You do not have permission to view knowledge base articles.')
        return redirect('support:kb_list')

    article = get_object_or_404(KBArticle, slug=slug)
    if request.method == 'POST':
        if not _has_permission(request, 'support_knowledge_base', 'can_edit'):
            messages.error(request, 'You do not have permission to edit knowledge base articles.')
            return redirect('support:kb_article_detail', slug=slug)

        title = request.POST.get('title', '').strip()
        cat_pk = _parse_pk(request.POST.get('category_id'))
        if not title or cat_pk is None:
            messages.error(request, 'A title and a valid category are required.')
            return redirect('support:kb_article_edit', slug=slug)
        cat = get_object_or_404(KBCategory, pk=cat_pk)

        article.category = cat
        article.title = title
        article.summary = request.POST.get('summary', '').strip()
        article.body = request.POST.get('body', '').strip()
        article.status = request.POST.get('status', 'draft')
        article.tags = request.POST.get('tags', '').strip()
        article.is_featured = 'is_featured' in request.POST
        article.is_pinned = 'is_pinned' in request.POST
        article.save()
        messages.success(request, 'Article updated.')
        return redirect('support:kb_article_detail', slug=article.slug)
    return render(request, 'support/kb_article_form.html', {
        'article': article,
        'categories': KBCategory.objects.filter(is_active=True),
        'page_title': f'Edit: {article.title}',
    })


# ─────────────────────────────────────────────────────────────────────────────
# FAQs
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
@require_permission('support_knowledge_base', 'can_view', skip_get=False)
def faq_list(request):
    search = request.GET.get('search', '')
    categories = FAQCategory.objects.filter(is_active=True).prefetch_related('faqs')
    if search:
        categories = categories.filter(
            Q(faqs__question__icontains=search) | Q(faqs__answer__icontains=search)
        ).distinct()
    return render(request, 'support/faq_list.html', {'categories': categories, 'search': search})


@login_required
@support_required
def faq_create(request):
    if request.method == 'POST':
        if not _has_permission(request, 'support_knowledge_base', 'can_create'):
            messages.error(request, 'You do not have permission to create FAQs.')
            return redirect('support:faq_list')

        question = request.POST.get('question', '').strip()
        answer = request.POST.get('answer', '').strip()
        cat_pk = _parse_pk(request.POST.get('category_id'))
        if not question or not answer or cat_pk is None:
            messages.error(request, 'A category, question and answer are required.')
            return redirect('support:faq_list')
        cat = get_object_or_404(FAQCategory, pk=cat_pk)
        order = _parse_pk(request.POST.get('order', 0)) or 0

        FAQ.objects.create(
            category=cat,
            question=question,
            answer=answer,
            order=order,
            created_by=request.user,
        )
        messages.success(request, 'FAQ added.')
    return redirect('support:faq_list')


@login_required
@support_required
def faq_delete(request, pk):
    if request.method == 'POST':
        if not _has_permission(request, 'support_knowledge_base', 'can_delete'):
            messages.error(request, 'You do not have permission to delete FAQs.')
            return redirect('support:faq_list')
        FAQ.objects.filter(pk=pk).delete()
        messages.success(request, 'FAQ deleted.')
    return redirect('support:faq_list')


# ─────────────────────────────────────────────────────────────────────────────
# Canned Responses
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
@require_permission('support_communications', 'can_view', skip_get=False)
def canned_list(request):
    search = request.GET.get('search', '')
    qs = CannedResponse.objects.filter(is_active=True)
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(body__icontains=search))
    return render(request, 'support/canned_list.html', {
        'canned': qs,
        'search': search,
        'category_choices': SupportTicket.CATEGORY_CHOICES,
    })


@login_required
@support_required
def canned_create(request):
    if request.method == 'POST':
        if not _has_permission(request, 'support_communications', 'can_create'):
            messages.error(request, 'You do not have permission to create canned responses.')
            return redirect('support:canned_list')
        CannedResponse.objects.create(
            title=request.POST.get('title', '').strip(),
            body=request.POST.get('body', '').strip(),
            category=request.POST.get('category', ''),
            created_by=request.user,
        )
        messages.success(request, 'Canned response created.')
    return redirect('support:canned_list')


@login_required
@support_required
def canned_delete(request, pk):
    if request.method == 'POST':
        if not _has_permission(request, 'support_communications', 'can_delete'):
            messages.error(request, 'You do not have permission to delete canned responses.')
            return redirect('support:canned_list')
        CannedResponse.objects.filter(pk=pk).delete()
        messages.success(request, 'Canned response deleted.')
    return redirect('support:canned_list')


# ─────────────────────────────────────────────────────────────────────────────
# SLA Policies (admin)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_admin_required
@require_permission('support_config', 'can_view', skip_get=False)
def sla_list(request):
    return render(request, 'support/sla_list.html', {
        'slas': SLAPolicy.objects.all(),
        'priority_choices': SupportTicket.PRIORITY_CHOICES,
    })


@login_required
@support_admin_required
def sla_save(request):
    if request.method == 'POST':
        if not _has_permission(request, 'support_config', 'can_create'):
            messages.error(request, 'You do not have permission to manage SLA policies.')
            return redirect('support:sla_list')

        priority = request.POST.get('priority')
        valid_priorities = [p[0] for p in SupportTicket.PRIORITY_CHOICES]
        if priority not in valid_priorities:
            messages.error(request, 'Please select a valid priority.')
            return redirect('support:sla_list')

        try:
            first_response_hours = int(request.POST.get('first_response_hours', 4))
            resolution_hours = int(request.POST.get('resolution_hours', 24))
            escalation_hours = int(request.POST.get('escalation_hours', 8))
        except (TypeError, ValueError):
            messages.error(request, 'SLA hours must be whole numbers.')
            return redirect('support:sla_list')

        SLAPolicy.objects.update_or_create(
            priority=priority,
            defaults={
                'name': request.POST.get('name', '').strip(),
                'first_response_hours': first_response_hours,
                'resolution_hours': resolution_hours,
                'escalation_hours': escalation_hours,
                'is_active': True,
            }
        )
        messages.success(request, 'SLA policy saved.')
    return redirect('support:sla_list')


# ─────────────────────────────────────────────────────────────────────────────
# Departments (admin)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_admin_required
@require_permission('support_config', 'can_view', skip_get=False)
def department_list(request):
    departments = SupportDepartment.objects.prefetch_related('members').annotate(
        ticket_count=Count('dept_tickets', filter=Q(dept_tickets__ticket__status__in=OPEN_STATUSES))
    )
    all_agents = User.objects.filter(
        Q(is_staff=True) | Q(profile__role__in=['admin', 'support'])
    ).order_by('first_name')
    return render(request, 'support/department_list.html', {
        'departments': departments,
        'all_agents': all_agents,
    })


@login_required
@support_admin_required
def department_save(request, pk=None):
    if request.method == 'POST':
        required_action = 'can_edit' if pk else 'can_create'
        if not _has_permission(request, 'support_config', required_action):
            messages.error(request, 'You do not have permission to manage support departments.')
            return redirect('support:department_list')

        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Department name is required.')
            return redirect('support:department_list')

        head_pk = _parse_pk(request.POST.get('head_id'))
        head = User.objects.filter(pk=head_pk).first() if head_pk is not None else None
        is_active = 'is_active' in request.POST

        if pk:
            dept = get_object_or_404(SupportDepartment, pk=pk)
            dept.name = name
            dept.email = request.POST.get('email', '').strip()
            dept.description = request.POST.get('description', '').strip()
            dept.head = head
            dept.is_active = is_active
            dept.save()
            _log(request, 'dept_update', 'SupportDepartment', dept.pk, name)
            messages.success(request, f'Department "{name}" updated.')
        else:
            dept = SupportDepartment.objects.create(
                name=name,
                email=request.POST.get('email', '').strip(),
                description=request.POST.get('description', '').strip(),
                head=head,
                is_active=is_active,
            )
            _log(request, 'dept_create', 'SupportDepartment', dept.pk, name)
            messages.success(request, f'Department "{name}" created.')
    return redirect('support:department_list')


@login_required
@support_admin_required
def department_toggle_active(request, pk):
    if request.method == 'POST':
        if not _has_permission(request, 'support_config', 'can_edit'):
            messages.error(request, 'You do not have permission to manage support departments.')
            return redirect('support:department_list')
        dept = get_object_or_404(SupportDepartment, pk=pk)
        dept.is_active = not dept.is_active
        dept.save(update_fields=['is_active'])
        _log(request, 'dept_toggle_active', 'SupportDepartment', dept.pk, f'is_active={dept.is_active}')
        messages.success(request, f'Department "{dept.name}" is now {"active" if dept.is_active else "inactive"}.')
    return redirect('support:department_list')


# ─────────────────────────────────────────────────────────────────────────────
# Agents (admin)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_admin_required
@require_permission('support_config', 'can_view', skip_get=False)
def agent_list(request):
    agents = User.objects.filter(
        Q(is_staff=True) | Q(profile__role__in=['admin', 'support'])
    ).order_by('first_name').annotate(
        open_count=Count('assigned_tickets', filter=Q(assigned_tickets__status__in=OPEN_STATUSES)),
        resolved_count=Count('assigned_tickets', filter=Q(assigned_tickets__status='resolved')),
        avg_csat=Avg('assigned_tickets__feedback__rating'),
    ).select_related('agent_profile', 'profile')
    return render(request, 'support/agent_list.html', {'agents': agents})


@login_required
@support_admin_required
def agent_toggle_available(request, pk):
    if request.method == 'POST':
        if not _has_permission(request, 'support_config', 'can_edit'):
            messages.error(request, 'You do not have permission to manage agents.')
            return redirect('support:agent_list')
        agent = get_object_or_404(User, pk=pk)
        profile, _ = AgentProfile.objects.get_or_create(user=agent)
        profile.is_available = not profile.is_available
        profile.save(update_fields=['is_available'])
        _log(request, 'agent_toggle_available', 'AgentProfile', profile.pk, f'is_available={profile.is_available}')
        messages.success(request, f'{agent.get_full_name() or agent.username} is now {"available" if profile.is_available else "unavailable"}.')
    return redirect('support:agent_list')


# ─────────────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
@require_permission('support_analytics', 'can_view', skip_get=False)
def analytics(request):
    period = request.GET.get('period', '30')
    days = int(period) if str(period).isdigit() else 30
    since = timezone.now() - timedelta(days=days)
    qs = SupportTicket.objects.filter(created_at__gte=since)

    total = qs.count()
    resolved = qs.filter(status='resolved').count()
    resolution_rate = round((resolved / total) * 100, 1) if total else 0
    avg_csat = TicketFeedback.objects.filter(created_at__gte=since).aggregate(avg=Avg('rating'))['avg']
    csat_count = TicketFeedback.objects.filter(created_at__gte=since).count()
    avg_per_day = round(total / days, 1) if days else 0

    sla_total = SupportTicketExtra.objects.filter(ticket__created_at__gte=since, due_at__isnull=False).count()
    sla_ok = SupportTicketExtra.objects.filter(
        ticket__created_at__gte=since,
        due_at__isnull=False,
        ticket__resolved_at__lte=F('due_at')
    ).count()

    # Daily trend
    daily = []
    for i in range(days - 1, -1, -1):
        day = timezone.now() - timedelta(days=i)
        ds = day.replace(hour=0, minute=0, second=0)
        de = day.replace(hour=23, minute=59, second=59)
        daily.append({
            'label': day.strftime('%b %d'),
            'created': qs.filter(created_at__range=(ds, de)).count(),
            'resolved': qs.filter(status='resolved', resolved_at__range=(ds, de)).count(),
        })

    category_stats = list(qs.values('category').annotate(n=Count('id')).order_by('-n'))
    status_stats = list(qs.values('status').annotate(n=Count('id')).order_by('-n'))
    priority_stats = list(qs.values('priority').annotate(n=Count('id')).order_by('-n'))
    by_dept = list(SupportTicketExtra.objects.filter(
        ticket__created_at__gte=since
    ).values('department__name').annotate(count=Count('id')).order_by('-count'))

    agents = User.objects.filter(
        Q(is_staff=True) | Q(profile__role__in=['admin', 'support'])
    ).annotate(
        total=Count('assigned_tickets', filter=Q(assigned_tickets__created_at__gte=since)),
        resolved=Count('assigned_tickets', filter=Q(
            assigned_tickets__created_at__gte=since,
            assigned_tickets__status='resolved'
        )),
        csat=Avg('assigned_tickets__feedback__rating'),
    ).filter(total__gt=0).order_by('-resolved')

    return render(request, 'support/analytics.html', {
        'days': days,
        'period': period,
        'total_in_period': total,
        'resolved_in_period': resolved,
        'resolution_rate': resolution_rate,
        'csat_avg': round(avg_csat, 1) if avg_csat else 0,
        'avg_per_day': avg_per_day,
        'csat_count': csat_count,
        'sla_compliance': round((sla_ok / sla_total) * 100, 1) if sla_total else 100,
        'daily': daily,
        'daily_trend': json.dumps(daily),
        'by_category': json.dumps([{'category': item['category'], 'count': item['n']} for item in category_stats]),
        'by_status': json.dumps([{'status': item['status'], 'count': item['n']} for item in status_stats]),
        'by_priority': json.dumps([{'priority': item['priority'], 'count': item['n']} for item in priority_stats]),
        'by_dept': json.dumps([{'department__name': item['department__name'] or 'Unassigned', 'count': item['count']} for item in by_dept]),
        'agent_perf': agents,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Chat Sessions
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
@require_permission('support_communications', 'can_view', skip_get=False)
def chat_list(request):
    status_filter = request.GET.get('status', '')
    qs = ChatSession.objects.select_related('student', 'agent').order_by('-started_at')
    if status_filter:
        qs = qs.filter(status=status_filter)
    paginator = Paginator(qs, 25)
    sessions = paginator.get_page(request.GET.get('page'))
    return render(request, 'support/chat_list.html', {
        'sessions': sessions,
        'status_filter': status_filter,
        'status_choices': CHAT_STATUS_CHOICES,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Announcements
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
@require_permission('support_communications', 'can_view', skip_get=False)
def announcement_list(request):
    return render(request, 'support/announcement_list.html', {
        'announcements': SupportAnnouncement.objects.select_related('created_by').all(),
    })


@login_required
@support_required
def announcement_create(request):
    if request.method == 'POST':
        if not _has_permission(request, 'support_communications', 'can_create'):
            messages.error(request, 'You do not have permission to publish announcements.')
            return redirect('support:announcement_list')

        title = request.POST.get('title', '').strip()
        body = request.POST.get('body', '').strip()
        if not title or not body:
            messages.error(request, 'Title and body are required.')
            return redirect('support:announcement_list')

        expires_raw = request.POST.get('expires_at', '').strip()
        expires_at = None
        if expires_raw:
            expires_at = parse_datetime(expires_raw)
            if expires_at is None:
                messages.error(request, 'Invalid expiry date/time.')
                return redirect('support:announcement_list')
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at)

        SupportAnnouncement.objects.create(
            title=title,
            body=body,
            target_role=request.POST.get('target_role', ''),
            is_pinned='is_pinned' in request.POST,
            expires_at=expires_at,
            created_by=request.user,
        )
        messages.success(request, 'Announcement published.')
    return redirect('support:announcement_list')


@login_required
@support_required
def announcement_delete(request, pk):
    if request.method == 'POST':
        if not _has_permission(request, 'support_communications', 'can_delete'):
            messages.error(request, 'You do not have permission to delete announcements.')
            return redirect('support:announcement_list')
        SupportAnnouncement.objects.filter(pk=pk).delete()
        messages.success(request, 'Announcement deleted.')
    return redirect('support:announcement_list')


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_admin_required
@require_permission('support_config', 'can_view', skip_get=False)
def audit_log(request):
    qs = SupportAuditLog.objects.select_related('actor').all()
    search = request.GET.get('search', '')
    action_filter = request.GET.get('action', '')
    if search:
        qs = qs.filter(Q(description__icontains=search) | Q(target_id__icontains=search))
    if action_filter:
        qs = qs.filter(action__icontains=action_filter)
    paginator = Paginator(qs, 50)
    logs = paginator.get_page(request.GET.get('page'))
    return render(request, 'support/audit_log.html', {
        'logs': logs,
        'search': search,
        'action_filter': action_filter,
    })


# ─────────────────────────────────────────────────────────────────────────────
# AJAX APIs
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@support_required
def api_ticket_stats(request):
    now = timezone.now()
    open_qs = SupportTicket.objects.filter(status__in=OPEN_STATUSES)
    return JsonResponse({
        'total_open': open_qs.count(),
        'urgent': open_qs.filter(priority='urgent').count(),
        'sla_breached': SupportTicketExtra.objects.filter(
            due_at__lt=now, ticket__status__in=OPEN_STATUSES
        ).count(),
        'unassigned': open_qs.filter(assigned_to__isnull=True).count(),
        'escalated': SupportTicketExtra.objects.filter(
            is_escalated=True, ticket__status__in=OPEN_STATUSES
        ).count(),
        'open_chats': ChatSession.objects.filter(status='active').count(),
    })


@login_required
@support_required
def api_canned_response(request, pk):
    if not _has_permission(request, 'support_communications', 'can_view'):
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)

    cr = get_object_or_404(CannedResponse, pk=pk, is_active=True)
    CannedResponse.objects.filter(pk=pk).update(use_count=cr.use_count + 1)
    return JsonResponse({'ok': True, 'body': cr.body, 'title': cr.title})


@login_required
@support_required
def api_kb_article_vote(request, pk):
    article = get_object_or_404(KBArticle, pk=pk)
    vote = request.POST.get('vote')
    if vote == 'yes':
        KBArticle.objects.filter(pk=pk).update(helpful_count=article.helpful_count + 1)
    elif vote == 'no':
        KBArticle.objects.filter(pk=pk).update(not_helpful_count=article.not_helpful_count + 1)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('support:kb_article_detail', slug=article.slug)
