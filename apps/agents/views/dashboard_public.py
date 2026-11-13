"""Public agent profile pages (split out of dashboard.py): the profile view, review
submission, OG preview image and the /agent/<slug>/ share redirect."""

from django.shortcuts import render
from json import loads as json_loads
from apps.agents.views.dashboard_common import _resolve_agent_plan, logger


def agent_public_profile(request, slug, state_code=None):
    from django.http import Http404
    from django.conf import settings
    from apps.agents.models import Agent, AgentProfileView
    import time

    # Try to find by slug first
    agent = Agent.objects.filter(profile__slug=slug).first()

    # Fallback for ID if slug not found and is numeric
    if not agent and slug.isdigit():
        agent = Agent.objects.filter(id=int(slug)).first()

    if not agent:
        raise Http404("Agent not found")
    # Suspended / deleted / unpaid agents have no public page, as on the card views (audit AG3).
    from apps.agents.views.qr import _card_viewer_is_privileged, _hidden_from_public

    from apps.agents.services.account_auth import (
        public_agent_is_hidden,
        render_public_profile_unavailable,
    )

    if _hidden_from_public(agent) and not _card_viewer_is_privileged(request, agent):
        return render_public_profile_unavailable(request, agent)

    if public_agent_is_hidden(request, agent):
        return render_public_profile_unavailable(request, agent)

    is_owner = False
    if request.user.is_authenticated:
        is_owner = Agent.objects.filter(user=request.user, id=agent.id).exists()

    if not is_owner:
        try:
            session_key = f"agent_profile_viewed_{agent.id}"
            last_viewed_at = request.session.get(session_key)
            cooldown_seconds = 30 * 60
            current_time = int(time.time())

            if (
                not last_viewed_at
                or (current_time - int(last_viewed_at)) > cooldown_seconds
            ):
                AgentProfileView.record_view(agent)
                request.session[session_key] = current_time

                try:
                    from apps.event_referral.models import TrialAgentActivityLog
                    referer = (request.META.get('HTTP_REFERER') or '')[:250]
                    TrialAgentActivityLog.log(
                        agent=agent,
                        activity_type=TrialAgentActivityLog.ACTIVITY_PROFILE_VIEW,
                        title='Public Profile Viewed',
                        description='Visitor viewed public profile card/page',
                        details={'referer': referer},
                        request=request,
                    )
                except Exception:
                    pass

                from apps.wa_agent_bot.services.notification_service import (
                    notify_agent_profile_view,
                )

                notify_agent_profile_view(request, agent.id)
        except Exception as e:
            if settings.DEBUG:
                logger.warning(f"Profile tracking failed: {e}")

    # Fetch approved reviews
    reviews = (
        agent.reviews.filter(is_approved=True)
        .select_related("user")
        .order_by("-created_at")
    )

    # Find existing review for current user to populate form
    existing_review = None
    if request.user.is_authenticated and not is_owner:
        existing_review = agent.reviews.filter(user=request.user).first()

    profile = agent.get_primary_profile()
    if profile is None:
        raise Http404("Agent profile not found")
    display_name = (
        (profile.display_name if profile else "") or agent.fullname or "Agent"
    )
    agent_initial = display_name[0].upper() if display_name else "A"

    if profile and not profile.is_profile_visible:
        return render(
            request,
            "agents/profile_private_fallback.html",
            {
                "agent": agent,
                "profile": profile,
                "agentDisplayName": display_name,
                "agentInitial": agent_initial,
                "hide_eligibility_popup": True,
            },
        )

    social_links = {}
    if profile and profile.social_links:
        if isinstance(profile.social_links, dict):
            social_links = profile.social_links
        elif isinstance(profile.social_links, str):
            try:
                social_links = json_loads(profile.social_links)
            except ValueError:
                pass

    # Resolve agent_plan for public profile
    agent_plan = _resolve_agent_plan(agent.plan_type, agent=agent)

    from apps.agents.services.og_meta import profile_og_context

    context = {
        "agent": agent,
        "profile": profile,
        "agent_plan": agent_plan,
        "isOwnerView": is_owner,
        "reviews": reviews,
        "existingReview": existing_review,
        "reviewSlug": slug,
        "agentDisplayName": display_name,
        "agentInitial": agent_initial,
        "socialLinks": social_links,
        "performanceStats": getattr(agent, "performanceStats", None),
        "leadPreferences": getattr(agent, "leadPreferences", None),
        "review_scroll_delay_ms": 3000,
        "hide_eligibility_popup": True,
        "is_legacy_profile_path": bool(not state_code or request.path.startswith("/profile/")),
    }
    context.update(profile_og_context(request, agent, display_name=display_name))
    try:
        from apps.agents.services.review_growth import get_review_growth_config

        context["review_scroll_delay_ms"] = get_review_growth_config()[
            "review_scroll_delay_ms"
        ]
    except Exception:
        pass

    # Google Review Showcase & Nudge Context
    try:
        from apps.agents.services.google_review import (
            get_agent_google_review_data,
            get_google_nudge_config,
        )

        context["google_review_display"] = get_agent_google_review_data(agent)
        context["google_nudge_config"] = get_google_nudge_config(agent)
    except Exception:
        context["google_review_display"] = None
        context["google_nudge_config"] = None

    return render(request, "agents/profile_view.html", context)


