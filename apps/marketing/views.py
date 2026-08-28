from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import F
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.eduweb.models import AuditLog

from .forms import LeadForm, LeadMessageForm
from .models import Lead, LeadActivity, LeadMessage
from .permissions import is_marketing_admin, marketing_required


# =============================================================================
# DASHBOARD
# =============================================================================

@marketing_required
def dashboard(request):
    admin_view = is_marketing_admin(request.user)
    base_qs = Lead.objects.all() if admin_view else Lead.objects.filter(marketer=request.user)

    status_counts = [
        (value, label, base_qs.filter(status=value).count())
        for value, label in Lead.STATUS_CHOICES
    ]
    recent_leads = base_qs.select_related('marketer').order_by('-created_at')[:10]
    recent_activities = (
        LeadActivity.objects.filter(lead__in=base_qs)
        .select_related('lead', 'marketer')
        .order_by('-created_at')[:10]
    )

    if admin_view:
        # Unread = sent by the channel's own marketer, not yet seen by admin.
        unread_count = LeadMessage.objects.filter(is_read=False, sender_id=F('marketer_id')).count()
    else:
        unread_count = (
            LeadMessage.objects.filter(marketer=request.user, is_read=False)
            .exclude(sender=request.user).count()
        )

    return render(request, 'marketing/dashboard.html', {
        'status_counts': status_counts,
        'recent_leads': recent_leads,
        'recent_activities': recent_activities,
        'unread_message_count': unread_count,
        'is_marketing_admin': admin_view,
        'total_leads': base_qs.count(),
    })


# =============================================================================
# LEADS
# =============================================================================

@marketing_required
def lead_list(request):
    admin_view = is_marketing_admin(request.user)
    qs = Lead.objects.select_related('marketer') if admin_view else Lead.objects.filter(marketer=request.user)

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    selected_marketer = request.GET.get('marketer', '') if admin_view else ''
    if selected_marketer:
        qs = qs.filter(marketer_id=selected_marketer)

    return render(request, 'marketing/lead_list.html', {
        'leads': qs.order_by('-created_at'),
        'is_marketing_admin': admin_view,
        'status_choices': Lead.STATUS_CHOICES,
        'marketers': User.objects.filter(profile__role='marketer').order_by('username') if admin_view else None,
        'selected_status': status,
        'selected_marketer': selected_marketer,
        'form': LeadForm(),
    })


@marketing_required
def lead_create(request):
    """"Add Lead" is a modal on lead_list.html, not a standalone page — this
    view exists purely to handle that modal's POST. On success it redirects
    to lead_list (the modal's JS detects the redirect and reloads); on
    validation failure it re-renders just the fields partial, which the
    modal's JS swaps in without a full navigation. Mirrors
    apps/management/views.py::institution_partner_create."""
    if request.method != 'POST':
        return redirect('marketing:lead_list')

    admin_view = is_marketing_admin(request.user)
    marketer_user = request.user
    if admin_view:
        chosen = request.POST.get('marketer')
        if chosen:
            marketer_user = get_object_or_404(User, pk=chosen, profile__role='marketer')

    form = LeadForm(request.POST)
    if form.is_valid():
        lead = form.save(commit=False)
        lead.marketer = marketer_user
        lead.save()
        LeadActivity.objects.create(
            lead=lead, marketer=request.user, note='Lead created.', status_at_time=lead.status,
        )
        AuditLog.objects.create(
            user=request.user, action='create', model_name='Lead',
            object_id=str(lead.pk), description=f'Created lead: {lead}',
        )
        messages.success(request, 'Lead created.')
        return redirect('marketing:lead_list')

    return render(request, 'marketing/_lead_form_fields.html', {
        'form': form, 'lead': None, 'is_marketing_admin': admin_view,
        'marketers': User.objects.filter(profile__role='marketer').order_by('username') if admin_view else None,
    })


