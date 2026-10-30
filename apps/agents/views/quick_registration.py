"""Save a name and phone from the public popup or registration gate."""

import json
import re
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from apps.agents.services.registration_leads import capture_quick_lead, mark_form_completed, normalize_phone

_NAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9 ._\-]{1,69}')
_TWO_LETTERS_RE = re.compile(r'[A-Za-z].*[A-Za-z]|[A-Za-z]{2}')
_PHONE_RE = re.compile(r'^[6-9]\d{9}$')
_REF_RE = re.compile(r'[A-Za-z0-9_-]{1,50}')
_PIN_RE = re.compile(r'^[1-9]\d{5}$')
_SEGMENT_IDS = frozenset({'health', 'life', 'motor', 'sme'})
_REUSABLE_AGENT_STATUSES = ('incomplete', 'pending_payment', 'rejected')


def _client_ip(request):
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


def _welcome_preview_url(ref):
    url = reverse('agents:welcome_preview')
    if ref:
        return f'{url}?{urlencode({"ref": ref})}'
    return url


def _source_url(request):
    page = (request.POST.get('page') or '').strip()
    if page.startswith('/') and not page.startswith('//'):
        return request.build_absolute_uri(page)[:500]
    return (request.build_absolute_uri() or '')[:500]


def _full_popup_fields(json_body, post):
    email = (json_body.get('email') or post.get('email') or '').strip()
    pincode = (
        json_body.get('pincode')
        or json_body.get('agent_pincode')
        or post.get('pincode')
        or post.get('agent_pincode')
        or ''
    ).strip()
    segments = _parse_segments(json_body, post)
    return email, pincode, segments


def _is_full_popup_submission(json_body, post):
    email, pincode, segments = _full_popup_fields(json_body, post)
    return bool(email and pincode and segments)


def _validate(name, phone):
    errors = {}
    if not _NAME_RE.fullmatch(name) or not _TWO_LETTERS_RE.search(name):
        errors['name'] = 'Enter your name using letters (2–70 characters).'
    if not _PHONE_RE.fullmatch(phone):
        errors['phone'] = 'Enter a valid 10-digit mobile number starting with 6, 7, 8, or 9.'
    return errors


def _parse_segments(json_body, post):
    raw = json_body.get('segments')
    if raw is None:
        raw = post.getlist('segments') or post.getlist('segments[]')
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(',') if part.strip()]
    if not isinstance(raw, (list, tuple)):
        raw = []
    cleaned = []
    for item in raw:
        key = str(item or '').strip().lower()
        if key in _SEGMENT_IDS and key not in cleaned:
            cleaned.append(key)
    return cleaned


def _unique_draft_slug(fullname, email=''):
    from apps.agents.models import AgentDraft, AgentProfile
    base = slugify(fullname or '') or slugify((email or '').split('@')[0]) or 'agent'
    slug = base
    n = 1
    while (
        AgentProfile.objects.filter(slug=slug).exists()
        or AgentDraft.objects.filter(slug=slug).exists()
    ):
        slug = f'{base}-{n}'
        n += 1
        if n > 80:
            import time
            slug = f'{base}-{int(time.time())}'
            break
    return slug[:255]


def _create_or_update_popup_draft(request, *, name, phone, email, pincode, state, segments):
    from apps.agents.models import AgentDraft

    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key

    draft = None
    draft_id = request.session.get('current_draft_id')
    if draft_id:
        draft = AgentDraft.objects.filter(pk=draft_id).first()
    if not draft and email:
        draft = AgentDraft.objects.filter(email__iexact=email).order_by('-pk').first()
    if not draft:
        draft = AgentDraft.objects.filter(mobile=phone).order_by('-pk').first()
    if not draft:
        draft = AgentDraft(session_key=session_key, email=email)

    draft.session_key = session_key
    draft.email = email
    draft.email_verified = True
    draft.fullname = name[:70]
    draft.mobile = phone
    draft.whatsapp = phone
    draft.agent_pincode = pincode
    draft.state = state or ''
    draft.segments = segments
    if not draft.slug:
        draft.slug = _unique_draft_slug(name, email)
    draft.registration_step = 1
    draft.save()

    request.session['current_draft_id'] = draft.pk
    request.session['reg_step'] = 2
    request.session['post_payment_landing'] = 'edit_profile'
    request.session.modified = True
    return draft


