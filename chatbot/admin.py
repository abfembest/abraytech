from django.contrib import admin
from .models import ChatSession, ChatMessage, IntentResponse

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'email', 'started_at', 'last_activity', 'is_active')
    list_filter = ('is_active', 'started_at')
    search_fields = ('first_name', 'email')
    readonly_fields = ('started_at', 'last_activity')
    actions = ['close_sessions']

    def close_sessions(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} session(s) marked as closed.')
    close_sessions.short_description = "Close selected sessions"

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'sender', 'short_content', 'timestamp')
    list_filter = ('sender', 'timestamp')
    search_fields = ('content',)
    readonly_fields = ('timestamp',)

    def short_content(self, obj):
        return obj.content[:75] + '...' if len(obj.content) > 75 else obj.content
    short_content.short_description = 'Message preview'

@admin.register(IntentResponse)
class IntentResponseAdmin(admin.ModelAdmin):
    list_display = ('intent', 'response_text')
    search_fields = ('intent', 'response_text')