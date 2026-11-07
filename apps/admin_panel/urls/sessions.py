"""Admin routes served by views/sessions.py."""
from django.urls import path

from ..views.sessions import sessions_index, sessions_revoke

urlpatterns = [
    path("admin/sessions/", sessions_index, name="admin_sessions_index"),
    path("admin/sessions/revoke/", sessions_revoke, name="admin_sessions_revoke"),
]
