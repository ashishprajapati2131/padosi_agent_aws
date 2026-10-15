"""
Product Approval Workflow State Machine and Audit Service.
"""
from datetime import datetime
from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.approval import ProductApprovalLog
from apps.wholesale.models.profile import WholesalerProfile

class ApprovalService:
    """Encapsulates business rules and state transitions for product approval."""

    VALID_TRANSITIONS = {
        'DRAFT': ['SUBMITTED', 'ARCHIVED'],
        'SUBMITTED': ['UNDER_REVIEW', 'DRAFT', 'CHANGES_REQUESTED', 'APPROVED', 'REJECTED'],
        'UNDER_REVIEW': ['CHANGES_REQUESTED', 'APPROVED', 'REJECTED', 'SUBMITTED'],
        'CHANGES_REQUESTED': ['SUBMITTED', 'DRAFT', 'ARCHIVED'],
        'APPROVED': ['PUBLISHED', 'PAUSED', 'UNDER_REVIEW'],
        'PUBLISHED': ['PAUSED', 'UNDER_REVIEW', 'ARCHIVED'],
        'PAUSED': ['PUBLISHED', 'UNDER_REVIEW', 'ARCHIVED'],
        'REJECTED': ['DRAFT', 'ARCHIVED'],
        'ARCHIVED': ['DRAFT'],
    }

    @staticmethod
    def _create_snapshot(product: WholesaleProduct) -> dict:
        """Serializes current product attributes for audit snapshot."""
        return {
            'id': product.id,
            'title': product.title,
            'sku': product.sku,
            'category': product.category.name if product.category else None,
            'base_price': str(product.base_price),
            'moq': product.moq,
            'stock': product.stock_quantity,
            'approval_status': product.approval_status,
            'wholesaler': product.wholesaler.business_name,
        }

    @staticmethod
    @transaction.atomic
    def submit_for_approval(product: WholesaleProduct, actor_user) -> WholesaleProduct:
        """Wholesaler submits a draft or revised listing for admin review."""
        if product.approval_status not in ('DRAFT', 'CHANGES_REQUESTED'):
            raise ValidationError(f"Cannot submit product currently in '{product.get_approval_status_display()}' status.")

        # Ensure minimal required fields are set
        if not product.title or not product.base_price or product.base_price <= 0:
            raise ValidationError("Product title and positive wholesale base price are required.")
        if not product.category:
            raise ValidationError("Product category must be assigned.")
        if not product.images.exists():
            raise ValidationError("At least one product image is required before submission.")

        old_status = product.approval_status
        product.approval_status = 'SUBMITTED'
        product.submitted_at = datetime.now()
        product.save(update_fields=['approval_status', 'submitted_at', 'updated_at'])

        action_name = 'RESUBMITTED' if old_status == 'CHANGES_REQUESTED' else 'SUBMITTED'
        ProductApprovalLog.objects.create(
            product=product,
            actor_username=actor_user.username if hasattr(actor_user, 'username') else str(actor_user),
            actor_role='SELLER',
            action=action_name,
            from_status=old_status,
            to_status='SUBMITTED',
            notes_to_seller=None,
            internal_notes='Submitted by seller for review.',
            snapshot_data=ApprovalService._create_snapshot(product)
        )
        return product

    @staticmethod
    @transaction.atomic
    def start_review(product: WholesaleProduct, admin_user) -> WholesaleProduct:
        """Admin marks product as actively under review."""
        if product.approval_status != 'SUBMITTED':
            raise ValidationError("Product is not currently in 'Submitted' queue.")

        product.approval_status = 'UNDER_REVIEW'
        product.reviewed_by = admin_user.username if hasattr(admin_user, 'username') else str(admin_user)
        product.save(update_fields=['approval_status', 'reviewed_by', 'updated_at'])

        ProductApprovalLog.objects.create(
            product=product,
            actor_username=product.reviewed_by,
            actor_role='ADMIN',
            action='ASSIGNED_REVIEW',
            from_status='SUBMITTED',
            to_status='UNDER_REVIEW',
            snapshot_data=ApprovalService._create_snapshot(product)
        )
        return product

    @staticmethod
    @transaction.atomic
    def request_changes(product: WholesaleProduct, admin_user, feedback: str, internal_notes: str = None) -> WholesaleProduct:
        """Admin requests specific revisions from the wholesaler."""
        if not feedback or len(feedback.strip()) < 5:
            raise ValidationError("Actionable feedback explaining required changes is mandatory.")

        if product.approval_status not in ('SUBMITTED', 'UNDER_REVIEW'):
            raise ValidationError("Can only request changes for products submitted or under review.")

        old_status = product.approval_status
        product.approval_status = 'CHANGES_REQUESTED'
        product.admin_feedback = feedback.strip()
        product.reviewed_by = admin_user.username if hasattr(admin_user, 'username') else str(admin_user)
        product.reviewed_at = datetime.now()
        product.save(update_fields=['approval_status', 'admin_feedback', 'reviewed_by', 'reviewed_at', 'updated_at'])

        ProductApprovalLog.objects.create(
            product=product,
            actor_username=product.reviewed_by,
            actor_role='ADMIN',
            action='CHANGES_REQUESTED',
            from_status=old_status,
            to_status='CHANGES_REQUESTED',
            notes_to_seller=feedback.strip(),
            internal_notes=internal_notes,
            snapshot_data=ApprovalService._create_snapshot(product)
        )
        return product

    @staticmethod
    @transaction.atomic
    def reject_product(product: WholesaleProduct, admin_user, reason: str, internal_notes: str = None) -> WholesaleProduct:
        """Admin rejects a product listing with a mandatory reason."""
        if not reason or len(reason.strip()) < 5:
            raise ValidationError("Rejection reason is mandatory.")

        if product.approval_status not in ('SUBMITTED', 'UNDER_REVIEW'):
            raise ValidationError("Can only reject products submitted or under review.")

        old_status = product.approval_status
        product.approval_status = 'REJECTED'
        product.rejection_reason = reason.strip()
        product.reviewed_by = admin_user.username if hasattr(admin_user, 'username') else str(admin_user)
        product.reviewed_at = datetime.now()
        product.save(update_fields=['approval_status', 'rejection_reason', 'reviewed_by', 'reviewed_at', 'updated_at'])

        ProductApprovalLog.objects.create(
            product=product,
            actor_username=product.reviewed_by,
            actor_role='ADMIN',
            action='REJECTED',
            from_status=old_status,
            to_status='REJECTED',
            notes_to_seller=reason.strip(),
            internal_notes=internal_notes,
            snapshot_data=ApprovalService._create_snapshot(product)
        )
        return product

    @staticmethod
    @transaction.atomic
    def approve_product(product: WholesaleProduct, admin_user, auto_publish: bool = True, internal_notes: str = None) -> WholesaleProduct:
        """
        Admin approves the listing.
        If wholesaler is approved and auto_publish is True -> sets to PUBLISHED.
        Otherwise -> sets to APPROVED.
        """
        # Security invariant: Wholesaler cannot approve their own listing
        if hasattr(admin_user, 'wholesaler_profile') and admin_user.wholesaler_profile.id == product.wholesaler.id:
            raise PermissionDenied("A seller cannot approve their own product.")

        if product.approval_status not in ('SUBMITTED', 'UNDER_REVIEW'):
            raise ValidationError(f"Cannot approve product in '{product.get_approval_status_display()}' status.")

        old_status = product.approval_status
        new_status = 'PUBLISHED' if (auto_publish and product.wholesaler.is_verified) else 'APPROVED'
        
        product.approval_status = new_status
        product.admin_feedback = None
        product.rejection_reason = None
        product.reviewed_by = admin_user.username if hasattr(admin_user, 'username') else str(admin_user)
        product.reviewed_at = datetime.now()
        product.approved_at = datetime.now()
        product.save(update_fields=['approval_status', 'admin_feedback', 'rejection_reason', 'reviewed_by', 'reviewed_at', 'approved_at', 'updated_at'])

        action_type = 'PUBLISHED' if new_status == 'PUBLISHED' else 'APPROVED'
        ProductApprovalLog.objects.create(
            product=product,
            actor_username=product.reviewed_by,
            actor_role='ADMIN',
            action=action_type,
            from_status=old_status,
            to_status=new_status,
            internal_notes=internal_notes,
            snapshot_data=ApprovalService._create_snapshot(product)
        )
        return product

    @staticmethod
    @transaction.atomic
    def pause_product(product: WholesaleProduct, actor_user) -> WholesaleProduct:
        """Pauses a published listing from active public display."""
        if product.approval_status != 'PUBLISHED':
            raise ValidationError("Only published listings can be paused.")

        product.approval_status = 'PAUSED'
        product.save(update_fields=['approval_status', 'updated_at'])

        ProductApprovalLog.objects.create(
            product=product,
            actor_username=actor_user.username if hasattr(actor_user, 'username') else str(actor_user),
            actor_role='SELLER',
            action='PAUSED',
            from_status='PUBLISHED',
            to_status='PAUSED',
            snapshot_data=ApprovalService._create_snapshot(product)
        )
        return product

    @staticmethod
    @transaction.atomic
    def resume_product(product: WholesaleProduct, actor_user) -> WholesaleProduct:
        """Resumes a paused listing to published state."""
        if product.approval_status != 'PAUSED':
            raise ValidationError("Only paused listings can be resumed.")
        if not product.wholesaler.is_verified:
            raise ValidationError("Wholesaler account is not currently verified.")

        product.approval_status = 'PUBLISHED'
        product.save(update_fields=['approval_status', 'updated_at'])

        ProductApprovalLog.objects.create(
            product=product,
            actor_username=actor_user.username if hasattr(actor_user, 'username') else str(actor_user),
            actor_role='SELLER',
            action='PUBLISHED',
            from_status='PAUSED',
            to_status='PUBLISHED',
            snapshot_data=ApprovalService._create_snapshot(product)
        )
        return product
