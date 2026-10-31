"""
apps/admin_panel/services/referral_service.py

Shared Referral Service — canonical single source of truth.

All tier logic, referral code generation, referral crediting, and reward
assignment flow through this module.  Both the Testing Module and the organic
Registration hook call these helpers so the business rules are NEVER duplicated.

Tier table (Django canonical — consistent across all surfaces):
    5  referrals  → discount_25   / 25%  upgrade discount
    10 referrals  → discount_50   / 50%  upgrade discount
    15 referrals  → pro_plan_1rs  / 100% upgrade discount (Pro @ ₹1)
"""

import random
import re
import string



# ─────────────────────────────────────────────────────────────────────────────
#  TIER TABLE  — ONE place, never duplicated
# ─────────────────────────────────────────────────────────────────────────────

REFERRAL_TIERS = [
    {'min': 5,  'max': 9,       'reward': 'discount_25',  'discount': 25},
    {'min': 10, 'max': 14,      'reward': 'discount_50',  'discount': 50},
    {'min': 15, 'max': 9999999, 'reward': 'pro_plan_1rs', 'discount': 100},
]


def get_tier_for_count(total_referrals: int) -> dict | None:
    """
    Return the highest tier the agent has reached, or None if below Tier 1.

    Mirrors ReferralCode::currentTier() from Laravel but uses the Django
    canonical 5/10/15 milestones everywhere.
    """
    tier = None
    for t in REFERRAL_TIERS:
        if total_referrals >= t['min']:
            tier = t
    return tier


# ─────────────────────────────────────────────────────────────────────────────
#  REFERRAL CODE GENERATION  — mirrors ReferralCode::generateForAgent()
# ─────────────────────────────────────────────────────────────────────────────

def generate_referral_code_for_agent(cursor, agent_id: int, agent_fullname: str) -> dict:
    """
    Lookup or generate a referral code for the given agent using the Laravel
    algorithm exactly:
        base = first 4 uppercase alphanumeric chars of fullname (fallback 'REF')
        code = base + 4 random uppercase alphanumeric chars (loop until unique)

    Returns the referral code row dict: {id, code, total_referrals, ...}
    Caller must pass an already-open cursor (inside a transaction).
    """
    cursor.execute(
        "SELECT id, code, total_referrals, is_active, reward_type, reward_claimed "
        "FROM referral_codes WHERE agent_id = %s LIMIT 1",
        [agent_id],
    )
    row = cursor.fetchone()
    if row:
        cols = ['id', 'code', 'total_referrals', 'is_active', 'reward_type', 'reward_claimed']
        return dict(zip(cols, row))

    # Generate new code using Laravel algorithm
    clean_name = re.sub(r'[^A-Z0-9]', '', (agent_fullname or '').upper())
    base = clean_name[:4]
    if len(base) < 2:
        base = 'REF'

    for _ in range(50):
        candidate = base + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        cursor.execute("SELECT COUNT(*) FROM referral_codes WHERE code = %s", [candidate])
        if cursor.fetchone()[0] == 0:
            break

    cursor.execute(
        """
        INSERT INTO referral_codes
            (agent_id, code, is_active, total_referrals, pending_referrals,
             clicks, reward_claimed, created_at, updated_at)
        VALUES (%s, %s, 1, 0, 0, 0, 0, NOW(), NOW())
        """,
        [agent_id, candidate],
    )

    cursor.execute(
        "SELECT id, code, total_referrals, is_active, reward_type, reward_claimed "
        "FROM referral_codes WHERE agent_id = %s LIMIT 1",
        [agent_id],
    )
    row = cursor.fetchone()
    cols = ['id', 'code', 'total_referrals', 'is_active', 'reward_type', 'reward_claimed']
    return dict(zip(cols, row))


# ─────────────────────────────────────────────────────────────────────────────
#  APPLY REWARD  — update agents + referral_codes tables based on tier
# ─────────────────────────────────────────────────────────────────────────────

def apply_tier_reward(cursor, agent_id: int, ref_code_id: int, total_referrals: int) -> dict | None:
    """
    Calculate the current tier and, if a tier is reached, write the reward to:
        agents.referral_reward_type
        agents.upgrade_discount_percent
        referral_codes.reward_type

    Returns the tier dict if a tier was applied, None otherwise.
    Caller must pass an already-open cursor (inside a transaction).
    """
    tier = get_tier_for_count(total_referrals)
    if not tier:
        return None

    cursor.execute(
        """
        UPDATE agents
        SET referral_reward_type = %s,
            upgrade_discount_percent = %s,
            updated_at = NOW()
        WHERE id = %s
        """,
        [tier['reward'], tier['discount'], agent_id],
    )
    cursor.execute(
        """
        UPDATE referral_codes
        SET reward_type = %s, updated_at = NOW()
        WHERE id = %s
        """,
        [tier['reward'], ref_code_id],
    )
    return tier


# ─────────────────────────────────────────────────────────────────────────────
#  CREDIT REFERRAL  — core hook called after successful registration
# ─────────────────────────────────────────────────────────────────────────────

