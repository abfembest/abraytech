from django.contrib import admin

# Register your models here.
# portfolio/admin.py
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Project, DashboardImage

class DashboardImageInline(admin.TabularInline):
    model = DashboardImage
    extra = 1
    fields = ('image', 'title', 'summary', 'order', 'preview')
    readonly_fields = ('preview',)
    
    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="80" style="border-radius: 6px;" />', obj.image.url)
        return "-"
    preview.short_description = "Preview"

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'client', 'created_at', 'image_count')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [DashboardImageInline]
    search_fields = ('name', 'client', 'description')
    
    def image_count(self, obj):
        return obj.dashboard_images.count()
    image_count.short_description = "Dashboard images"

@admin.register(DashboardImage)
class DashboardImageAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'order', 'created_at')
    list_filter = ('project', 'created_at')
    search_fields = ('title', 'summary')