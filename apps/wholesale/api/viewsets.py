"""
REST API Viewsets for Wholesale System.
"""
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.inquiry import BuyerInquiry
from apps.wholesale.services.pricing_service import PricingService
from apps.wholesale.services.cross_sell_service import CrossSellService
from .serializers import (
    WholesaleProductCatalogSerializer, WholesaleProductDetailSerializer,
    ProductCategorySerializer, BuyerInquirySerializer
)

class PublicWholesaleProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public Read-Only API for Wholesale Marketplace.
    Strictly filters out any unapproved or unverified products.
    """
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        qs = WholesaleProduct.objects.filter(
            approval_status='PUBLISHED',
            wholesaler__verification_status='APPROVED'
        ).select_related('wholesaler', 'category').prefetch_related('images', 'price_tiers', 'variants')

        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(brand__icontains=q) | Q(sku__icontains=q))

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category__slug=category)

        return qs.order_by('-is_featured', '-view_count')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return WholesaleProductDetailSerializer
        return WholesaleProductCatalogSerializer

    @action(detail=True, methods=['get'])
    def calculate_price(self, request, slug=None):
        """Calculates volume pricing for given quantity: ?quantity=50"""
        product = self.get_object()
        try:
            qty = int(request.query_params.get('quantity', product.moq))
        except (ValueError, TypeError):
            qty = product.moq

        summary = PricingService.calculate_order_summary(product, qty)
        return Response(summary)

    @action(detail=True, methods=['get'])
    def recommendations(self, request, slug=None):
        """Returns complementary and related products for cross-sell."""
        product = self.get_object()
        comp = CrossSellService.get_complementary_products(product, limit=4)
        rel = CrossSellService.get_related_products(product, limit=4)

        return Response({
            'complementary': WholesaleProductCatalogSerializer(comp, many=True).data,
            'related': WholesaleProductCatalogSerializer(rel, many=True).data,
        })


class PublicCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """List of active product categories."""
    permission_classes = [permissions.AllowAny]
    queryset = ProductCategory.objects.filter(is_active=True).order_by('sort_order', 'name')
    serializer_class = ProductCategorySerializer
    lookup_field = 'slug'


from rest_framework.throttling import AnonRateThrottle

class InquiryAnonThrottle(AnonRateThrottle):
    rate = '10/minute'

class BuyerInquiryCreateViewSet(viewsets.GenericViewSet):
    """Allows buyers to submit quotations."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [InquiryAnonThrottle]
    serializer_class = BuyerInquirySerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inquiry = serializer.save()
        return Response({
            'success': True,
            'inquiry_id': inquiry.id,
            'message': 'Quotation request submitted successfully.'
        }, status=status.HTTP_201_CREATED)
