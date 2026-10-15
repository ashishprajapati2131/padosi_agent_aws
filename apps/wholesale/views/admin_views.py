"""
Wholesale Administrator Views: Moderation Queues, Split-Screen Review, Wholesaler Approvals, Cross-Sell Management, and Feature Flag.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import JsonResponse
from datetime import datetime
from apps.home.models.site_setting import SiteSetting
from apps.wholesale.adapters.auth_bridge import wholesale_admin_required, is_wholesale_enabled
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.profile import WholesalerProfile, BusinessVerificationDocument
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.relationship import ProductRelationship
from apps.wholesale.services.approval_service import ApprovalService
from apps.wholesale.services.cross_sell_service import CrossSellService

@wholesale_admin_required
def admin_dashboard_view(request):
    """Admin wholesale operations overview."""
    # Wholesalers pending KYC verification (submitted, under review, info required, or pending documents)
    pending_wholesalers_qs = WholesalerProfile.objects.filter(
        Q(verification_status__in=['SUBMITTED', 'UNDER_REVIEW', 'INFO_REQUIRED']) |
        Q(documents__status='PENDING')
    ).distinct().prefetch_related('documents').order_by('-updated_at')

    pending_kyc_count = pending_wholesalers_qs.count()
    pending_wholesalers = pending_wholesalers_qs[:15]

    all_wholesalers = WholesalerProfile.objects.all().prefetch_related('documents').order_by('-created_at')

    pending_products_count = WholesaleProduct.objects.filter(approval_status__in=['SUBMITTED', 'UNDER_REVIEW']).count()
    changes_requested_count = WholesaleProduct.objects.filter(approval_status='CHANGES_REQUESTED').count()
    published_products_count = WholesaleProduct.objects.filter(approval_status='PUBLISHED').count()
    total_wholesalers = WholesalerProfile.objects.count()

    recent_submissions = WholesaleProduct.objects.filter(
        approval_status__in=['SUBMITTED', 'UNDER_REVIEW']
    ).select_related('wholesaler', 'category').order_by('-updated_at')[:6]

    context = {
        'wholesale_enabled': is_wholesale_enabled(),
        'pending_kyc_count': pending_kyc_count,
        'pending_products_count': pending_products_count,
        'changes_requested_count': changes_requested_count,
        'published_products_count': published_products_count,
        'total_wholesalers': total_wholesalers,
        'recent_submissions': recent_submissions,
        'pending_wholesalers': pending_wholesalers,
        'all_wholesalers': all_wholesalers,
    }
    return render(request, 'wholesale/admin/dashboard.html', context)


@wholesale_admin_required
def admin_approval_queue_view(request):
    """Tabbed queue of product submissions requiring moderation."""
    status_tab = request.GET.get('tab', 'pending').lower()

    base_qs = WholesaleProduct.objects.select_related('wholesaler', 'category').prefetch_related('images', 'price_tiers')

    if status_tab == 'pending':
        products = base_qs.filter(approval_status__in=['SUBMITTED', 'UNDER_REVIEW'])
    elif status_tab == 'changes_requested':
        products = base_qs.filter(approval_status='CHANGES_REQUESTED')
    elif status_tab == 'approved':
        products = base_qs.filter(approval_status='APPROVED')
    elif status_tab == 'published':
        products = base_qs.filter(approval_status='PUBLISHED')
    elif status_tab == 'rejected':
        products = base_qs.filter(approval_status='REJECTED')
    else:  # all
        products = base_qs.all()

    # Search filter
    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(
            Q(title__icontains=q) |
            Q(sku__icontains=q) |
            Q(wholesaler__business_name__icontains=q)
        )

    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)

    paginator = Paginator(products.order_by('-updated_at'), 15)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    categories = ProductCategory.objects.filter(is_active=True)

    # Badge counts
    counts = {
        'pending': base_qs.filter(approval_status__in=['SUBMITTED', 'UNDER_REVIEW']).count(),
        'changes_requested': base_qs.filter(approval_status='CHANGES_REQUESTED').count(),
        'approved': base_qs.filter(approval_status='APPROVED').count(),
        'published': base_qs.filter(approval_status='PUBLISHED').count(),
        'rejected': base_qs.filter(approval_status='REJECTED').count(),
        'all': base_qs.count(),
    }

    context = {
        'wholesale_enabled': is_wholesale_enabled(),
        'page_obj': page_obj,
        'current_tab': status_tab,
        'categories': categories,
        'counts': counts,
        'search_query': q,
    }
    return render(request, 'wholesale/admin/approval_queue.html', context)


@wholesale_admin_required
def admin_review_product_view(request, product_id):
    """
    Product Review Interface.
    Left: Exact buyer preview of product.
    Right: Wholesaler KYC verification summary, compliance checks, and approval actions.
    Bottom: Audit history.
    """
    product = get_object_or_404(
        WholesaleProduct.objects.select_related('wholesaler', 'category').prefetch_related('images', 'price_tiers', 'variants', 'approval_logs'),
        id=product_id
    )

    if request.method == 'POST':
        decision = request.POST.get('decision')
        notes_to_seller = request.POST.get('notes_to_seller', '').strip()
        internal_notes = request.POST.get('internal_notes', '').strip()

        try:
            admin_user = request.user if hasattr(request, 'user') and request.user.is_authenticated else 'admin'
            if decision == 'approve':
                ApprovalService.approve_product(product, admin_user, auto_publish=True, internal_notes=internal_notes)
                messages.success(request, f"Product '{product.title}' has been APPROVED and published!")
                return redirect('wholesale:admin_approval_queue')

            elif decision == 'request_changes':
                ApprovalService.request_changes(product, admin_user, feedback=notes_to_seller, internal_notes=internal_notes)
                messages.warning(request, f"Revision requested for '{product.title}'. Wholesaler notified.")
                return redirect('wholesale:admin_approval_queue')

            elif decision == 'reject':
                ApprovalService.reject_product(product, admin_user, reason=notes_to_seller, internal_notes=internal_notes)
                messages.error(request, f"Product '{product.title}' was REJECTED.")
                return redirect('wholesale:admin_approval_queue')

            elif decision == 'start_review':
                ApprovalService.start_review(product, admin_user)
                messages.info(request, f"Product is now marked as Under Review.")
                return redirect('wholesale:admin_review_product', product_id=product.id)

        except Exception as e:
            messages.error(request, str(e))

    wholesaler_docs = product.wholesaler.documents.all()
    audit_logs = product.approval_logs.all().order_by('-created_at')

    context = {
        'product': product,
        'wholesaler': product.wholesaler,
        'wholesaler_docs': wholesaler_docs,
        'audit_logs': audit_logs,
        'images': product.images.all(),
        'price_tiers': product.price_tiers.all().order_by('min_quantity'),
        'variants': product.variants.all(),
    }
    return render(request, 'wholesale/admin/review_detail.html', context)


@wholesale_admin_required
def admin_verify_wholesaler_view(request, wholesaler_id):
    """Admin reviews and approves/rejects wholesaler KYC business documents."""
    wholesaler = get_object_or_404(WholesalerProfile, id=wholesaler_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        admin_notes = request.POST.get('admin_notes', '').strip()
        reason = request.POST.get('rejection_reason', '').strip()

        if action == 'approve':
            wholesaler.verification_status = 'APPROVED'
            wholesaler.verified_at = datetime.now()
            wholesaler.admin_notes = admin_notes
            wholesaler.save()
            messages.success(request, f"Wholesaler '{wholesaler.business_name}' is now VERIFIED & APPROVED!")
        elif action == 'reject':
            wholesaler.verification_status = 'REJECTED'
            wholesaler.rejection_reason = reason or "Submitted documents could not be verified."
            wholesaler.admin_notes = admin_notes
            wholesaler.save()
            messages.error(request, f"Wholesaler '{wholesaler.business_name}' verification was rejected.")
        elif action == 'request_info':
            wholesaler.verification_status = 'INFO_REQUIRED'
            wholesaler.rejection_reason = reason or "Please provide updated GST / Registration documents."
            wholesaler.admin_notes = admin_notes
            wholesaler.save()
            messages.warning(request, f"Requested additional info from '{wholesaler.business_name}'.")

        return redirect('wholesale:admin_dashboard')

    context = {
        'wholesaler': wholesaler,
        'documents': wholesaler.documents.all(),
    }
    return render(request, 'wholesale/admin/verify_wholesaler.html', context)


@wholesale_admin_required
def admin_categories_view(request):
    """Category tree management: Add categories and subcategories."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent_id') or None
        icon_class = request.POST.get('icon_class', 'fa-solid fa-box').strip()
        desc = request.POST.get('description', '').strip()

        if name:
            ProductCategory.objects.create(
                name=name,
                parent_id=parent_id,
                icon_class=icon_class,
                description=desc
            )
            messages.success(request, f"Category '{name}' created successfully!")
            return redirect('wholesale:admin_categories')

    categories = ProductCategory.objects.filter(parent__isnull=True).prefetch_related('subcategories')
    context = {'categories': categories}
    return render(request, 'wholesale/admin/categories.html', context)