from django.views.decorators.http import require_POST


@require_POST
def store_review(request, slug, state_code=None):
    from django.http import JsonResponse
    from apps.agents.models import Agent, AgentReview
    import re

    # Retrieve agent
    agent = Agent.objects.filter(profile__slug=slug).first()
    if not agent and slug.isdigit():
        agent = Agent.objects.filter(id=int(slug)).first()
    from apps.agents.views.qr import _card_viewer_is_privileged, _hidden_from_public

    if not agent or _hidden_from_public(agent):  # audit AG3
        return JsonResponse(
            {"status": "error", "message": "Agent not found"}, status=404
        )

    from apps.agents.services.account_auth import public_agent_is_hidden
    if public_agent_is_hidden(request, agent):
        return JsonResponse(
            {"status": "error", "message": "Profile not available"}, status=404
        )

    # Prevent agent from reviewing themselves
    if request.user.is_authenticated:
        is_owner = Agent.objects.filter(user=request.user, id=agent.id).exists()
        if is_owner:
            return JsonResponse(
                {"status": "error", "message": "You cannot review yourself"}, status=403
            )

    from apps.admin_panel.middleware import ThreatMonitorMiddleware, is_ip_blocked

    client_ip = ThreatMonitorMiddleware.get_client_ip(request)
    if is_ip_blocked(client_ip):
        return JsonResponse(
            {"status": "error", "message": "Access denied due to suspicious activity."},
            status=403,
        )

    from django.core.cache import cache

    rate_key = f"review_ratelimit_{client_ip}"
    # Atomic add/incr: get-then-set let parallel posts all pass the limit (audit AG17).
    submits = 1 if cache.add(rate_key, 1, timeout=3600) else cache.incr(rate_key)
    if submits > 20:
        return JsonResponse(
            {
                "status": "error",
                "message": "Too many reviews submitted from this network. Please try again later.",
            },
            status=429,
        )

    rating_val = request.POST.get("rating")
    review_val = request.POST.get("review")

    errors = {}
    if not rating_val or rating_val == "0":
        errors["rating"] = ["The rating field is required."]
    else:
        try:
            rating_val = int(rating_val)
            if rating_val < 1 or rating_val > 5:
                errors["rating"] = ["The rating must be between 1 and 5."]
        except ValueError:
            errors["rating"] = ["The rating must be an integer."]

    if not review_val:
        errors["review"] = ["The review field is required."]
    elif len(review_val) < 10:
        errors["review"] = ["The review must be at least 10 characters."]
    elif len(review_val) > 500:
        errors["review"] = ["The review may not be greater than 500 characters."]

    if not request.user.is_authenticated:
        fullname = (request.POST.get("fullname") or "").strip()
        email = (request.POST.get("email") or "").strip()
        mobile = (request.POST.get("mobile") or "").strip()

        if not fullname:
            errors["fullname"] = ["The fullname field is required."]
        if email:
            if "@" not in email or "." not in email:
                errors["email"] = ["The email must be a valid email address."]
        if not mobile:
            errors["mobile"] = ["The mobile field is required."]
        else:
            mobile_digits = re.sub(r"[^0-9]", "", mobile)
            if len(mobile_digits) != 10:
                errors["mobile"] = ["The mobile format is invalid. Must be 10 digits."]
    else:
        fullname = (
            f"{request.user.first_name} {request.user.last_name}".strip()
            or request.user.username
        )
        email = (request.user.email or "").strip()
        # Try to find user's agent mobile
        user_agent = Agent.objects.filter(user=request.user).first()
        mobile = user_agent.mobile if user_agent else ""

    if errors:
        return JsonResponse({"status": "error", "errors": errors}, status=422)

    from apps.agents.services.review_growth import (
        agent_review_count,
        get_review_growth_config,
        get_review_growth_status,
        review_threshold_just_crossed,
        should_show_upgrade_cta,
    )

    previous_review_count = agent_review_count(agent)

    reviewer_email = email.lower() if email else None

    if request.user.is_authenticated:
        review_obj, created = AgentReview.objects.update_or_create(
            agent=agent,
            user=request.user,
            defaults={
                "reviewer_name": fullname,
                "reviewer_email": reviewer_email,
                "reviewer_mobile": mobile,
                "rating": rating_val,
                "review": review_val,
                "is_approved": True,
            },
        )
    else:
        mobile_digits = re.sub(r"[^0-9]", "", mobile)
        # The email/mobile is unverified, so an anonymous submission may create a review
        # but never overwrite one.
        if (
            reviewer_email
            and AgentReview.objects.filter(
                agent=agent, reviewer_email=reviewer_email
            ).exists()
        ):
            return JsonResponse(
                {
                    "status": "error",
                    "message": "A review from this email already exists for this agent.",
                    "errors": {
                        "email": [
                            "A review from this email already exists for this agent."
                        ]
                    },
                },
                status=422,
            )
        if (
            mobile_digits
            and AgentReview.objects.filter(
                agent=agent, reviewer_mobile=mobile_digits
            ).exists()
        ):
            return JsonResponse(
                {
                    "status": "error",
                    "message": "A review from this mobile number already exists for this agent.",
                    "errors": {
                        "mobile": [
                            "A review from this mobile number already exists for this agent."
                        ]
                    },
                },
                status=422,
            )
        review_obj = AgentReview.objects.create(
            agent=agent,
            reviewer_email=reviewer_email,
            user=None,
            reviewer_name=fullname,
            reviewer_mobile=mobile_digits,
            rating=rating_val,
            review=review_val,
            is_approved=True,
        )
        created = True
    message = (
        "Review submitted successfully!" if created else "Review updated successfully!"
    )

    new_review_count = agent_review_count(agent)
    growth_status = get_review_growth_status(agent)
    if review_threshold_just_crossed(
        previous_review_count, new_review_count
    ) and should_show_upgrade_cta(agent):
        try:
            from apps.agents.models import AgentNotification

            growth_cfg = get_review_growth_config()
            AgentNotification.objects.create(
                agent=agent,
                title="Upgrade Unlocked",
                body=growth_cfg.get(
                    "upgrade_message",
                    "You have collected enough reviews. Upgrade to Professional for full visibility.",
                )[:500],
            )
        except Exception:
            logger.exception(
                "Failed to create upgrade-unlocked notification for agent #%s", agent.id
            )

    response_message = message
    if not created:
        response_message = f"{message} Note: updating an existing review from the same email does not add a new review."
    if growth_status.get("show_upgrade_progress"):
        remaining = growth_status.get("remaining_reviews", 0)
        response_message = (
            f"{response_message} You have {new_review_count} of {growth_status['min_reviews']} unique customer reviews"
            f" — {remaining} more unlocks your Professional upgrade."
        )
    elif growth_status.get("upgrade_ready"):
        response_message = f"{response_message} You unlocked the Professional upgrade — open your agent dashboard to continue."

    nudge_data = None
    try:
        from apps.agents.services.google_review import get_google_nudge_config

        nudge_data = get_google_nudge_config(agent)
    except Exception:
        pass

    return JsonResponse(
        {
            "status": "success",
            "message": response_message,
            "review_count": new_review_count,
            "min_reviews": growth_status.get("min_reviews", 3),
            "upgrade_ready": bool(growth_status.get("upgrade_ready")),
            "review_created": bool(created),
            "google_nudge": nudge_data,
        }
    )



