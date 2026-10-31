from pathlib import Path
from django.conf import settings

def get_invoice_root():
    """
    Returns the absolute base path for invoice storage: media/app/private/invoices/
    """
    base_dir = getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent.parent.parent)
    return base_dir / 'media' / 'app' / 'private' / 'invoices'

def get_folder_path(folder_name):
    """
    Returns the absolute path for a specific discount folder.
    """
    return get_invoice_root() / folder_name

