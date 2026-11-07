"""Admin routes served by views/security.py."""
from django.urls import path

from ..views.security import threat_logs, delete_threat_log, blocked_ips, block_ip, unblock_ip

urlpatterns = [
    path("admin/security/threat-logs/",                 threat_logs,        name="security_threat_logs"),
    path("admin/security/threat-logs/delete/",          delete_threat_log,  name="security_threat_logs_delete"),
    path("admin/security/blocked-ips/",                 blocked_ips,        name="security_blocked_ips"),
    path("admin/security/block-ip/",                    block_ip,           name="security_block_ip"),
    path("admin/security/blocked-ips/<int:ip_id>/unblock/", unblock_ip,     name="security_unblock_ip"),
]
