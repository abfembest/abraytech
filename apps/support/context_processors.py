from django.utils import timezone
from apps.eduweb.models import SupportTicket
from .models import SupportTicketExtra, ChatSession

OPEN_STATUSES = ['open', 'in_progress', 'waiting_response']

def support_context(request):
    if not request.user.is_authenticated:
        return {}
    u = request.user
    if not (u.is_superuser or u.is_staff or getattr(getattr(u, 'profile', None), 'role', '') in ('admin', 'support')):
        return {}
    try:
        now = timezone.now()
        open_qs = SupportTicket.objects.filter(status__in=OPEN_STATUSES)
        return {
            'support_stats': {
                'total_open': open_qs.count(),
                'escalated': SupportTicketExtra.objects.filter(is_escalated=True, ticket__status__in=OPEN_STATUSES).count(),
                'sla_breached': SupportTicketExtra.objects.filter(due_at__lt=now, ticket__status__in=OPEN_STATUSES).count(),
                'open_chats': ChatSession.objects.filter(status='active').count(),
                'unassigned': open_qs.filter(assigned_to__isnull=True).count(),
            }
        }
    except Exception:
        return {'support_stats': {}}
