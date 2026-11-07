"""QR file write flows used by apps/admin_panel/views/qr_files.py."""

import datetime
import os
import secrets
import string
import time

from django.conf import settings
from django.db.models import F

from apps.admin_panel.models.qr_file import QrFile


def _write_upload(uploaded_file, filename):
    upload_dir = os.path.join(settings.MEDIA_ROOT, "qr_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)

    with open(file_path, "wb+") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)

    return os.path.join("qr_uploads", filename).replace("\\", "/")


def _remove_physical_file(qr_file):
    path = os.path.join(settings.MEDIA_ROOT, qr_file.file_path)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def store_qr_file(uploaded_file, original_name, extension):
    """Generate a unique public code, save the upload to disk and create the record."""
    unique_code = ""
    while True:
        unique_code = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
        )  # public download code
        if not QrFile.objects.filter(unique_code=unique_code).exists():
            break

    filename = f"{unique_code}_{int(time.time())}.{extension}"
    relative_path = _write_upload(uploaded_file, filename)

    return QrFile.objects.create(
        unique_code=unique_code,
        filename=filename,
        original_name=original_name,
        file_path=relative_path,
        file_type=extension,
        file_size=uploaded_file.size,
        download_count=0,
    )


def replace_qr_file(qr_file, uploaded_file, original_name, extension):
    """Delete the old physical file, write the new one and update the record (code unchanged)."""
    _remove_physical_file(qr_file)

    filename = f"{qr_file.unique_code}_{int(time.time())}.{extension}"
    relative_path = _write_upload(uploaded_file, filename)

    qr_file.filename = filename
    qr_file.original_name = original_name
    qr_file.file_path = relative_path
    qr_file.file_type = extension
    qr_file.file_size = uploaded_file.size
    qr_file.save()
    return qr_file


def delete_qr_file(qr_file):
    """Delete the physical file then the record."""
    _remove_physical_file(qr_file)
    qr_file.delete()


def increment_download_count(qr_file):
    # Increment download count atomically (read-modify-save lost concurrent downloads)
    QrFile.objects.filter(pk=qr_file.pk).update(
        download_count=F("download_count") + 1, updated_at=datetime.datetime.now()
    )
