"""Save a name and phone from the public eligibility popup, then continue registration."""

import re
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.admin_panel.models import RegistrationLead

_NAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9 ._\-]{1,69}')
_TWO_LETTERS_RE = re.compile(r'[A-Za-z].*[A-Za-z]|[A-Za-z]{2}')
_PHONE_RE = re.compile(r'^[6-9]\d{9}$')
_REF_RE = re.compile(r'[A-Za-z0-9_-]{1,50}')


def _client_ip(request):
    from apps.admin_panel.middleware import ThreatMonitorMiddleware
    ip = ThreatMonitorMiddleware.get_client_ip(request) or request.META.get('REMOTE_ADDR') or ''
    try:
        validate_ipv46_address(ip)
    except ValidationError:
        return None
    return ip


def _clean_ref(value):
    ref = (value or '').strip()[:50]
    if _REF_RE.fullmatch(ref):
        return ref
    return ''


def _registration_url(ref):
    url = reverse('agents:agent_registration')
    if ref:
        return f'{url}?{urlencode({"ref": ref})}'
    return url


def _source_url(request):
    page = (request.POST.get('page') or '').strip()
    if page.startswith('/') and not page.startswith('//'):
        return request.build_absolute_uri(page)[:500]
    return (request.build_absolute_uri() or '')[:500]


def _validate(name, phone):
    errors = {}
    if not _NAME_RE.fullmatch(name) or not _TWO_LETTERS_RE.search(name):
        errors['name'] = 'Enter your name using letters (2–70 characters).'
    if not _PHONE_RE.fullmatch(phone):
        errors['phone'] = 'Enter a valid 10-digit mobile number starting with 6, 7, 8, or 9.'
    return errors


def _wants_json(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


@require_http_methods(['GET', 'POST'])
def quick_registration(request):
    """The standalone page is retired. A valid submit still opens agent registration."""
    if request.method == 'GET':
        return redirect('home:home')

    ref = _clean_ref(request.POST.get('ref'))
    if (request.POST.get('website') or '').strip():
        errors = {'form': 'Something went wrong. Please try again.'}
    else:
        name = (request.POST.get('name') or '').strip()
        phone = re.sub(r'\D', '', request.POST.get('phone') or '')[:10]
        errors = _validate(name, phone)
        if not errors:
            RegistrationLead.objects.create(
                name=name[:100],
                phone=phone,
                status='Started',
                source_url=_source_url(request),
                ip_address=_client_ip(request),
                user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:500],
                ref_code=ref,
            )
            request.session['quick_reg_name'] = name[:100]
            request.session['quick_reg_phone'] = phone
            request.session['quick_reg_continue'] = True
            request.session.pop('quick_reg_success', None)
            target = _registration_url(ref)
            if _wants_json(request):
                return JsonResponse({'ok': True, 'redirect': target})
            return redirect(target)

    if _wants_json(request):
        return JsonResponse({'ok': False, 'errors': errors}, status=400)
    return redirect('home:home')
