"""Admin routes served by views/wa_bot_admin.py."""
from django.urls import path

from ..views.wa_bot_admin import (
    wa_bot_sessions_list,
    wa_bot_logs_list,
    wa_bot_dashboard,
    wa_bot_security_status,
    wa_bot_toggle_service,
    wa_bot_toggle_lead_alerts,
    wa_bot_save_view_alerts,
    wa_bot_messages,
    wa_bot_broadcast,
    wa_bot_broadcast_action,
    wa_bot_broadcast_progress,
    wa_bot_broadcast_templates,
    wa_bot_session_action,
    wa_bot_get_qr_ajax,
    wa_bot_send_test_message,
    wa_bot_reset_session,
    wa_bot_resend_credentials,
    wa_bot_save_config,
    wa_bot_sync_webhook,
    wa_bot_list_remote_sessions,
)

urlpatterns = [
    path("admin/wa_agent_bot/wabotsession/", wa_bot_sessions_list, name="admin_wa_bot_sessions"),
    path("admin/wa-bot/sessions/",           wa_bot_sessions_list, name="admin_wa_bot_sessions_alt"),
    path("admin/wa_agent_bot/wabotmessagelog/", wa_bot_logs_list, name="admin_wa_bot_logs"),
    path("admin/wa-bot/logs/",               wa_bot_logs_list, name="admin_wa_bot_logs_alt"),
    path("admin/whatsapp/", wa_bot_dashboard, name="admin_wa_dashboard"),
    path("admin/whatsapp/sessions/", wa_bot_sessions_list, name="admin_wa_sessions_list"),
    path("admin/whatsapp/logs/", wa_bot_logs_list, name="admin_wa_logs_list"),
    path("admin/whatsapp/security/", wa_bot_security_status, name="admin_wa_security_status"),
    path("admin/whatsapp/toggle-bot/", wa_bot_toggle_service, name="admin_wa_toggle_service"),
    # (removed /admin/whatsapp/toggle-service/: an unused alias that also stole the name
    #  admin_toggle_wa_bot_service from the Settings page toggle; B24)
    path("admin/whatsapp/toggle-lead-alerts/", wa_bot_toggle_lead_alerts, name="admin_wa_toggle_lead_alerts"),
    path("admin/whatsapp/view-alerts/", wa_bot_save_view_alerts, name="admin_wa_save_view_alerts"),
    path("admin/whatsapp/messages/", wa_bot_messages, name="admin_wa_messages"),
    path("admin/whatsapp/broadcast/", wa_bot_broadcast, name="admin_wa_broadcast"),
    path("admin/whatsapp/broadcast/<int:broadcast_id>/action/", wa_bot_broadcast_action, name="admin_wa_broadcast_action"),
    path("admin/whatsapp/broadcast/progress/", wa_bot_broadcast_progress, name="admin_wa_broadcast_progress"),
    path("admin/whatsapp/broadcast/templates/", wa_bot_broadcast_templates, name="admin_wa_broadcast_templates"),
    path("admin/whatsapp/session-action/", wa_bot_session_action, name="admin_wa_session_action"),
    path("admin/whatsapp/get-qr/", wa_bot_get_qr_ajax, name="admin_wa_get_qr_ajax"),
    path("admin/whatsapp/send-test/", wa_bot_send_test_message, name="admin_wa_send_test_message"),
    path("admin/whatsapp/reset-session/<int:session_id>/", wa_bot_reset_session, name="admin_wa_reset_session"),
    path("admin/whatsapp/resend-creds/<int:session_id>/", wa_bot_resend_credentials, name="admin_wa_resend_credentials"),
    path("admin/whatsapp/save-config/", wa_bot_save_config, name="admin_wa_save_config"),
    path("admin/whatsapp/sync-webhook/", wa_bot_sync_webhook, name="admin_wa_sync_webhook"),
    path("admin/whatsapp/list-sessions/", wa_bot_list_remote_sessions, name="admin_wa_list_remote_sessions"),
]
