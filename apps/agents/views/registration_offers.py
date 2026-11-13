"""Discount endpoints: social-follow and scratch-card rewards, exclusive discount status and promo-code checks."""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from apps.agents.models import AgentDraft, PromoCode
from apps.home.models import SiteSetting
from apps.agents.services.feature_unlock import resolve_checkout_plan_slug

from .registration_common import _get_client_ip, logger
from .registration_pricing import (
    _DEFAULT_PRICING,
    _exclusive_base_price,
    _get_tier_prices,
    _scratch_session_key,
)


_SOCIAL_FOLLOW_PLATFORMS = frozenset(
    {
        "instagram",
        "facebook",
        "x",
        "twitter",
        "linkedin",
        "youtube",
        "whatsapp",
        "telegram",
        "threads",
        "pinterest",
    }
)


@require_POST
def record_social_follow(request):
    """Record that the user successfully followed social accounts and compute plan discounts."""
    import json

    try:
        data = json.loads(request.body)
        platform = str(data.get("platform") or "").strip().lower()[:50]
        agent_id = data.get("agent_id")  # draft_id
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON."}, status=400)

    if not agent_id or not platform:
        return JsonResponse({"success": False, "message": "Missing data."}, status=400)
    from apps.home.models import SiteSetting

    pricing_config = SiteSetting.get_value("pricing_config", _DEFAULT_PRICING)

    # Each distinct platform raises the discount tier, so only real/configured
    # networks count — arbitrary strings ("a","b","c",...) unlocked the top tier.
    allowed_platforms = set(_SOCIAL_FOLLOW_PLATFORMS)
    exclusive_cfg = SiteSetting.get_value("exclusive_plan_config") or {}
    for cfg in (pricing_config, exclusive_cfg):
        links = cfg.get("social_links") if isinstance(cfg, dict) else None
        for link in links or []:
            if isinstance(link, dict) and link.get("platform"):
                allowed_platforms.add(str(link["platform"]).strip().lower())
    if platform not in allowed_platforms:
        return JsonResponse(
            {"success": False, "message": "Unknown platform."}, status=400
        )

    session_key = f"followed_platforms_{agent_id}"
    followed = request.session.get(session_key, [])
    if platform not in followed:
        followed.append(platform)
        request.session[session_key] = followed
        if hasattr(request.session, "modified"):
            request.session.modified = True

    follow_count = len(followed)
    tier_info = _get_tier_prices(pricing_config, follow_count)

    return JsonResponse(
        {
            "success": True,
            "message": "Follow recorded successfully!",
            "discount_unlocked": follow_count > 0,
            "follow_count": follow_count,
            "applied_discount": tier_info["applied_discount"],
            "starter_applied_discount": tier_info.get("starter_applied_discount", 0),
            "prof_applied_discount": tier_info.get("prof_applied_discount", 0),
            "starter_price": tier_info["starter_price"],
            "starter_base": tier_info["starter_base"],
            "starter_total": tier_info["starter_total"],
            "prof_price": tier_info["prof_price"],
            "prof_base": tier_info["prof_base"],
            "prof_total": tier_info["prof_total"],
            "followed_platforms": followed,
        }
    )


