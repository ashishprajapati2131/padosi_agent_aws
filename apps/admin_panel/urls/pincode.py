"""Admin routes served by views/pincode.py."""
from django.urls import path

from ..views.pincode import (
    index as pincode_index,
    upload as pincode_upload,
    import_data as pincode_import,
    get_districts as pincode_districts,
    sample_download as pincode_sample,
    export_data as pincode_export,
    delete_by_state as pincode_delete_state,
)

urlpatterns = [
    path("admin/pincode-manager/",                pincode_index,             name="admin_pincode_index"),
    path("admin/pincode-manager/upload/",         pincode_upload,            name="admin_pincode_upload"),
    path("admin/pincode-manager/import/",         pincode_import,            name="admin_pincode_import"),
    path("admin/pincode-manager/districts/",      pincode_districts,         name="admin_pincode_districts"),
    path("admin/pincode-manager/sample/",         pincode_sample,            name="admin_pincode_sample"),
    path("admin/pincode-manager/export/",         pincode_export,            name="admin_pincode_export"),
    path("admin/pincode-manager/delete-state/",   pincode_delete_state,      name="admin_pincode_delete_state"),
]
