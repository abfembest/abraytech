"""
support/admin.py
Django admin registrations for all support models.
"""
from django.contrib import admin
from django.utils.html import format_html
from apps.eduweb.models import SupportTicket, TicketReply
from .models import (
    SLAPolicy, SupportDepartment, SupportTicketExtra, TicketAttachment,
    TicketHistory, TicketEscalation, TicketFeedback, KBCategory, KBArticle,
    FAQCategory, FAQ, CannedResponse, ChatSession, ChatMessage,
    AgentProfile, SupportAnnouncement, SupportAuditLog,
)


@admin.register(SLAPolicy)
class SLAPolicyAdmin(admin.ModelAdmin):
    list_display = ['name', 'priority', 'first_response_hours', 'resolution_hours', 'escalation_hours', 'is_active']
    list_filter = ['priority', 'is_active']
    ordering = ['priority']


@admin.register(SupportDepartment)
class SupportDepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'head', 'is_active', 'open_ticket_count']
    list_filter = ['is_active']
    filter_horizontal = ['members']
    prepopulated_fields = {'slug': ['name']}

    def open_ticket_count(self, obj):
        return obj.open_ticket_count
    open_ticket_count.short_description = 'Open Tickets'


class TicketReplyInline(admin.TabularInline):
    model = TicketReply
    extra = 0
    readonly_fields = ['author', 'created_at']
    fields = ['author', 'body', 'is_internal', 'is_system', 'created_at']


class TicketAttachmentInline(admin.TabularInline):
    model = TicketAttachment
    extra = 0
    readonly_fields = ['uploaded_by', 'original_name', 'file_size', 'created_at']




    def subject_short(self, obj):
        return obj.subject[:60]
    subject_short.short_description = 'Subject'

    def is_overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color:red;font-weight:bold;">OVERDUE</span>')
        return '—'
    is_overdue_display.short_description = 'SLA'



@admin.register(SupportTicketExtra)
class SupportTicketExtraAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'department', 'sla_policy', 'source', 'is_escalated', 'due_at', 'sla_breach_status']
    list_filter = ['is_escalated', 'source', 'sla_breach_status']
    raw_id_fields = ['ticket']

@admin.register(TicketFeedback)
class TicketFeedbackAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'rating', 'submitted_by', 'created_at']
    list_filter = ['rating']
    readonly_fields = ['ticket', 'submitted_by', 'created_at']


@admin.register(KBCategory)
class KBCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'order', 'is_active', 'article_count']
    prepopulated_fields = {'slug': ['name']}
    list_editable = ['order', 'is_active']


@admin.register(KBArticle)
class KBArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'status', 'author', 'view_count', 'helpful_count', 'updated_at']
    list_filter = ['status', 'category', 'is_featured', 'is_pinned']
    search_fields = ['title', 'body', 'tags']
    prepopulated_fields = {'slug': ['title']}
    readonly_fields = ['view_count', 'helpful_count', 'not_helpful_count', 'created_at', 'updated_at']


@admin.register(FAQCategory)
class FAQCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'order', 'is_active']
    prepopulated_fields = {'slug': ['name']}


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ['question_short', 'category', 'is_published', 'order']
    list_filter = ['category', 'is_published']
    search_fields = ['question', 'answer']

    def question_short(self, obj):
        return obj.question[:80]
    question_short.short_description = 'Question'


@admin.register(CannedResponse)
class CannedResponseAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'use_count', 'is_active', 'created_by']
    list_filter = ['category', 'is_active']
    search_fields = ['title', 'body']


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'student', 'agent', 'status', 'rating', 'started_at', 'ended_at']
    list_filter = ['status']
    readonly_fields = ['session_id', 'started_at']


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'department', 'is_available', 'max_tickets', 'current_load', 'average_rating', 'total_resolved']
    list_filter = ['is_available', 'department']

    def current_load(self, obj):
        return f"{obj.current_load}/{obj.max_tickets}"
    current_load.short_description = 'Load'


@admin.register(SupportAnnouncement)
class SupportAnnouncementAdmin(admin.ModelAdmin):
    list_display = ['title', 'is_active', 'is_pinned', 'target_role', 'expires_at', 'created_by', 'created_at']
    list_filter = ['is_active', 'is_pinned']


@admin.register(SupportAuditLog)
class SupportAuditLogAdmin(admin.ModelAdmin):
    list_display = ['actor', 'action', 'target_type', 'target_id', 'ip_address', 'created_at']
    list_filter = ['action', 'target_type']
    search_fields = ['actor__username', 'description', 'target_id']
    readonly_fields = list_display + ['description', 'user_agent']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
