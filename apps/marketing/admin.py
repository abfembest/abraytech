from django.contrib import admin

from .models import Lead, LeadActivity, LeadMessage


class LeadActivityInline(admin.TabularInline):
    model = LeadActivity
    extra = 0
    readonly_fields = ('marketer', 'note', 'status_at_time', 'created_at')


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'marketer', 'source', 'status', 'created_at')
    list_filter = ('status', 'source', 'marketer')
    search_fields = ('name', 'organization', 'email', 'phone')
    inlines = [LeadActivityInline]


@admin.register(LeadActivity)
class LeadActivityAdmin(admin.ModelAdmin):
    list_display = ('lead', 'marketer', 'status_at_time', 'created_at')
    list_filter = ('status_at_time',)
    search_fields = ('lead__name', 'note')


@admin.register(LeadMessage)
class LeadMessageAdmin(admin.ModelAdmin):
    list_display = ('marketer', 'lead', 'sender', 'is_read', 'created_at')
    list_filter = ('is_read',)
    search_fields = ('marketer__username', 'sender__username', 'body')
