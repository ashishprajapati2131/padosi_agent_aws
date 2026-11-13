"""Lead capture endpoints: contact form and exit-popup quick lead (rate limit + honeypot helpers)."""
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import re
import logging
from apps.admin_panel.models.contact_submission import ContactSubmission
from django.core.cache import cache

# Keep the original logger name so log lines/filters are unchanged.
logger = logging.getLogger('apps.home.views.pages')

CONTACT_MAX_PER_IP = 5
CONTACT_WINDOW_SECONDS = 60 * 60
QUICK_LEAD_MAX_PER_IP = 5
QUICK_LEAD_WINDOW_SECONDS = 60 * 60


def _rate_limited(key, limit, window):
    """Count this attempt atomically; True once more than `limit` attempts hit the window."""
    try:
        count = 1 if cache.add(key, 1, timeout=window) else cache.incr(key)
    except Exception:
        # incr raises if the key expired between add and incr; fail open like before.
        logger.warning('Rate-limit counter update failed for %s', key, exc_info=True)
        return False
    return count > limit


def _is_honeypot_hit(request):
    """Bots fill the hidden website_url field; real visitors never see it."""
    return bool(request.POST.get('website_url', '').strip())


@require_POST
def contact_submit(request):
    """
    AJAX contact form handler — mirrors Laravel's ContactController.store().
    Validates input, saves to contact_submissions table, returns JSON.
    """
    logger.info('CONTACT FORM SUBMISSION received')

    from apps.admin_panel.middleware import ThreatMonitorMiddleware
    rl_key = f"rl_contact_{ThreatMonitorMiddleware.get_client_ip(request)}"
    if _rate_limited(rl_key, CONTACT_MAX_PER_IP, CONTACT_WINDOW_SECONDS):
        return JsonResponse({
            'success': False,
            'message': 'Too many messages sent from your network. Please try again in an hour.',
        }, status=429)
    contact_ok = JsonResponse({
        'success': True,
        'message': 'Thank you! Your message has been sent successfully. We will get back to you soon.',
    }, status=200)
    if _is_honeypot_hit(request):
        return contact_ok

    try:
        name    = request.POST.get('name', '').strip()
        mobile  = request.POST.get('mobile', '').strip()
        email   = request.POST.get('email', '').strip()
        company = request.POST.get('company', '').strip()
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()

        # Validation
        errors = {}
        if len(name) < 2 or len(name) > 100:
            errors['name'] = ['Full name must be between 2 and 100 characters.']
        if not re.fullmatch(r'[0-9]{10}', mobile):
            errors['mobile'] = ['Please enter a valid 10-digit mobile number.']
        if not email or '@' not in email or len(email) > 100:
            errors['email'] = ['Please enter a valid email address.']
        if len(subject) < 5 or len(subject) > 100:
            errors['subject'] = ['Subject must be between 5 and 100 characters.']
        if len(message) < 10 or len(message) > 1000:
            errors['message'] = ['Message must be between 10 and 1000 characters.']

        if errors:
            return JsonResponse({
                'success': False,
                'message': 'Please fix the validation errors below.',
                'errors':  errors,
            }, status=422)

        # Save to DB
        submission = ContactSubmission.objects.create(
            name=name,
            mobile=mobile,
            email=email,
            company=company or None,
            subject=subject,
            message=message,
            status='pending',
        )
        logger.info('CONTACT FORM SUBMISSION — saved #%s ref=%s', submission.id, submission.reference_id)
        return contact_ok

    except Exception as exc:
        logger.error('CONTACT FORM SUBMISSION — Error: %s', exc, exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to submit your message. Please try again.',
        }, status=400)


@require_POST
def quick_lead_capture(request):
    """Handle instant lead inquiries submitted via the exit-intent popup."""
    from apps.admin_panel.middleware import ThreatMonitorMiddleware
    rl_key = f"rl_quick_lead_{ThreatMonitorMiddleware.get_client_ip(request)}"
    if _rate_limited(rl_key, QUICK_LEAD_MAX_PER_IP, QUICK_LEAD_WINDOW_SECONDS):
        return JsonResponse({
            'status': 'error',
            'message': 'Too many requests from your network. Please try again in an hour.'
        }, status=429)
    lead_ok = {
        'status': 'success',
        'message': 'Thank you! A verified neighbourhood advisor will connect with you shortly.'
    }
    if _is_honeypot_hit(request):
        return JsonResponse(lead_ok)

    name = request.POST.get('name', '').strip()
    mobile = request.POST.get('mobile', '').strip()
    pincode = request.POST.get('pincode', '').strip()
    insurance_type = request.POST.get('insurance_type', 'General').strip()

    if not name or not mobile:
        return JsonResponse({'status': 'error', 'message': 'Name and mobile number are required.'}, status=400)

    clean_mobile = re.sub(r'[^0-9]', '', mobile)
    # Strip +91 / trunk 0 instead of truncating, so "+91 98765 43210" stays 9876543210.
    if len(clean_mobile) == 12 and clean_mobile.startswith('91'):
        clean_mobile = clean_mobile[2:]
    elif len(clean_mobile) == 11 and clean_mobile.startswith('0'):
        clean_mobile = clean_mobile[1:]
    if not re.fullmatch(r'[6-9]\d{9}', clean_mobile):
        return JsonResponse({'status': 'error', 'message': 'Please enter a valid 10-digit mobile number.'}, status=400)

    email = request.POST.get('email', '').strip()
    if email:
        from django.core.exceptions import ValidationError
        from django.core.validators import validate_email
        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({'status': 'error', 'message': 'Please enter a valid email address.'}, status=400)
    email = email or f"lead_{clean_mobile}@padosiagent.com"
    subject = f"Exit Popup Lead: {insurance_type}"[:100]
    message = f"Customer Name: {name}\nMobile: {mobile}\nPincode: {pincode}\nInsurance Type: {insurance_type}\nSource: Exit-Intent Popup"

    try:
        ContactSubmission.objects.create(
            name=name[:100],
            email=email,
            mobile=clean_mobile[:10],
            subject=subject,
            message=message,
            status='pending'
        )
        return JsonResponse(lead_ok)
    except Exception as e:
        logger.error("Error creating exit popup lead: %s", e)
        return JsonResponse({'status': 'error', 'message': 'Could not submit your request. Please try again.'}, status=500)
