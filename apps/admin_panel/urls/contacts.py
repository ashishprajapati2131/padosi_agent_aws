"""Admin routes served by views/contacts.py."""
from django.urls import path

from ..views.contacts import (
    contacts_index,
    contacts_show,
    contacts_update_status,
    contacts_delete,
    contacts_assign,
    contacts_set_priority,
    contacts_reply,
)

urlpatterns = [
    path("admin/contacts/",                       contacts_index,         name="admin_contacts_index"),
    path("admin/contacts/<int:submission_id>/",   contacts_show,          name="admin_contacts_show"),
    path("admin/contacts/update-status/",         contacts_update_status, name="admin_contacts_update_status"),
    path("admin/contacts/delete/",                contacts_delete,        name="admin_contacts_delete"),
    path("admin/contacts/assign/",                contacts_assign,        name="admin_contacts_assign"),
    path("admin/contacts/priority/",              contacts_set_priority,  name="admin_contacts_set_priority"),
    path("admin/contacts/reply/",                 contacts_reply,         name="admin_contacts_reply"),
]
