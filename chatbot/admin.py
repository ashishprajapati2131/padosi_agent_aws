from django.contrib import admin
from .models import ChatSession, ChatMessage, LatencyLog

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'created_at', 'updated_at')
    search_fields = ('session_id',)

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'role', 'timestamp', 'tool_name')
    list_filter = ('role', 'timestamp')
    search_fields = ('session__session_id', 'content')

@admin.register(LatencyLog)
class LatencyLogAdmin(admin.ModelAdmin):
    list_display = ('endpoint', 'total_time', 'time_to_first_token', 'created_at')
    list_filter = ('endpoint', 'created_at')
