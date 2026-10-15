"""
Distributor Portal Cross-Sell & B2B Supplies Views.
Allows distributors to browse admin-approved products from verified wholesalers,
check bulk wholesale volume tiers, place network orders, and track supplier RFQs.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from apps.distributors.views.dashboard import is_distributor
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.inquiry import BuyerInquiry
from apps.wholesale.forms.rfq_forms import BuyerInquiryForm
from apps.wholesale.services.rfq_service import RFQService


@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def cross_sell_index(request):
    """
    Distributor Cross-Sell Products Catalog & Order Management.
    Only shows products approved by platform admin.
    """
    from apps.wholesale.adapters.auth_bridge import is_wholesale_enabled
    if not is_wholesale_enabled():
        return render(request, 'distributors/cross_sell.html', {
            'products': [],
            'categories': [],
            'my_inquiries': [],
            'total_products': 0,
            'is_disabled': True,
        })

    products = list(
        WholesaleProduct.objects.filter(
            approval_status='PUBLISHED',
            wholesaler__verification_status='APPROVED'
        ).select_related('wholesaler', 'category')
         .prefetch_related('images', 'price_tiers', 'variants')
         .order_by('-is_featured', '-id')
    )
    categories = list(
        ProductCategory.objects.filter(is_active=True, parent__isnull=True)
    )
    my_inquiries = list(
        BuyerInquiry.objects.filter(buyer_user=request.user)
        .select_related('product', 'wholesaler')
        .order_by('-created_at')[:20]
    )

    context = {
        'products': products,
        'categories': categories,
        'my_inquiries': my_inquiries,
        'total_products': len(products),
    }
    return render(request, 'distributors/cross_sell.html', context)


@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def cross_sell_order(request, product_id):
    """Handles distributor order / quotation submission to the wholesaler."""
    product = get_object_or_404(WholesaleProduct, id=product_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'

    if request.method == 'POST':
        form = BuyerInquiryForm(request.POST)
        if form.is_valid():
            try:
                inquiry = RFQService.submit_inquiry(
                    product=product,
                    data=form.cleaned_data,
                    buyer_user=request.user
                )
                msg = f"Order inquiry (RFQ #{inquiry.id}) for {product.title} has been submitted to supplier {product.wholesaler.business_name}!"
                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': msg,
                        'inquiry_id': inquiry.id,
                        'wholesaler': product.wholesaler.business_name
                    })
                messages.success(request, msg)
                return redirect('distributors:cross_sell')
            except Exception as e:
                err = f"Failed to submit inquiry: {str(e)}"
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': err}, status=400)
                messages.error(request, err)
        else:
            err = "Please complete all required fields."
            errors = {k: [str(e) for e in v] for k, v in form.errors.items()}
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': err, 'errors': errors}, status=400)
            messages.error(request, err)

    if is_ajax:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
    return redirect('distributors:cross_sell')
