"""Post-payment side effects: referral/promo/trial bookkeeping and event, insurance and refund webhook handlers."""

from django.http import HttpResponse
from django.utils import timezone
from apps.agents.models import Agent, PromoCode
from apps.agents.services.feature_unlock import plan_slug_from_name

from .registration_common import logger


def _isolated(label, fn):
    """Run a best-effort side effect of payment activation in its own savepoint.

    These steps used to run bare inside the activation transaction behind a
    try/except. A DB error there (e.g. referral code insert failing) marked the
    whole transaction for rollback, so the payment silently stayed 'pending'
    while the user was told it succeeded. A nested atomic() confines the
    failure to its own savepoint.
    """
    from django.db import transaction

    try:
        with transaction.atomic():
            return fn()
    except Exception as err:
        logger.warning("%s failed (payment activation unaffected): %s", label, err)
        return None


def _trial_days_for(subscription, default_days):
    """Trial length for an order: a free-trial promo's own duration wins.

    The plans page already shows promo.trial_duration_days, but activation
    always used the site-wide trial length.
    """
    code = (getattr(subscription, "promo_code", None) or "").strip()
    if code:
        promo = PromoCode.objects.filter(code=code).first()
        if promo and promo.is_free_trial_code() and promo.trial_duration_days:
            return int(promo.trial_duration_days)
    return default_days


def _increment_promo_usage(promo_code):
    if not promo_code:
        return
    from django.db.models import F, Q

    # Conditional UPDATE: concurrent orders cannot push times_used past max_uses (audit PAY15).
    PromoCode.objects.filter(code=promo_code).filter(
        Q(max_uses__isnull=True) | Q(times_used__lt=F("max_uses"))
    ).update(times_used=F("times_used") + 1)


def _credit_referral_conversion(agent):
    """Mark the referral as converted and apply the correct tier reward."""
    if not agent or not agent.referred_by_code:
        return
    # Skip ₹0 signups — they don't count as paid conversions for referral tiers
    from apps.agents.models import AgentSubscription

    paid = AgentSubscription.objects.filter(
        agent=agent,
        payment_status="completed",
        registration_amount__gt=0,
    ).exists()
    if not paid:
        return

    from apps.admin_panel.models.referral_code import ReferralCode
    from apps.admin_panel.models.referral_usage import ReferralUsage

    ref_code_obj = ReferralCode.objects.filter(code=agent.referred_by_code).first()
    if not ref_code_obj:
        return
    # Block self-referral abuse (an agent using their own referral code)
    if ref_code_obj.agent_id == agent.id:
        logger.warning(
            f"[Referral] Self-referral attempt blocked for agent {agent.id} using own code {agent.referred_by_code}"
        )
        return
    usage, u_created = ReferralUsage.objects.get_or_create(
        referral_code=ref_code_obj,
        referred_agent_id=agent.id,
        defaults={"status": "converted", "signed_up_at": timezone.now()},
    )
    if not u_created and usage.status != "converted":
        usage.status = "converted"
        usage.save()

    actual_conversions = ReferralUsage.objects.filter(
        referral_code=ref_code_obj, status="converted"
    ).count()
    ref_code_obj.total_referrals = actual_conversions
    ref_code_obj.save()

    # Apply the highest tier the referrer has now reached (canonical table: 5/10/15)
    current_tier = ref_code_obj.currentTier()
    if not current_tier:
        return
    referring_agent = Agent.objects.filter(pk=ref_code_obj.agent_id).first()
    if not referring_agent:
        return
    reward = current_tier["reward"]
    if reward == "pro_plan_1rs" and referring_agent.plan_type == "free_trial":
        referring_agent.referral_reward_type = "pro_plan_1rs"
        referring_agent.referral_reward_earned_at = timezone.now()
        referring_agent.save()
    elif reward == "discount_50":
        referring_agent.referral_reward_type = "discount_50"
        if not referring_agent.referral_reward_earned_at:
            referring_agent.referral_reward_earned_at = timezone.now()
        referring_agent.save()
    elif reward == "discount_25":
        # Only set if no better reward already exists
        if referring_agent.referral_reward_type not in ("discount_50", "pro_plan_1rs"):
            referring_agent.referral_reward_type = "discount_25"
            if not referring_agent.referral_reward_earned_at:
                referring_agent.referral_reward_earned_at = timezone.now()
            referring_agent.save()


