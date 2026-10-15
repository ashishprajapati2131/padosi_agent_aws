"""
Wholesaler Portal Views: Dashboard, 8-Step Product Wizard, Inventory, Inquiries, and Bulk Import.
"""
import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.db import transaction
from apps.wholesale.adapters.auth_bridge import wholesaler_required, get_wholesaler_profile, is_wholesale_admin
from apps.wholesale.models.product import WholesaleProduct, ProductImage, ProductVariant
from apps.wholesale.models.pricing import WholesalePriceTier
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.inquiry import BuyerInquiry
from apps.wholesale.models.import_job import BulkImportJob
from apps.wholesale.forms.product_forms import ProductWizardForm
from apps.wholesale.services.approval_service import ApprovalService
from apps.wholesale.services.pricing_service import PricingService
from apps.wholesale.services.bulk_import_service import BulkImportService
from apps.wholesale.services.rfq_service import RFQService

@wholesaler_required
def wholesaler_dashboard_view(request):
    """Wholesaler overview dashboard with verification alerts, KPIs, and recent leads."""
    profile = get_wholesaler_profile(request)
    if not profile:
        if is_wholesale_admin(request):
            return redirect('wholesale:admin_dashboard')
        return redirect('wholesale:wholesaler_register')

    products_qs = profile.products.all()

    kpi = {
        'total_products': products_qs.count(),
        'published_products': products_qs.filter(approval_status='PUBLISHED').count(),
        'pending_approvals': products_qs.filter(approval_status__in=['SUBMITTED', 'UNDER_REVIEW']).count(),
        'changes_requested': products_qs.filter(approval_status='CHANGES_REQUESTED').count(),
        'draft_products': products_qs.filter(approval_status='DRAFT').count(),
        'low_stock_count': products_qs.filter(stock_quantity__lte=10, approval_status='PUBLISHED').count(),
        'total_inquiries': profile.inquiries_received.count(),
        'new_inquiries': profile.inquiries_received.filter(status='NEW').count(),
    }

    recent_inquiries = profile.inquiries_received.select_related('product').order_by('-created_at')[:5]
    recent_products = products_qs.order_by('-updated_at')[:5]

    context = {
        'profile': profile,
        'kpi': kpi,
        'recent_inquiries': recent_inquiries,
        'recent_products': recent_products,
    }
    return render(request, 'wholesale/wholesaler/dashboard.html', context)


@wholesaler_required
def wholesaler_product_list_view(request):
    """Manage products list with status filtering, search, and quick actions."""
    profile = get_wholesaler_profile(request)
    if not profile:
        if is_wholesale_admin(request):
            return redirect('wholesale:admin_dashboard')
        return redirect('wholesale:wholesaler_register')

    products = profile.products.select_related('category').prefetch_related('images', 'price_tiers')

    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        products = products.filter(approval_status=status_filter.upper())

    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(title__icontains=q) | products.filter(sku__icontains=q)

    paginator = Paginator(products.order_by('-updated_at'), 15)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'profile': profile,
        'page_obj': page_obj,
        'current_status': status_filter,
        'search_query': q,
        'total_count': paginator.count,
    }
    return render(request, 'wholesale/wholesaler/product_list.html', context)


