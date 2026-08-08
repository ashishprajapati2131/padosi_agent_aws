import os
import base64
import datetime
import pdfkit
import logging
from django.conf import settings
from django.db import connection
from django.template.loader import render_to_string
from .invoice_storage import get_invoice_root, get_folder_path, ensure_invoice_directories

logger = logging.getLogger(__name__)

def get_logo_data_uri():
    """Embed the PadosiAgent logo as a base64 data URI (matches Laravel's base64 logo embed)."""
    try:
        from django.contrib.staticfiles import finders
    except Exception:
        finders = None
    for name in ('img/logo.webp', 'img/logo.png'):
        path = finders.find(name) if finders else None
        if path and os.path.exists(path):
            ext = 'png' if name.endswith('.png') else 'webp'
            with open(path, 'rb') as f:
                return f"data:image/{ext};base64,{base64.b64encode(f.read()).decode()}"
    return ''

def resolve_discount_folder(discount_percent, total_amount):
    """
    Match Laravel exactly:
    total_amount <= 1.00 -> 1re
    0 -> no_discount
    10 -> 10_percent
    25 -> 25_percent
    50 -> 50_percent
    everything else -> others
    """
    try:
        total_amount = float(total_amount)
    except (TypeError, ValueError):
        total_amount = 0.0

    try:
        discount_percent = float(discount_percent)
    except (TypeError, ValueError):
        discount_percent = 0.0

    if total_amount <= 1.00:
        return '1re'
    
    if discount_percent == 0:
        return 'no_discount'
    elif discount_percent == 10:
        return '10_percent'
    elif discount_percent == 25:
        return '25_percent'
    elif discount_percent == 50:
        return '50_percent'
    else:
        return 'others'

def generate_invoice_number():
    """
    Match Laravel: PA/{yy}-{yy}/{seq:05d} (financial-year based).
    Delegates to the shared generator in apps.agents.services.invoice.
    """
    from apps.agents.services.invoice import generate_invoice_number as _gen
    return _gen()

