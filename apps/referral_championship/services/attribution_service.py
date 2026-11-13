import logging
import re
from apps.referral_championship.models import (
    ChampionshipCampaign,
    ChampionshipParticipant,
    ChampionshipFraudFlag,
)

logger = logging.getLogger(__name__)


def get_or_create_participant(agent, campaign=None):
    """Ensure an eligible agent has a permanent unique referral ID."""
    if not campaign:
        campaign = ChampionshipCampaign.get_current()
    return ChampionshipParticipant.get_or_create_for_agent(agent, campaign)


def bind_referral_session(request, ref_id):
    """
    Lock referral attribution in session upon visiting a referral link.
    First valid referral attribution wins and becomes locked.
    """
    ref_id = (ref_id or '').strip().upper()
    if not ref_id:
        return None

    # Check if attribution already locked in session
    existing_ref = request.session.get('championship_ref_id')
    if existing_ref:
        return existing_ref

    participant = ChampionshipParticipant.objects.filter(
        referral_id=ref_id,
        campaign__is_active=True
    ).exclude(campaign__status__in=['ended', 'archived']).first()

    if participant:
        request.session['championship_ref_id'] = participant.referral_id
        request.session['championship_campaign_id'] = participant.campaign_id
        request.session['championship_referrer_id'] = participant.id
        request.session.modified = True
        return participant.referral_id

    return None


def _last10(mobile):
    # +91 / 0 prefixes and separators ignored: compare the last 10 digits.
    return re.sub(r'\D', '', str(mobile or ''))[-10:]


def validate_referral_integrity(referrer_participant, candidate_agent, ip_address=None):
    """
    Fraud prevention check:
    - Block self-referrals (same agent ID, mobile, or email).
    - Returns (is_valid, reason).
    """
    if not referrer_participant or not candidate_agent:
        return False, "Missing referrer or candidate agent"

    referrer_agent = referrer_participant.agent

    if referrer_agent.id == candidate_agent.id:
        return False, "Self-referral detected"

    if _last10(candidate_agent.mobile) and _last10(candidate_agent.mobile) == _last10(referrer_agent.mobile):
        ChampionshipFraudFlag.objects.create(
            participant=referrer_participant,
            reason="Duplicate mobile number detected with referrer",
            details=f"Referrer #{referrer_agent.id} candidate #{candidate_agent.id}"
        )
        return False, "Duplicate mobile number detected"

    if candidate_agent.email and referrer_agent.email and candidate_agent.email.strip().lower() == referrer_agent.email.strip().lower():
        ChampionshipFraudFlag.objects.create(
            participant=referrer_participant,
            reason="Duplicate email detected with referrer",
            details=f"Referrer #{referrer_agent.id} candidate #{candidate_agent.id}"
        )
        return False, "Duplicate email detected"

    return True, "Attribution valid"
