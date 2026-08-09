# Support App — Integration Guide

## 1. Add to INSTALLED_APPS (settings.py)
```python
INSTALLED_APPS = [
    ...
    'support',
]
```

## 2. Add Context Processor (settings.py)
```python
TEMPLATES = [{
    ...
    'OPTIONS': {
        'context_processors': [
            ...
            'support.context_processors.support_context',  # ADD THIS
        ],
    },
}]
```

## 3. Add URL (project/urls.py)
```python
from django.urls import path, include

urlpatterns = [
    ...
    path('support/', include('support.urls', namespace='support')),
]
```

## 4. Run Migrations
```bash
python manage.py makemigrations support
python manage.py migrate
```

## 5. Drop-in Sidebar (base.html)
Inside the sidebar `<nav>` block, where the existing Support submenu is, ADD:
```django
{% include 'support/includes/sidebar_support_menu.html' %}
```

Permission-aware: renders only for superuser, is_staff, role='admin', role='support'.

## 6. Create SLA Policies (via Django Admin or Support > SLA menu)
Recommended defaults:
- Low: response 8h, resolution 72h
- Medium: response 4h, resolution 24h
- High: response 2h, resolution 8h
- Critical: response 30min, resolution 4h

## 7. Role Check
The app uses `user.profile.role` with values: 'admin', 'support'
- 'support' role: access dashboard, tickets, KB, FAQs, canned responses, chats, announcements
- 'admin' / superuser: all of the above + SLA, departments, agents, audit log

## Security
- All views protected by @support_required or @support_admin_required
- CSRF on all forms
- Immutable audit log (save() raises on update)
- File uploads: UUID-renamed, size-validated (10MB), extension-whitelisted
- All DB queries use select_related / prefetch_related for performance
- No raw SQL — all ORM
- Pagination on all lists

## App Structure
support/
├── models.py          # 15 models: Ticket, KB, FAQ, SLA, Chat, Audit, etc.
├── views.py           # 30+ views covering all LMS support scenarios
├── urls.py            # 25+ URL patterns
├── admin.py           # Full Django admin for all models
├── permissions.py     # Role decorators + IP helper
├── context_processors.py  # Sidebar badge counts
├── apps.py
└── templates/support/
    ├── dashboard.html         # KPI + charts + leaderboard
    ├── ticket_list.html       # Filtered list + pagination
    ├── ticket_detail.html     # Thread + modals (status/assign/escalate)
    ├── ticket_create.html     # Staff-side ticket creation
    ├── analytics.html         # Full analytics with 5 charts + agent table
    ├── kb_list.html           # KB article grid
    ├── kb_article_detail.html # Article reader + vote
    ├── kb_article_form.html   # Create/Edit article
    ├── faq_list.html          # FAQ accordion + add modal
    ├── canned_list.html       # Canned response manager
    ├── sla_list.html          # SLA policy manager (admin)
    ├── department_list.html   # Department cards (admin)
    ├── agent_list.html        # Agent workload cards (admin)
    ├── chat_list.html         # Chat session viewer
    ├── announcement_list.html # Support announcements
    ├── audit_log.html         # Immutable audit trail (admin)
    └── includes/
        └── sidebar_support_menu.html  # Drop-in sidebar block
