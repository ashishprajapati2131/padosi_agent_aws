"""Wire Paldi / EV- referral data into the Referral Championship agent dashboard."""
from types import SimpleNamespace

from django.urls import reverse

from apps.event_referral.models import EventReferral
from apps.event_referral.services.participant_service import get_participant_for_agent


def _event_activity_state(ref):
    if ref.state == EventReferral.STATE_PAID and ref.counts:
        return 'paid'
    if ref.state == EventReferral.STATE_PAID:
        return 'registered'
    return ref.state or 'registered'


def _event_display_name(ref):
    name = (ref.snapshot_name or '').strip()
    if not name and ref.referred_agent_id:
        name = (getattr(ref.referred_agent, 'fullname', None) or '').strip()
    return name or 'Agent'


def event_referral_activity_row(ref):
    """Row shape compatible with championship Recent Activity template."""
    name = _event_display_name(ref)
    ts = ref.paid_at or ref.registered_at
    return SimpleNamespace(
        event_referral=True,
        referred_agent=SimpleNamespace(fullname=name),
        snapshot_name=ref.snapshot_name,
        snapshot_mobile=ref.snapshot_mobile,
        snapshot_email=ref.snapshot_email,
        snapshot_plan=ref.snapshot_plan,
        snapshot_payment_status=ref.snapshot_payment_status or ref.state,
        counts=ref.counts,
        state=ref.state,
        created_at=ts,
        registration_state=_event_activity_state(ref),
    )


def event_referral_activity_row_api(ref):
    name = _event_display_name(ref)
    ts = ref.paid_at or ref.registered_at
    return {
        'id': ref.id,
        'event_referral': True,
        'referred_agent_name': name,
        'initials': (name[:2] or 'AG').upper(),
        'created_at': ts.isoformat() if ts else None,
        'created_at_formatted': ts.strftime('%d %b, %I:%M %p') if ts else '',
        'registration_state': _event_activity_state(ref),
        'counts': bool(ref.counts),
        'snapshot_plan': ref.snapshot_plan or '',
        'snapshot_contact': ref.snapshot_mobile or ref.snapshot_email or '',
    }


def build_event_referral_championship_context(request, agent, build_absolute_uri):
    """
    When agent is an EV- challenger, return funnel metrics + referral link for championship UI.
    Returns None if not an event referral participant.
    """
    participant = get_participant_for_agent(agent)
    if not participant:
        return None

    refs_qs = (
        EventReferral.objects.filter(participant=participant)
        .select_related('referred_agent')
        .order_by('-registered_at')
    )
    all_refs = list(refs_qs[:50])
    recent = all_refs[:20]

    invited_count = refs_qs.count()
    form_filled_count = refs_qs.exclude(state=EventReferral.STATE_REJECTED).count()
    paid_count = refs_qs.filter(state=EventReferral.STATE_PAID).count()
    qualified_count = participant.paid_count

    referral_url = build_absolute_uri(
        reverse('agents:agent_registration_referral', kwargs={'ref_code': participant.referral_code}),
    )

    return {
        'event_referral_mode': True,
        'event_referral_participant': participant,
        'event_referral_all': all_refs,
        'display_referral_id': participant.referral_code,
        'referral_url': referral_url,
        'invited_count': invited_count,
        'form_filled_count': form_filled_count,
        'paid_count': paid_count,
        'qualified_count': qualified_count,
        'referrals_target': participant.required_paid_referrals,
        'recent_referrals': [event_referral_activity_row(r) for r in recent],
        'recent_referrals_api': [event_referral_activity_row_api(r) for r in recent],
    }


def event_referral_qr_join_url(request, agent, build_absolute_uri):
    """QR / share URL for event challengers; None if not event participant."""
    participant = get_participant_for_agent(agent)
    if not participant:
        return None
    return build_absolute_uri(
        reverse('agents:agent_registration_referral', kwargs={'ref_code': participant.referral_code}),
    )
