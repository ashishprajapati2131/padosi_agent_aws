"""Admin routes served by views/users.py."""
from django.urls import path

from ..views.users import user_list, user_edit, user_update

urlpatterns = [
    path("admin/users/", user_list, name="admin_users"),
    path("admin/users/<int:user_id>/edit/", user_edit, name="admin_users_edit"),
    path("admin/users/<int:user_id>/update/", user_update, name="admin_users_update"),
]