@marketing_required
def lead_edit(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    admin_view = is_marketing_admin(request.user)
    if not admin_view and lead.marketer_id != request.user.id:
        raise Http404

    if request.method == 'POST':
        form = LeadForm(request.POST, instance=lead)
        if form.is_valid():
            form.save()
            LeadActivity.objects.create(
                lead=lead, marketer=request.user, note='Lead details updated.', status_at_time=lead.status,
            )
            AuditLog.objects.create(
                user=request.user, action='update', model_name='Lead',
                object_id=str(lead.pk), description=f'Updated lead: {lead}',
            )
            messages.success(request, 'Lead updated.')
            return redirect('marketing:lead_list')
    else:
        form = LeadForm(instance=lead)

    return render(request, 'marketing/_lead_form_fields.html', {
        'form': form, 'lead': lead, 'is_marketing_admin': admin_view,
        'marketers': User.objects.filter(profile__role='marketer').order_by('username') if admin_view else None,
    })


@marketing_required
def lead_detail(request, pk):
    lead = get_object_or_404(Lead.objects.select_related('marketer'), pk=pk)
    admin_view = is_marketing_admin(request.user)
    if not admin_view and lead.marketer_id != request.user.id:
        raise Http404

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_note':
            note = request.POST.get('note', '').strip()
            if note:
                LeadActivity.objects.create(
                    lead=lead, marketer=request.user, note=note, status_at_time=lead.status,
                )
                messages.success(request, 'Note added.')
        elif action == 'change_status':
            new_status = request.POST.get('status')
            if new_status in dict(Lead.STATUS_CHOICES) and new_status != lead.status:
                lead.status = new_status
                lead.save(update_fields=['status', 'updated_at'])
                LeadActivity.objects.create(
                    lead=lead, marketer=request.user,
                    note=f'Status changed to {lead.get_status_display()}.', status_at_time=new_status,
                )
                messages.success(request, 'Status updated.')
        return redirect('marketing:lead_detail', pk=pk)

    return render(request, 'marketing/lead_detail.html', {
        'lead': lead,
        'activities': lead.activities.select_related('marketer').all(),
        'status_choices': Lead.STATUS_CHOICES,
        'is_marketing_admin': admin_view,
    })


# =============================================================================
# CHAT — shared by the per-lead row modal, lead_detail's inline panel, and
# the general (no-lead) chat page/list. See apps/marketing/models.py::
# LeadMessage for why one channel per marketer covers both cases.
# =============================================================================

def _resolve_channel(request, lead_id, marketer_id):
    """Returns (marketer_user, lead_or_None), or None if the current user
    isn't allowed to address that channel."""
    admin_view = is_marketing_admin(request.user)
    lead = None
    if lead_id:
        lead = get_object_or_404(Lead, pk=lead_id)
        marketer_user = lead.marketer
    elif marketer_id:
        marketer_user = get_object_or_404(User, pk=marketer_id, profile__role='marketer')
    else:
        marketer_user = request.user

    if not admin_view and marketer_user.id != request.user.id:
        return None
    return marketer_user, lead


@marketing_required
@require_GET
def chat_messages(request):
    resolved = _resolve_channel(request, request.GET.get('lead'), request.GET.get('marketer'))
    if resolved is None:
        return HttpResponseForbidden()
    marketer_user, lead = resolved

    after_id = int(request.GET.get('after') or 0)
    new_messages = list(
        LeadMessage.objects.filter(marketer=marketer_user, lead=lead, id__gt=after_id)
        .select_related('sender').order_by('created_at')
    )

    unread_ids = [m.id for m in new_messages if m.sender_id != request.user.id and not m.is_read]
    if unread_ids:
        LeadMessage.objects.filter(id__in=unread_ids).update(is_read=True)

    return JsonResponse({'messages': [
        {
            'id': m.id,
            'sender_name': m.sender.get_full_name() or m.sender.username,
            'is_mine': m.sender_id == request.user.id,
            'body': m.body,
            'created_at': m.created_at.strftime('%b %d, %I:%M %p'),
        }
        for m in new_messages
    ]})


@marketing_required
@require_POST
def chat_send(request):
    resolved = _resolve_channel(request, request.POST.get('lead'), request.POST.get('marketer'))
    if resolved is None:
        return HttpResponseForbidden()
    marketer_user, lead = resolved

    form = LeadMessageForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    msg = LeadMessage.objects.create(
        marketer=marketer_user, lead=lead, sender=request.user, body=form.cleaned_data['body'],
    )
    return JsonResponse({
        'id': msg.id,
        'sender_name': msg.sender.get_full_name() or msg.sender.username,
        'is_mine': True,
        'body': msg.body,
        'created_at': msg.created_at.strftime('%b %d, %I:%M %p'),
    })


@marketing_required
def chat(request):
    admin_view = is_marketing_admin(request.user)
    if admin_view:
        marketer_id = request.GET.get('marketer')
        if not marketer_id:
            return redirect('marketing:chat_list')
        channel_marketer = get_object_or_404(User, pk=marketer_id, profile__role='marketer')
    else:
        channel_marketer = request.user

    return render(request, 'marketing/chat.html', {
        'channel_marketer': channel_marketer,
        'is_marketing_admin': admin_view,
    })


@marketing_required
def chat_list(request):
    """"Messages" — every open conversation, not just one row per marketer.
    A marketer can have several simultaneous threads (general chat + one
    per lead they've messaged about); each is its own row here so admin
    can jump straight into any of them and continue it, rather than only
    ever landing on whichever thread happened to be most recently active."""
    if not is_marketing_admin(request.user):
        return redirect('marketing:chat')

    conversations = []
    marketers_with_messages = set()
    for marketer_user in User.objects.filter(profile__role='marketer').order_by('username'):
        messages_qs = LeadMessage.objects.filter(marketer=marketer_user).select_related('lead')
        lead_ids = messages_qs.order_by().values_list('lead_id', flat=True).distinct()
        for lead_id in lead_ids:
            marketers_with_messages.add(marketer_user.pk)
            thread = messages_qs.filter(lead_id=lead_id)
            last_message = thread.order_by('-created_at').first()
            conversations.append({
                'marketer': marketer_user,
                'lead': last_message.lead,
                'last_message': last_message,
                'unread_count': thread.filter(is_read=False, sender=marketer_user).count(),
            })

    conversations.sort(key=lambda c: c['last_message'].created_at, reverse=True)

    # Marketers with no messages at all yet still get a (message-less) row,
    # so admin can discover and start a conversation with them.
    empty_marketers = (
        User.objects.filter(profile__role='marketer')
        .exclude(pk__in=marketers_with_messages)
        .order_by('username')
    )
    for marketer_user in empty_marketers:
        conversations.append({'marketer': marketer_user, 'lead': None, 'last_message': None, 'unread_count': 0})

    return render(request, 'marketing/chat_list.html', {'rows': conversations})
