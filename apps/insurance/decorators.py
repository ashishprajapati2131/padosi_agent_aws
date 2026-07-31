from functools import wraps
from django.http import HttpResponseForbidden

def is_insurance_manager(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_manager()

def is_insurance_onboarding(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_onboarding()

def is_insurance_accounts(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_accounts()

def insurance_manager_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not is_insurance_manager(request.user):
            return HttpResponseForbidden("Unauthorized")
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def insurance_manager_or_onboarding_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not (is_insurance_manager(request.user) or is_insurance_onboarding(request.user)):
            return HttpResponseForbidden("Unauthorized")
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def insurance_manager_or_accounts_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not (is_insurance_manager(request.user) or is_insurance_accounts(request.user)):
            return HttpResponseForbidden("Unauthorized")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