def _ensure_referral_code(agent):
    from apps.admin_panel.models.referral_code import ReferralCode

    if not ReferralCode.objects.filter(agent=agent).exists():
        ReferralCode.generateForAgent(agent)


def _championship_qualification(agent, subscription):
    from apps.referral_championship.services.qualification_service import (
        process_championship_qualification,
    )

    process_championship_qualification(agent, subscription)


def _event_referral_qualification(agent, subscription):
    from apps.event_referral.services.qualification_service import (
        qualify_event_referral,
    )

    qualify_event_referral(agent, subscription)


def _event_referral_register_hook(agent):
    from apps.event_referral.services.qualification_service import (
        register_referred_agent,
    )

    register_referred_agent(agent)


def _order_plan_slug(subscription, agent):
    """Plan to activate for a paid order.

    Falls back to the plan the agent was priced for at checkout (agent.plan_type
    is set when the order is created) — never to 'professional', which granted
    an upgrade whenever a plan display name did not parse.
    """
    from apps.agents.services.feature_unlock import normalize_plan_slug, PLAN_SLUGS

    slug = plan_slug_from_name(getattr(subscription, "selected_plan", "") or "")
    if slug:
        return slug
    current = normalize_plan_slug(getattr(agent, "plan_type", "") or "")
    return current if current in PLAN_SLUGS else "starter"


def _fulfil_event_order_webhook(
    event_registration, order_id, payment_id, payment_entity
):
    from apps.agents.views.events import EventPaymentRejected, fulfil_event_registration

    if not payment_id:
        logger.error(
            f"[Webhook] Event order {order_id} has no payment id; not fulfilled"
        )
        return HttpResponse("Webhook ignored: event order without payment", status=200)
    payment = payment_entity if payment_entity.get("id") == payment_id else None
    try:
        _reg, fulfilled = fulfil_event_registration(
            event_registration.pk, order_id, payment_id, payment=payment
        )
    except EventPaymentRejected as exc:
        # 200: a rejected payment never becomes valid, so a retry cannot help.
        logger.error(
            f"[Webhook] Event registration #{event_registration.pk} not fulfilled: "
            f"order {order_id}, payment {payment_id}: {exc}"
        )
        return HttpResponse("Webhook ignored: event payment rejected", status=200)
    except Exception:
        logger.exception(
            f"[Webhook] Event fulfilment failed for order {order_id}, payment {payment_id}"
        )
        return HttpResponse("Event fulfilment failed", status=500)
    if not fulfilled:
        return HttpResponse(
            "Webhook processed successfully (already completed)", status=200
        )
    return HttpResponse("Webhook processed successfully", status=200)


def _fulfil_insurance_order_webhook(fulfil, order_id, payment_id, payment_entity):
    """Run an insurance fulfil_* function with the event-order response rules."""
    from apps.insurance.views.payments import InsurancePaymentRejected

    if not payment_id:
        logger.error(
            f"[Webhook] Insurance order {order_id} has no payment id; not fulfilled"
        )
        return HttpResponse(
            "Webhook ignored: insurance order without payment", status=200
        )
    payment = payment_entity if payment_entity.get("id") == payment_id else None
    try:
        _obj, fulfilled = fulfil(order_id, payment_id, payment=payment)
    except InsurancePaymentRejected as exc:
        # 200: a rejected payment never becomes valid, so a retry cannot help.
        logger.error(
            f"[Webhook] Insurance order {order_id} not fulfilled: payment {payment_id} rejected ({type(exc).__name__}; reason logged by the fulfil step / stored on the order)"
        )
        return HttpResponse("Webhook ignored: insurance payment rejected", status=200)
    except Exception:
        logger.exception(
            f"[Webhook] Insurance fulfilment failed for order {order_id}, payment {payment_id}"
        )
        return HttpResponse("Insurance fulfilment failed", status=500)
    if not fulfilled:
        return HttpResponse(
            "Webhook processed successfully (already completed)", status=200
        )
    return HttpResponse("Webhook processed successfully", status=200)


