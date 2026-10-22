"""Create and advance one RegistrationLead per mobile number."""

import re

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.admin_panel.models import RegistrationLead

STATUS_QUICK_REGISTERED = 'quick_registered'
STATUS_FORM_STARTED = 'form_started'
STATUS_FORM_COMPLETED = 'form_completed'
STATUS_PAYMENT_COMPLETED = 'payment_completed'
STATUS_CONVERTED = 'converted'
STATUS_ABANDONED = 'abandoned'

SESSION_NAME = 'quick_reg_name'
SESSION_PHONE = 'quick_reg_phone'
SESSION_LEAD_ID = 'quick_reg_lead_id'
SESSION_CONTINUE = 'quick_reg_continue'

_STATUS_RANK = {
    STATUS_ABANDONED: 0,
    STATUS_QUICK_REGISTERED: 1,
    STATUS_FORM_STARTED: 2,
    STATUS_FORM_COMPLETED: 3,
    STATUS_PAYMENT_COMPLETED: 4,
    STATUS_CONVERTED: 5,
}

BLOCKING_AGENT_STATUSES = (
    'active',
    'pending_approval',
    'suspended',
    'blacklisted',
    'inactive',
)
REUSABLE_AGENT_STATUSES = ('incomplete', 'pending_payment', 'rejected')
_PHONE_RE = re.compile(r'^[6-9]\d{9}$')


def normalize_phone(value):
    digits = re.sub(r'\D', '', value or '')
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith('0') and len(digits) == 11:
        digits = digits[1:]
    return digits[-10:] if len(digits) >= 10 else digits


def _safe_client_ip(request):
    try:
        from django.core.exceptions import ValidationError
        from django.core.validators import validate_ipv46_address
        from apps.admin_panel.middleware import ThreatMonitorMiddleware
        ip = ThreatMonitorMiddleware.get_client_ip(request) or request.META.get('REMOTE_ADDR') or ''
        validate_ipv46_address(ip)
        return ip
    except Exception:
        return None


def bind_session(request, lead):
    if not lead or not request:
        return
    request.session[SESSION_NAME] = (lead.name or '')[:100]
    request.session[SESSION_PHONE] = lead.phone
    request.session[SESSION_LEAD_ID] = lead.pk
    request.session[SESSION_CONTINUE] = True
    request.session.pop('quick_reg_success', None)

    # Restore draft progress if not already in session
    if not request.session.get('current_draft_id'):
        try:
            from apps.agents.models import AgentDraft
            draft = None
            if lead.draft_id:
                draft = AgentDraft.objects.filter(pk=lead.draft_id).first()
            if not draft and lead.phone:
                draft = AgentDraft.objects.filter(mobile=lead.phone).order_by('-pk').first()
            if draft:
                request.session['current_draft_id'] = draft.pk
                if not lead.draft_id:
                    lead.draft_id = draft.pk
                    lead.save(update_fields=['draft_id'])
        except Exception:
            pass

    request.session.modified = True


def session_lead(request):
    if not request:
        return None
    lead_id = request.session.get(SESSION_LEAD_ID)
    phone = normalize_phone(request.session.get(SESSION_PHONE))
    if not phone and hasattr(request, 'COOKIES'):
        cookie_phone = normalize_phone(request.COOKIES.get('pa_quick_reg_phone'))
        if _PHONE_RE.fullmatch(cookie_phone):
            phone = cookie_phone
    lead = None
    if lead_id:
        lead = RegistrationLead.objects.filter(pk=lead_id).first()
    if lead is None and _PHONE_RE.fullmatch(phone):
        lead = RegistrationLead.objects.filter(phone=phone).first()
    if lead and lead.status != STATUS_CONVERTED:
        bind_session(request, lead)
        return lead
    return None


def _agent_for_phone(phone):
    from django.db.models import Q
    from apps.agents.models import Agent
    variants = {phone, f'91{phone}', f'+91{phone}', f'0{phone}'}
    query = Q(mobile=phone)
    for value in variants:
        query |= Q(mobile=value)
    return (
        Agent.objects.filter(query)
        .exclude(status='deleted')
        .order_by('-id')
        .first()
    )


def _advance_status(lead, target):
    current = _STATUS_RANK.get(lead.status, 0)
    wanted = _STATUS_RANK.get(target, 0)
    if wanted > current:
        lead.status = target
        return True
    return False


