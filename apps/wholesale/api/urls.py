"""
API URL routes for wholesale endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .viewsets import PublicWholesaleProductViewSet, PublicCategoryViewSet, BuyerInquiryCreateViewSet

router = DefaultRouter()
router.register(r'products', PublicWholesaleProductViewSet, basename='api-product')
router.register(r'categories', PublicCategoryViewSet, basename='api-category')
router.register(r'inquiries', BuyerInquiryCreateViewSet, basename='api-inquiry')

urlpatterns = [
    path('', include(router.urls)),
]