def agent_og_image(request, agent_id=None, slug=None):
    from django.core.cache import cache
    from django.http import HttpResponse, Http404
    from PIL import Image
    import io
    from apps.agents.models import Agent, og_image_cache_key
    from apps.agents.services.og_image import render_agent_og_jpeg

    agent = None
    if agent_id:
        agent = Agent.objects.filter(id=agent_id).first()
    elif slug:
        agent = Agent.objects.filter(profile__slug=slug).first()
        if not agent and slug.isdigit():
            agent = Agent.objects.filter(id=int(slug)).first()
        if not agent:
            try:
                from apps.referral_championship.models import ChampionshipParticipant

                participant = (
                    ChampionshipParticipant.objects.filter(
                        referral_id=slug.strip().upper()
                    )
                    .select_related("agent")
                    .first()
                )
                if participant:
                    from django.conf import settings
                    import os

                    champ_img_path = os.path.join(
                        settings.BASE_DIR, "static", "img", "championship_og.jpg"
                    )
                    if os.path.exists(champ_img_path):
                        with open(champ_img_path, "rb") as f:
                            content = f.read()
                        response = HttpResponse(content, content_type="image/jpeg")
                        response["Cache-Control"] = "public, max-age=86400"
                        return response
                    if participant.agent:
                        agent = participant.agent
            except Exception:
                pass
        if not agent:
            try:
                from apps.admin_panel.models.referral_code import ReferralCode

                ref_obj = (
                    ReferralCode.objects.filter(code=slug)
                    .select_related("agent")
                    .first()
                )
                if ref_obj and ref_obj.agent:
                    agent = ref_obj.agent
            except Exception:
                pass

    from apps.agents.views.qr import _card_viewer_is_privileged, _hidden_from_public

    from apps.agents.services.account_auth import public_binary_unavailable_or_404

    if not agent:
        raise Http404("Agent not found")
    if _hidden_from_public(agent) and not _card_viewer_is_privileged(request, agent):  # audit AG3
        return public_binary_unavailable_or_404(request, agent)

    cache_key = og_image_cache_key(agent.id)
    # Cache bypass forces a full PIL render; only the owning agent or an admin
    # may use it, otherwise it is a free CPU-exhaustion lever on a public URL.
    nocache = request.GET.get("nocache") == "1"
    if nocache:
        from apps.admin_panel.auth import _get_admin_from_session
        owns = request.user.is_authenticated and agent.user_id == request.user.pk
        if not owns and not _get_admin_from_session(request):
            nocache = False

    if not nocache:
        cached_image = cache.get(cache_key)
        if cached_image:
            response = HttpResponse(cached_image, content_type="image/jpeg")
            response["Cache-Control"] = "public, max-age=86400"
            response["Access-Control-Allow-Origin"] = "*"
            return response

    try:
        from apps.agents.services.og_image import render_and_cache

        encoded_image = render_and_cache(agent)
        response = HttpResponse(encoded_image, content_type="image/jpeg")
        response["Cache-Control"] = "public, max-age=604800"
        response["Access-Control-Allow-Origin"] = "*"
        return response
    except Exception as e:
        logger.exception(f"OG Image Generation error: {e}")
        fallback_canvas = Image.new("RGB", (1200, 630), (15, 58, 102))
        buf = io.BytesIO()
        fallback_canvas.save(buf, format="JPEG", quality=50)
        response = HttpResponse(buf.getvalue(), content_type="image/jpeg")
        response["Cache-Control"] = "no-store"
        response["Access-Control-Allow-Origin"] = "*"
        return response


