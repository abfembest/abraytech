"""
support/urls.py
"""
from django.urls import path
from . import views

app_name = 'support'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Self-service — the single "Help & Support" page shared by every role
    path('submit/', views.submit_ticket, name='submit_ticket'),

    # Tickets
    path('tickets/', views.ticket_list, name='ticket_list'),
    path('tickets/create/', views.ticket_create, name='ticket_create'),
    path('tickets/<str:ticket_id>/', views.ticket_detail, name='ticket_detail'),

    # Knowledge Base
    path('kb/', views.kb_list, name='kb_list'),
    path('kb/create/', views.kb_article_create, name='kb_article_create'),
    path('kb/<slug:slug>/', views.kb_article_detail, name='kb_article_detail'),
    path('kb/<slug:slug>/edit/', views.kb_article_edit, name='kb_article_edit'),

    # FAQs
    path('faqs/', views.faq_list, name='faq_list'),
    path('faqs/create/', views.faq_create, name='faq_create'),
    path('faqs/<int:faq_id>/delete/', views.faq_delete, name='faq_delete'),

    # Canned Responses
    path('canned/', views.canned_list, name='canned_list'),
    path('canned/create/', views.canned_create, name='canned_create'),
    path('canned/<int:pk>/delete/', views.canned_delete, name='canned_delete'),

    # SLA
    path('sla/', views.sla_list, name='sla_list'),
    path('sla/save/', views.sla_save, name='sla_save'),

    # Departments
    path('departments/', views.department_list, name='department_list'),
    path('departments/save/', views.department_save, name='department_save'),
    path('departments/<int:pk>/save/', views.department_save, name='department_save_edit'),
    path('departments/<int:pk>/toggle-active/', views.department_toggle_active, name='department_toggle_active'),

    # Agents
    path('agents/', views.agent_list, name='agent_list'),
    path('agents/<int:pk>/toggle-available/', views.agent_toggle_available, name='agent_toggle_available'),

    # Analytics
    path('analytics/', views.analytics, name='analytics'),

    # Chat
    path('chats/', views.chat_list, name='chat_list'),

    # Announcements
    path('announcements/', views.announcement_list, name='announcement_list'),
    path('announcements/create/', views.announcement_create, name='announcement_create'),
    path('announcements/<int:pk>/delete/', views.announcement_delete, name='announcement_delete'),

    # Audit Log
    path('audit/', views.audit_log, name='audit_log'),

    # AJAX / API
    path('api/stats/', views.api_ticket_stats, name='api_stats'),
    path('api/canned/<int:pk>/', views.api_canned_response, name='api_canned'),
    path('api/kb/<int:pk>/vote/', views.api_kb_article_vote, name='api_kb_vote'),
]