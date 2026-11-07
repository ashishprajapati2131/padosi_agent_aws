from apps.admin_panel.parsing import parse_int
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.http import Http404, FileResponse, JsonResponse
from django.db import connection
from django.views.decorators.http import require_http_methods
from django.contrib import messages
import logging
import os
from decimal import Decimal, InvalidOperation
from apps.agents.models import Invoice, PromoCode
from apps.agents.services.invoice import (
    generate_invoice_number,
    get_pdf_absolute_path,
    get_logo_data_uri,
    InvoiceService,
)

from .dashboard import _get_admin_from_session
from ..services.google_sheet_sync import sync_all_pending
from ..services.invoices_service import (
    create_manual_invoice_record,
    generate_invoice_pdf,
    generate_manual_invoice_pdf,
)
from ..selectors.invoices import (
    count_filtered_invoices,
    fetch_agent_profile_state,
    fetch_invoice_kpis,
    fetch_invoice_page,
    fetch_invoice_row,
    fetch_invoice_sheet_url,
    fetch_invoice_sheet_view_url,
    fetch_unsynced_invoice_count,
)

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def invoice_list(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    folder = request.GET.get("folder", "all")
    search = request.GET.get("search", "")
    page = max(1, parse_int(request.GET.get("page"), 1))
    per_page = 25

    total_count, total_revenue, folder_counts = fetch_invoice_kpis()

    # Pagination logic
    total_filtered = count_filtered_invoices(folder, search)

    paginator = Paginator(range(total_filtered), per_page)
    page_obj = paginator.get_page(page)
    page_range = paginator.get_elided_page_range(
        page_obj.number, on_each_side=1, on_ends=1
    )

    offset = (page_obj.number - 1) * per_page

    invoices = fetch_invoice_page(folder, search, per_page, offset)
    googleSheetUrl = fetch_invoice_sheet_url()
    googleSheetViewUrl = fetch_invoice_sheet_view_url()
    unsynced_invoice_count = fetch_unsynced_invoice_count()

    context = {
        "admin": admin,
        "invoices": invoices,
        "folder": folder,
        "search": search,
        "folder_counts": folder_counts,
        "totalCount": total_count,
        "totalRevenue": total_revenue,
        "total_filtered": total_filtered,
        "googleSheetUrl": googleSheetUrl,
        "googleSheetViewUrl": googleSheetViewUrl,
        "unsynced_invoice_count": unsynced_invoice_count,
        "page_obj": page_obj,
        "page_range": page_range,
        "first_item": page_obj.start_index(),
        "last_item": page_obj.end_index(),
    }

    return render(request, "admin/invoices/index.html", context)


@require_http_methods(["GET"])
def preview_invoice(request, invoice_id):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    invoice = fetch_invoice_row(invoice_id)
    if invoice is None:
        raise Http404("Invoice not found")
    columns = list(invoice)

    if not invoice.get("pdf_path"):
        try:
            generate_invoice_pdf(invoice_id)
        except Invoice.DoesNotExist:
            pass
        # Re-fetch after generation
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM invoices WHERE id = %s", [invoice_id])
            row = cursor.fetchone()
            invoice = dict(zip(columns, row))

    # Bill-to state fallback to the agent profile state (matches Laravel template)
    if not invoice.get("agent_state") and invoice.get("agent_id"):
        agent_state = fetch_agent_profile_state(invoice["agent_id"])
        if agent_state:
            invoice["agent_state"] = agent_state

    # GST logic for template preview matching Laravel
    agent_state = invoice.get("agent_state") or ""
    is_igst = "gujarat" not in agent_state.lower()
    invoice["is_igst"] = is_igst

    gst_amount = float(invoice.get("gst_amount") or 0)
    if is_igst:
        invoice["gst_amount_igst"] = gst_amount
    else:
        invoice["gst_amount_cgst"] = gst_amount / 2
        invoice["gst_amount_sgst"] = gst_amount / 2

    return render(
        request,
        "admin/invoices/preview.html",
        {
            "invoice": invoice,
            "logo_src": get_logo_data_uri(),
        },
    )


@require_http_methods(["GET"])
def download_invoice(request, invoice_id):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    invoice = fetch_invoice_row(invoice_id)
    if invoice is None:
        raise Http404("Invoice not found")

    pdf_path = invoice.get("pdf_path")
    abs_path = get_pdf_absolute_path(pdf_path) if pdf_path else None

    # Generate if missing or not physically present
    if not pdf_path or not abs_path or not os.path.exists(abs_path):
        try:
            inv_obj, pdf_path = generate_invoice_pdf(invoice_id)
            if not pdf_path:
                raise Http404("Could not generate PDF")
            abs_path = get_pdf_absolute_path(pdf_path)
            invoice_number = inv_obj.invoice_number
        except Invoice.DoesNotExist:
            raise Http404("Invoice not found")
    else:
        invoice_number = invoice.get("invoice_number")

    if not abs_path or not os.path.exists(abs_path):
        raise Http404("PDF file not found")

    # Keep the full invoice number in the download name (Laravel sends
    # "PA/26-27/XXXXX.pdf"); replace "/" so the filename survives browser
    # sanitization.
    filename = f"{invoice_number.replace('/', '-')}.pdf"

    return FileResponse(open(abs_path, "rb"), as_attachment=True, filename=filename)


@require_http_methods(["POST"])
def save_sheet_url(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    from apps.admin_panel.views.pages import _is_super_admin

    if not _is_super_admin(admin):
        messages.error(
            request, "Only a Super Admin can change where invoices are synced."
        )
        return redirect("admin_invoices")

    sheet_url = request.POST.get("sheet_url", "").strip()
    sheet_view_url = request.POST.get("sheet_view_url", "").strip()

    # Smart auto-detection if user pasted a spreadsheet link into script URL or vice-versa
    if "docs.google.com/spreadsheets" in sheet_url and not sheet_view_url:
        sheet_view_url = sheet_url
        sheet_url = ""
        messages.warning(
            request,
            "You pasted a Google Sheet spreadsheet link. For auto-syncing, also paste the Apps Script Web App URL.",
        )
    elif "script.google.com" in sheet_view_url and not sheet_url:
        sheet_url = sheet_view_url
        sheet_view_url = ""

    from urllib.parse import urlparse

    if sheet_url and not InvoiceService.is_apps_script_url(sheet_url):
        messages.error(
            request,
            "The sync URL must be a Google Apps Script web app (https://script.google.com/...).",
        )
        return redirect("admin_invoices")
    if sheet_view_url and (
        urlparse(sheet_view_url).scheme != "https"
        or (urlparse(sheet_view_url).hostname or "").lower() != "docs.google.com"
    ):
        messages.error(
            request,
            "The sheet link must be a Google Sheets link (https://docs.google.com/...).",
        )
        return redirect("admin_invoices")

    with connection.cursor() as cursor:
        if sheet_url:
            cursor.execute(
                """
                INSERT INTO site_settings (`key`, `value`, `group`, `created_at`, `updated_at`) 
                VALUES ('invoice_google_sheet_url', %s, 'invoices', NOW(), NOW())
                ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `updated_at` = NOW()
            """,
                [sheet_url],
            )

        if sheet_view_url:
            cursor.execute(
                """
                INSERT INTO site_settings (`key`, `value`, `group`, `created_at`, `updated_at`) 
                VALUES ('invoice_google_sheet_view_url', %s, 'invoices', NOW(), NOW())
                ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `updated_at` = NOW()
            """,
                [sheet_view_url],
            )

    from apps.admin_panel.models import AdminActivityLog

    AdminActivityLog.log(
        "Changed invoice Google Sheet settings",
        "SiteSetting",
        None,
        details=f"sync={sheet_url or '(unchanged)'} view={sheet_view_url or '(unchanged)'}",
        request=request,
    )
    messages.success(request, "Google Sheet settings saved successfully!")
    return redirect("admin_invoices")


@require_http_methods(["POST"])
def sync_sheet(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    sheet_url = fetch_invoice_sheet_url()

    if not sheet_url:
        messages.error(
            request, "Google Sheet URL is not configured. Please save a URL first."
        )
        return redirect("admin_invoices")

    pending = fetch_unsynced_invoice_count()

    count = sync_all_pending(limit=50)
    if pending > count:
        messages.success(
            request,
            f"Synced {count} invoice(s) to Google Sheet ({pending - count} remaining).",
        )
    else:
        messages.success(
            request, f"Synced {count} invoice(s) to Google Sheet successfully."
        )
    return redirect("admin_invoices")


@require_http_methods(["POST"])
def sync_single_invoice(request, invoice_id):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    from apps.admin_panel.services.google_sheet_sync import sync_invoice_to_sheet
    from apps.agents.models import Invoice

    inv = Invoice.objects.filter(id=invoice_id).first()
    inv_label = inv.invoice_number if inv else f"#{invoice_id}"

    success = sync_invoice_to_sheet(invoice_id)
    if success:
        messages.success(
            request, f"Invoice {inv_label} synced to Google Sheet successfully!"
        )
    else:
        messages.error(
            request,
            f"Failed to sync invoice {inv_label} to Google Sheet. Check the Web App URL.",
        )

    referrer = request.META.get("HTTP_REFERER")
    if referrer and "/admin/invoices" in referrer:
        return redirect(referrer)
    return redirect("admin_invoices")


@require_http_methods(["GET"])
def open_sheet(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    # Prioritize direct spreadsheet URL if saved
    view_url = fetch_invoice_sheet_view_url() or None

    if not view_url:
        view_url = fetch_invoice_sheet_url() or None

    if not view_url:
        messages.warning(request, "No Google Sheet link has been saved yet.")
        return redirect("admin_invoices")

    return redirect(view_url)


@require_http_methods(["GET", "POST"])
def create_manual_invoice(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    if request.method == "GET":
        from apps.home.models import SiteSetting

        pricing_config = SiteSetting.get_value("pricing_config") or {}
        starter = pricing_config.get("starter", {})
        prof = pricing_config.get("professional", {})

        old = request.session.pop("invoice_old", {})

        context = {
            "starter": starter,
            "prof": prof,
            "old": old,
        }
        return render(request, "admin/invoices/create.html", context)

    # POST processing
    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    mobile = request.POST.get("mobile", "").strip()
    address = request.POST.get("address", "").strip()
    state = request.POST.get("state", "").strip()

    plan_name = request.POST.get("plan_name", "").strip()
    base_amount_str = request.POST.get("base_amount", "0")
    gst_amount_str = request.POST.get("gst_amount", "0")
    total_amount_str = request.POST.get("total_amount", "0")
    # Uppercase to stay consistent with admin_verify_promo, which looks up
    # codes in upper case. Otherwise a lowercase-typed promo verifies and
    # discounts the amounts client-side but is never found on the server,
    # leaving discount_percent=0 / discount_folder='no_discount'.
    promo_code_str = request.POST.get("promo_code", "").strip().upper()
    custom_invoice_number = request.POST.get("invoice_number", "").strip()
    payment_id = request.POST.get("razorpay_payment_id", "").strip()
    send_email = request.POST.get("send_email") in ("on", "1", "true")

    email_subject = request.POST.get(
        "email_subject", "Your Invoice from Padosi"
    ).strip()
    email_header = request.POST.get("email_header", "").strip()
    email_body = request.POST.get("email_body", "").strip()

    old_values = {
        "name": name,
        "email": email,
        "mobile": mobile,
        "address": address,
        "state": state,
        "plan_name": plan_name,
        "base_amount": base_amount_str,
        "gst_amount": gst_amount_str,
        "total_amount": total_amount_str,
        "promo_code": promo_code_str,
        "invoice_number": custom_invoice_number,
        "razorpay_payment_id": payment_id,
        "send_email": send_email,
        "email_subject": email_subject,
        "email_header": email_header,
        "email_body": email_body,
    }

    def back_with_error(message):
        request.session["invoice_old"] = old_values
        messages.error(request, message)
        return redirect("admin_invoices_create")

    try:
        base_amount = Decimal(base_amount_str)
        gst_amount = Decimal(gst_amount_str)
        total_amount = Decimal(total_amount_str)
    except (InvalidOperation, TypeError):
        return back_with_error("Invalid amounts provided.")
    if not all(
        a.is_finite() and a >= 0 for a in (base_amount, gst_amount, total_amount)
    ):
        return back_with_error("Amounts must be zero or more.")
    if abs(base_amount + gst_amount - total_amount) > Decimal("1"):
        return back_with_error("Base amount + GST must equal the total amount.")
    # One paid invoice per payment: a resubmitted form created a second invoice for the same money.
    if payment_id and Invoice.objects.filter(razorpay_payment_id=payment_id).exists():
        return back_with_error(f"An invoice already exists for payment {payment_id}.")

    from apps.home.models import SiteSetting

    pricing_config = SiteSetting.get_value("pricing_config") or {}

    plan_name_lower = plan_name.lower()
    full_price = 0
    if "trial" in plan_name_lower:
        full_price = 0
    elif "starter" in plan_name_lower or "basic" in plan_name_lower:
        full_price = float(pricing_config.get("starter", {}).get("full_price", 2359))
    elif "professional" in plan_name_lower:
        full_price = float(
            pricing_config.get("professional", {}).get("full_price", 8258)
        )

    discount_percent = 0
    if full_price > 0 and float(total_amount) < full_price:
        discount_percent = round(
            ((full_price - float(total_amount)) / full_price) * 100, 1
        )
        discount_percent = max(0, discount_percent)
    elif promo_code_str:
        try:
            pc = PromoCode.objects.get(code=promo_code_str, is_active=True)
            # A fixed-amount code (e.g. Rs 500) is not a percentage; storing it as one overflowed the field.
            if pc.is_valid() and pc.discount_type == "percentage":
                discount_percent = min(float(pc.discount_value), 100)
        except PromoCode.DoesNotExist:
            pass

    # Invoice number: custom (with duplicate check) or auto-generated PA/YY-YY/XXXXX
    if custom_invoice_number:
        if Invoice.objects.filter(invoice_number=custom_invoice_number).exists():
            return back_with_error(
                f"Invoice number {custom_invoice_number} already exists. Please use a different number."
            )
        invoice_number = custom_invoice_number
    else:
        invoice_number = generate_invoice_number()

    invoice, folder = create_manual_invoice_record(
        invoice_number=invoice_number,
        name=name,
        email=email,
        mobile=mobile,
        address=address,
        state=state,
        plan_name=plan_name,
        base_amount=base_amount,
        gst_amount=gst_amount,
        total_amount=total_amount,
        discount_percent=discount_percent,
        promo_code=promo_code_str,
        payment_id=payment_id,
    )
    from apps.admin_panel.models import AdminActivityLog

    AdminActivityLog.log(
        "Created manual paid invoice",
        "Invoice",
        invoice.pk,
        details=f"{invoice_number} {email} Rs {total_amount} payment={payment_id or '-'}",
        request=request,
    )

    abs_pdf_path, pdf_error = generate_manual_invoice_pdf(
        invoice, folder, invoice_number
    )
    if pdf_error:
        return back_with_error(pdf_error)

    # Send email only when requested
    if send_email:
        try:
            # Use Brevo/SMTP fallback service
            from apps.agents.services.brevo import email_service

            body = f"{email_header}<br><br>{email_body}".replace("\n", "<br>")
            success = email_service.send_generic(
                to_email=email,
                to_name=name,
                subject=email_subject,
                html_content=body,
                attachment_path=abs_pdf_path,
            )
            if not success:
                # The invoice exists: don't refill the form (resubmitting made a duplicate invoice).
                messages.error(
                    request,
                    f"Invoice {invoice_number} created but the email could not be sent (Brevo and SMTP failed). Resend it from the list.",
                )
                return redirect("admin_invoices")
        except Exception:
            logger.exception("Manual invoice %s email failed", invoice_number)
            messages.error(
                request,
                f"Invoice {invoice_number} created but the email could not be sent. Resend it from the list.",
            )
            return redirect("admin_invoices")

        messages.success(
            request,
            f"Invoice {invoice_number} created and emailed to {email} successfully.",
        )
    else:
        messages.success(request, f"Invoice {invoice_number} created successfully.")

    return redirect("admin_invoices_create")


@require_http_methods(["POST"])
def admin_verify_promo(request):
    import json

    admin = _get_admin_from_session(request)
    if not admin:
        return JsonResponse({"success": False, "message": "Unauthorized"})

    try:
        data = json.loads(request.body)
        promo_code = data.get("promo_code", "").strip().upper()
    except Exception:
        promo_code = request.POST.get("promo_code", "").strip().upper()

    if not promo_code:
        return JsonResponse({"success": False, "message": "Promo code is required."})

    try:
        promo = PromoCode.objects.get(code=promo_code, is_active=True)
        if promo.is_valid():
            return JsonResponse(
                {
                    "success": True,
                    "discount_type": promo.discount_type,
                    "discount_value": float(promo.discount_value),
                    "message": f"Promo code applied successfully!",
                }
            )
    except PromoCode.DoesNotExist:
        pass

    return JsonResponse(
        {
            "success": False,
            "message": "Invalid or expired promo code.",
        }
    )
