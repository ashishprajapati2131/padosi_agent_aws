"""Write flows for the admin Free Trial manager (views/free_trial.py)."""

from django.db import transaction
import random
from datetime import datetime

from django.db import connection

from ..services.site_settings import set_setting
from ..services.referral_service import (
    generate_referral_code_for_agent,
    apply_tier_reward,
)


def update_trial_config(price, duration_days, badge, description, is_active):
    set_setting('trial_plan_config', {
        'price':         price,
        'duration_days': duration_days,
        'badge':         badge or 'TRIAL',
        'description':   description or 'Try before you commit — full access',
        'is_active':     is_active,
    }, 'pricing')


def update_upgrade_discount(discount):
    """Save the discount and apply it to active trial agents. Returns rows updated."""
    set_setting('trial_upgrade_discount', discount, 'pricing')

    # Bulk-update all active trial agents — exact Laravel parity
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # naive IST, like the DB columns
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE agents
            SET upgrade_discount_percent = %s
            WHERE plan_type = 'free_trial' AND trial_ends_at > %s
            """,
            [discount, now_str],
        )
        updated_count = cursor.rowcount

    return updated_count


def update_referral_config(eligibility, count_free_trial):
    set_setting('referral_config', {
        'eligibility':      eligibility,
        'count_free_trial': count_free_trial,
    }, 'referral')


def force_test_credit(admin_id, agent_id, log_activity):
    """log_activity(admin_id, description, model_type) is the view's audit shim,
    called inside the transaction. Returns the resolved agent_id."""
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # 2. Lookup agent
                cursor.execute("SELECT id, fullname FROM agents WHERE id = %s LIMIT 1", [agent_id])
                agent_row = cursor.fetchone()
                if not agent_row:
                    from django.http import Http404
                    raise Http404("No Agent found.")

                agent_id = agent_row[0]
                agent_fullname = agent_row[1]

                # 3–4. Lookup or generate referral code (shared service)
                ref = generate_referral_code_for_agent(cursor, agent_id, agent_fullname)
                ref_code_id  = ref['id']
                ref_code_str = ref['code']

                # 5. Insert dummy agent
                import time
                ts = int(time.time())
                dummy_fullname = f"Test Conversion {ts}"
                dummy_email    = f"test{ts}@test.com"
                dummy_mobile   = "99999" + str(random.randint(10000, 99999))

                cursor.execute("""
                    INSERT INTO agents (fullname, email, mobile, status, referred_by_code, created_at, updated_at)
                    VALUES (%s, %s, %s, 'active', %s, NOW(), NOW())
                """, [dummy_fullname, dummy_email, dummy_mobile, ref_code_str])
                dummy_agent_id = cursor.lastrowid

                # 6. Insert referral usage
                cursor.execute("""
                    INSERT INTO referral_usages (referral_code_id, referrer_agent_id, referred_agent_id, referred_agent_name, status, converted_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'converted', NOW(), NOW(), NOW())
                """, [ref_code_id, agent_id, dummy_agent_id, dummy_fullname])

                # 7. Increment referral_codes.total_referrals
                cursor.execute("""
                    UPDATE referral_codes
                    SET total_referrals = total_referrals + 1, updated_at = NOW()
                    WHERE id = %s
                """, [ref_code_id])

                # 8. Refresh total
                cursor.execute("SELECT total_referrals FROM referral_codes WHERE id = %s LIMIT 1", [ref_code_id])
                new_total = cursor.fetchone()[0]

                # 9–10. Apply tier reward via shared service
                apply_tier_reward(cursor, agent_id, ref_code_id, new_total)

                # 11. Log activity
                log_msg = f"FORCED TEST CONVERSION explicitly added to Agent ID {agent_id}. Reward Tier updated."
                log_activity(admin_id, log_msg, 'ReferralCode')

    except Exception as e:
        raise e

    return agent_id


def create_trial_promo(code, discount_type, discount_value, max_uses, expires_at,
                       trial_plan_name, trial_duration_days, trial_price_override, notes):
    """Returns the new promo id."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO promo_codes
                (code, discount_type, discount_value, is_active, is_free_trial,
                 applicable_plan, max_uses, times_used, expires_at,
                 trial_plan_name, trial_duration_days, trial_price_override, notes,
                 created_at, updated_at)
            VALUES (%s, %s, %s, 1, 1, 'free_trial', %s, 0, %s, %s, %s, %s, %s, NOW(), NOW())
            """,
            [code, discount_type, discount_value, max_uses, expires_at,
             trial_plan_name, trial_duration_days, trial_price_override, notes],
        )
        new_id = cursor.lastrowid

    return new_id


def update_trial_promo(promo_id, discount_type, discount_value, max_uses, expires_at,
                       trial_plan_name, trial_duration_days, trial_price_override, notes):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE promo_codes SET
                discount_type = %s, discount_value = %s, max_uses = %s, expires_at = %s,
                trial_plan_name = %s, trial_duration_days = %s, trial_price_override = %s,
                notes = %s, updated_at = NOW()
            WHERE id = %s AND is_free_trial = 1
            """,
            [discount_type, discount_value, max_uses, expires_at,
             trial_plan_name, trial_duration_days, trial_price_override, notes, promo_id],
        )


def toggle_trial_promo(promo_id):
    """Returns the new is_active value (0/1), or None if not found."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT is_active FROM promo_codes WHERE id = %s AND is_free_trial = 1",
            [promo_id],
        )
        row = cursor.fetchone()
        if not row:
            return None

        new_status = 0 if row[0] else 1
        cursor.execute(
            "UPDATE promo_codes SET is_active = %s, updated_at = NOW() WHERE id = %s",
            [new_status, promo_id],
        )

    return new_status


def delete_trial_promo(promo_id):
    """Returns the deleted code, or None if not found."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, code FROM promo_codes WHERE id = %s AND is_free_trial = 1",
            [promo_id],
        )
        row = cursor.fetchone()
        if not row:
            return None

        code_str = row[1]
        cursor.execute("DELETE FROM promo_codes WHERE id = %s", [promo_id])

    return code_str
