"""Agent account endpoints (split out of dashboard.py): push token, referral info API,
plan upgrade request and trial activity logging."""

from apps.admin_panel.models.referral_code import ReferralCode
from apps.admin_panel.models.referral_usage import ReferralUsage
from apps.agents.models import (
    Agent,
    AgentDeviceToken,
    AgentSubscription,
)
from apps.agents.services.feature_unlock import (
    PLAN_LABELS,
    resolve_checkout_plan_slug,
)
from apps.agents.views.registration import _deactivate_superseded_subscriptions
from apps.home.models import SiteSetting
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from json import (
    JSONDecodeError as JSONDecodeError,
    loads as json_loads,
)
from apps.agents.views.dashboard_common import logger


@require_POST
def agent_push_token(request):
    """
    Handle POST request to store/update the FCM push token for the authenticated agent.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"message": "Unauthenticated."}, status=401)

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        return JsonResponse({"message": "Agent not found."}, status=403)

    try:
        try:
            data = json_loads(request.body)
        except JSONDecodeError:
            data = request.POST

        token = data.get("token", "").strip()
        platform = data.get("platform", "").strip() or None

        if not token:
            return JsonResponse({"message": "Token is required."}, status=422)

        AgentDeviceToken.objects.update_or_create(
            token=token,
            defaults={
                "agent": agent,
                "platform": platform,
                "last_seen_at": timezone.now(),
            },
        )
        return JsonResponse({"message": "Token saved."})
    except Exception as e:
        logger.error(f"FCM token store failed: {e}")
        return JsonResponse({"message": "Failed to save token."}, status=500)


def referral_info(request):
    """
    Agent referral info API (for dashboard)
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthenticated."}, status=401)

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        return JsonResponse({"error": "Agent Profile Not found"}, status=404)

    try:
        ref_code = ReferralCode.objects.filter(agent=agent).first()
        if not ref_code:
            ref_code = ReferralCode.generateForAgent(agent)

        # Auto self-heal total_referrals from actual converted usages
        actual_conversions = ReferralUsage.objects.filter(
            referral_code=ref_code, status="converted"
        ).count()

        if ref_code.total_referrals != actual_conversions:
            ref_code.total_referrals = actual_conversions
            ref_code.save()

        next_tier = ref_code.nextTier()

        # Calculate pending referrals: registered with this code but not converted yet
        total_registered_agents = list(
            Agent.objects.filter(referred_by_code=ref_code.code).values_list(
                "id", flat=True
            )
        )
        converted_agent_ids = list(
            ReferralUsage.objects.filter(
                referral_code=ref_code, status="converted"
            ).values_list("referred_agent_id", flat=True)
        )

        pending_referrals = len(set(total_registered_agents) - set(converted_agent_ids))

        # Build absolute referral URL in Django
        from django.urls import reverse

        try:
            referral_url = request.build_absolute_uri(
                reverse("agents:referral_join", args=[ref_code.code])
            )
        except Exception:
            referral_url = (
                f"{request.scheme}://{request.get_host()}/join/{ref_code.code}/"
            )

        return JsonResponse(
            {
                "code": ref_code.code,
                "total_referrals": actual_conversions,
                "pending_referrals": pending_referrals,
                "current_tier": ref_code.currentTier(),
                "next_tier": next_tier,
                "next_target": next_tier["min"] if next_tier else None,
                "reward_claimed": bool(ref_code.reward_claimed),
                "referral_url": referral_url,
            }
        )
    except Exception as e:
        logger.error(f"Referral info API failed: {e}")
        return JsonResponse({"error": f"Server Error: {str(e)}"}, status=500)