def _validate_popup_extras(json_body, post, email, pincode, segments):
    errors = {}
    if not email:
        errors['email'] = 'Enter a valid email address.'
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = 'Enter a valid email address.'
        else:
            from apps.agents.models import Agent
            from apps.agents.services.account_auth import email_owned_by_non_agent_account
            if email_owned_by_non_agent_account(email):
                errors['email'] = (
                    'This email is already used by a PadosiAgent partner or staff account. '
                    'Please use a different email.'
                )
            else:
                existing = Agent.objects.filter(email__iexact=email).first()
                if existing and existing.status not in _REUSABLE_AGENT_STATUSES:
                    errors['email'] = 'This email is already registered. Please login.'
                    errors['login'] = True

    if not _PIN_RE.fullmatch(pincode):
        errors['pincode'] = 'Enter a valid 6-digit pincode.'
        pin_row = None
    else:
        from apps.agents.views.registration import _resolve_registration_pincode
        pin_row = _resolve_registration_pincode(pincode)
        if not pin_row:
            errors['pincode'] = 'This pincode was not found. Please enter a valid pincode.'

    if not segments:
        errors['segments'] = 'Select at least one insurance segment.'
    elif any(seg not in _SEGMENT_IDS for seg in segments):
        errors['segments'] = 'Please select a valid insurance segment.'

    return errors, pin_row


def _wants_json(request):
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
        or request.content_type == 'application/json'
    )


def _attach_quick_reg_cookie(response, request, phone):
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


def _success_payload(lead, name, phone, redirect, reload=False):
    return {
        'ok': True,
        'redirect': redirect,
        'reload': reload,
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


@require_http_methods(['GET', 'POST'])
def quick_registration(request):
    """Public popup creates a draft and opens the card/website preview.

    The registration-page gate still only needs name + phone and stays on that page.
    """
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
    on_registration_page = page.startswith('/agent-registration') or page.startswith('/register')
    full_popup = _is_full_popup_submission(json_body, request.POST)
    if (json_body.get('website') or request.POST.get('website') or '').strip():
        errors = {'form': 'Something went wrong. Please try again.'}
    else:
        name = (json_body.get('name') or request.POST.get('name') or '').strip()
        phone = normalize_phone(json_body.get('phone') or request.POST.get('phone'))
        errors = _validate(name, phone)
        if not errors and (full_popup or not on_registration_page):
            email, pincode, segments = _full_popup_fields(json_body, request.POST)
            extra_errors, pin_row = _validate_popup_extras(json_body, request.POST, email, pincode, segments)
            errors.update(extra_errors)
        else:
            email = ''
            pincode = ''
            segments = []
            pin_row = None

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
            elif on_registration_page and not full_popup:
                target = _registration_url(ref)
                if _wants_json(request):
                    response = JsonResponse(_success_payload(lead, name, phone, '', reload=True))
                else:
                    response = redirect(target)
                return _attach_quick_reg_cookie(response, request, phone)
            else:
                state = ((getattr(pin_row, 'state', None) or '') if pin_row else '').strip()
                draft = _create_or_update_popup_draft(
                    request,
                    name=name,
                    phone=phone,
                    email=email,
                    pincode=pincode,
                    state=state,
                    segments=segments,
                )
                try:
                    mark_form_completed(request, draft=draft)
                except Exception:
                    pass
                target = _welcome_preview_url(ref)
                if _wants_json(request):
                    payload = _success_payload(lead, name, phone, target)
                    payload['draft_id'] = draft.pk
                    response = JsonResponse(payload)
                else:
                    response = redirect(target)
                return _attach_quick_reg_cookie(response, request, phone)

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