def agent_public_share_profile(request, slug):
    from apps.agents.models import Agent
    from django.shortcuts import redirect, render
    from django.http import Http404
    from django.urls import reverse

    agent = Agent.objects.filter(profile__slug=slug).first()
    if not agent and str(slug).isdigit():
        agent = Agent.objects.filter(id=int(slug)).first()

    if not agent:
        raise Http404("Agent not found")

    from apps.agents.services.account_auth import (
        public_agent_is_hidden,
        render_public_profile_unavailable,
    )
    if public_agent_is_hidden(request, agent):
        return render_public_profile_unavailable(request, agent)

    profile = agent.get_primary_profile()

    # Inactive, suspended or deleted checks
    is_active = getattr(agent, "is_active", True)
    is_visible = profile.is_profile_visible if profile else False

    if not is_active or not is_visible:
        return render(
            request,
            "agents/profile_unavailable.html",
            {"agent": agent, "profile": profile},
            status=404,
        )

    profile_slug = (
        (profile.slug if profile and profile.slug else "")
        or getattr(agent, "agent_slug", "")
        or str(agent.id)
    )

    state_code = getattr(agent, "state_code", "gj")
    if callable(state_code):
        state_code = state_code()
    state_code = str(state_code or "gj").strip().lower()

    try:
        target_url = reverse(
            "agents:agent_public_profile_state_direct",
            kwargs={"state_code": state_code, "slug": profile_slug},
        )
    except Exception:
        try:
            target_url = reverse(
                "agents:agent_public_profile", kwargs={"slug": profile_slug}
            )
        except Exception:
            target_url = f"/{state_code}/{profile_slug}/"

    query_string = request.META.get("QUERY_STRING", "")
    if query_string:
        target_url = f"{target_url}?{query_string}"

    return redirect(target_url, permanent=True)
