import os
import logging
from urllib.parse import quote
from json import (
    dumps as json_dumps,
    loads as json_loads,
    JSONDecodeError as JSONDecodeError,
)
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib.auth import logout
from django.contrib import messages
from apps.home.services.portal_messages import PORTAL_AGENT, portal_error
from django.utils import timezone
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from apps.agents.models import (
    Agent,
    AgentProfile,
    AgentSubscription,
    AgentLead,
    AgentProfileView,
    AgentDeviceToken,
    FavoriteAgent,
)
from apps.home.models import SiteSetting, UpcomingFeature
from apps.admin_panel.models.referral_code import ReferralCode
from apps.admin_panel.models.referral_usage import ReferralUsage
from apps.agents.utils.file_validation import (
    validate_license_document,
    validate_magic_bytes,
)
from apps.agents.services.feature_unlock import (
    FEATURE_ATTR_MAP,
    PLAN_LABELS,
    build_unlock_hints,
    evaluate_unlock_rules,
    filter_overlay_extras,
    normalize_plan_slug,
    overlay_plan,
    plan_shows_feature,
    plan_slug_from_name,
    profile_completion_percent,
    resolve_checkout_plan_slug,
    resolve_plan_entitlements,
    EDIT_PROFILE_CHILD_FEATURES,
)
from apps.agents.views.registration import (
    _deactivate_superseded_subscriptions,
    _display_plan_name,
    verify_and_activate_pending_payment,
)

logger = logging.getLogger(__name__)

# Split into sibling modules; re-exported so imports of apps.agents.views.dashboard.<name> keep working.
from apps.agents.views.dashboard_common import (  # noqa: E402,F401
    PlanFeatureProxy,
    _resolve_agent_plan,
    _resolve_base_agent_plan,
)
from apps.agents.views.dashboard_public import (  # noqa: E402,F401
    agent_og_image,
    agent_public_profile,
    agent_public_share_profile,
    store_review,
)
from apps.agents.views.dashboard_profile import (  # noqa: E402,F401
    _EDIT_LOG_STEP_LABELS,
    _collect_license_uploads,
    _email_taken_by_other_login,
    _log_profile_edit,
    _profile_edit_snapshot,
    apply_profile_update,
    edit_profile,
    render_edit_profile,
    update_profile,
)
from apps.agents.views.dashboard_leads import (  # noqa: E402,F401
    _with_fresh_db,
    agent_capture_lead,
)
from apps.agents.views.dashboard_account import (  # noqa: E402,F401
    agent_log_trial_activity,
    agent_push_token,
    agent_upgrade_plan,
    referral_info,
)
from apps.agents.views.dashboard_settings import (  # noqa: E402,F401
    agent_update_visibility,
    save_google_review_settings,
    serve_private_file,
    toggle_agent_google_review,
    track_google_review_click_view,
)