@require_POST
def agent_upgrade_plan(request):
    """
    Handle plan upgrade checkout for logged-in agents (creates Razorpay order).
    """
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Unauthenticated."}, status=401
        )

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        return JsonResponse(
            {"success": False, "message": "Agent not found."}, status=403
        )

    try:
        try:
            data = json_loads(request.body)
        except JSONDecodeError:
            data = request.POST

        raw_plan_type = data.get("plan_type")
        plan_type = resolve_checkout_plan_slug(raw_plan_type)
        if plan_type not in ["starter", "professional"]:
            return JsonResponse(
                {"success": False, "message": "Invalid plan selection."}, status=400
            )
        # Same rule as the app upgrade link: only a plan above the current one.
        from plan_upgrade_handoff import upgrade_target_allowed
        from apps.agents.services.account_auth import agent_has_completed_payment

        is_trial_or_unpaid = (
            agent.isOnFreeTrial()
            or agent.status in ("event_challenge", "trial")
            or getattr(agent, "event_referral_participant", None) is not None
            or not agent_has_completed_payment(agent)
        )
        if not is_trial_or_unpaid and not upgrade_target_allowed(agent.plan_type, plan_type):
            return JsonResponse(
                {
                    "success": False,
                    "message": "You are already on this plan or a higher one.",
                },
                status=400,
            )

        promo_code = data.get("promo_code", "").strip()
        promo_obj = None
        if promo_code:
            # PromoCode lives in apps.agents.models (the old admin_panel path
            # did not exist, so every upgrade with a promo code failed).
            from apps.agents.models import PromoCode

            promo_obj = PromoCode.objects.filter(
                code=promo_code, is_active=True
            ).first()

        # Re-compute prices. The upgrade discount applies to agents on a free
        # trial only, exactly as the dashboard displays it; charging it to every
        # agent made Razorpay take less than the price shown.
        discount_pct = 0
        if agent.isOnFreeTrial():
            admin_default = SiteSetting.get_value("trial_upgrade_discount", 20)
            agent_specific = agent.upgrade_discount_percent or 0

            ref_code = ReferralCode.objects.filter(agent=agent).first()
            referral_discount = 0
            if ref_code:
                tier = ref_code.currentTier()
                if tier and "discount" in tier:
                    referral_discount = tier["discount"]

            discount_pct = max(
                int(admin_default), int(agent_specific), int(referral_discount)
            )

        pricing_config = SiteSetting.get_value(
            "pricing_config",
            {
                "starter": {"name": PLAN_LABELS["starter"], "full_price": 1999},
                "professional": {
                    "name": PLAN_LABELS["professional"],
                    "full_price": 9999,
                },
            },
        )

        # full_price is the BASE price excl. GST (₹1,999 / ₹9,999).
        starter_base_price = float(
            pricing_config.get("starter", {}).get("full_price", 1999)
        )
        prof_base_price = float(
            pricing_config.get("professional", {}).get("full_price", 9999)
        )

        # Apply promo discount to base price (excl. GST)
        starter_after_promo = starter_base_price
        if promo_obj and promo_obj.is_valid("basic"):
            starter_after_promo = starter_base_price - promo_obj.calculate_discount(
                starter_base_price
            )

        discount_factor = (100 - discount_pct) / 100
        starter_base = round(starter_after_promo * discount_factor)
        starter_disc = round(starter_base + starter_base * 0.18)

        prof_after_promo = prof_base_price
        if promo_obj and promo_obj.is_valid("professional"):
            prof_after_promo = prof_base_price - promo_obj.calculate_discount(
                prof_base_price
            )

        prof_base = round(prof_after_promo * discount_factor)
        if agent.referral_reward_type == "pro_plan_1rs":
            prof_base = 1
            discount_pct = 99.99

        from apps.agents.services.review_growth import get_review_upgrade_pricing

        review_upgrade = (
            get_review_upgrade_pricing(agent) if plan_type == "professional" else None
        )

        if review_upgrade:
            prof_base = review_upgrade["checkout_base_excl_gst"]
            prof_disc = review_upgrade["checkout_total_incl_gst"]
        elif agent.referral_reward_type == "pro_plan_1rs":
            prof_disc = 1.00
        else:
            prof_disc = round(prof_base + prof_base * 0.18)

        if plan_type == "starter":
            total_amount = starter_disc
            plan_amount = starter_base
            plan_name = PLAN_LABELS["starter"]
        else:
            total_amount = prof_disc
            plan_amount = prof_base
            plan_name = PLAN_LABELS["professional"]

        # Check duplicate paid subscription: trial/festive agents are never blocked from buying a 1-year plan.
        # Only a real captured Razorpay payment for this exact plan that is still active blocks checkout.
        already_paid = None
        if not is_trial_or_unpaid:
            from django.utils import timezone
            from apps.agents.services.account_auth import is_real_razorpay_id

            for sub in AgentSubscription.objects.filter(
                agent=agent,
                payment_status="completed",
                status="active",
                selected_plan=plan_name,
                expires_at__gt=timezone.now(),
            ):
                if float(sub.registration_amount or 0) > 0 and (
                    is_real_razorpay_id(sub.razorpay_payment_id, "pay_")
                    or is_real_razorpay_id(sub.razorpay_order_id, "order_")
                ):
                    already_paid = sub
                    break

        if already_paid:
            return JsonResponse(
                {"success": True, "already_completed": True, "agent_id": agent.id}
            )

        import time
        from apps.agents.services.razorpay_checkout import (
            checkout_payload,
            create_checkout_order,
            gateway_failure_message,
        )

        amount_paise = int(round(total_amount * 100))
        razorpay_order_id, mock_checkout = create_checkout_order(
            amount_paise,
            f"agent_upgrade_{agent.pk}_{int(time.time())}",
            request,
        )

        if not razorpay_order_id and amount_paise > 0:
            return JsonResponse(
                {
                    "success": False,
                    "message": gateway_failure_message(),
                }
            )

        # Update or create AgentSubscription
        subscription, created = AgentSubscription.objects.update_or_create(
            agent=agent,
            razorpay_order_id=razorpay_order_id,
            defaults={
                "selected_plan": plan_name or plan_type,
                "promo_code": promo_code if promo_obj else None,
                "registration_amount": total_amount,
                "payment_status": "pending",
                "status": "inactive",
            },
        )

        # Keep current agent status until payment succeeds — do not demote active trial users.

        # If 0 amount, complete instantly
        if amount_paise == 0:
            subscription.payment_status = "completed"
            subscription.status = "active"
            subscription.starts_at = timezone.now()
            subscription.expires_at = timezone.now() + timezone.timedelta(days=365)
            subscription.save()

            agent.status = "active"
            agent.plan_type = plan_type
            agent.save()
            _deactivate_superseded_subscriptions(agent, subscription.pk)
            try:
                from apps.agents.services.registration_leads import sync_lead_for_agent

                sync_lead_for_agent(agent)
            except Exception:
                logger.exception(
                    "Quick-registration lead sync failed during zero-amount upgrade for agent #%s",
                    agent.id,
                )

            # Credit referral
            if agent.referred_by_code:
                try:
                    ref_code_obj = ReferralCode.objects.filter(
                        code=agent.referred_by_code
                    ).first()
                    if ref_code_obj:
                        usage, u_created = ReferralUsage.objects.get_or_create(
                            referral_code=ref_code_obj,
                            referred_agent_id=agent.id,
                            defaults={
                                "status": "converted",
                                "signed_up_at": timezone.now(),
                            },
                        )
                        if not u_created and usage.status != "converted":
                            usage.status = "converted"
                            usage.save()

                        # Recalculate converted count
                        actual_conversions = ReferralUsage.objects.filter(
                            referral_code=ref_code_obj, status="converted"
                        ).count()
                        ref_code_obj.total_referrals = actual_conversions
                        ref_code_obj.save()

                        if actual_conversions >= 5:
                            referring_agent = Agent.objects.filter(
                                pk=ref_code_obj.agent_id
                            ).first()
                            if (
                                referring_agent
                                and referring_agent.plan_type == "free_trial"
                            ):
                                referring_agent.referral_reward_type = "pro_plan_1rs"
                                referring_agent.referral_reward_earned_at = (
                                    timezone.now()
                                )
                                referring_agent.save()
                except Exception as ref_err:
                    logger.warning(
                        f"Referral credit during plan upgrade failed: {ref_err}"
                    )

            try:
                ReferralCode.generateForAgent(agent)
            except Exception:
                pass

            return JsonResponse(
                {"success": True, "already_completed": True, "agent_id": agent.id}
            )

        request.session["pending_checkout"] = {
            "agent_id": agent.id,
            "order_id": razorpay_order_id,
            "plan_type": plan_type,
            "plan_name": plan_name,
        }
        request.session.modified = True

        try:
            from apps.agents.services.registration_leads import mark_payment_pending

            mark_payment_pending(agent)
        except Exception:
            logger.exception(
                "Quick-registration payment pending sync failed during upgrade for agent #%s",
                agent.id,
            )

        try:
            from apps.event_referral.models import TrialAgentActivityLog
            TrialAgentActivityLog.log(
                agent=agent,
                activity_type=TrialAgentActivityLog.ACTIVITY_UPGRADE_INITIATED,
                title=f'Upgrade Initiated ({plan_name})',
                description=f'Selected {plan_name} plan for ₹{int(total_amount)}',
                details={
                    'plan_type': plan_type,
                    'plan_name': plan_name,
                    'total_amount': total_amount,
                    'order_id': razorpay_order_id,
                    'promo_code': promo_code or '',
                },
                request=request,
                force=True,
            )
        except Exception:
            pass

        return JsonResponse(
            checkout_payload(
                razorpay_order_id,
                amount_paise,
                agent,
                is_mock=mock_checkout,
                extra={
                    "plan_amount": plan_amount,
                    "total_amount": total_amount,
                },
                request=request,
            )
        )

    except Exception as e:
        logger.error(f"Plan upgrade request failed: {e}")
        return JsonResponse(
            {"success": False, "message": "An unexpected error occurred."}, status=500
        )


@require_POST
def agent_log_trial_activity(request):
    """
    Lightweight endpoint for frontend event tracking (e.g. upgrade modal open, clicks).
    """
    from django.http import JsonResponse
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False}, status=401)
    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        return JsonResponse({"ok": False}, status=404)
    try:
        try:
            data = json_loads(request.body) if request.body else request.POST
        except Exception:
            data = request.POST or {}
        activity_type = data.get("activity_type") or "upgrade_modal_open"
        title = data.get("title") or "Upgrade Modal Opened"
        description = data.get("description") or "Agent clicked Upgrade Plan button"
        details = data.get("details") or {}
        from apps.event_referral.models import TrialAgentActivityLog
        TrialAgentActivityLog.log(
            agent=agent,
            activity_type=activity_type,
            title=title,
            description=description,
            details=details,
            request=request,
            force=True,
        )
        return JsonResponse({"ok": True})
    except Exception as e:
        logger.warning("agent_log_trial_activity error: %s", e)
        return JsonResponse({"ok": False})
