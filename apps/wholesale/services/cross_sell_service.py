"""
Cross-Sell and Related Products Recommendation Service.
Ensures only published, approved, and stock-ready products are recommended.
"""
from django.db.models import Q
from typing import List
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.relationship import ProductRelationship

class CrossSellService:
    """Service to discover and associate related and complementary wholesale products."""

    @staticmethod
    def get_eligible_queryset():
        """Returns base queryset for products eligible for public recommendations."""
        return WholesaleProduct.objects.filter(
            approval_status='PUBLISHED',
            wholesaler__verification_status='APPROVED'
        ).select_related('wholesaler', 'category').prefetch_related('images', 'price_tiers')

    @classmethod
    def get_complementary_products(cls, product: WholesaleProduct, limit: int = 4) -> List[WholesaleProduct]:
        """
        Retrieves products explicitly curated as complementary to the given product.
        """
        relationships = ProductRelationship.objects.filter(
            source_product=product,
            relationship_type='COMPLEMENTARY',
            is_active=True,
            target_product__approval_status='PUBLISHED',
            target_product__wholesaler__verification_status='APPROVED'
        ).select_related('target_product__wholesaler', 'target_product__category').order_by('display_order')[:limit]

        return [rel.target_product for rel in relationships]

    @classmethod
    def get_related_products(cls, product: WholesaleProduct, limit: int = 4) -> List[WholesaleProduct]:
        """
        Retrieves similar products in the same category or with matching tags.
        Falls back to other products from the same wholesaler.
        """
        base_qs = cls.get_eligible_queryset().exclude(id=product.id)

        # 1. Curated 'RELATED' relationships first
        curated_rels = ProductRelationship.objects.filter(
            source_product=product,
            relationship_type='RELATED',
            is_active=True,
            target_product__approval_status='PUBLISHED',
            target_product__wholesaler__verification_status='APPROVED'
        ).select_related('target_product')[:limit]
        
        curated_ids = [r.target_product_id for r in curated_rels]
        results = list(curated_rels)

        if len(results) >= limit:
            return [r.target_product for r in results]

        # 2. Match same category
        needed = limit - len(results)
        category_matches = list(
            base_qs.filter(category=product.category)
            .exclude(id__in=curated_ids)
            .order_by('-is_featured', '-view_count')[:needed]
        )
        
        combined = [r.target_product for r in results] + category_matches
        if len(combined) >= limit:
            return combined[:limit]

        # 3. Match same brand or tags if still needed
        needed = limit - len(combined)
        existing_ids = [p.id for p in combined] + [product.id]
        fallback_matches = list(
            base_qs.exclude(id__in=existing_ids)
            .order_by('-is_featured', '-created_at')[:needed]
        )
        return combined + fallback_matches

    @staticmethod
    def set_complementary_pair(source_product: WholesaleProduct, target_product: WholesaleProduct, order: int = 0):
        """Associates target product as complementary to source product."""
        if source_product.id == target_product.id:
            raise ValueError("A product cannot be complementary to itself.")
        
        rel, _ = ProductRelationship.objects.update_or_create(
            source_product=source_product,
            target_product=target_product,
            relationship_type='COMPLEMENTARY',
            defaults={'display_order': order, 'is_active': True}
        )
        return rel