@login_required(login_url="agents:agent_login")
def agent_dashboard(request):
    r"""
    Handle rendering the agent dashboard.
    Ported from App\Http\Controllers\Agent\AgentDashboardController@index
    Includes self-healing logic and pricing calculation.
    """
    user = request.user
    from apps.agents.services.account_auth import (
        resolve_agent_for_user,
        agent_can_access_dashboard,
        find_agent,
    )

    is_admin = user.is_staff or user.is_superuser
    agent = resolve_agent_for_user(user)
    if not agent and getattr(user, "email", None):
        agent = find_agent(user.email)

    if agent:
        from apps.agents.services.account_auth import (
            ACCOUNT_RESTRICTED_MESSAGE,
            agent_account_is_active,
        )
        if not agent_account_is_active(agent):
            from django.contrib.auth import logout
            from apps.home.services.portal_messages import PORTAL_AGENT, portal_error
            logout(request)
            portal_error(request, ACCOUNT_RESTRICTED_MESSAGE, PORTAL_AGENT)
            return redirect("agents:agent_login")

    if not agent and not is_admin:
        messages.error(request, "Please complete your registration.")
        return redirect("agents:agent_registration")

    event_referral_participant = None
    force_lock_all_features = False
    event_referral_expired_locked = False
    event_referral_share_url = ""
    if agent:
        try:
            from apps.event_referral.services.participant_service import (
                prepare_event_referral_portal_state,
            )

            (
                event_referral_participant,
                force_lock_all_features,
                event_referral_expired_locked,
            ) = prepare_event_referral_portal_state(agent)
            if event_referral_participant:
                agent.refresh_from_db()
                event_referral_share_url = request.build_absolute_uri(
                    reverse(
                        "agents:agent_registration_referral",
                        kwargs={"ref_code": event_referral_participant.referral_code},
                    )
                )
        except Exception as ev_err:
            logger.warning("Event referral dashboard context failed: %s", ev_err)

    if agent and not is_admin:
        try:
            sess_key = f"trial_dash_view_{agent.id}"
            import time  # was never imported: the NameError silently skipped this log
            now_ts = int(time.time())
            last_ts = request.session.get(sess_key, 0)
            if not last_ts or (now_ts - int(last_ts) > 900):
                request.session[sess_key] = now_ts
                from apps.event_referral.models import TrialAgentActivityLog
                TrialAgentActivityLog.log(
                    agent=agent,
                    activity_type=TrialAgentActivityLog.ACTIVITY_DASHBOARD,
                    title='Dashboard Visited',
                    description='Agent viewed dashboard',
                    request=request,
                )
        except Exception:
            pass

    event_referral_whatsapp_url = ""
    if event_referral_share_url:
        event_referral_whatsapp_url = "https://api.whatsapp.com/send?text=" + quote(
            event_referral_share_url
        )

    event_referral_welcome = bool(
        request.session.pop("event_referral_welcome_dashboard", False)
    )
    suppress_review_share = bool(
        request.session.pop("suppress_review_share_popup", False)
    )

    # Only re-check Razorpay if payment has not been completed yet (netbanking / lost callback recovery).
    if agent:
        from apps.agents.services.account_auth import agent_has_completed_payment

        if not agent_has_completed_payment(agent):
            try:
                verify_and_activate_pending_payment(agent)
                agent.refresh_from_db()
            except Exception as e:
                logger.warning(
                    "Dashboard payment re-verify failed for agent #%s: %s", agent.id, e
                )

        latest_completed_sub = (
            AgentSubscription.objects.filter(
                agent=agent,
                payment_status="completed",
                status="active",
            )
            .order_by("-starts_at", "-created_at", "-id")
            .first()
        )
        if latest_completed_sub:
            synced_plan = plan_slug_from_name(latest_completed_sub.selected_plan or "")
            if synced_plan and synced_plan != normalize_plan_slug(
                agent.plan_type or ""
            ):
                agent.plan_type = synced_plan
                agent.save(update_fields=["plan_type", "updated_at"])
            try:
                _deactivate_superseded_subscriptions(agent, latest_completed_sub.pk)
            except Exception:
                logger.exception(
                    "Failed to deactivate superseded subscriptions for agent #%s",
                    agent.id,
                )

        # ── Self-Heal: Stuck in pending_payment but subscription completed ──
        if (
            agent.status
            in ["pending_payment", "pending_accounts_payment", "incomplete"]
            or agent.registration_step < 2
        ):
            completed_sub = (
                AgentSubscription.objects.filter(
                    agent=agent, payment_status="completed", status="active"
                )
                .order_by("-created_at")
                .first()
            )

            if completed_sub:
                plan_name = (completed_sub.selected_plan or "").lower()
                plan_type = plan_slug_from_name(plan_name) or "professional"

                if plan_type == "free_trial":
                    agent.status = "active"
                    if not agent.trial_ends_at:
                        agent.trial_ends_at = completed_sub.expires_at or (
                            timezone.now() + timezone.timedelta(days=30)
                        )
                else:
                    agent.status = "pending_approval"
                agent.plan_type = plan_type
                agent.registration_step = 2
                agent.save()
                agent.refresh_from_db()
                try:
                    from apps.agents.services.registration_leads import (
                        sync_lead_for_agent,
                    )

                    sync_lead_for_agent(agent)
                except Exception:
                    logger.exception(
                        "Quick-registration lead sync failed during dashboard self-heal for agent #%s",
                        agent.id,
                    )
                logger.info(
                    f"AgentDashboard self-heal: agent #{agent.id} promoted to {agent.status}."
                )

    if not is_admin and (not agent or not agent_can_access_dashboard(agent)):
        messages.warning(
            request, "Please complete your payment to access the dashboard."
        )
        return redirect("agents:chooseplan")

    # Enforce role guard check for dashboard access
    is_admin = user.is_staff or user.is_superuser
    if not (agent or is_admin):
        logout(request)
        portal_error(request, "Unauthorized access. Gated area.", PORTAL_AGENT)
        return redirect("agents:agent_login")

    # Load statistics
    start_of_month = timezone.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    try:
        from django.db.models import Count

        lead_stats = AgentLead.objects.filter(agent=agent).aggregate(
            total=Count("id"),
            monthly=Count("id", filter=Q(created_at__gte=start_of_month)),
            new=Count("id", filter=Q(lead_status="new")),
            contacted=Count("id", filter=Q(lead_status="contacted")),
            follow_up=Count("id", filter=Q(lead_status="follow_up")),
            closed=Count("id", filter=Q(lead_status="closed")),
        )
        total_leads = lead_stats["total"] or 0
        monthly_leads = lead_stats["monthly"] or 0
        new_leads = lead_stats["new"] or 0
        contacted_leads = lead_stats["contacted"] or 0
        follow_up_leads = lead_stats["follow_up"] or 0
        closed_leads = lead_stats["closed"] or 0
    except Exception as e:
        logger.warning(f"Dashboard lead stats unavailable for agent #{agent.id}: {e}")
        total_leads = monthly_leads = new_leads = contacted_leads = follow_up_leads = (
            closed_leads
        ) = 0

    active_leads = new_leads + contacted_leads + follow_up_leads
    conversion_rate = (
        round((closed_leads / total_leads * 100), 1) if total_leads > 0 else 0.0
    )

    try:
        pv_stats = AgentProfileView.objects.filter(agent=agent).aggregate(
            total=Sum("view_count"),
            monthly=Sum("view_count", filter=Q(view_date__gte=start_of_month.date())),
        )
        total_page_views = pv_stats["total"] or 0
        monthly_visits = pv_stats["monthly"] or 0
    except Exception as e:
        logger.warning(
            f"Dashboard profile view stats unavailable for agent #{agent.id}: {e}"
        )
        total_page_views = monthly_visits = 0

    try:
        recent_leads = AgentLead.objects.filter(agent=agent).order_by("-created_at")[
            :10
        ]
        # Newest 500 only: the list rendered every lead an agent ever got (audit AG8).
        all_leads = AgentLead.objects.filter(agent=agent).order_by("-created_at")[:500]
    except Exception as e:
        logger.warning(f"Dashboard recent leads unavailable for agent #{agent.id}: {e}")
        recent_leads = []
        all_leads = []

    dashboard_stats = {
        "conversionRate": conversion_rate,
        "monthlyTarget": 0,
        "totalPageViews": total_page_views,
        "contactRequests": total_leads,
        "monthlyVisits": monthly_visits,
        "totalLeads": total_leads,
        "monthlyLeads": monthly_leads,
        "newLeads": new_leads,
        "contactedLeads": contacted_leads,
        "followUpLeads": follow_up_leads,
        "closedLeads": closed_leads,
        "activeLeads": active_leads,
    }

    # Referral Config check
    referral_config = SiteSetting.get_value(
        "referral_config", {"eligibility": "free_trial_only"}
    )
    show_referral = False
    if referral_config.get("eligibility") == "all" or agent.plan_type == "free_trial":
        show_referral = True

    # ── Unread Notifications (Laravel: fetch + mark-read-on-view) ────────────
    from apps.agents.models import AgentNotification

    unread_notifications = []
    if agent:
        try:
            unread_notifications = list(
                AgentNotification.objects.filter(agent=agent, is_read=False).order_by(
                    "-created_at"
                )
            )
            if unread_notifications:
                # Only the ones shown; newer rows stay unread (audit AG15).
                AgentNotification.objects.filter(
                    id__in=[n.id for n in unread_notifications]
                ).update(is_read=True)
        except Exception as e:
            logger.warning(
                f"Dashboard notifications unavailable for agent #{agent.id}: {e}"
            )

    # Profile Completion Check (shared rubric with activity-unlock rules)
    profile = agent.get_primary_profile()
    completion = profile_completion_percent(agent)

    # Free Trial Upgrade Discount Calculation
    is_on_trial = agent.isOnFreeTrial()
    days_left = 0
    if is_on_trial and agent.trial_ends_at:
        days_left = (agent.trial_ends_at - timezone.now()).days
        if days_left < 0:
            days_left = 0

    discount_pct = 0
    if is_on_trial:
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
            "professional": {"name": PLAN_LABELS["professional"], "full_price": 9999},
        },
    )

    # full_price is the BASE price excl. GST (₹1,999 / ₹9,999).
    starter_base_price = float(pricing_config.get("starter", {}).get("full_price", 1999))
    prof_base_price = float(pricing_config.get("professional", {}).get("full_price", 9999))

    # Undiscounted totals incl. 18% GST (for strikethrough display)
    starter_full = round(starter_base_price + starter_base_price * 0.18)
    prof_full = round(prof_base_price + prof_base_price * 0.18)

    # Apply trial discount to base price
    discount_factor = (100 - discount_pct) / 100
    starter_base = round(starter_base_price * discount_factor)
    starter_disc = round(starter_base + starter_base * 0.18)

    if agent.referral_reward_type == "pro_plan_1rs":
        prof_base = 1
        prof_disc = 1.00
        discount_pct = 99.99
    else:
        prof_base = round(prof_base_price * discount_factor)
        prof_disc = round(prof_base + prof_base * 0.18)

    from django.conf import settings

    plan_name = _display_plan_name(agent, pricing_config)

    dashboard_plan_type = agent.plan_type
    if event_referral_participant:
        from apps.event_referral.services.participant_service import (
            event_referral_effective_plan_type,
        )

        override_plan = event_referral_effective_plan_type(
            agent, event_referral_participant
        )
        if override_plan:
            dashboard_plan_type = override_plan

    # Resolve SubscriptionPlan using robust multi-tier helper
    agent_plan = _resolve_agent_plan(dashboard_plan_type, agent=agent)

    try:
        favorite_ids = set(
            FavoriteAgent.objects.filter(user=request.user).values_list(
                "agent_id", flat=True
            )
        )
    except Exception:
        favorite_ids = set()

    try:
        popup_notifications = [
            n
            for n in unread_notifications
            if (n.title or "").strip() not in ("Upgrade Unlocked",)
        ]
        unread_notifications_json = json_dumps(
            [{"title": n.title, "body": n.body} for n in popup_notifications],
            ensure_ascii=False,
        ).replace("</", r"<\/")
    except Exception:
        unread_notifications_json = "[]"
    try:
        feature_unlock_hints = build_unlock_hints(
            agent, normalize_plan_slug(agent.plan_type)
        )
        from apps.agents.services.review_growth import build_review_growth_hints

        feature_unlock_hints.update(build_review_growth_hints(agent))
        feature_unlock_hints_json = json_dumps(feature_unlock_hints).replace(
            "</", r"<\/"
        )
    except Exception:
        feature_unlock_hints_json = "[]"

    from apps.agents.services.qr_branded import build_qr_target_url
    from apps.agents.services.review_growth import (
        QR_TYPE_LABELS,
        QR_TYPES,
        agent_review_count,
        build_review_unlock_summary,
        get_review_growth_config,
        get_review_growth_status,
        get_review_upgrade_pricing,
        qr_access_for_plan,
        should_show_popup,
        should_show_upgrade_cta,
        should_show_upgrade_progress,
    )

    growth_cfg = get_review_growth_config()
    growth_status = get_review_growth_status(agent)
    professional_plan = _resolve_agent_plan("professional", agent=agent)
    review_unlock_summary = build_review_unlock_summary(
        agent, agent_plan, professional_plan
    )
    from apps.agents.services.review_growth import get_review_milestone_features

    review_milestone_features = get_review_milestone_features(
        agent_plan, professional_plan
    )
    from apps.agents.views.registration import _PROFESSIONAL_PLAN_UI_FEATURES

    prof_cfg = pricing_config.get("professional", {})
    prof_name = PLAN_LABELS["professional"]
    prof_desc = prof_cfg.get(
        "description", "Maximum visibility and premium tools for top agents."
    )
    slug = (
        (profile.slug if profile and profile.slug else "")
        or getattr(agent, "agent_slug", "")
        or str(agent.id)
    )
    state_code = (
        agent.state_code()
        if callable(getattr(agent, "state_code", None))
        else getattr(agent, "state_code", "gj")
    )
    profile_url = (
        request.build_absolute_uri(
            reverse(
                "agents:agent_public_profile_state_direct",
                kwargs={"state_code": state_code, "slug": slug},
            )
        )
        if slug
        else request.build_absolute_uri("/")
    )
    share_text = (
        f"I'm now on PadosiAgent — India's trusted insurance agent network. "
        f"View my profile and leave a review: {profile_url}"
    )
    # ── Digital Visiting Card feature flag & studio config ──
    from apps.admin_panel.services.digital_card_studio import (
        get_digital_card_studio_config,
    )

    card_flag_val = SiteSetting.get_value("agent_digital_card_enabled", None)
    if card_flag_val is not None:
        if isinstance(card_flag_val, str):
            agent_digital_card_enabled = card_flag_val.strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        else:
            agent_digital_card_enabled = bool(card_flag_val)
    else:
        agent_digital_card_enabled = True

    studio_config = get_digital_card_studio_config(use_cache=False)
    studio_config["enabled"] = agent_digital_card_enabled

    card_cfg = profile.get_card_config() if profile else {}
    card_agency_name = (
        card_cfg.get("agency_name") or getattr(profile, "agency_name", "") or ""
    ).strip()
    card_tagline = (
        card_cfg.get("tagline")
        or getattr(profile, "card_tagline", "")
        or studio_config.get("default_card_tagline", "")
        or ""
    ).strip()
    card_banner_css = (
        getattr(
            profile,
            "card_banner_css",
            "linear-gradient(135deg, #0B1F3A 0%, #1E3A8A 50%, #0D9488 100%)",
        )
        if profile
        else "linear-gradient(135deg, #0B1F3A 0%, #1E3A8A 50%, #0D9488 100%)"
    )

    qr_items = []
    if qr_access_for_plan(agent_plan) and slug:
        for qr_type in QR_TYPES:
            if qr_type == "card" and not agent_digital_card_enabled:
                continue
            target = build_qr_target_url(request, agent, qr_type)
            qr_items.append(
                {
                    "type": qr_type,
                    "label": QR_TYPE_LABELS[qr_type],
                    "preview_url": reverse(
                        "agents:agent_qr_image", kwargs={"qr_type": qr_type}
                    ),
                    "download_url": reverse(
                        "agents:agent_qr_download", kwargs={"qr_type": qr_type}
                    ),
                    "public_png_url": reverse(
                        "agents:agent_public_qr_image",
                        kwargs={"slug": slug, "qr_type": qr_type},
                    ),
                    "target_url": target,
                    "whatsapp_url": "https://api.whatsapp.com/send?text="
                    + quote(
                        f"I'm on PadosiAgent. Scan my {QR_TYPE_LABELS[qr_type]}: {target}"
                    ),
                    "facebook_url": "https://www.facebook.com/sharer/sharer.php?u="
                    + quote(target, safe=""),
                }
            )

    # ── Coming Soon features & legacy plan content ──
    _agent_plan_slug = normalize_plan_slug(agent.plan_type or "")
    if _agent_plan_slug in ("starter", "basic"):
        _plan_filter = ["all", "starter"]
        coming_soon_html = SiteSetting.get_value("coming_soon_starter_html", "") or ""
    elif _agent_plan_slug in ("professional", "exclusive", "pro"):
        _plan_filter = ["all", "professional"]
        coming_soon_html = (
            SiteSetting.get_value("coming_soon_professional_html", "") or ""
        )
    else:
        _plan_filter = ["all"]
        coming_soon_html = ""

    try:
        upcoming_features = list(
            UpcomingFeature.objects.filter(
                is_active=True, visible_to__in=_plan_filter
            ).order_by("sort_order", "id")
        )
    except Exception:
        upcoming_features = []

    # ── Referral Championship Context ──
    champ_campaign = None
    champ_participant = None
    champ_is_unlocked = False
    champ_min_profile = 80
    champ_min_reviews = 10
    champ_reviews = agent_review_count(agent)
    champ_completion = completion
    try:
        from apps.referral_championship.models import ChampionshipCampaign
        from apps.referral_championship.services.attribution_service import (
            get_or_create_participant,
        )

        champ_campaign = ChampionshipCampaign.get_current()
        if champ_campaign:
            champ_participant = get_or_create_participant(agent, champ_campaign)
            champ_unlock_cfg = champ_campaign.unlock_config or {
                "min_profile_percent": 80,
                "min_reviews": 10,
            }
            champ_min_profile = int(champ_unlock_cfg.get("min_profile_percent", 80))
            champ_min_reviews = int(champ_unlock_cfg.get("min_reviews", 10))
            from apps.event_referral.services.participant_service import (
                event_referral_bypasses_championship_unlock,
            )

            if event_referral_bypasses_championship_unlock(agent):
                champ_is_unlocked = True
            else:
                champ_is_unlocked = (
                    champ_completion >= champ_min_profile
                    and champ_reviews >= champ_min_reviews
                )
    except Exception as e:
        logger.warning("Referral championship context error: %s", e)

    auto_show_studio = bool(
        request.session.pop("auto_show_invite_studio", False)
        or request.GET.get("show_studio") == "1"
    )

    from apps.agents.services.invite_studio import get_studio_context

    studio_context = get_studio_context(
        request, agent, profile=profile, champ_participant=champ_participant
    )

    from apps.agents.services.plan_upgrade_handoff import dashboard_upgrade_slug

    app_upgrade_plan = dashboard_upgrade_slug(agent, request.GET.get("upgrade"))

    # ── Google Review System Context ──
    from apps.agents.services.google_review import (
        get_google_review_system_config,
        agent_can_use_google_reviews,
        get_agent_google_review_config,
    )

    google_review_sys_cfg = get_google_review_system_config()
    google_review_system_enabled = bool(google_review_sys_cfg.get("enabled", False))
    google_review_eligible = agent_can_use_google_reviews(agent)
    agent_gr_cfg = get_agent_google_review_config(agent)
    agent_gr_reviews = (
        agent_gr_cfg.cached_reviews
        if (agent_gr_cfg and isinstance(agent_gr_cfg.cached_reviews, list))
        else []
    )

    context = {
        **studio_context,
        "google_review_system_enabled": google_review_system_enabled,
        "google_review_eligible": google_review_eligible,
        "agent_gr_cfg": agent_gr_cfg,
        "agent_gr_reviews": agent_gr_reviews,
        "google_review_sys_cfg": google_review_sys_cfg,
        "auto_show_invite_studio": auto_show_studio,
        "champ_campaign": champ_campaign,
        "champ_participant": champ_participant,
        "champ_min_profile": champ_min_profile,
        "champ_min_reviews": champ_min_reviews,
        "champ_is_unlocked": champ_is_unlocked,
        "champ_completion": champ_completion,
        "champ_reviews": champ_reviews,
        "agent_plan": agent_plan,
        "agent": agent,
        "profile": profile,
        "favorite_ids": favorite_ids,
        "dashboardStats": dashboard_stats,
        "recentLeads": recent_leads,
        "allLeads": all_leads,
        "showReferral": show_referral,
        "unreadNotifications": unread_notifications,
        "unread_notifications_json": unread_notifications_json,
        "completion": completion,
        "isOnTrial": is_on_trial,
        "daysLeft": days_left,
        "discountPct": discount_pct,
        "starterFull": starter_full,
        "starterDisc": starter_disc,
        "profFull": prof_full,
        "profDisc": prof_disc,
        "planName": plan_name,
        "feature_unlock_hints_json": feature_unlock_hints_json,
        "qr_service_enabled": qr_access_for_plan(agent_plan),
        "qr_allow_download": qr_access_for_plan(agent_plan, download=True),
        "qr_items": qr_items,
        "agent_digital_card_enabled": agent_digital_card_enabled,
        "studio_config": studio_config,
        "card_config": card_cfg,
        "card_agency_name": card_agency_name,
        "card_tagline": card_tagline,
        "card_banner_css": card_banner_css,
        "card_public_url": reverse("agents:agent_public_card", kwargs={"slug": slug})
        if slug
        else "",
        "card_qr_url": reverse("agents:agent_card_pure_qr", kwargs={"slug": slug})
        if slug
        else "",
        "card_qr_download_url": (
            reverse("agents:agent_card_pure_qr", kwargs={"slug": slug}) + "?download=1"
        )
        if slug
        else "",
        "show_review_share_popup": (
            should_show_popup(agent)
            and not suppress_review_share
            and not (
                event_referral_participant
                and event_referral_participant.status == "active"
            )
        ),
        "show_starter_upgrade_cta": should_show_upgrade_cta(agent),
        "show_starter_upgrade_progress": should_show_upgrade_progress(agent),
        "review_growth_status": growth_status,
        "show_visibility_section": (
            growth_cfg.get("enabled", True)
            and growth_cfg.get("visibility_section_enabled", True)
        ),
        "review_growth": growth_cfg,
        "review_upgrade_price": get_review_upgrade_pricing(agent),
        "review_count_display": agent_review_count(agent),
        "share_profile_url": profile_url,
        "share_text": share_text,
        "share_text_encoded": quote(share_text),
        "share_url_encoded": quote(profile_url, safe=""),
        "fcm_api_key": getattr(settings, "FCM_API_KEY", ""),
        "fcm_auth_domain": getattr(settings, "FCM_AUTH_DOMAIN", ""),
        "fcm_project_id": getattr(settings, "FCM_PROJECT_ID", ""),
        "fcm_storage_bucket": getattr(settings, "FCM_STORAGE_BUCKET", ""),
        "fcm_messaging_sender_id": getattr(settings, "FCM_MESSAGING_SENDER_ID", ""),
        "fcm_app_id": getattr(settings, "FCM_APP_ID", ""),
        "fcm_vapid_key": getattr(settings, "FCM_VAPID_KEY", ""),
        "hide_footer": True,
        "review_unlock_summary": review_unlock_summary,
        "review_milestone_features": review_milestone_features,
        "review_unlock_summary_json": json_dumps(
            review_unlock_summary, ensure_ascii=False
        )
        if review_unlock_summary
        else "null",
        "review_growth_status_json": json_dumps(growth_status, ensure_ascii=False),
        "professional_plan_features": _PROFESSIONAL_PLAN_UI_FEATURES,
        "prof_name": prof_name,
        "prof_desc": prof_desc,
        "prof_base": int(prof_base),
        "prof_disc": int(prof_disc),
        "prof_full": int(prof_full),
        "starter_base": int(starter_base),
        "starter_disc": int(starter_disc),
        "starter_full": int(starter_full),
        "agent_id": agent.id,
        "coming_soon_html": coming_soon_html,
        "upcoming_features": upcoming_features,
        "has_upcoming_features": bool(upcoming_features),
        "event_referral_participant": event_referral_participant,
        "force_lock_all_features": force_lock_all_features,
        "event_referral_share_url": event_referral_share_url,
        "event_referral_whatsapp_url": event_referral_whatsapp_url,
        "event_referral_welcome": event_referral_welcome,
        "event_referral_expired_locked": event_referral_expired_locked,
        "paldi_event_name": "Paldi",
        "app_upgrade_plan": app_upgrade_plan,
        "active_sub": latest_completed_sub,
        "sub_days_left": (
            (latest_completed_sub.expires_at - timezone.now()).days
            if (latest_completed_sub and latest_completed_sub.expires_at)
            else None
        ),
    }

    # ── Wholesale Marketplace Showcase for Agent Dashboard ──
    from apps.wholesale.adapters.auth_bridge import is_wholesale_enabled

    wholesale_enabled = is_wholesale_enabled()

    wholesale_products = []
    wholesale_categories = []
    agent_inquiries = []
    if wholesale_enabled:
        try:
            from apps.wholesale.models.product import WholesaleProduct
            from apps.wholesale.models.category import ProductCategory
            from apps.wholesale.models.inquiry import BuyerInquiry

            wholesale_products = list(
                WholesaleProduct.objects.filter(
                    approval_status="PUBLISHED",
                    wholesaler__verification_status="APPROVED",
                )
                .select_related("wholesaler", "category")
                .prefetch_related("images", "price_tiers", "variants")
                .order_by("-is_featured", "-id")[:30]
            )
            wholesale_categories = list(
                ProductCategory.objects.filter(is_active=True, parent__isnull=True)[:8]
            )
            agent_inquiries = (
                list(
                    BuyerInquiry.objects.filter(buyer_user=request.user)
                    .select_related("product", "wholesaler")
                    .order_by("-created_at")[:15]
                )
                if request.user.is_authenticated
                else []
            )
        except Exception as ws_err:
            logger.warning(
                "Failed to load wholesale products for agent dashboard: %s", ws_err
            )
            agent_inquiries = []

    context["wholesale_enabled"] = wholesale_enabled
    context["wholesale_products"] = wholesale_products
    context["wholesale_categories"] = wholesale_categories
    context["agent_inquiries"] = agent_inquiries

    return render(request, "agents/dashboard.html", context)


