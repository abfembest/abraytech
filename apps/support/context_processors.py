from django.utils import timezone
from apps.eduweb.models import SupportTicket
from .models import SupportTicketExtra, ChatSession

OPEN_STATUSES = ['open', 'in_progress', 'waiting_response']
_SUPPORT_COUNTS_TTL = 30


def support_context(request):
    if not request.user.is_authenticated:
        return {}
    u = request.user
    if not (u.is_superuser or u.is_staff or getattr(getattr(u, 'profile', None), 'role', '') in ('admin', 'support')):
        return {}

    from django.core.cache import cache as _cache

    cache_key = 'support_badge_counts'
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        now = timezone.now()
        open_qs = SupportTicket.objects.filter(status__in=OPEN_STATUSES)
        result = {
            'support_stats': {
                'total_open': open_qs.count(),
                'escalated': SupportTicketExtra.objects.filter(is_escalated=True, ticket__status__in=OPEN_STATUSES).count(),
                'sla_breached': SupportTicketExtra.objects.filter(due_at__lt=now, ticket__status__in=OPEN_STATUSES).count(),
                'open_chats': ChatSession.objects.filter(status='active').count(),
                'unassigned': open_qs.filter(assigned_to__isnull=True).count(),
            }
        }
        _cache.set(cache_key, result, _SUPPORT_COUNTS_TTL)
        return result
    except Exception:
        return {'support_stats': {}}