@wholesaler_required
def product_wizard_view(request, product_id=None):
    """
    Product Creation and Editing Wizard.
    Handles basic info, media, tiered pricing builder, variants matrix, inventory, and submission.
    """
    profile = get_wholesaler_profile(request)

    # Invariant: Wholesaler must be verified by Admin before adding products
    if not profile or not profile.is_verified:
        messages.warning(
            request,
            "Your wholesaler account is currently pending Admin KYC verification. You will be able to add and list products once your business verification has been approved by the Administrator."
        )
        return redirect('wholesale:wholesaler_dashboard')

    product = None
    if product_id:
        product = get_object_or_404(WholesaleProduct, id=product_id, wholesaler=profile)

    form = ProductWizardForm(request.POST or None, request.FILES or None, instance=product)

    if request.method == 'POST':
        action = request.POST.get('wizard_action', 'save_draft')
        if form.is_valid():
            try:
                with transaction.atomic():
                    new_product = form.save(commit=False)
                    new_product.wholesaler = profile
                    if not product:
                        new_product.approval_status = 'DRAFT'
                    new_product.save()

                    # 1. Handle Primary Image
                    if request.FILES.get('primary_image'):
                        new_product.images.filter(is_primary=True).update(is_primary=False)
                        ProductImage.objects.create(
                            product=new_product,
                            image=request.FILES['primary_image'],
                            is_primary=True,
                            sort_order=0
                        )

                    # 2. Handle Additional Images
                    additional_files = request.FILES.getlist('additional_images')
                    for idx, img_file in enumerate(additional_files):
                        ProductImage.objects.create(
                            product=new_product,
                            image=img_file,
                            is_primary=False,
                            sort_order=idx + 1
                        )

                    # 3. Handle Price Tiers JSON
                    tiers_json = form.cleaned_data.get('price_tiers_json')
                    if tiers_json:
                        try:
                            tiers_data = json.loads(tiers_json)
                            PricingService.save_tiers_for_product(new_product, tiers_data)
                        except Exception as tier_err:
                            messages.warning(request, f"Price tiers warning: {str(tier_err)}")

                    # 4. Handle Variants JSON
                    variants_json = form.cleaned_data.get('variants_json')
                    if variants_json:
                        try:
                            var_data = json.loads(variants_json)
                            new_product.variants.all().delete()
                            for v in var_data:
                                if v.get('title') or v.get('name'):
                                    v_title = v.get('title') or v.get('name')
                                    ProductVariant.objects.create(
                                        product=new_product,
                                        name=v_title,
                                        sku=v.get('sku') or f"{new_product.sku}-{v_title[:10]}",
                                        price_delta=Decimal(str(v['price'])) if v.get('price') else Decimal('0.00'),
                                        stock_quantity=int(v.get('stock', 0)),
                                        is_active=True
                                    )
                        except Exception as var_err:
                            messages.warning(request, f"Variants warning: {str(var_err)}")

                    # 5. Handle Action: Submit for approval or Save Draft
                    if action == 'submit_for_approval':
                        try:
                            ApprovalService.submit_for_approval(new_product, request.user)
                            messages.success(request, f"'{new_product.title}' has been submitted for admin approval!")
                        except Exception as submit_err:
                            messages.error(request, f"Product saved as draft, but submission failed: {str(submit_err)}")
                            return redirect('wholesale:wholesaler_products')
                    else:
                        messages.success(request, f"'{new_product.title}' saved successfully as draft.")

                    return redirect('wholesale:wholesaler_products')

            except Exception as e:
                messages.error(request, f"Failed to save product: {str(e)}")

    # Pre-populate existing tiers and variants for the UI
    existing_tiers = []
    existing_variants = []
    if product:
        for t in product.price_tiers.all().order_by('min_quantity'):
            existing_tiers.append({
                'min_qty': t.min_quantity,
                'max_qty': t.max_quantity or '',
                'price': str(t.unit_price)
            })
        for v in product.variants.all():
            existing_variants.append({
                'title': v.name,
                'name': v.name,
                'sku': v.sku or '',
                'price': str(v.price_delta),
                'stock': v.stock_quantity,
            })

    categories = ProductCategory.objects.filter(is_active=True).order_by('name')

    context = {
        'form': form,
        'product': product,
        'categories': categories,
        'existing_tiers_json': json.dumps(existing_tiers),
        'existing_variants_json': json.dumps(existing_variants),
    }
    return render(request, 'wholesale/wholesaler/product_form.html', context)


@wholesaler_required
def product_status_toggle_view(request, product_id):
    """Pauses or resumes a listing."""
    profile = get_wholesaler_profile(request)
    product = get_object_or_404(WholesaleProduct, id=product_id, wholesaler=profile)

    if product.approval_status == 'PUBLISHED':
        ApprovalService.pause_product(product, request.user)
        messages.info(request, f"'{product.title}' is now paused.")
    elif product.approval_status == 'PAUSED':
        try:
            ApprovalService.resume_product(product, request.user)
            messages.success(request, f"'{product.title}' is now live on the marketplace!")
        except Exception as e:
            messages.error(request, str(e))
    else:
        messages.warning(request, "Only published or paused products can be toggled.")

    return redirect('wholesale:wholesaler_products')


@wholesaler_required
def bulk_upload_view(request):
    """Download CSV template and upload bulk product files."""
    profile = get_wholesaler_profile(request)

    # Invariant: Wholesaler must be verified by Admin before bulk uploading products
    if not profile or not profile.is_verified:
        messages.warning(
            request,
            "Your wholesaler account is currently pending Admin KYC verification. Bulk product uploading will be available once your business verification has been approved by the Administrator."
        )
        return redirect('wholesale:wholesaler_dashboard')

    if request.GET.get('action') == 'download_template':
        csv_data = BulkImportService.generate_sample_csv()
        response = HttpResponse(csv_data, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="wholesale_product_import_template.csv"'
        return response

    if request.method == 'POST' and request.FILES.get('csv_file'):
        file_obj = request.FILES['csv_file']
        if not file_obj.name.endswith('.csv'):
            messages.error(request, "Please upload a valid .csv file.")
            return redirect('wholesale:bulk_upload')

        job = BulkImportJob.objects.create(
            wholesaler=profile,
            file=file_obj,
            original_filename=file_obj.name,
            status='PENDING'
        )
        # Process the import
        BulkImportService.process_import_job(job)
        if job.status in ('COMPLETED', 'PARTIAL'):
            messages.success(request, job.summary_message)
        else:
            messages.error(request, job.summary_message)
        return redirect('wholesale:bulk_upload')

    recent_jobs = profile.import_jobs.prefetch_related('errors').order_by('-created_at')[:5]

    context = {
        'profile': profile,
        'recent_jobs': recent_jobs,
    }
    return render(request, 'wholesale/wholesaler/bulk_import.html', context)


@wholesaler_required
def wholesaler_inquiries_view(request):
    """Manages buyer RFQ inquiries, lead statuses, and sending quotations."""
    profile = get_wholesaler_profile(request)
    if not profile:
        if is_wholesale_admin(request):
            return redirect('wholesale:admin_dashboard')
        return redirect('wholesale:wholesaler_register')

    inquiries = profile.inquiries_received.select_related('product', 'variant').prefetch_related('messages').order_by('-created_at')

    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        inquiries = inquiries.filter(status=status_filter.upper())

    paginator = Paginator(inquiries, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'profile': profile,
        'page_obj': page_obj,
        'current_status': status_filter,
    }
    return render(request, 'wholesale/wholesaler/inquiries.html', context)
