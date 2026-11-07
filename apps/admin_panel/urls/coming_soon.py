"""Admin routes served by views/coming_soon.py."""
from django.urls import path

from ..views.coming_soon import (
    coming_soon_index,
    save_coming_soon,
    save_feature,
    toggle_feature_status,
    delete_feature,
    reorder_features,
    seed_default_features,
    save_google_review_config,
    toggle_google_review_system,
)

urlpatterns = [
    path("admin/coming-soon/", coming_soon_index, name="admin_coming_soon_index"),
    path("admin/coming-soon/save/", save_coming_soon, name="admin_coming_soon_save"),
    path("admin/coming-soon/feature/save/", save_feature, name="admin_coming_soon_feature_save"),
    path("admin/coming-soon/feature/<int:id>/toggle/", toggle_feature_status, name="admin_coming_soon_feature_toggle"),
    path("admin/coming-soon/feature/<int:id>/delete/", delete_feature, name="admin_coming_soon_feature_delete"),
    path("admin/coming-soon/feature/reorder/", reorder_features, name="admin_coming_soon_feature_reorder"),
    path("admin/coming-soon/feature/seed/", seed_default_features, name="admin_coming_soon_feature_seed"),
    path("admin/coming-soon/google-review/save/", save_google_review_config, name="admin_google_review_config_save"),
    path("admin/coming-soon/google-review/toggle/", toggle_google_review_system, name="admin_google_review_toggle"),
]
