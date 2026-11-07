"""Admin routes served by views/reviews.py."""
from django.urls import path

from ..views.reviews import (
    reviews_index,
    toggle_review_approval,
    bulk_approve_reviews,
    delete_review,
)

urlpatterns = [
    path("admin/reviews/",                reviews_index,          name="admin_reviews_index"),
    path("admin/reviews/toggle-approval/", toggle_review_approval, name="admin_reviews_toggle_approval"),
    path("admin/reviews/bulk-approve/",   bulk_approve_reviews,   name="admin_reviews_bulk_approve"),
    path("admin/reviews/delete/",         delete_review,          name="admin_reviews_delete"),
]