@wholesale_admin_required
def admin_cross_sell_view(request):
    """Manages complementary product pairings for cross-sell discovery."""
    if request.method == 'POST':
        source_id = request.POST.get('source_product_id')
        target_id = request.POST.get('target_product_id')
        order = int(request.POST.get('display_order', 0))

        if source_id and target_id and source_id != target_id:
            src = get_object_or_404(WholesaleProduct, id=source_id)
            tgt = get_object_or_404(WholesaleProduct, id=target_id)
            CrossSellService.set_complementary_pair(src, tgt, order)
            messages.success(request, f"Cross-sell link created: '{src.title}' → '{tgt.title}'")
            return redirect('wholesale:admin_cross_sell')

    relationships = ProductRelationship.objects.select_related('source_product', 'target_product').order_by('-id')[:20]
    live_products = WholesaleProduct.objects.filter(approval_status='PUBLISHED')[:50]

    context = {
        'relationships': relationships,
        'live_products': live_products,
    }
    return render(request, 'wholesale/admin/cross_sell.html', context)


@wholesale_admin_required
def admin_toggle_feature_flag_view(request):
    """
    Instant Feature Flag Toggle for Wholesale Marketplace.
    Allows admin to turn the entire wholesale system ON or OFF with 1 click.
    """
    if request.method == 'POST':
        current_state = is_wholesale_enabled()
        new_state = not current_state
        SiteSetting.set_value('wholesale_marketplace_enabled', new_state, group='general')

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
            return JsonResponse({
                'success': True,
                'enabled': new_state,
                'message': f"Wholesale Marketplace is now {'ENABLED' if new_state else 'DISABLED'}."
            })

        messages.success(request, f"Wholesale Marketplace is now {'ENABLED' if new_state else 'DISABLED'}.")
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'wholesale:admin_dashboard'
        return redirect(next_url)

    # GET returns current status
    return JsonResponse({'enabled': is_wholesale_enabled()})
