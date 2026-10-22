"""Save a name and phone from the public popup or registration gate."""

import re
from urllib.parse import urlencode

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.agents.services.registration_leads import capture_quick_lead, normalize_phone

_NAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9 ._\-]{1,69}')
_TWO_LETTERS_RE = re.compile(r'[A-Za-z].*[A-Za-z]|[A-Za-z]{2}')
_PHONE_RE = re.compile(r'^[6-9]\d{9}$')
_REF_RE = re.compile(r'[A-Za-z0-9_-]{1,50}')


def _client_ip(request):
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_ipv46_address
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


import json

def _wants_json(request):
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
        or request.content_type == 'application/json'
    )


@require_http_methods(['GET', 'POST'])
def quick_registration(request):
    """A valid submit opens or unlocks agent registration without duplicate leads."""
    if request.method == 'GET':
        return redirect('home:home')

    json_body = {}
    if request.content_type == 'application/json' and request.body:
        try:
            json_body = json.loads(request.body.decode('utf-8'))
        except Exception:
            json_body = {}

    ref = _clean_ref(json_body.get('ref') or request.POST.get('ref') or request.session.get('ref_code'))
    page = (json_body.get('page') or request.POST.get('page') or '').strip()
    on_registration = page.startswith('/agent-registration') or page.startswith('/register')
    if (json_body.get('website') or request.POST.get('website') or '').strip():
        errors = {'form': 'Something went wrong. Please try again.'}
    else:
        name = (json_body.get('name') or request.POST.get('name') or '').strip()
        phone = normalize_phone(json_body.get('phone') or request.POST.get('phone'))
        errors = _validate(name, phone)
        if not errors:
            lead, blocked = capture_quick_lead(
                request,
                name=name,
                phone=phone,
                ref_code=ref,
                source_url=_source_url(request),
            )
            if blocked:
                errors = {'phone': blocked, 'login': True}
            else:
                target = _registration_url(ref)
                if _wants_json(request):
                    payload = {
                        'ok': True,
                        'redirect': '' if on_registration else target,
                        'reload': bool(on_registration),
                        'lead_id': lead.pk if lead else None,
                        'lead': {
                            'id': lead.pk if lead else None,
                            'name': lead.name if lead else name[:100],
                            'phone': lead.phone if lead else phone,
                            'whatsapp': lead.phone if lead else phone,
                            'status': lead.status if lead else 'quick_registered',
                        },
                        'name': name[:100],
                        'phone': phone,
                        'whatsapp': phone,
                    }
                    response = JsonResponse(payload)
                else:
                    response = redirect(target)

                # Set cookie to preserve lead and registration progress across tabs and sessions
                try:
                    from django.conf import settings
                    is_secure = not settings.DEBUG and request.is_secure()
                    response.set_cookie(
                        'pa_quick_reg_phone',
                        phone,
                        max_age=30 * 86400,
                        httponly=True,
                        samesite='Lax',
                        secure=is_secure,
                    )
                except Exception:
                    pass

                return response

    if _wants_json(request):
        has_account = bool(errors.get('login'))
        status_code = 409 if has_account else 422
        payload = {
            'ok': False,
            'errors': errors,
            'has_account': has_account,
        }
        if has_account:
            payload['login_url'] = reverse('agents:agent_login')
            payload['redirect'] = reverse('agents:agent_login')
        return JsonResponse(payload, status=status_code)
    if errors.get('login'):
        return redirect('agents:agent_login')
    return redirect('home:home')