def _handle_refund_webhook(data):
    """Revoke a paid subscription once Razorpay confirms a FULL refund.

    Before this, refunds left the subscription 'completed', so the agent kept
    dashboard access and championship credit. Partial refunds are ignored.
    """
    from django.db import transaction
    from apps.agents.models import AgentSubscription, Invoice
    from apps.agents.services.account_auth import agent_has_completed_payment

    payload = data.get("payload") or {}
    payment = (payload.get("payment") or {}).get("entity") or {}
    payment_id = payment.get("id") or (
        (payload.get("refund") or {}).get("entity") or {}
    ).get("payment_id")
    order_id = payment.get("order_id")
    try:
        amount = int(payment.get("amount") or 0)
        refunded = int(payment.get("amount_refunded") or 0)
    except (TypeError, ValueError):
        amount, refunded = 0, 0
    is_full_refund = payment.get("refund_status") == "full" or (
        amount > 0 and refunded >= amount
    )
    if not payment_id or not is_full_refund:
        return HttpResponse("Refund noted (partial or unmatched)", status=200)

    from django.db.models import Q

    match = Q(razorpay_payment_id=payment_id)
    if order_id:
        match |= Q(razorpay_order_id=order_id)

    agents = {}
    lost_access = {}
    try:
        with transaction.atomic():
            subs = list(AgentSubscription.objects.select_for_update().filter(match))
            if not subs:
                return HttpResponse(
                    "Refund noted (no matching subscription)", status=200
                )

            for sub in subs:
                if sub.payment_status == "refunded":
                    continue
                sub.payment_status = "refunded"
                sub.status = "inactive"
                sub.save(update_fields=["payment_status", "status", "updated_at"])
                if sub.agent_id:
                    agents[sub.agent_id] = sub.agent

            Invoice.objects.filter(match, payment_status="paid").update(
                payment_status="refunded"
            )

            lost_access = {}
            for agent_id, agent in agents.items():
                # Only drop access if no OTHER real payment remains (e.g. upgrades).
                if not agent_has_completed_payment(agent):
                    lost_access[agent_id] = agent
                    if agent.status in ("active", "pending_approval"):
                        agent.status = "pending_payment"
                        agent.save(update_fields=["status"])
                    continue
                # A refunded upgrade: go back to the newest payment that still
                # stands. Its row had been deactivated as superseded, so the
                # agent used to keep the refunded plan.
                remaining = (
                    AgentSubscription.objects.select_for_update()
                    .filter(agent=agent, payment_status="completed")
                    .order_by("-starts_at", "-created_at")
                    .first()
                )
                if remaining:
                    if remaining.status != "active":
                        remaining.status = "active"
                        remaining.save(update_fields=["status", "updated_at"])
                    previous_plan = plan_slug_from_name(remaining.selected_plan or "")
                    if previous_plan and previous_plan != agent.plan_type:
                        agent.plan_type = previous_plan
                        agent.save(update_fields=["plan_type"])
    except Exception as err:
        logger.error(
            "[Webhook] Refund processing failed for payment %s: %s", payment_id, err
        )
        return HttpResponse("Refund processing failed", status=500)

    # Referral credit is withdrawn only when the agent's paid access ended; a
    # refunded upgrade leaves the original (credited) payment standing.
    for agent in lost_access.values():
        try:
            from apps.referral_championship.services.qualification_service import (
                revert_championship_qualification,
            )

            revert_championship_qualification(agent, reason="refund")
        except Exception as champ_err:
            logger.warning(
                "[Webhook] Championship refund revert failed for agent %s: %s",
                agent.pk,
                champ_err,
            )
        try:
            from apps.event_referral.services.qualification_service import (
                revert_event_referral,
            )

            revert_event_referral(agent, reason="refund")
        except Exception as ev_err:
            logger.warning(
                "[Webhook] Event referral refund revert failed for agent %s: %s",
                agent.pk,
                ev_err,
            )

    logger.info(
        "[Webhook] Full refund processed for payment %s (%d agent(s) updated)",
        payment_id,
        len(agents),
    )
    return HttpResponse("Refund processed", status=200)
