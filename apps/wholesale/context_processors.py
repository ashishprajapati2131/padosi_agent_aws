"""
Context processors for apps.wholesale.
Provides global template context: category navigation, current wholesaler profile, admin badge counts, feature flag.
"""
from apps.home.models.site_setting import SiteSetting
from .adapters.auth_bridge import get_wholesaler_profile, is_wholesale_admin, is_wholesale_enabled

def wholesale_context(request):
    """Adds wholesale global data to template contexts."""
    site_name = SiteSetting.get_value('site_name', 'PadosiAgent')
    context = {
        'wholesale_site_name': f"{site_name} Wholesale",
        'wholesale_enabled': is_wholesale_enabled(),
        'current_wholesaler': None,
        'is_wholesale_admin': False,
        'pending_approvals_count': 0,
        'header_categories': [],
    }
    
    try:
        from .models.category import ProductCategory
        context['header_categories'] = ProductCategory.objects.filter(
            is_active=True, parent__isnull=True
        ).prefetch_related('subcategories')[:8]
    except Exception:
        pass

    try:
        context['current_wholesaler'] = get_wholesaler_profile(request)
        context['is_wholesale_admin'] = is_wholesale_admin(request)
        if context['is_wholesale_admin']:
            from .models.product import WholesaleProduct
            context['pending_approvals_count'] = WholesaleProduct.objects.filter(
                approval_status__in=['SUBMITTED', 'UNDER_REVIEW']
            ).count()
    except Exception:
        pass

    return context
