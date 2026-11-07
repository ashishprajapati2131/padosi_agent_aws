"""Admin routes served by views/geocoding.py."""
from django.urls import path

from ..views.geocoding import (
    index as geocoding_index,
    geocode_single,
    geocode_batch,
    stats as geocoding_stats,
)

urlpatterns = [
    path("admin/geocoding-manager/",               geocoding_index,  name="admin_geocoding_index"),
    path("admin/geocoding-manager/single/",        geocode_single,   name="admin_geocoding_single"),
    path("admin/geocoding-manager/batch/",         geocode_batch,    name="admin_geocoding_batch"),
    path("admin/geocoding-manager/stats/",         geocoding_stats,  name="admin_geocoding_stats"),
]
