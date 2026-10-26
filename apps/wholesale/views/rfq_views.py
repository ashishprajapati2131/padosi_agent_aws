"""
Buyer RFQ Submission and Messaging Views.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.inquiry import BuyerInquiry
from apps.wholesale.forms.rfq_forms import BuyerInquiryForm
from apps.wholesale.services.rfq_service import RFQService
from apps.wholesale.adapters.auth_bridge import wholesaler_required, get_wholesaler_profile, wholesale_feature_gate, safe_next_url
from apps.agents.utils.file_validation import validate_magic_bytes

DEFAULT_RFQ_NEXT = '/agent/dashboard/?tab=marketplace'


@wholesale_feature_gate
def submit_rfq_view(request, product_id):
    """Handles Buyer Request for Quote / Order Inquiry form submission."""
    product = get_object_or_404(WholesaleProduct, id=product_id)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
    next_url = safe_next_url(
        request, request.POST.get('next') or request.META.get('HTTP_REFERER'), DEFAULT_RFQ_NEXT
    )

    if request.method == 'POST':
        import time
        from django.core.cache import cache
        from apps.admin_panel.middleware import ThreatMonitorMiddleware

        client_ip = ThreatMonitorMiddleware.get_client_ip(request)
        rl_key = f"rl_rfq_{client_ip}"
        now_ts = time.time()
        ts_list = [t for t in cache.get(rl_key, []) if t > now_ts - 60]
        if len(ts_list) >= 10:
            err_msg = "Too many inquiry requests. Please wait a minute before submitting again."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': err_msg}, status=429)
            messages.error(request, err_msg)
            return redirect(next_url)

        ts_list.append(now_ts)
        cache.set(rl_key, ts_list, timeout=60)

        form = BuyerInquiryForm(request.POST)
        if form.is_valid():
            try:
                inquiry = RFQService.submit_inquiry(
                    product=product,
                    data=form.cleaned_data,
                    buyer_user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None
                )
                msg = f"Your order inquiry (RFQ #{inquiry.id}) for {product.title} has been submitted to {product.wholesaler.business_name}! The supplier will contact you with shipping/order confirmation."
                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': msg,
                        'inquiry_id': inquiry.id,
                        'wholesaler': product.wholesaler.business_name,
                    })
                messages.success(request, msg)
                return redirect(next_url)
            except Exception as e:
                err_msg = f"Failed to submit inquiry: {str(e)}"
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
                messages.error(request, err_msg)
        else:
            err_msg = "Please verify all fields in the order inquiry form."
            errors = {field: [str(e) for e in err_list] for field, err_list in form.errors.items()}
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': err_msg, 'errors': errors}, status=400)
            messages.error(request, err_msg)

    if is_ajax:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
    return redirect(next_url)


@wholesaler_required
def rfq_reply_view(request, inquiry_id):
    """Seller replies to an RFQ inquiry with message or quotation price."""
    profile = get_wholesaler_profile(request)
    inquiry = get_object_or_404(BuyerInquiry, id=inquiry_id, wholesaler=profile)

    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        message_text = request.POST.get('message', '').strip()
        quote_amount = request.POST.get('quote_amount')

        if action_type == 'quote' and quote_amount:
            try:
                RFQService.update_quotation(
                    inquiry=inquiry,
                    wholesaler_profile=profile,
                    quote_amount=float(quote_amount),
                    notes=message_text
                )
                messages.success(request, f"Quotation of ₹{quote_amount} sent for RFQ #{inquiry.id}.")
            except Exception as e:
                messages.error(request, str(e))
        elif message_text:
            attachment = request.FILES.get('attachment')
            if attachment:
                content = attachment.read()
                attachment.seek(0)
                is_valid, err_msg = validate_magic_bytes(content, attachment.name)
                if not is_valid:
                    messages.error(request, f"Attachment rejected: {err_msg}")
                    return redirect('wholesale:wholesaler_inquiries')
            RFQService.add_message(
                inquiry=inquiry,
                sender_name=profile.business_name,
                sender_role='SELLER',
                message=message_text,
                attachment=attachment
            )
            messages.success(request, "Reply sent to buyer.")

    return redirect('wholesale:wholesaler_inquiries')
