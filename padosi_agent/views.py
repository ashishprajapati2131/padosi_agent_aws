import logging
from django.http import JsonResponse, HttpResponseRedirect
from django.middleware.csrf import get_token, REASON_BAD_TOKEN, REASON_NO_CSRF_COOKIE, REASON_NO_REFERER
from django.contrib import messages
from django.urls import reverse

logger = logging.getLogger(__name__)


def csrf_failure_view(request, reason=""):
    """
    Custom CSRF Failure View.
    Ensures end clients NEVER get stuck on raw 403 Forbidden pages due to expired/stale CSRF cookies or long idle times.
    
    - For AJAX / API / JSON requests: Returns a clean JSON 403 response with a fresh CSRF token so JS can auto-retry.
    - For HTML Form submissions: Sets a fresh CSRF cookie, adds a user-friendly toast message, and redirects back seamlessly.
    """
    logger.warning(f"CSRF Validation Failure for client IP {request.META.get('REMOTE_ADDR')}: {reason} at {request.path}")
    
    # 1. Force generate a brand new fresh CSRF token for the client
    fresh_token = get_token(request)

    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
        or request.content_type == 'application/json'
        or request.path.startswith('/api/')
    )

    if is_ajax:
        response = JsonResponse({
            'success': False,
            'csrf_error': True,
            'csrf_token': fresh_token,
            'message': 'Your security session was refreshed. Please try submitting again.'
        }, status=403)
        # Ensure fresh token is set in response cookie
        response.set_cookie('padosi_csrf_token', fresh_token, path='/', samesite='Lax')
        return response

    # Standard HTML Form Submission handling
    messages.warning(
        request, 
        "Your security session timed out due to inactivity. We have refreshed your security token — please try submitting your form again."
    )
    
    referer = request.META.get('HTTP_REFERER')
    if referer and referer.startswith(('http://', 'https://')):
        redirect_url = referer
    else:
        redirect_url = request.path or '/'

    response = HttpResponseRedirect(redirect_url)
    response.set_cookie('padosi_csrf_token', fresh_token, path='/', samesite='Lax')
    return response


def csrf_refresh_api(request):
    """
    Lightweight API endpoint for client-side JS to fetch a fresh CSRF token on-demand.
    """
    fresh_token = get_token(request)
    response = JsonResponse({
        'success': True,
        'csrf_token': fresh_token
    })
    response.set_cookie('padosi_csrf_token', fresh_token, path='/', samesite='Lax')
    return response
