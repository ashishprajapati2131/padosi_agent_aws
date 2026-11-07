"""Admin routes served by views/export.py."""
from django.urls import path

from ..views.export import (
    index as export_index,
    export_agents,
    export_leads,
    export_contacts,
    export_subscriptions,
    export_reviews,
    export_pending,
)

urlpatterns = [
    path("admin/export/",                   export_index,              name="export_index"),
    path("admin/export/agents/",            export_agents,             name="export_agents"),
    path("admin/export/leads/",             export_leads,              name="export_leads"),
    path("admin/export/contacts/",          export_contacts,           name="export_contacts"),
    path("admin/export/subscriptions/",     export_subscriptions,      name="export_subscriptions"),
    path("admin/export/reviews/",           export_reviews,            name="export_reviews"),
    path("admin/export/pending/",           export_pending,            name="export_pending"),
]
