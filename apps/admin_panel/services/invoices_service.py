"""Invoice write flows used by apps/admin_panel/views/invoices.py."""

import os

from apps.agents.models import Agent, Invoice
from apps.agents.services.invoice import get_pdf_absolute_path, InvoiceService


def generate_invoice_pdf(invoice_id):
    """Generate the PDF for an invoice; returns (invoice, pdf_path). Raises Invoice.DoesNotExist."""
    inv_obj = Invoice.objects.get(id=invoice_id)
    return inv_obj, InvoiceService().generate_pdf(inv_obj)


def create_manual_invoice_record(
    *,
    invoice_number,
    name,
    email,
    mobile,
    address,
    state,
    plan_name,
    base_amount,
    gst_amount,
    total_amount,
    discount_percent,
    promo_code,
    payment_id,
):
    """Create a paid manual invoice on the shared dummy agent; returns (invoice, folder)."""
    # Invoice requires agent_id, so manual invoices hang off one dummy agent.
    dummy_email = "manual_invoice_dummy@padosi.local"
    agent, created = Agent.objects.get_or_create(
        email=dummy_email,
        defaults={
            "fullname": "Manual Invoice User",
            "mobile": "0000000000",
            "status": "incomplete",
        },
    )

    folder = Invoice.resolve_discount_folder(discount_percent, total_amount)

    invoice = Invoice.objects.create(
        invoice_number=invoice_number,
        agent=agent,
        agent_name=name,
        agent_email=email,
        agent_mobile=mobile,
        agent_address=address,
        agent_state=state,
        plan_name=plan_name,
        plan_type="manual",
        base_amount=base_amount,
        gst_amount=gst_amount,
        total_amount=total_amount,
        discount_percent=discount_percent,
        discount_folder=folder,
        promo_code=promo_code,
        razorpay_payment_id=payment_id or None,
        payment_status="paid",
    )
    return invoice, folder


def generate_manual_invoice_pdf(invoice, folder, invoice_number):
    """Generate the manual invoice PDF; returns (abs_pdf_path, error_message).

    On failure the invoice row is deleted so a retry can reuse the number.
    """
    pdf_path = InvoiceService().generate_pdf(invoice)
    if not pdf_path:
        # The invoice row was already created; remove it (and any partially
        # written PDF) so a custom invoice number/folder is not consumed by a
        # failed creation. Without this, retrying with the same number fails
        # with "already exists" and an orphan row stays in the DB.
        invoice.delete()
        guess_path = get_pdf_absolute_path(f"invoices/{folder}/{invoice_number}.pdf")
        try:
            if guess_path and os.path.exists(guess_path):
                os.remove(guess_path)
        except OSError:
            pass
        return None, "Failed to generate Invoice PDF."

    abs_pdf_path = get_pdf_absolute_path(pdf_path)
    if not abs_pdf_path or not os.path.exists(abs_pdf_path):
        invoice.delete()
        return None, "Failed to locate generated PDF."
    return abs_pdf_path, None