@require_POST
@csrf_protect
def record_scratch_reveal(request):
    """Persist that the user revealed the starter/professional scratch price."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST
    plan_type = resolve_checkout_plan_slug(data.get("plan_type"))
    if plan_type not in ("starter", "professional"):
        return JsonResponse({"success": False, "message": "Invalid plan."}, status=400)
    request.session[_scratch_session_key(plan_type)] = True
    request.session.modified = True
    return JsonResponse({"success": True, "plan_type": plan_type})


def exclusive_discount_status(request):
    """Get the current discount status and followed platforms."""
    agent_id = request.GET.get("agent_id")
    if not agent_id:
        return JsonResponse(
            {"success": False, "message": "Missing agent_id"}, status=400
        )

    session_key = f"followed_platforms_{agent_id}"
    followed = request.session.get(session_key, [])
    discount_unlocked = len(followed) > 0

    from apps.home.models import SiteSetting

    exclusive_config = SiteSetting.get_value("exclusive_plan_config") or {}

    follow_count = len(followed)
    current_price = _exclusive_base_price(
        exclusive_config, follow_count, discount_unlocked
    )

    # Only heal the draft this session owns — this is a GET and must not let a
    # caller flip discount state on arbitrary draft ids.
    if discount_unlocked and str(agent_id) == str(
        request.session.get("current_draft_id") or ""
    ):
        # Sync session state to database to heal any mismatched states
        from apps.agents.models import AgentDraft, UserPlanProgress

        try:
            draft = AgentDraft.objects.get(pk=agent_id)
            progress, _ = UserPlanProgress.objects.get_or_create(
                draft=draft, plan_key="exclusive_gamified"
            )
            progress.discount_unlocked = True
            progress.save()
            logger.info(f"Healed and saved discount_unlocked=True for draft {draft.id}")
        except Exception as e:
            logger.error(f"Failed to heal UserPlanProgress in discount_status: {e}")

    return JsonResponse(
        {
            "success": True,
            "discount_unlocked": discount_unlocked,
            "current_price": current_price,
            "followed_platforms": followed,
        }
    )


# Wrong promo codes allowed per client IP and per browser session before the
# check is paused (stops guessing codes). Security audit 2026-10-02 M3.
PROMO_FAIL_LIMIT = 10


PROMO_FAIL_WINDOW_SECONDS = 15 * 60


def _promo_fail_keys(request):
    keys = [f"promo_fail_ip_{_get_client_ip(request)}"]
    if request.session.session_key:
        keys.append(f"promo_fail_sess_{request.session.session_key}")
    return keys


def _promo_checks_paused(request):
    from django.core.cache import cache

    try:
        return any(
            (cache.get(k) or 0) >= PROMO_FAIL_LIMIT for k in _promo_fail_keys(request)
        )
    except Exception:
        return False


def _record_promo_failure(request):
    from django.core.cache import cache

    for key in _promo_fail_keys(request):
        try:
            cache.add(key, 0, timeout=PROMO_FAIL_WINDOW_SECONDS)
            cache.incr(key)
        except Exception:
            pass


@require_POST
@csrf_protect
def agent_verify_promo(request):
    """
    Verify promo code.
    Mirrors Laravel's AgentRegistrationController::verifyPromo.
    """
    try:
        data = json.loads(request.body)
        promo_code = data.get("promo_code", "").strip().upper()
    except (json.JSONDecodeError, AttributeError):
        promo_code = request.POST.get("promo_code", "").strip().upper()

    if not promo_code:
        return JsonResponse({"success": False, "message": "Promo code is required."})

    if len(promo_code) > 50:
        return JsonResponse(
            {
                "success": False,
                "message": "Promo code is too long (maximum 50 characters).",
            }
        )

    if _promo_checks_paused(request):
        return JsonResponse(
            {
                "success": False,
                "message": "Too many attempts. Please try again after 15 minutes.",
            },
            status=429,
        )

    try:
        promo = PromoCode.objects.filter(code__iexact=promo_code).first()
        if promo and promo.is_valid():
            request.session["applied_promo_code"] = promo.code
            request.session.modified = True
            return JsonResponse(
                {
                    "success": True,
                    "message": f'Promo code "{promo.code}" is valid and will be applied at checkout!',
                }
            )
        elif promo:
            _record_promo_failure(request)
            return JsonResponse(
                {
                    "success": False,
                    "message": "Promo code has expired or is no longer valid.",
                }
            )
    except Exception as e:
        logger.error(f"Promo verification error: {e}")

    _record_promo_failure(request)
    return JsonResponse(
        {
            "success": False,
            "message": "Invalid or expired promo code.",
        }
    )


@require_POST
@csrf_protect
def agent_clear_promo(request):
    """
    Clear the applied promo code from the session.
    Called when the user clicks 'Remove' on the plans page promo widget.
    """
    request.session.pop("applied_promo_code", None)
    request.session.modified = True
    return JsonResponse({"success": True, "message": "Promo code removed."})
