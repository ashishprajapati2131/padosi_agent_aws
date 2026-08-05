from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404, FileResponse, JsonResponse
from django.db import connection
from django.views.decorators.http import require_http_methods
import os
import random
import string
from django.core.mail import EmailMessage
from django.conf import settings
from apps.agents.models import Agent, Invoice, PromoCode

from .dashboard import _get_admin_from_session
from ..services.pdf_generator import generate_invoice_pdf, get_pdf_absolute_path
from ..services.google_sheet_sync import sync_all_pending

def get_folder_label(folder):
    labels = {
        'no_discount': 'No Discount',
        '10_percent': '10%',
        '25_percent': '25%',
        '50_percent': '50%',
        '1re': '₹1 (Special)',
    }
    return labels.get(folder, 'Others')

@require_http_methods(["GET"])
def invoice_list(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    folder = request.GET.get("folder", "all")
    search = request.GET.get("search", "")
    page = int(request.GET.get("page", 1))
    per_page = 25

    with connection.cursor() as cursor:
        # 1. Total KPIs
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM invoices")
        row = cursor.fetchone()
        total_count = row[0] if row else 0
        total_revenue = row[1] if row else 0

        # 2. Folder Aggregations
        cursor.execute("""
            SELECT discount_folder, COUNT(*), COALESCE(SUM(total_amount), 0)
            FROM invoices
            GROUP BY discount_folder
        """)
        folder_rows = cursor.fetchall()
        
        # Initialize default counts
        folder_counts = {
            'all': {'total': total_count, 'revenue': total_revenue},
            'no_discount': {'total': 0, 'revenue': 0},
            '10_percent': {'total': 0, 'revenue': 0},
            '25_percent': {'total': 0, 'revenue': 0},
            '50_percent': {'total': 0, 'revenue': 0},
            '1re': {'total': 0, 'revenue': 0},
            'others': {'total': 0, 'revenue': 0},
        }
        
        for f_row in folder_rows:
            f_name, f_count, f_rev = f_row[0], f_row[1], f_row[2]
            if f_name in folder_counts:
                folder_counts[f_name] = {'total': f_count, 'revenue': f_rev}
            else:
                folder_counts['others']['total'] += f_count
                folder_counts['others']['revenue'] += f_rev

        # 3. List Query
        where_clauses = []
        params = []

        valid_folders = ["no_discount", "10_percent", "25_percent", "50_percent", "1re", "others"]
        if folder != "all" and folder in valid_folders:
            where_clauses.append("discount_folder = %s")
            params.append(folder)

        if search:
            search_term = f"%{search}%"
            where_clauses.append("(invoice_number LIKE %s OR agent_name LIKE %s OR agent_email LIKE %s OR razorpay_payment_id LIKE %s)")
            params.extend([search_term, search_term, search_term, search_term])

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Pagination logic
        count_query = f"SELECT COUNT(*) FROM invoices {where_sql}"
        cursor.execute(count_query, params)
        total_filtered = cursor.fetchone()[0]

        paginator = Paginator(range(total_filtered), per_page)
        page_obj = paginator.get_page(page)
        page_range = paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1)
        
        offset = (page_obj.number - 1) * per_page

        list_query = f"""
            SELECT id, invoice_number, agent_name, agent_email, plan_name, 
                   total_amount, discount_percent, promo_code, discount_folder, 
                   synced_to_sheet, synced_at, created_at
            FROM invoices
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        list_params = params + [per_page, offset]
        cursor.execute(list_query, list_params)
        
        columns = [col[0] for col in cursor.description]
        invoices = []
        for row in cursor.fetchall():
            inv = dict(zip(columns, row))
            inv['folder_label'] = get_folder_label(inv['discount_folder'])
            invoices.append(inv)
            
        cursor.execute("SELECT value FROM site_settings WHERE `key` = 'invoice_google_sheet_url'")
        row = cursor.fetchone()
        googleSheetUrl = row[0] if row else None

    context = {
        'admin': admin,
        'invoices': invoices,
        'folder': folder,
        'search': search,
        'folder_counts': folder_counts,
        'totalCount': total_count,
        'totalRevenue': total_revenue,
        'total_filtered': total_filtered,
        'googleSheetUrl': googleSheetUrl,
        
        'page_obj': page_obj,
        'page_range': page_range,
        'first_item': page_obj.start_index(),
        'last_item': page_obj.end_index(),
    }

    return render(request, "admin/invoices/index.html", context)


@require_http_methods(["GET"])
def preview_invoice(request, invoice_id):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")
        
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM invoices WHERE id = %s", [invoice_id])
        if not cursor.description:
            raise Http404("Invoice not found")
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        
        if not row:
            raise Http404("Invoice not found")
            
        invoice = dict(zip(columns, row))
        
    if not invoice.get('pdf_path'):
        generate_invoice_pdf(invoice_id)
        # Re-fetch after generation
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM invoices WHERE id = %s", [invoice_id])
            row = cursor.fetchone()
            invoice = dict(zip(columns, row))
            
    # GST logic for template preview matching Laravel
    agent_state = invoice.get('agent_state') or ''
    is_igst = 'gujarat' not in agent_state.lower()
    invoice['is_igst'] = is_igst
    
    gst_amount = float(invoice.get('gst_amount') or 0)
    if is_igst:
        invoice['gst_amount_igst'] = gst_amount
    else:
        invoice['gst_amount_cgst'] = gst_amount / 2
        invoice['gst_amount_sgst'] = gst_amount / 2
        
    return render(request, "admin/invoices/preview.html", {'invoice': invoice})


@require_http_methods(["GET"])
def download_invoice(request, invoice_id):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")
        
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM invoices WHERE id = %s", [invoice_id])
        if not cursor.description:
            raise Http404("Invoice not found")
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        
        if not row:
            raise Http404("Invoice not found")
            
        invoice = dict(zip(columns, row))
        
    pdf_path = invoice.get('pdf_path')
    abs_path = get_pdf_absolute_path(pdf_path) if pdf_path else None
    
    # Generate if missing or not physically present
    if not pdf_path or not abs_path or not os.path.exists(abs_path):
        result = generate_invoice_pdf(invoice_id)
        if not result.get('success'):
            raise Http404("Could not generate PDF")
        abs_path = result.get('absolute_path')
        invoice_number = result.get('invoice_number')
    else:
        invoice_number = invoice.get('invoice_number')
        
    if not abs_path or not os.path.exists(abs_path):
        raise Http404("PDF file not found")
        
    filename = f"{invoice_number}.pdf"
    
    return FileResponse(open(abs_path, 'rb'), as_attachment=True, filename=filename)


@require_http_methods(["POST"])
def save_sheet_url(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")
        
    sheet_url = request.POST.get('sheet_url', '').strip()
    
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO site_settings (`key`, `value`, `group`, `created_at`, `updated_at`) 
            VALUES ('invoice_google_sheet_url', %s, 'invoices', NOW(), NOW())
            ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `updated_at` = NOW()
        """, [sheet_url])
        
    return redirect('admin_invoices')


