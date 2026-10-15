"""
Buyer RFQ (Request for Quotation) and Lead Management Service.
"""
from typing import Dict, Any, Optional
from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from apps.wholesale.models.inquiry import BuyerInquiry, InquiryMessage
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.profile import WholesalerProfile

class RFQService:
    """Handles inquiry creation, messaging thread, and status tracking."""

    @staticmethod
    @transaction.atomic
    def submit_inquiry(product: WholesaleProduct, data: Dict[str, Any], buyer_user=None) -> BuyerInquiry:
        """Creates a new wholesale inquiry or quote request."""
        # Validation
        qty = int(data.get('requested_quantity', 0))
        if qty < product.moq:
            raise ValidationError(f"Requested quantity ({qty}) cannot be less than Minimum Order Quantity ({product.moq}).")

        inquiry = BuyerInquiry.objects.create(
            product=product,
            wholesaler=product.wholesaler,
            variant_id=data.get('variant_id') or None,
            buyer_user=buyer_user if getattr(buyer_user, 'is_authenticated', False) else None,
            buyer_name=data.get('buyer_name', '').strip(),
            buyer_email=data.get('buyer_email', '').strip(),
            buyer_phone=data.get('buyer_phone', '').strip(),
            company_name=data.get('company_name', '').strip() or None,
            delivery_city=data.get('delivery_city', '').strip(),
            delivery_pincode=data.get('delivery_pincode', '').strip(),
            requested_quantity=qty,
            target_price_per_unit=data.get('target_price_per_unit') or None,
            expected_purchase_timeline=data.get('expected_purchase_timeline', 'Immediate (Within 7 days)'),
            message=data.get('message', '').strip(),
            status='NEW'
        )

        # Initial message in thread
        InquiryMessage.objects.create(
            inquiry=inquiry,
            sender_name=inquiry.buyer_name,
            sender_role='BUYER',
            message=inquiry.message
        )

        # Increment product inquiry counter
        product.inquiry_count += 1
        product.save(update_fields=['inquiry_count'])

        return inquiry

    @staticmethod
    def add_message(inquiry: BuyerInquiry, sender_name: str, sender_role: str, message: str, attachment=None) -> InquiryMessage:
        """Adds a reply message to the inquiry conversation."""
        msg = InquiryMessage.objects.create(
            inquiry=inquiry,
            sender_name=sender_name,
            sender_role=sender_role,
            message=message.strip(),
            attachment=attachment
        )
        # Update inquiry status if seller replied
        if sender_role == 'SELLER' and inquiry.status == 'NEW':
            inquiry.status = 'SELLER_REPLIED'
            inquiry.save(update_fields=['status', 'updated_at'])

        return msg

    @staticmethod
    def update_quotation(inquiry: BuyerInquiry, wholesaler_profile: WholesalerProfile, quote_amount: float, notes: str = None) -> BuyerInquiry:
        """Seller sends a formal unit or total quotation to the buyer."""
        if inquiry.wholesaler.id != wholesaler_profile.id:
            raise PermissionDenied("You can only respond to inquiries sent to your business.")

        inquiry.seller_quotation_amount = quote_amount
        inquiry.seller_notes = notes
        inquiry.status = 'QUOTATION_SENT'
        inquiry.save(update_fields=['seller_quotation_amount', 'seller_notes', 'status', 'updated_at'])

        RFQService.add_message(
            inquiry=inquiry,
            sender_name=wholesaler_profile.business_name,
            sender_role='SELLER',
            message=f"Quotation Submitted: ₹{quote_amount}. {notes or ''}"
        )
        return inquiry