def generate_invoice_pdf(invoice_id):
    """
    Fetch invoice via raw SQL, render pdf.html and generate PDF using pdfkit + wkhtmltopdf.
    Reuses existing PDF if present.
    Returns dictionary with success status and details.
    """
    ensure_invoice_directories()
    
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM invoices WHERE id = %s", [invoice_id])
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        
        if not row:
            return {"success": False, "error": "Invoice not found"}
            
        invoice_data = dict(zip(columns, row))
        
    # Build invoice context (GST logic for template)
    agent_state = invoice_data.get('agent_state') or ''
    is_igst = 'gujarat' not in agent_state.lower()
    invoice_data['is_igst'] = is_igst
    
    gst_amount = float(invoice_data.get('gst_amount') or 0)
    if is_igst:
        invoice_data['gst_amount_igst'] = gst_amount
    else:
        invoice_data['gst_amount_cgst'] = gst_amount / 2
        invoice_data['gst_amount_sgst'] = gst_amount / 2

    invoice_number = invoice_data.get('invoice_number')
    if not invoice_number:
        invoice_number = generate_invoice_number()
        invoice_data['invoice_number'] = invoice_number
        with connection.cursor() as cursor:
            cursor.execute("UPDATE invoices SET invoice_number = %s WHERE id = %s", [invoice_number, invoice_id])
    
    total_amount = invoice_data.get('total_amount', 0)
    discount_percent = invoice_data.get('discount_percent', 0)
    
    folder = invoice_data.get('discount_folder')
    if not folder:
        folder = resolve_discount_folder(discount_percent, total_amount)
        invoice_data['discount_folder'] = folder
    
    pdf_path = f"invoices/{folder}/{invoice_number}.pdf"
    
    # Store relative path in database if empty or changed
    if invoice_data.get('pdf_path') != pdf_path:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE invoices SET pdf_path = %s, discount_folder = %s WHERE id = %s", [pdf_path, folder, invoice_id])
    
    folder_abs_path = get_folder_path(folder)
    absolute_path = os.path.join(str(folder_abs_path), f"{invoice_number}.pdf")
    # Invoice numbers contain slashes (PA/26-27/XXXXX) -> create nested dirs
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
    
    # Check if PDF already exists (Laravel behavior: do not regenerate if present)
    if os.path.exists(absolute_path):
        return {
            "success": True,
            "invoice_number": invoice_number,
            "folder": folder,
            "pdf_path": pdf_path,
            "absolute_path": absolute_path,
            "status": "reused"
        }
    
    agent_state = str(invoice_data.get('agent_state') or '').strip().lower()
    is_gujarat = ('gujarat' in agent_state)
    invoice_data['is_gujarat'] = is_gujarat
    
    gst_amount = float(invoice_data.get('gst_amount') or 0)
    half_gst = gst_amount / 2 if is_gujarat else 0
    
    plan_name = invoice_data.get('plan_name') or "Custom Plan"
    plan_type = invoice_data.get('plan_type')
    
    plan_desc = "PadosiAgent Subscription"
    if plan_type == 'free_trial':
        plan_desc += " – 30 Day Trial"
    elif plan_type == 'basic':
        plan_desc += " – 1 Year Starter"
    elif plan_type == 'professional':
        plan_desc += " – 1 Year Professional"
        
    items = [
        {
            'name': plan_name,
            'description': plan_desc,
            'amount': float(invoice_data.get('base_amount') or 0),
        }
    ]

    context = {
        'invoice': invoice_data,
        'items': items,
        'is_gujarat': is_gujarat,
        'half_gst': half_gst,
        'logo_src': get_logo_data_uri(),
    }

    # Render HTML template natively
    html_string = render_to_string('admin/invoices/pdf.html', context)
    
    # Generate PDF via xhtml2pdf
    from xhtml2pdf import pisa
    import tempfile
    
    # Temporary monkey-patch for xhtml2pdf Windows file-lock bug on NamedTemporaryFile
    original_named_temp_file = tempfile.NamedTemporaryFile

    class ClosedNamedTemporaryFile:
        def __init__(self, *args, **kwargs):
            kwargs['delete'] = False
            self._file = original_named_temp_file(*args, **kwargs)
            self.name = self._file.name
            self._closed = False

        def write(self, data):
            if not self._closed:
                self._file.write(data)

        def flush(self):
            if not self._closed:
                self._file.flush()
                self._file.close()
                self._closed = True

        def close(self):
            pass

        def __del__(self):
            try:
                if os.path.exists(self.name):
                    os.remove(self.name)
            except Exception:
                pass

    tempfile.NamedTemporaryFile = ClosedNamedTemporaryFile

    try:
        # Invoice numbers contain slashes (PA/26-27/00042), so the path may
        # nest below the discount folder; create the parent dirs like
        # Laravel's Storage::put does automatically.
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        with open(absolute_path, "w+b") as result_file:
            pisa_status = pisa.CreatePDF(html_string, dest=result_file, encoding='utf-8')
    finally:
        # Restore original tempfile behavior
        tempfile.NamedTemporaryFile = original_named_temp_file

    if pisa_status.err:
        return {"success": False, "error": "Failed to render PDF using xhtml2pdf"}
    
    return {
        "success": True,
        "invoice_number": invoice_number,
        "folder": folder,
        "pdf_path": pdf_path,
        "absolute_path": absolute_path,
        "status": "generated"
    }

def get_pdf_absolute_path(pdf_path):
    """
    Helper to resolve the database pdf_path string to the physical file system absolute path.
    Supports nested paths (invoice numbers contain slashes, e.g. invoices/no_discount/PA/26-27/XXXXX.pdf).
    """
    if not pdf_path:
        return None

    normalized = pdf_path.replace("\\", "/").strip("/")
    if normalized.startswith("invoices/"):
        normalized = normalized[len("invoices/"):]
    return get_invoice_root() / normalized

def pdf_exists(pdf_path):
    """
    Return True if PDF exists on the disk.
    """
    abs_path = get_pdf_absolute_path(pdf_path)
    if not abs_path:
        return False
    return os.path.exists(abs_path)
