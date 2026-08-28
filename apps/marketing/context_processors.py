"""
apps/marketing/context_processors.py

Registered in settings.py's TEMPLATES context_processors, same as
apps/support/context_processors.py — injects the "Messages" sidebar badge
count (templates/management/base.html) for marketer/admin/superuser
accounts on every page, not just marketing pages.
"""
from django.db.models import F


def marketing_context(request):
    if not request.user.is_authenticated or not hasattr(request.user, 'profile'):
        return {}

    role = request.user.profile.role
    is_admin_view = request.user.is_superuser or role == 'admin'
    if not is_admin_view and role != 'marketer':
        return {}

    from .models import LeadMessage

    try:
        if is_admin_view:
            # Unread = sent by the channel's own marketer, not yet seen by admin.
            unread = LeadMessage.objects.filter(is_read=False, sender_id=F('marketer_id')).count()
        else:
            unread = (
                LeadMessage.objects.filter(marketer=request.user, is_read=False)
                .exclude(sender=request.user).count()
            )
    except Exception:
        unread = 0

    return {'marketing_unread_count': unread}
