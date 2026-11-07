"""Admin routes served by views/pages.py."""
from django.urls import path

from ..views.pages import (
    pages_index,
    pages_create,
    pages_store,
    pages_edit,
    pages_update,
    pages_delete,
)

urlpatterns = [
    path('admin/pages/',                          pages_index,  name='admin_pages_index'),
    path('admin/pages/create/',                   pages_create, name='admin_pages_create'),
    path('admin/pages/store/',                    pages_store,  name='admin_pages_store'),
    path('admin/pages/<int:page_id>/edit/',        pages_edit,   name='admin_pages_edit'),
    path('admin/pages/<int:page_id>/update/',      pages_update, name='admin_pages_update'),
    path('admin/pages/<int:page_id>/delete/',      pages_delete, name='admin_pages_delete'),
]