def _apply_form_payment_flags(lead):
    rank = _STATUS_RANK.get(lead.status, 0)
    lead.form_filled = rank >= _STATUS_RANK[STATUS_FORM_COMPLETED]
    if rank >= _STATUS_RANK[STATUS_PAYMENT_COMPLETED]:
        lead.payment_status = 'completed'
    elif lead.payment_status not in ('completed', 'failed', 'pending', 'none'):
        lead.payment_status = 'none'


def capture_quick_lead(request, name, phone, ref_code='', source_url=''):
    """Save or reuse one lead for this phone. Does not create duplicates."""
    phone = normalize_phone(phone)
    name = (name or '').strip()[:100]
    agent = _agent_for_phone(phone)
    if agent and agent.status in BLOCKING_AGENT_STATUSES:
        return None, (
            'This mobile number is already registered. Please login with that account.'
        )

    existing = RegistrationLead.objects.filter(phone=phone).order_by('-updated_at', '-id').first()
    if existing and existing.status == STATUS_CONVERTED:
        return None, (
            'This mobile number is already registered. Please login with that account.'
        )

    ip = _safe_client_ip(request)
    user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:500] if (request and hasattr(request, 'META')) else ''

    with transaction.atomic():
        lead = (
            RegistrationLead.objects.select_for_update()
            .filter(phone=phone)
            .order_by('-updated_at', '-id')
            .first()
        )
        if lead is None:
            lead = RegistrationLead(
                name=name,
                phone=phone,
                status=STATUS_QUICK_REGISTERED,
                source_url=(source_url or '')[:500],
                ip_address=ip,
                user_agent=user_agent,
                ref_code=(ref_code or '')[:50],
                payment_status='none',
                form_filled=False,
            )
        else:
            if name:
                lead.name = name
            if source_url and not lead.source_url:
                lead.source_url = source_url[:500]
            if ref_code and not lead.ref_code:
                lead.ref_code = ref_code[:50]
            lead.ip_address = ip or lead.ip_address
            lead.user_agent = user_agent or lead.user_agent
            _advance_status(lead, STATUS_QUICK_REGISTERED)
        if agent and agent.status in REUSABLE_AGENT_STATUSES:
            lead.agent_id = agent.id
        if not lead.draft_id:
            try:
                from apps.agents.models import AgentDraft
                existing_draft = AgentDraft.objects.filter(mobile=phone).order_by('-pk').first()
                if existing_draft:
                    lead.draft_id = existing_draft.pk
            except Exception:
                pass
        _apply_form_payment_flags(lead)
        try:
            lead.save()
        except IntegrityError:
            lead = (
                RegistrationLead.objects.select_for_update()
                .filter(phone=phone)
                .order_by('-updated_at', '-id')
                .first()
            )
            if lead is None:
                raise
            if name:
                lead.name = name
            _advance_status(lead, STATUS_QUICK_REGISTERED)
            _apply_form_payment_flags(lead)
            lead.save()

    bind_session(request, lead)
    return lead, None


def mark_form_started(request, lead=None):
    lead = lead or session_lead(request)
    if not lead or lead.status == STATUS_CONVERTED:
        return lead
    if _advance_status(lead, STATUS_FORM_STARTED):
        _apply_form_payment_flags(lead)
        lead.save(update_fields=['status', 'form_filled', 'payment_status', 'updated_at'])
    return lead


