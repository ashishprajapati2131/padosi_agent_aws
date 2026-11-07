"""Admin routes served by views/system.py."""
from django.urls import path

from apps.admin_panel.views.system import (
    health,
    clear_cache,
    purge_cloudflare,
    save_cloudflare_settings,
    logs,
    api_logs,
    backups,
    run_backup,
    run_maintenance_jobs,
    download_backup,
)

urlpatterns = [
    path("admin/system/health/", health, name="admin_system_health"),
    path("admin/system/clear-cache/", clear_cache, name="admin_system_clear_cache"),
    path("admin/system/purge-cloudflare/", purge_cloudflare, name="admin_system_purge_cloudflare"),
    path("admin/system/save-cloudflare/", save_cloudflare_settings, name="admin_system_save_cloudflare"),
    path("admin/system/logs/", logs, name="admin_system_logs"),
    path("admin/system/api-logs/", api_logs, name="admin_system_api_logs"),
    path("admin/system/backups/", backups, name="admin_system_backups"),
    path("admin/system/backups/run/", run_backup, name="admin_system_run_backup"),
    path("admin/system/run-jobs/", run_maintenance_jobs, name="admin_system_run_jobs"),
    path("admin/system/backups/download/<str:filename>/", download_backup, name="admin_system_download_backup"),
]