@require_POST
@login_required(login_url="agents:agent_login")
@csrf_protect
def update_lead_status(request):
    """
    Handle AJAX request to update the status of a lead for an agent.
    """
    user = request.user
    agent = Agent.objects.filter(user=user).first()
    if not agent:
        return JsonResponse(
            {"status": "error", "message": "Agent not found"}, status=403
        )

    lead_id = request.POST.get("lead_id")
    new_status = request.POST.get("status")

    valid_statuses = ["new", "contacted", "follow_up", "closed"]
    if new_status not in valid_statuses:
        return JsonResponse(
            {"status": "error", "message": "Invalid status provided"}, status=400
        )

    lead = AgentLead.objects.filter(id=lead_id, agent=agent).first()
    if not lead:
        return JsonResponse(
            {"status": "error", "message": "Lead not found or access denied"},
            status=404,
        )

    lead.lead_status = new_status
    lead.save()

    return JsonResponse(
        {
            "status": "success",
            "message": "Lead status updated successfully",
            "new_status": new_status,
        }
    )


@login_required(login_url="agents:agent_login")
def referral(request):
    r"""
    Handle rendering the agent referral milestone page.
    Ported from App\Http\Controllers\Agent\AgentDashboardController@referral
    """
    user = request.user
    agent = Agent.objects.filter(user=user).first()

    if not agent:
        messages.error(request, "Please complete your registration.")
        return redirect("agents:agent_registration")

    # Eligibility check
    referral_config = SiteSetting.get_value(
        "referral_config", {"eligibility": "free_trial_only"}
    )
    show_referral = (
        referral_config.get("eligibility") == "all" or agent.plan_type == "free_trial"
    )

    if not show_referral:
        messages.error(request, "Referral program is not available for your plan.")
        return redirect("agents:agent_dashboard")

    # Load or generate referral code
    ref_code = ReferralCode.objects.filter(agent=agent).first()
    if not ref_code:
        ref_code = ReferralCode.generateForAgent(agent)

    # Sync total_referrals count with actual converted usages
    actual_conversions = ReferralUsage.objects.filter(
        referral_code=ref_code, status="converted"
    ).count()

    if ref_code.total_referrals != actual_conversions:
        ref_code.total_referrals = actual_conversions
        ref_code.save()

    # Calculate pending conversions: agents registered via ref_code.code, but not converted yet
    registered_ids = list(
        Agent.objects.filter(referred_by_code=ref_code.code).values_list(
            "id", flat=True
        )
    )
    converted_ids = list(
        ReferralUsage.objects.filter(
            referral_code=ref_code, status="converted"
        ).values_list("referred_agent_id", flat=True)
    )

    pending_count = len(set(registered_ids) - set(converted_ids))

    current_tier = ref_code.currentTier()
    next_tier = ref_code.nextTier()

    # ── Progress Bar & Tier Calculations ──
    total = int(actual_conversions)
    pending = int(pending_count)

    # Current tier label
    tier_label = "None Yet 🏅"
    if current_tier:
        r = current_tier.get("reward", "")
        if r == "pro_plan_1rs":
            tier_label = "Tier 3: Pro @ ₹1 🥇"
        elif r == "discount_50":
            tier_label = "Tier 2: 50% OFF 🥈"
        elif r == "discount_25":
            tier_label = "Tier 1: 25% OFF 🥉"
        else:
            tier_label = str(r).replace("_", " ").upper()

    # Progress bar calculation
    next_target = next_tier.get("min") if next_tier else None
    if next_target:
        prev = 0 if next_target == 5 else (5 if next_target == 10 else 10)
        raw_pct = (
            round(((total - prev) / (next_target - prev)) * 100)
            if (next_target - prev) > 0
            else 0
        )
        pct = min(100, max(0, raw_pct))
        progress_label = f"{total} / {next_target} conversions"
        next_goal_text = f"{next_target - total} more to unlock next tier!"
    else:
        pct = 100
        progress_label = f"{total} / 15 ✓"
        next_goal_text = "🎉 All tiers unlocked! Claim your reward when upgrading."

    # Build absolute referral join URL
    domain = request.get_host()
    scheme = "https" if request.is_secure() else "http"
    referral_url = f"{scheme}://{domain}/agent-registration/join/{ref_code.code}/"

    # WhatsApp & Email messages construction (with urlencode)
    import urllib.parse

    rocket_enc = "🚀"
    point_enc = "👉"
    rupee_enc = "₹"

    wa_msg_raw = f"{rocket_enc} I've already started my digital growth journey with PadosiAgent and the response is amazing.\n\nNow it's your turn.\n\nAs my contact, you get SPECIAL TRIAL ACCESS just at {rupee_enc}99 for 30 days.\n(No Promo Code required).\n\n{point_enc} Click below & register:\n{referral_url}\n\nOnce you're in, you'll understand why smart agents are shifting online."
    wa_msg = urllib.parse.quote(wa_msg_raw)
    email_sub = urllib.parse.quote(
        "Special Invitation: Join PadosiAgent Digital Growth"
    )
    email_body = wa_msg

    # Load referred usages
    referred_agents = ReferralUsage.objects.filter(referral_code=ref_code).order_by(
        "-signed_up_at"
    )

    # Load registered agents from agents table (referred_by_code)
    all_registered = Agent.objects.filter(referred_by_code=ref_code.code).order_by(
        "-created_at"
    )

    # Pre-process referral details for template rendering
    for referred in all_registered:
        # Find corresponding usage
        usage = referred_agents.filter(referred_agent_id=referred.id).first()
        referred.is_converted = usage and usage.status == "converted"
        referred.converted_date = (
            f" · {usage.converted_at.strftime('%d %b')}"
            if (referred.is_converted and usage.converted_at)
            else ""
        )
        referred.email_display = referred.email or (
            usage.referred_agent_email if usage else "—"
        )

        # plan label configuration
        plan = referred.plan_type or ""
        if plan == "professional":
            referred.plan_label_text = "Professional"
            referred.plan_label_color = "#7c3aed"
            referred.plan_label_bg = "#ede9fe"
        elif plan == "basic":
            referred.plan_label_text = "Starter"
            referred.plan_label_color = "#2563eb"
            referred.plan_label_bg = "#dbeafe"
        elif plan == "free_trial":
            referred.plan_label_text = "Free Trial"
            referred.plan_label_color = "#f59e0b"
            referred.plan_label_bg = "#fef3c7"
        else:
            referred.plan_label_text = plan.title() if plan else "—"
            referred.plan_label_color = "#64748b"
            referred.plan_label_bg = "#f1f5f9"

        # status map configuration
        status = referred.status or ""
        if status == "active":
            referred.status_text = "Active"
            referred.status_color = "#15803d"
            referred.status_bg = "#dcfce7"
        elif status == "pending_approval":
            referred.status_text = "Pending Approval"
            referred.status_color = "#b45309"
            referred.status_bg = "#fef3c7"
        elif status == "pending_payment":
            referred.status_text = "Pending Payment"
            referred.status_color = "#1d4ed8"
            referred.status_bg = "#dbeafe"
        elif status == "inactive":
            referred.status_text = "Inactive"
            referred.status_color = "#94a3b8"
            referred.status_bg = "#f1f5f9"
        else:
            referred.status_text = status.title() if status else "—"
            referred.status_color = "#64748b"
            referred.status_bg = "#f1f5f9"

    context = {
        "agent": agent,
        "refCode": ref_code,
        "actualConversions": actual_conversions,
        "pendingCount": pending_count,
        "currentTier": current_tier,
        "nextTier": next_tier,
        "referralUrl": referral_url,
        "referredAgents": referred_agents,
        "allRegistered": all_registered,
        "total": total,
        "pending": pending,
        "tierLabel": tier_label,
        "nextTarget": next_target,
        "pct": pct,
        "progressLabel": progress_label,
        "nextGoalText": next_goal_text,
        "waMsg": wa_msg,
        "emailSub": email_sub,
        "emailBody": email_body,
        "hide_footer": True,
    }

    return render(request, "agents/referral.html", context)