@require_http_methods(["POST"])
def sync_sheet(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")
        
    count = sync_all_pending()
    
    # Normally we would use Django messages framework, but keeping it simple as requested
    return redirect('admin_invoices')


@require_http_methods(["GET"])
def open_sheet(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")
        
    with connection.cursor() as cursor:
        cursor.execute("SELECT value FROM site_settings WHERE `key` = 'invoice_google_sheet_url'")
        row = cursor.fetchone()
        sheet_url = row[0] if row else None
        
    if not sheet_url:
        return redirect('admin_invoices')
        
    return redirect(sheet_url)

@require_http_methods(["GET", "POST"])
def create_manual_invoice(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    if request.method == "GET":
        from apps.home.models import SiteSetting
        pricing_config = SiteSetting.get_value('pricing_config') or {}
        starter = pricing_config.get('starter', {})
        prof = pricing_config.get('professional', {})
        
        context = {
            'starter': starter,
            'prof': prof,
        }
        return render(request, "admin/invoices/create.html", context)

    # POST processing
    name = request.POST.get('name', '').strip()
    email = request.POST.get('email', '').strip()
    mobile = request.POST.get('mobile', '').strip()
    address = request.POST.get('address', '').strip()
    state = request.POST.get('state', '').strip()
    
    plan_name = request.POST.get('plan_name', '').strip()
    base_amount_str = request.POST.get('base_amount', '0')
    gst_amount_str = request.POST.get('gst_amount', '0')
    total_amount_str = request.POST.get('total_amount', '0')
    promo_code_str = request.POST.get('promo_code', '').strip()
    
    email_subject = request.POST.get('email_subject', 'Your Invoice from Padosi').strip()
    email_header = request.POST.get('email_header', '').strip()
    email_body = request.POST.get('email_body', '').strip()

    try:
        base_amount = float(base_amount_str)
        gst_amount = float(gst_amount_str)
        total_amount = float(total_amount_str)
    except ValueError:
        return render(request, "admin/invoices/create.html", {"error": "Invalid amounts provided."})

    discount_percent = 0
    if promo_code_str:
        try:
            pc = PromoCode.objects.get(code=promo_code_str, is_active=True)
            if pc.is_valid():
                # In real scenario we might calculate discount exactly
                discount_percent = pc.discount_value
        except PromoCode.DoesNotExist:
            pass

    # We need a Dummy Agent because Invoice requires agent_id.
    # Let's find or create a dummy agent for manual invoices.
    dummy_email = "manual_invoice_dummy@padosi.local"
    agent, created = Agent.objects.get_or_create(
        email=dummy_email,
        defaults={
            'fullname': "Manual Invoice User",
            'mobile': "0000000000",
            'status': "incomplete"
        }
    )

    import datetime
    now = datetime.datetime.now()
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    invoice_number = f"INV-M-{now.strftime('%Y%m%d')}-{random_str}"
    
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
        plan_type='manual',
        base_amount=base_amount,
        gst_amount=gst_amount,
        total_amount=total_amount,
        discount_percent=discount_percent,
        discount_folder=folder,
        promo_code=promo_code_str,
        payment_status='paid'
    )

    # Generate PDF
    result = generate_invoice_pdf(invoice.id)
    if result and result.get('success'):
        pdf_path = result.get('absolute_path')
        if pdf_path and os.path.exists(pdf_path):
            # Send Email
            try:
                # Use Brevo/SMTP fallback service
                from apps.agents.services.brevo import email_service
                body = f"{email_header}<br><br>{email_body}".replace('\n', '<br>')
                success = email_service.send_generic(
                    to_email=email,
                    to_name=name,
                    subject=email_subject,
                    html_content=body,
                    attachment_path=pdf_path
                )
                if not success:
                    return render(request, "admin/invoices/create.html", {"error": f"Invoice created but failed to send email via Brevo or SMTP."})

            except Exception as e:
                return render(request, "admin/invoices/create.html", {"error": f"Invoice created but failed to send email: {str(e)}"})
            
            return render(request, "admin/invoices/create.html", {"success": f"Invoice {invoice_number} created and emailed to {email} successfully."})
        else:
            return render(request, "admin/invoices/create.html", {"error": "Failed to locate generated PDF."})
    else:
        return render(request, "admin/invoices/create.html", {"error": "Failed to generate Invoice PDF."})

@require_http_methods(["POST"])
def admin_verify_promo(request):
    import json
    admin = _get_admin_from_session(request)
    if not admin:
        return JsonResponse({'success': False, 'message': 'Unauthorized'})

    try:
        data = json.loads(request.body)
        promo_code = data.get('promo_code', '').strip().upper()
    except Exception:
        promo_code = request.POST.get('promo_code', '').strip().upper()

    if not promo_code:
        return JsonResponse({'success': False, 'message': 'Promo code is required.'})

    try:
        promo = PromoCode.objects.get(code=promo_code, is_active=True)
        if promo.is_valid():
            return JsonResponse({
                'success': True,
                'discount_type': promo.discount_type,
                'discount_value': float(promo.discount_value),
                'message': f'Promo code applied successfully!',
            })
    except PromoCode.DoesNotExist:
        pass

    return JsonResponse({
        'success': False,
        'message': 'Invalid or expired promo code.',
    })
