"""Admin routes served by views/pincode_heatmap.py."""
from django.urls import path

from ..views import pincode_heatmap

urlpatterns = [
    path("admin/pincode-heatmap/",                  pincode_heatmap.pincode_heatmap_index, name="admin_pincode_heatmap"),
    path("admin/pincode-heatmap/toggle-flag/",      pincode_heatmap.toggle_heatmap_flag,   name="admin_toggle_heatmap_flag"),
    path("admin/pincode-heatmap/lookup/",           pincode_heatmap.pincode_lookup,        name="admin_pincode_heatmap_lookup"),
]
