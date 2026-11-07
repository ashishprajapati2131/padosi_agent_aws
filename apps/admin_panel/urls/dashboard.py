"""Admin routes served by views/dashboard.py."""
from django.urls import path

from ..views.dashboard import show_login_form, admin_login, admin_dashboard, admin_logout

urlpatterns = [
    path("admin/", show_login_form, name="admin_login"),
    path("admin/login/", show_login_form, name="admin_login_page"),
    path("admin/login/post/", admin_login, name="admin_login_post"),
    path("admin/dashboard/", admin_dashboard, name="admin_dashboard"),
    path("admin/logout/", admin_logout, name="admin_logout"),
]
