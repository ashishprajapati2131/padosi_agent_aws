"""
Auth Bridge Adapter for Wholesale System in PadosiAgent.
Seamlessly bridges authentication with:
- PadosiAgent Admin sessions (cookie-based session_token or session['admin_id'])
- PadosiAgent Agent portal (request.user or Agent model)
- Direct Django Users and Wholesaler accounts
- Global Wholesale Marketplace Feature Flag
"""
from functools import wraps
from django.shortcuts import redirect, render
from django.contrib import messages
from django.urls import reverse
from apps.home.models.site_setting import SiteSetting

def is_wholesale_enabled():
    """
    Checks the platform feature flag for the wholesale marketplace.
    Default: False (disabled/OFF). Can be toggled from Admin Panel.
    """
    val = SiteSetting.get_value('wholesale_marketplace_enabled', False)
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() not in ('false', '0', 'off', 'no', 'disabled')
    return False

def get_wholesaler_profile(request):
    """
    Retrieves the WholesalerProfile for the current request.
    Checks:
      1. request._cached_wholesaler_profile
      2. request.user.wholesaler_profile
      3. session['wholesaler_id']
      4. Agent linked wholesaler account
    """
    if hasattr(request, '_cached_wholesaler_profile'):
        return request._cached_wholesaler_profile
    
    profile = None
    from apps.wholesale.models.profile import WholesalerProfile

    # 1. Direct Django user
    if hasattr(request, 'user') and request.user.is_authenticated:
        profile = WholesalerProfile.objects.filter(user=request.user).first()
    
    # 2. Session wholesaler ID
    if not profile and hasattr(request, 'session') and request.session.get('wholesaler_id'):
        profile = WholesalerProfile.objects.filter(id=request.session.get('wholesaler_id')).first()
        
    request._cached_wholesaler_profile = profile
    return profile

def is_wholesaler(request):
    """Returns True if the current user is an authenticated wholesaler."""
    return get_wholesaler_profile(request) is not None

def is_wholesale_admin(request):
    """
    Returns True if user is a Wholesale Administrator.
    Checks PadosiAgent admin session tokens, standard staff/superuser flags.
    """
    # 1. PadosiAgent custom session cookie
    try:
        from apps.admin_panel.views.dashboard import _get_admin_from_session
        admin_id = _get_admin_from_session(request)
        if admin_id:
            return True
    except Exception:
        pass

    # 2. Django session admin_id
    if hasattr(request, 'session') and request.session.get('admin_id'):
        return True

    # 3. Standard Django superuser / staff
    if hasattr(request, 'user') and request.user.is_authenticated:
        return bool(request.user.is_staff or request.user.is_superuser)

    return False

def wholesale_feature_gate(view_func):
    """
    Enforces the 'wholesale_marketplace_enabled' feature flag.
    If disabled:
      - Admins can still access for maintenance/review.
      - Other users see a polite 'Marketplace Currently Inactive' notice.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Admins always bypass the gate
        if is_wholesale_admin(request):
            return view_func(request, *args, **kwargs)

        if not is_wholesale_enabled():
            return render(request, 'wholesale/public/disabled.html', {
                'wholesale_site_name': SiteSetting.get_value('site_name', 'PadosiAgent'),
            }, status=503)

        return view_func(request, *args, **kwargs)
    return _wrapped_view

def wholesaler_required(view_func):
    """Decorator ensuring request comes from an authenticated Wholesaler."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        profile = get_wholesaler_profile(request)
        if profile:
            return view_func(request, *args, **kwargs)

        # If user is a wholesale admin without their own wholesaler profile, redirect to admin dashboard
        if is_wholesale_admin(request):
            messages.info(request, "You are logged in as an Administrator. Redirecting to Wholesale Admin Operations.")
            return redirect('wholesale:admin_dashboard')

        if not hasattr(request, 'user') or not request.user.is_authenticated:
            messages.warning(request, "Please log in to access the Wholesaler Portal.")
            return redirect(f"{reverse('wholesale:wholesaler_login')}?next={request.get_full_path()}")

        messages.info(request, "Please register your business details to continue.")
        return redirect('wholesale:wholesaler_register')

    return _wrapped_view

def wholesale_admin_required(view_func):
    """Decorator ensuring request comes from a Wholesale Administrator."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not is_wholesale_admin(request):
            messages.error(request, "Administrative privileges are required to access this portal.")
            if not request.user.is_authenticated:
                return redirect(f"{reverse('wholesale:wholesaler_login')}?next={request.get_full_path()}")
            return redirect('wholesale:catalog')
        return view_func(request, *args, **kwargs)
    return _wrapped_view