def mark_form_completed(request, draft=None, agent=None):
    phone = ''
    name = ''
    draft_id = None
    agent_id = None
    if draft is not None:
        phone = normalize_phone(getattr(draft, 'mobile', '') or '')
        name = (getattr(draft, 'fullname', '') or '').strip()[:100]
        draft_id = getattr(draft, 'pk', None)
    if agent is not None:
        phone = phone or normalize_phone(getattr(agent, 'mobile', '') or '')
        name = name or (getattr(agent, 'fullname', '') or '').strip()[:100]
        agent_id = getattr(agent, 'id', None)
    if not phone:
        phone = normalize_phone(request.session.get(SESSION_PHONE) if request else '')
    if not _PHONE_RE.fullmatch(phone):
        return None

    lead = RegistrationLead.objects.filter(phone=phone).first()
    session_obj = session_lead(request) if request is not None else None
    if session_obj and session_obj.status != STATUS_CONVERTED:
        if lead is None:
            # Same visitor edited the number. Keep this row so a refresh cannot fork a second lead.
            session_obj.phone = phone
            lead = session_obj
        elif lead.pk != session_obj.pk:
            return None
    if lead is None:
        lead, _err = capture_quick_lead(request, name or 'Agent', phone)
        if lead is None:
            return None
    if lead.status == STATUS_CONVERTED:
        return lead
    if name:
        lead.name = name
    if draft_id:
        lead.draft_id = draft_id
    if agent_id:
        lead.agent_id = agent_id
    _advance_status(lead, STATUS_FORM_COMPLETED)
    _apply_form_payment_flags(lead)
    try:
        lead.save()
    except IntegrityError:
        return None
    if request is not None:
        bind_session(request, lead)
    return lead


def mark_payment_pending(agent):
    """Checkout started. A completed or converted lead is left unchanged."""
    if agent is None:
        return None
    phone = normalize_phone(getattr(agent, 'mobile', '') or '')
    lead = RegistrationLead.objects.filter(phone=phone).first() if phone else None
    if lead is None and getattr(agent, 'id', None):
        lead = RegistrationLead.objects.filter(agent_id=agent.id).first()
    if lead is None or lead.status == STATUS_CONVERTED or lead.payment_status == 'completed':
        return lead
    lead.agent_id = agent.id
    lead.payment_status = 'pending'
    lead.save(update_fields=['agent_id', 'payment_status', 'updated_at'])
    return lead


def mark_payment_completed(agent):
    if agent is None:
        return None
    phone = normalize_phone(getattr(agent, 'mobile', '') or '')
    lead = None
    if phone:
        lead = RegistrationLead.objects.filter(phone=phone).first()
    if lead is None and getattr(agent, 'id', None):
        lead = RegistrationLead.objects.filter(agent_id=agent.id).first()
    if lead is None:
        return None
    lead.agent_id = agent.id
    if getattr(agent, 'fullname', None):
        lead.name = agent.fullname[:100]
    if getattr(agent, 'status', '') == 'active':
        _advance_status(lead, STATUS_CONVERTED)
        lead.converted_at = lead.converted_at or timezone.now()
    else:
        _advance_status(lead, STATUS_PAYMENT_COMPLETED)
    lead.payment_status = 'completed'
    _apply_form_payment_flags(lead)
    update_fields = ['status', 'agent_id', 'name', 'form_filled', 'payment_status', 'updated_at']
    if lead.converted_at:
        update_fields.append('converted_at')
    lead.save(update_fields=update_fields)
    return lead


def mark_payment_failed(agent):
    if agent is None:
        return None
    phone = normalize_phone(getattr(agent, 'mobile', '') or '')
    lead = None
    if phone:
        lead = RegistrationLead.objects.filter(phone=phone).first()
    if lead is None and getattr(agent, 'id', None):
        lead = RegistrationLead.objects.filter(agent_id=agent.id).first()
    if lead is None or lead.status == STATUS_CONVERTED:
        return lead
    if lead.payment_status != 'completed':
        lead.payment_status = 'failed'
        lead.save(update_fields=['payment_status', 'updated_at'])
    return lead


def sync_lead_for_agent(agent):
    """Hide converted leads once the agent is active; otherwise keep pipeline status."""
    if agent is None:
        return None
    phone = normalize_phone(getattr(agent, 'mobile', '') or '')
    lead = None
    if phone:
        lead = RegistrationLead.objects.filter(phone=phone).first()
    if lead is None and getattr(agent, 'id', None):
        lead = RegistrationLead.objects.filter(agent_id=agent.id).first()
    if lead is None:
        return None
    lead.agent_id = agent.id
    status = getattr(agent, 'status', '') or ''
    if status == 'active':
        _advance_status(lead, STATUS_CONVERTED)
        lead.converted_at = lead.converted_at or timezone.now()
        lead.payment_status = 'completed'
        lead.form_filled = True
    elif status in ('pending_approval',):
        _advance_status(lead, STATUS_PAYMENT_COMPLETED)
        lead.payment_status = 'completed'
        lead.form_filled = True
    lead.save()
    return lead
