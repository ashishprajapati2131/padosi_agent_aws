from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db.models import Q
from django.contrib import messages
from decimal import Decimal
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.profile import WholesalerProfile
from apps.wholesale.services.cross_sell_service import CrossSellService
from apps.wholesale.services.pricing_service import PricingService
from apps.wholesale.forms.rfq_forms import BuyerInquiryForm
from apps.wholesale.adapters.auth_bridge import (
    wholesale_feature_gate, is_wholesale_admin, get_wholesaler_profile
)

@wholesale_feature_gate
def catalog_view(request):
    """
    Public marketplace is disabled as requested.
    Authenticated agents -> Agent Dashboard Marketplace tab.
    Authenticated distributors -> Distributor Cross-Sell view.
    Wholesalers -> Wholesaler Dashboard.
    Platform admins -> Wholesale Approvals queue.
    Guests/unauthenticated -> Redirected to Agent Login.
    """
    if not request.user.is_authenticated:
        messages.info(request, "Wholesale and cross-sell supplies are accessible exclusively inside the Agent and Distributor portals. Please log in.")
        return redirect('/agent-login/?next=/agent/dashboard/?tab=marketplace')

    # Agent routing
    if getattr(request.user, 'role', '') == 'agent' or hasattr(request.user, 'agent'):
        return redirect('/agent/dashboard/?tab=marketplace')

    # Distributor routing
    if getattr(request.user, 'role', '') == 'distributor' or request.user.groups.filter(name='distributor').exists():
        return redirect('distributors:cross_sell')

    # Wholesaler routing
    wholesaler = get_wholesaler_profile(request)
    if wholesaler:
        return redirect('wholesale:wholesaler_dashboard')

    # Admin routing
    if is_wholesale_admin(request):
        return redirect('wholesale:admin_approvals')

    # Default fallback for any other authenticated user
    return redirect('/agent/dashboard/?tab=marketplace')

    # 1. Search Query
    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(
            Q(title__icontains=q) |
            Q(brand__icontains=q) |
            Q(sku__icontains=q) |
            Q(tags__icontains=q) |
            Q(short_description__icontains=q)
        )

    # 2. Category Filter
    category_slug = request.GET.get('category', '').strip()
    selected_category = None
    if category_slug:
        selected_category = ProductCategory.objects.filter(slug=category_slug).first()
        if selected_category:
            subcat_ids = list(selected_category.subcategories.values_list('id', flat=True))
            category_ids = [selected_category.id] + subcat_ids
            products = products.filter(category_id__in=category_ids)

    # 3. Price Filter
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    if min_price:
        try:
            products = products.filter(base_price__gte=Decimal(min_price))
        except Exception:
            pass
    if max_price:
        try:
            products = products.filter(base_price__lte=Decimal(max_price))
        except Exception:
            pass

    # 4. MOQ Filter
    max_moq = request.GET.get('max_moq')
    if max_moq:
        try:
            products = products.filter(moq__lte=int(max_moq))
        except Exception:
            pass

    # 5. Verified Supplier Only
    verified_only = request.GET.get('verified_only') == '1'
    if verified_only:
        products = products.filter(wholesaler__verification_status='APPROVED')

    # 6. Sorting
    sort = request.GET.get('sort', 'popular')
    if sort == 'price_low':
        products = products.order_by('base_price')
    elif sort == 'price_high':
        products = products.order_by('-base_price')
    elif sort == 'newest':
        products = products.order_by('-created_at')
    elif sort == 'moq_low':
        products = products.order_by('moq')
    else:
        products = products.order_by('-is_featured', '-view_count', '-created_at')

    # Pagination
    paginator = Paginator(products, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Categories for navigation
    categories = ProductCategory.objects.filter(is_active=True, parent__isnull=True).prefetch_related('subcategories')

    context = {
        'page_obj': page_obj,
        'categories': categories,
        'selected_category': selected_category,
        'search_query': q,
        'current_sort': sort,
        'min_price': min_price or '',
        'max_price': max_price or '',
        'max_moq': max_moq or '',
        'verified_only': verified_only,
        'total_count': paginator.count,
    }
    return render(request, 'wholesale/public/catalog.html', context)


@wholesale_feature_gate
def product_detail_view(request, slug):
    """
    Product Detail View.
    Accessible only to authenticated users (Agents, Distributors, Wholesalers, Admins).
    Shows gallery, pricing tiers, specifications, credibility badge, and cross-sell carousel.
    """
    if not request.user.is_authenticated:
        messages.info(request, "Please log in to view B2B product specifications and wholesale rates.")
        return redirect(f'/agent-login/?next=/wholesale/product/{slug}/')

    product = get_object_or_404(
        WholesaleProduct.objects.select_related('wholesaler', 'category').prefetch_related('images', 'price_tiers', 'variants'),
        slug=slug
    )

    # If product is not live, only the owner or an admin can preview it
    if not product.is_live:
        is_owner = (
            request.user.is_authenticated and
            hasattr(request.user, 'wholesaler_profile') and
            request.user.wholesaler_profile.id == product.wholesaler.id
        )
        is_admin = is_wholesale_admin(request)
        if not (is_owner or is_admin):
            return render(request, 'wholesale/public/not_published.html', status=404)

    # Increment view count
    WholesaleProduct.objects.filter(id=product.id).update(view_count=product.view_count + 1)

    # Cross-Sell and Recommendations
    complementary_products = CrossSellService.get_complementary_products(product, limit=4)
    related_products = CrossSellService.get_related_products(product, limit=4)

    # Initial RFQ form pre-populated
    rfq_initial = {
        'requested_quantity': product.moq,
        'delivery_city': request.user.wholesaler_profile.city if hasattr(request.user, 'wholesaler_profile') else '',
    }
    rfq_form = BuyerInquiryForm(initial=rfq_initial)

    context = {
        'product': product,
        'images': product.images.all(),
        'price_tiers': product.price_tiers.all().order_by('min_quantity'),
        'variants': product.variants.filter(is_active=True),
        'complementary_products': complementary_products,
        'related_products': related_products,
        'rfq_form': rfq_form,
    }
    return render(request, 'wholesale/public/product_detail.html', context)


def calculate_price_api(request, product_id):
    """AJAX API: Calculates unit price, taxes, and total for a requested quantity."""
    product = get_object_or_404(WholesaleProduct, id=product_id)
    try:
        qty = int(request.GET.get('quantity', product.moq))
    except (ValueError, TypeError):
        qty = product.moq

    summary = PricingService.calculate_order_summary(product, qty)
    return JsonResponse(summary)
