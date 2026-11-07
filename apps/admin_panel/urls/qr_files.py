"""Admin routes served by views/qr_files.py."""
from django.urls import path

from ..views.qr_files import (
    qr_files_index,
    qr_files_store,
    qr_files_update,
    qr_files_destroy,
    qr_files_download,
)

urlpatterns = [
    path("admin/qr-files/", qr_files_index, name="admin_qr_files_index"),
    path("admin/qr-files/upload/", qr_files_store, name="admin_qr_files_store"),
    path("admin/qr-files/<int:id>/update/", qr_files_update, name="admin_qr_files_update"),
    path("admin/qr-files/<int:id>/delete/", qr_files_destroy, name="admin_qr_files_delete"),
    path("d/<str:code>/", qr_files_download, name="qr_download"),
]
