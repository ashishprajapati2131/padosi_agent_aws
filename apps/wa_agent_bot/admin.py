"""
WhatsApp Agent Bot — Admin Panel Registration

Registers WaBotSession and WaBotMessageLog models in the Django admin
for easy monitoring and debugging of bot conversations.
"""

from django.contrib import admin
from .models import WaBotSession, WaBotMessageLog


class WaBotMessageLogInline(admin.TabularInline):
    model = WaBotMessageLog
    extra = 0
    readonly_fields = ('direction', 'content', 'state_at_time', 'created_at')
    ordering = ('-created_at',)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(WaBotSession)
class WaBotSessionAdmin(admin.ModelAdmin):
    list_display = (
        'phone_number',
        'state',
        'is_registered',
        'is_logged_in',
        'message_count',
        'last_message_at',
        'created_at',
    )
    list_filter = ('state', 'is_registered', 'is_logged_in')
    search_fields = ('phone_number',)
    readonly_fields = ('created_at', 'updated_at', 'message_count', 'last_message_at')
    inlines = [WaBotMessageLogInline]

    fieldsets = (
        ('Session Info', {
            'fields': ('phone_number', 'state', 'is_registered', 'is_logged_in'),
        }),
        ('Agent Link', {
            'fields': ('agent',),
        }),
        ('Data', {
            'fields': ('registration_data', 'session_context', 'generated_password'),
            'classes': ('collapse',),
        }),
        ('Activity', {
            'fields': ('message_count', 'last_message_at', 'created_at', 'updated_at'),
        }),
    )


@admin.register(WaBotMessageLog)
class WaBotMessageLogAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'direction', 'category', 'status', 'short_content', 'created_at')
    list_filter = ('direction', 'category', 'status')
    search_fields = ('phone_number', 'content')
    readonly_fields = ('session', 'phone_number', 'direction', 'category', 'status', 'error', 'content', 'state_at_time', 'created_at')

    def short_content(self, obj):
        return obj.content[:80] + '...' if len(obj.content) > 80 else obj.content
    short_content.short_description = 'Content'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
