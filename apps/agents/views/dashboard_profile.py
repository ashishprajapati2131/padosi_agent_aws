"""Agent profile editing (split out of dashboard.py): edit/update views, the shared
apply_profile_update() used by the admin panel, and the profile edit audit log."""

from apps.agents.models import Agent
from apps.agents.services.feature_unlock import (
    PLAN_LABELS,
    build_unlock_hints,
    normalize_plan_slug,
    plan_shows_feature,
)
from apps.agents.utils.file_validation import (
    validate_license_document,
    validate_magic_bytes,
)
from apps.home.models import SiteSetting
from django.contrib import messages
from django.shortcuts import (
    redirect,
    render,
)
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from json import dumps as json_dumps
from apps.agents.views.dashboard_common import _resolve_agent_plan, logger


@never_cache
def edit_profile(request):
    if not request.user.is_authenticated:
        return redirect("agents:agent_login")

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        messages.error(request, "Please complete your registration.")
        return redirect("agents:agent_registration")

    return render_edit_profile(request, agent, is_admin_view=False)


def render_edit_profile(request, agent, is_admin_view=False):
    from apps.agents.models import AgentProfile

    profile, _ = AgentProfile.objects.get_or_create(agent=agent)

    # Load serviceable cities
    agent_cities = list(agent.serviceableCities.values_list("name", flat=True))

    main_cities = sorted(
        list(
            set(
                [
                    "Ahmedabad",
                    "Mumbai",
                    "Delhi",
                    "Bangalore",
                    "Hyderabad",
                    "Chennai",
                    "Kolkata",
                    "Pune",
                    "Surat",
                    "Jaipur",
                    "Lucknow",
                    "Kanpur",
                    "Nagpur",
                    "Indore",
                    "Thane",
                    "Bhopal",
                    "Visakhapatnam",
                    "Pimpri-Chinchwad",
                    "Patna",
                    "Vadodara",
                    "Ghaziabad",
                    "Ludhiana",
                    "Coimbatore",
                    "Agra",
                    "Madurai",
                    "Nashik",
                    "Vijayawada",
                    "Faridabad",
                    "Meerut",
                    "Rajkot",
                    "Kalyan-Dombivli",
                    "Vasai-Virar",
                    "Varanasi",
                    "Srinagar",
                    "Aurangabad",
                    "Dhanbad",
                    "Amritsar",
                    "Navi Mumbai",
                    "Allahabad",
                    "Howrah",
                    "Ranchi",
                    "Gwalior",
                    "Jabalpur",
                    "Jodhpur",
                    "Raipur",
                    "Chandigarh",
                    "Guntur",
                    "Guwahati",
                    "Solapur",
                    "Noida",
                    "Mysuru",
                    "Gurgaon",
                    "Bhubaneswar",
                    "Thiruvananthapuram",
                    "Dehradun",
                    "Jammu",
                    "Jamnagar",
                    "Ujjain",
                    "Jhansi",
                    "Kochi",
                    "Mangalore",
                    "Udaipur",
                    "Ajmer",
                    "Tiruppur",
                    "Nellore",
                    "Kurnool",
                    "Gaya",
                    "Hoshiarpur",
                    "Muzaffarpur",
                    "Vellore",
                    "Shimla",
                    "Rohtak",
                    "Ambala",
                    "Gandhinagar",
                    "Pondicherry",
                    "Siliguri",
                    "Raurkela",
                    "Durgapur",
                    "Asansol",
                ]
            )
        )
    )

    extra_cities = [c for c in agent_cities if c not in main_cities]

    import datetime

    current_year = datetime.datetime.now().year
    years_range = list(range(current_year, 1979, -1))
    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    from apps.agents.models import InvestmentType

    investment_types = InvestmentType.objects.filter(is_active=True)

    logged_in_admin = None
    is_super_admin = False
    admin_permissions = []

    if is_admin_view:
        from apps.admin_panel.auth import _get_admin_from_session
        admin_session_id = _get_admin_from_session(request)
        if admin_session_id:
            from apps.admin_panel.models.admin_auth import Admin

            logged_in_admin = Admin.objects.filter(id=admin_session_id).first()
            if logged_in_admin:
                is_super_admin = logged_in_admin.role == "super"
                raw_perms = logged_in_admin.permissions
                admin_permissions = raw_perms if isinstance(raw_perms, list) else []

    force_lock_all_features = False
    event_referral_expired_locked = False
    edit_plan_type = agent.plan_type
    if not is_admin_view:
        try:
            from apps.event_referral.services.participant_service import (
                event_referral_effective_plan_type,
                prepare_event_referral_portal_state,
            )

            _evt_participant, force_lock_all_features, event_referral_expired_locked = (
                prepare_event_referral_portal_state(agent)
            )
            agent.refresh_from_db()
            if _evt_participant and not force_lock_all_features:
                _evt_plan = event_referral_effective_plan_type(agent, _evt_participant)
                if _evt_plan:
                    edit_plan_type = _evt_plan
        except Exception:
            pass

    # Resolve SubscriptionPlan using robust multi-tier helper
    agent_plan = _resolve_agent_plan(edit_plan_type, agent=agent)

    feature_unlock_hints = build_unlock_hints(
        agent, normalize_plan_slug(edit_plan_type or agent.plan_type)
    )
    review_growth_status_json = "{}"
    show_starter_upgrade_cta = False
    show_starter_upgrade_progress = False
    if not is_admin_view:
        from apps.agents.services.review_growth import (
            build_review_growth_hints,
            get_review_growth_status,
            get_review_upgrade_pricing,
            should_show_upgrade_cta,
            should_show_upgrade_progress,
        )
        from apps.agents.views.registration import _PROFESSIONAL_PLAN_UI_FEATURES

        feature_unlock_hints.update(build_review_growth_hints(agent))
        growth_status = get_review_growth_status(agent)
        review_growth_status_json = json_dumps(growth_status, ensure_ascii=False)
        show_starter_upgrade_cta = should_show_upgrade_cta(agent)
        show_starter_upgrade_progress = should_show_upgrade_progress(agent)
        review_upgrade_price = get_review_upgrade_pricing(agent)
        pricing_config = SiteSetting.get_value(
            "pricing_config",
            {
                "professional": {
                    "name": PLAN_LABELS["professional"],
                    "full_price": 9999,
                },
            },
        )
        prof_cfg = pricing_config.get("professional", {})
        prof_name = PLAN_LABELS["professional"]
        prof_desc = prof_cfg.get(
            "description", "Maximum visibility and premium tools for top agents."
        )
        # full_price is the BASE price excl. GST
        prof_base_price = float(prof_cfg.get("full_price", 9999))
        prof_base = int(round(prof_base_price))
        prof_full = int(round(prof_base_price + prof_base_price * 0.18))
        professional_plan_features = _PROFESSIONAL_PLAN_UI_FEATURES
    else:
        review_upgrade_price = None
        professional_plan_features = []
        prof_name = prof_desc = ""
        prof_base = prof_full = 0

    from apps.agents.models import ProfileBannerPreset

    banner_presets = ProfileBannerPreset.objects.filter(is_active=True).order_by(
        "display_order", "-created_at"
    )
    banner_enabled_val = SiteSetting.get_value("profile_banner_enabled", "1")
    banner_feature_enabled = str(banner_enabled_val).lower() in ("1", "true", "yes")
    allow_custom_val = SiteSetting.get_value("profile_banner_allow_custom_upload", "1")
    banner_allow_custom_upload = str(allow_custom_val).lower() in ("1", "true", "yes")

    context = {
        "banner_presets": banner_presets,
        "banner_feature_enabled": banner_feature_enabled,
        "banner_allow_custom_upload": banner_allow_custom_upload,
        "agent_plan": agent_plan,
        "agent": agent,
        "profile": profile,
        "isAdminView": is_admin_view,
        "logged_in_admin": logged_in_admin,
        "is_super_admin": is_super_admin,
        "admin_permissions": admin_permissions,
        "base_template": "admin/base.html" if is_admin_view else "base.html",
        "main_cities": main_cities,
        "agent_cities": agent_cities,
        "extra_cities": extra_cities,
        "years_range": years_range,
        "months": months,
        "active_investment_types": investment_types,
        "feature_unlock_hints_json": json_dumps(
            feature_unlock_hints, ensure_ascii=False
        ),
        "show_starter_upgrade_cta": show_starter_upgrade_cta,
        "show_starter_upgrade_progress": show_starter_upgrade_progress,
        "review_growth_status_json": review_growth_status_json,
        "hide_footer": not is_admin_view,
        "review_upgrade_price": review_upgrade_price if not is_admin_view else None,
        "professional_plan_features": professional_plan_features,
        "prof_name": prof_name if not is_admin_view else "",
        "prof_desc": prof_desc if not is_admin_view else "",
        "prof_base": prof_base if not is_admin_view else 0,
        "prof_full": int(prof_full) if not is_admin_view else 0,
        "agent_id": agent.id,
        "force_lock_all_features": force_lock_all_features,
        "event_referral_expired_locked": event_referral_expired_locked,
    }
    return render(request, "agents/edit_profile.html", context)


@require_POST
@never_cache
def update_profile(request):
    from django.http import JsonResponse

    if not request.user.is_authenticated:
        return JsonResponse(
            {"status": "error", "message": "Authentication required"}, status=401
        )

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        return JsonResponse(
            {"status": "error", "message": "Agent not found"}, status=404
        )

    from apps.event_referral.services.participant_service import (
        prepare_event_referral_portal_state,
    )

    _, force_lock, _ = prepare_event_referral_portal_state(agent)
    if force_lock:
        return JsonResponse(
            {
                "status": "error",
                "message": "Your 48-hour challenge has ended. Upgrade your plan to edit your profile.",
                "redirect": reverse("agents:chooseplan"),
            },
            status=403,
        )

    return apply_profile_update(request, agent, is_admin_edit=False)


def _email_taken_by_other_login(email, agent):
    """True if another auth_user / users row already owns this email."""
    from django.contrib.auth.models import User as DjangoUser
    from apps.agents.services.account_auth import fetch_users_row

    new = (email or "").strip().lower()
    current = (agent.email or "").strip().lower()
    if not new or new == current:
        return False
    if DjangoUser.objects.filter(email__iexact=new).exclude(pk=agent.user_id).exists():
        return True
    return fetch_users_row(email=new) is not None


def _collect_license_uploads(request):
    """Read IRDAI and AMFI certificates before any profile write.

    The upload controls live on professional details (step 2). The wizard never
    posts step 5, which is the only place these files used to be stored, so a
    new certificate looked selected and then disappeared on refresh.
    """
    from django.http import JsonResponse

    payloads = []
    specs = (
        ("irdai", "irdai_license_doc", "IRDAI certificate"),
        ("amfi", "amfi_license_doc", "AMFI certificate"),
    )
    for kind, field, label in specs:
        upload = request.FILES.get(field)
        if not upload:
            continue
        content = b""
        too_big = False
        for chunk in upload.chunks():
            content += chunk
            if len(content) > 5 * 1024 * 1024:
                too_big = True
                break
        if too_big:
            return None, JsonResponse(
                {
                    "status": "error",
                    "message": f"{label} file size must be under 5MB.",
                    "errors": {field: ["File size must be under 5MB."]},
                },
                status=422,
            )
        ok, err, ext = validate_license_document(content, upload.name)
        if not ok:
            return None, JsonResponse(
                {
                    "status": "error",
                    "message": f"Invalid file type for {label}: {err}",
                    "errors": {field: [err]},
                },
                status=422,
            )
        payloads.append((field, content, ext, kind))
    return payloads, None


# Backend current_step -> edit-profile section (the page posts visual steps 1-5 as 1, 2, 4, 5, 7).
_EDIT_LOG_STEP_LABELS = {
    1: "Basic Info",
    2: "Professional Details",
    3: "Portfolio & Segments",
    4: "Portfolio & Segments",
    5: "Additional Info",
    6: "Lead Preferences",
    7: "Final Submission",
}


def _profile_edit_snapshot(agent, profile):
    """Readable {field: value} of everything the edit-profile sections save, for the admin diff."""
    from apps.agents.models import AgentPerformanceStat, AgentLeadPreference
    from apps.agents.services.profile_edit_log import (
        FIELDS,
        snapshot_value,
        child_snapshot,
    )

    snap = {"status": agent.status}
    columns = {
        "": (agent, {f.name for f in agent._meta.concrete_fields}),
        "profile.": (profile, {f.name for f in profile._meta.concrete_fields}),
    }
    for key in FIELDS:
        prefix, name = (
            ("profile.", key[8:]) if key.startswith("profile.") else ("", key)
        )
        obj, names = columns[prefix]
        if name in names:
            snap[key] = snapshot_value(getattr(obj, name))
    # Child tables are replaced wholesale on save; row columns follow CHILD_FORMATS.
    snap.update(
        child_snapshot(
            {
                "insurance_segments": agent.insuranceSegments.values_list(
                    "segment_type"
                ),
                "serviceable_cities": agent.serviceableCities.values_list("name"),
                "service_areas": agent.servicePincodes.values_list(
                    "service_pincode", "city_name", "selected_areas_json"
                ),
                "product_expertise": agent.productExpertise.values_list(
                    "segment_type", "product_name", "expertise_level"
                ),
                "family_licenses": agent.familyLicenses.values_list(
                    "full_name", "relationship", "license_number"
                ),
                "portfolios": agent.portfolios.values_list(
                    "segment_type", "primary_companies", "secondary_companies"
                ),
                "performance_stats": AgentPerformanceStat.objects.filter(
                    agent=agent
                ).values_list(
                    "claims_processed",
                    "claims_settled",
                    "claims_amount",
                    "response_time",
                ),
                "lead_preferences": AgentLeadPreference.objects.filter(
                    agent=agent
                ).values_list(
                    "leads_new_business",
                    "leads_portfolio_analysis",
                    "portfolio_charging",
                    "portfolio_fee",
                    "leads_claims_support",
                    "claims_charging",
                    "claims_fee_amount",
                    "claims_percent",
                ),
                "achievement_photos": agent.achievementPhotos.values_list("photo_path"),
                "career_timeline": agent.careerTimelines.values_list(
                    "month", "year", "event_type", "event_text"
                ),
            }
        )
    )
    return snap


def _log_profile_edit(request, agent, before, after, current_step, is_admin_edit):
    from apps.agents.models import AgentProfileEditLog
    from apps.admin_panel.middleware import ThreatMonitorMiddleware
    from apps.agents.services.profile_edit_log import build_changes

    changes = build_changes(before, after)
    status_before, status_after = before.get("status"), after.get("status")
    if not changes and status_before == status_after:
        return
    step = int(current_step) if str(current_step or "").isdigit() else None
    AgentProfileEditLog.objects.create(
        agent_id=agent.id,
        edited_by="admin" if is_admin_edit else "agent",
        edited_by_id=request.session.get("admin_id") if is_admin_edit else agent.id,
        # step must be set: get_edit_logs treats admin rows with step=None as approval boundaries
        step=step or 7,
        step_label=_EDIT_LOG_STEP_LABELS.get(step, "Profile Edit"),
        changes=changes,
        ip_address=ThreatMonitorMiddleware.get_client_ip(request),
        status_before=status_before,
        status_after=status_after,
    )

    try:
        from apps.event_referral.models import TrialAgentActivityLog
        step_name = _EDIT_LOG_STEP_LABELS.get(step, "Profile Edit")
        changed_keys = list(changes.keys()) if isinstance(changes, dict) else []
        summary = f"Updated: {', '.join(changed_keys[:5])}" if changed_keys else "Profile saved"
        TrialAgentActivityLog.log(
            agent=agent,
            activity_type=TrialAgentActivityLog.ACTIVITY_PROFILE_EDIT,
            title=f"Profile Edited ({step_name})",
            description=summary,
            details={
                "step": step or 7,
                "step_label": step_name,
                "edited_by": "admin" if is_admin_edit else "agent",
                "changed_fields": changed_keys,
                "changes": {
                    k: {
                        "before": str(v.get("before", ""))[:120],
                        "after": str(v.get("after", ""))[:120],
                    }
                    for k, v in list(changes.items())[:12]
                } if isinstance(changes, dict) else {},
            },
            request=request,
        )
    except Exception as e:
        logger.warning("Trial profile edit log failed: %s", e)



def apply_profile_update(request, agent, is_admin_edit=False):
    from django.http import JsonResponse
    from django.db import transaction
    from django.core.files.storage import default_storage
    from apps.agents.models import (
        Agent,
        AgentProfile,
        AgentPerformanceStat,
        AgentFamilyLicense,
        AgentInsuranceSegment,
        AgentProductExpertise,
        AgentPortfolio,
        AgentAchievementPhoto,
        AgentCareerTimeline,
        AgentLeadPreference,
        City,
    )
    import re
    import os
    import time
    import uuid

    profile, _ = AgentProfile.objects.get_or_create(agent=agent)
    edit_snapshot_before = _profile_edit_snapshot(agent, profile)
    current_step = request.POST.get("current_step")
    license_payloads, license_error = _collect_license_uploads(request)
    if license_error:
        return license_error

    # helper for step processing
    def should_process(step):
        return not current_step or str(current_step) == str(step)

    try:
        with transaction.atomic():
            # ── Step 1: Basic Info ──
            if should_process(1):
                full_name = (request.POST.get("full_name") or "").strip()
                email = (request.POST.get("email") or "").strip()
                mobile = (request.POST.get("mobile") or "").strip()
                display_name = (request.POST.get("display_name") or "").strip()
                whatsapp = (request.POST.get("whatsapp") or "").strip()
                languages = (request.POST.get("languages") or "").strip()
                address = (request.POST.get("address") or "").strip()
                date_of_birth = request.POST.get("date_of_birth")

                # Basic validation
                errors = {}
                from django.core.validators import validate_email
                from django.core.exceptions import ValidationError

                if not full_name:
                    errors["full_name"] = ["The full name field is required."]
                elif len(full_name) > 255:
                    errors["full_name"] = ["Full name cannot exceed 255 characters."]
                elif re.search(r"[<>]", full_name):
                    errors["full_name"] = ["Full name contains invalid characters."]
                if display_name and re.search(r"[<>]", display_name):
                    errors["display_name"] = [
                        "Display name contains invalid characters."
                    ]

                if is_admin_edit:
                    if not email:
                        errors["email"] = ["The email field is required."]
                    else:
                        try:
                            validate_email(email)
                            if (
                                Agent.objects.filter(email__iexact=email)
                                .exclude(id=agent.id)
                                .exists()
                            ):
                                errors["email"] = ["The email has already been taken."]
                            elif _email_taken_by_other_login(email, agent):
                                # Login resolves accounts by email across auth_user and
                                # users; taking a staff/insurance/distributor address
                                # let an agent log in as (and overwrite) that account.
                                errors["email"] = ["The email has already been taken."]
                        except ValidationError:
                            errors["email"] = ["Enter a valid email address."]
                else:
                    # The login email is fixed. A posted value is ignored so the
                    # rest of the profile can still be saved.
                    email = (agent.email or "").strip()

                if not mobile:
                    errors["mobile"] = ["The mobile field is required."]
                elif not mobile.isdigit() or len(mobile) < 10 or len(mobile) > 15:
                    errors["mobile"] = ["Enter a valid mobile number (10-15 digits)."]

                if display_name and len(display_name) > 255:
                    errors["display_name"] = [
                        "Display name cannot exceed 255 characters."
                    ]

                if whatsapp and (
                    not whatsapp.isdigit() or len(whatsapp) < 10 or len(whatsapp) > 20
                ):
                    errors["whatsapp"] = ["Enter a valid WhatsApp number."]

                if not languages:
                    errors["languages"] = ["The languages field is required."]
                elif len(languages) > 255:
                    errors["languages"] = [
                        "Languages field cannot exceed 255 characters."
                    ]

                if not address:
                    errors["address"] = ["The address field is required."]
                elif len(address) > 155:
                    errors["address"] = ["Address cannot exceed 155 characters."]

                if errors:
                    transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                    return JsonResponse(
                        {
                            "status": "error",
                            "message": "Validation failed",
                            "errors": errors,
                        },
                        status=422,
                    )

                agent.fullname = full_name
                if is_admin_edit:
                    previous_email = agent.email
                    agent.email = email
                agent.mobile = mobile

                # User types (Optional)
                user_types = request.POST.getlist(
                    "user_types[]"
                ) or request.POST.getlist("user_types")
                if user_types:
                    agent.user_types = user_types

                # Admin values
                if is_admin_edit:
                    badge_data = request.POST.getlist(
                        "badge[]"
                    ) or request.POST.getlist("badge")
                    agent.badge = ",".join(filter(None, badge_data))
                    if request.POST.get("status"):
                        agent.status = request.POST.get("status")

                agent.save()

                # Login reads `users`/`auth_user` by email. Only an admin edit may
                # move that address; an agent save leaves it unchanged.
                if is_admin_edit:
                    from apps.agents.services.account_auth import (
                        sync_agent_email_change,
                    )

                    sync_agent_email_change(previous_email, email, full_name)

                profile.display_name = display_name
                profile.whatsapp = whatsapp
                profile.languages = languages
                profile.address = address
                if date_of_birth:
                    profile.date_of_birth = date_of_birth
                else:
                    profile.date_of_birth = None

                # Profile Photo upload
                profile_photo = request.FILES.get("profile_photo")
                if profile_photo:
                    from django.core.files.base import ContentFile
                    from apps.agents.utils.file_validation import validate_profile_photo

                    photo_bytes = b"".join(profile_photo.chunks())
                    ok, photo_error, safe_ext = validate_profile_photo(
                        photo_bytes,
                        profile_photo.name,
                    )
                    if ok:
                        file_name = f"app/public/profile/agent_{agent.id}_{int(time.time())}{safe_ext}"
                        saved_path = default_storage.save(
                            file_name,
                            ContentFile(photo_bytes),
                        )
                        profile.profile_photo_path = saved_path
                    elif photo_error:
                        transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                        return JsonResponse(
                            {
                                "status": "error",
                                "message": "Validation failed",
                                "errors": {"profile_photo": [photo_error]},
                            },
                            status=422,
                        )

                # Banner handling: presets, custom upload, or reset
                remove_banner = request.POST.get("remove_banner") == "1"
                banner_preset_id = request.POST.get("banner_preset_id")
                custom_banner = request.FILES.get("custom_banner")

                from apps.home.models.site_setting import SiteSetting
                from apps.agents.models import ProfileBannerPreset

                banner_enabled_val = SiteSetting.get_value(
                    "profile_banner_enabled", "1"
                )
                banner_feature_enabled = str(banner_enabled_val).lower() in (
                    "1",
                    "true",
                    "yes",
                )
                allow_custom_val = SiteSetting.get_value(
                    "profile_banner_allow_custom_upload", "1"
                )
                banner_allow_custom_upload = str(allow_custom_val).lower() in (
                    "1",
                    "true",
                    "yes",
                )

                if banner_feature_enabled:

                    def _cleanup_old_custom_banner():
                        if profile.custom_banner_path:
                            try:
                                if default_storage.exists(profile.custom_banner_path):
                                    default_storage.delete(profile.custom_banner_path)
                            except Exception:
                                pass

                    if remove_banner:
                        _cleanup_old_custom_banner()
                        profile.banner_preset = None
                        profile.custom_banner_path = None
                    elif custom_banner:
                        if not banner_allow_custom_upload:
                            transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                            return JsonResponse(
                                {
                                    "status": "error",
                                    "message": "Custom banner uploads are currently disabled by administrator.",
                                    "errors": {
                                        "custom_banner": [
                                            "Custom banner uploads are currently disabled."
                                        ]
                                    },
                                },
                                status=403,
                            )

                        from apps.agents.utils.file_validation import (
                            validate_profile_photo,
                        )
                        from django.core.files.base import ContentFile

                        banner_bytes = b"".join(custom_banner.chunks())
                        ok, banner_err, safe_ext = validate_profile_photo(
                            banner_bytes, custom_banner.name
                        )
                        if ok:
                            _cleanup_old_custom_banner()
                            banner_name = f"banners/custom/agent_{agent.id}_{int(time.time())}{safe_ext}"
                            saved_banner_path = default_storage.save(
                                banner_name, ContentFile(banner_bytes)
                            )
                            profile.custom_banner_path = saved_banner_path
                            profile.banner_preset = None
                        elif banner_err:
                            transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                            return JsonResponse(
                                {
                                    "status": "error",
                                    "message": "Validation failed",
                                    "errors": {"custom_banner": [banner_err]},
                                },
                                status=422,
                            )
                    elif banner_preset_id:
                        try:
                            if str(banner_preset_id).isdigit():
                                preset_obj = ProfileBannerPreset.objects.filter(
                                    id=int(banner_preset_id), is_active=True
                                ).first()
                                if preset_obj:
                                    _cleanup_old_custom_banner()
                                    profile.banner_preset = preset_obj
                                    profile.custom_banner_path = None
                        except Exception:
                            pass

                profile.save()

            # ── Step 2: Professional Details ──
            if should_process(2):
                pan = (request.POST.get("pan") or "").strip()
                agency_name = (request.POST.get("agency_name") or "").strip()
                office_address = (request.POST.get("office_address") or "").strip()
                service_pincode = (request.POST.get("service_pincode") or "").strip()
                # Default to '0' so the field is NOT silently cleared when the
                # radio button is untouched (unchecked radio sends nothing in POST).
                has_pos_license = request.POST.get("has_pos_license", "0") == "1"
                experience_years = (request.POST.get("experience_years") or "").strip()
                client_base = (request.POST.get("client_base") or "").strip()

                # Validation
                errors = {}
                import re

                if pan and not re.match(
                    r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", pan, re.IGNORECASE
                ):
                    errors["pan"] = ["Enter a valid PAN number."]
                elif pan and len(pan) > 20:
                    errors["pan"] = ["PAN number cannot exceed 20 characters."]

                if agency_name and len(agency_name) > 255:
                    errors["agency_name"] = [
                        "Agency name cannot exceed 255 characters."
                    ]

                if office_address and len(office_address) > 255:
                    errors["office_address"] = [
                        "Office address cannot exceed 255 characters."
                    ]

                if not service_pincode:
                    errors["service_pincode"] = [
                        "The service pincode field is required."
                    ]
                elif not re.match(r"^[1-9][0-9]{5}$", service_pincode):
                    errors["service_pincode"] = ["Enter a valid 6-digit PIN code."]

                if not experience_years:
                    errors["experience_years"] = ["The experience field is required."]
                elif len(experience_years) > 50:
                    errors["experience_years"] = [
                        "Experience field cannot exceed 50 characters."
                    ]

                if not client_base:
                    errors["client_base"] = ["The client base field is required."]
                elif len(client_base) > 50:
                    errors["client_base"] = ["Client base cannot exceed 50 characters."]

                serviceable_cities_data = request.POST.getlist(
                    "serviceable_cities[]"
                ) or request.POST.getlist("serviceable_cities")
                if not serviceable_cities_data:
                    errors["serviceable_cities"] = [
                        "The serviceable cities field is required."
                    ]

                if errors:
                    transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                    return JsonResponse(
                        {
                            "status": "error",
                            "message": "Validation failed",
                            "errors": errors,
                        },
                        status=422,
                    )

                profile.pan_number = pan
                profile.agency_name = agency_name
                profile.office_address = office_address
                profile.service_pincode = service_pincode
                profile.has_pos_license = has_pos_license

                license_valid_till = request.POST.get("license_valid_till")
                if license_valid_till:
                    profile.license_valid_till = license_valid_till
                else:
                    profile.license_valid_till = None

                profile.arn_number = request.POST.get("arn_number", "").strip()
                profile.euin_number = request.POST.get("euin_number", "").strip()

                investment_valid_till = request.POST.get("investment_valid_till")
                if investment_valid_till:
                    profile.investment_valid_till = investment_valid_till
                else:
                    profile.investment_valid_till = None

                if is_admin_edit and request.POST.get("license_number"):
                    profile.license_number = request.POST.get("license_number")

                profile.save()

                agent.experience_range = experience_years
                agent.client_base = client_base

                insurance_companies = request.POST.getlist(
                    "insurance_companies[]"
                ) or request.POST.getlist("insurance_companies")
                if insurance_companies:
                    agent.insurance_companies = insurance_companies

                agent.save()

                # Family Licenses
                agent.familyLicenses.all().delete()
                family_indices = set()
                for key in request.POST.keys():
                    match = re.match(r"family_members\[(\d+)\]\[name\]", key)
                    if match:
                        family_indices.add(int(match.group(1)))

                for idx in sorted(family_indices):
                    name = request.POST.get(f"family_members[{idx}][name]", "").strip()
                    relationship = request.POST.get(
                        f"family_members[{idx}][relationship]", ""
                    ).strip()
                    license_num = request.POST.get(
                        f"family_members[{idx}][license]", ""
                    ).strip()
                    if name:
                        AgentFamilyLicense.objects.create(
                            agent=agent,
                            full_name=name,
                            relationship=relationship,
                            license_number=license_num,
                        )

                # Performance Stats
                claims_processed = int(request.POST.get("claims_processed") or 0)
                claims_settled = int(request.POST.get("claims_settled") or 0)
                claims_amount = float(request.POST.get("claims_amount") or 0.0)
                response_time = int(request.POST.get("response_time") or 2)
                success_rate = (
                    round((claims_settled / claims_processed) * 100, 2)
                    if claims_processed > 0
                    else 0.0
                )

                AgentPerformanceStat.objects.update_or_create(
                    agent=agent,
                    defaults={
                        "claims_processed": claims_processed,
                        "claims_settled": claims_settled,
                        "claims_amount": claims_amount,
                        "success_rate": success_rate,
                        "response_time": response_time,
                    },
                )

                # Serviceable Cities
                city_ids = []
                for city_name in serviceable_cities_data:
                    city, _ = City.objects.get_or_create(
                        name=city_name,
                        defaults={
                            "slug": re.sub(r"[^a-zA-Z0-9]", "-", city_name).lower(),
                            "is_active": True,
                        },
                    )
                    city_ids.append(city.id)
                agent.serviceableCities.set(city_ids)

            # ── Step 3: Insurance Segments ──
            if should_process(3):
                segments = request.POST.getlist("segments[]") or request.POST.getlist(
                    "segments"
                )

                agent.insuranceSegments.all().delete()
                for segment_type in segments:
                    AgentInsuranceSegment.objects.create(
                        agent=agent, segment_type=segment_type
                    )

                investment_types = request.POST.getlist(
                    "investment_types[]"
                ) or request.POST.getlist("investment_types")
                profile.investment_types = investment_types
                profile.save()

                # Product expertise ratings
                agent.productExpertise.all().delete()
                for key, value in request.POST.items():
                    match = re.match(r"expertise\[([^\]]+)\]\[([^\]]+)\]", key)
                    if match:
                        segment = match.group(1)
                        product = match.group(2)
                        try:
                            level = int(value)
                            if level > 0:
                                is_custom = (
                                    request.POST.get(
                                        f"custom_products[{segment}][{product}]"
                                    )
                                    == "1"
                                )
                                AgentProductExpertise.objects.create(
                                    agent=agent,
                                    segment_type=segment,
                                    product_name=product,
                                    expertise_level=level,
                                    is_custom=is_custom,
                                )
                        except ValueError:
                            pass

            # ── Step 4: Portfolios ──
            if should_process(4):
                # Always sync segments on step 4 even if empty, so unselecting all works
                segments = request.POST.getlist("segments[]") or request.POST.getlist(
                    "segments"
                )
                if (
                    "segments[]" in request.POST
                    or "segments" in request.POST
                    or str(current_step) == "4"
                ):
                    agent.insuranceSegments.all().delete()
                    for segment_type in segments:
                        AgentInsuranceSegment.objects.create(
                            agent=agent, segment_type=segment_type
                        )

                investment_types = request.POST.getlist(
                    "investment_types[]"
                ) or request.POST.getlist("investment_types")
                if (
                    "investment_types[]" in request.POST
                    or "investment_types" in request.POST
                    or str(current_step) == "4"
                ):
                    profile.investment_types = investment_types
                    profile.save()

                portfolio_data = {}
                for key in request.POST.keys():
                    match = re.match(r"portfolio\[([^\]]+)\]\[([^\]]+)\]", key)
                    if match:
                        segment = match.group(1)
                        field = match.group(2)
                        if segment not in portfolio_data:
                            portfolio_data[segment] = {}
                        if field != "companies_extra":
                            portfolio_data[segment][field] = request.POST.get(key)

                for key in request.POST.keys():
                    match = re.match(
                        r"portfolio\[([^\]]+)\]\[companies_extra\]\[(\d+)\]\[(name|percent)\]",
                        key,
                    )
                    if match:
                        segment = match.group(1)
                        idx = int(match.group(2))
                        field = match.group(3)

                        if segment not in portfolio_data:
                            portfolio_data[segment] = {}
                        if "companies_extra" not in portfolio_data[segment]:
                            portfolio_data[segment]["companies_extra"] = {}
                        if idx not in portfolio_data[segment]["companies_extra"]:
                            portfolio_data[segment]["companies_extra"][idx] = {}

                        portfolio_data[segment]["companies_extra"][idx][field] = (
                            request.POST.get(key)
                        )

                agent.portfolios.all().delete()
                for segment_type, data in portfolio_data.items():
                    primary_name = (data.get("primary_company") or "").strip()
                    primary_percent = (data.get("primary_percent") or "").strip()
                    secondary_name = (data.get("secondary_company") or "").strip()
                    secondary_percent = (data.get("secondary_percent") or "").strip()
                    other_companies = (data.get("other_companies") or "").strip()

                    if primary_name:
                        # Construct companies extra list
                        extra_list = []
                        if "companies_extra" in data:
                            for idx, comp in data["companies_extra"].items():
                                cname = (comp.get("name") or "").strip()
                                cpercent = (comp.get("percent") or "").strip()
                                if cname:
                                    extra_list.append(
                                        {"name": cname, "percent": cpercent}
                                    )

                        all_companies = [
                            {"name": primary_name, "percent": primary_percent}
                        ]
                        if secondary_name:
                            all_companies.append(
                                {"name": secondary_name, "percent": secondary_percent}
                            )
                        all_companies.extend(extra_list)

                        AgentPortfolio.objects.create(
                            agent=agent,
                            segment_type=segment_type,
                            primary_companies={
                                "name": primary_name,
                                "percentage": primary_percent,
                            },
                            secondary_companies={
                                "name": secondary_name,
                                "percentage": secondary_percent,
                                "others": other_companies,
                                "companies": all_companies,
                            },
                        )

            # ── Step 5: Additional Info ──
            if should_process(5):
                website = (request.POST.get("website") or "").strip()
                google_business = (request.POST.get("google_business") or "").strip()
                linkedin = (request.POST.get("linkedin_url") or "").strip()
                instagram = (request.POST.get("instagram_url") or "").strip()
                facebook = (request.POST.get("facebook_url") or "").strip()
                youtube = (request.POST.get("youtube_url") or "").strip()
                career_highlights = (
                    request.POST.get("career_highlights") or ""
                ).strip()

                # Validation
                errors = {}
                from django.core.validators import URLValidator
                from django.core.exceptions import ValidationError

                url_validator = URLValidator()

                def validate_optional_url(url, field_name):
                    if url:
                        if len(url) > 255:
                            errors[field_name] = ["URL cannot exceed 255 characters."]
                        else:
                            try:
                                url_validator(url)
                            except ValidationError:
                                errors[field_name] = [
                                    f"Enter a valid URL for {field_name}."
                                ]

                validate_optional_url(website, "website")
                validate_optional_url(google_business, "google_business")
                validate_optional_url(linkedin, "linkedin_url")
                validate_optional_url(instagram, "instagram_url")
                validate_optional_url(facebook, "facebook_url")
                validate_optional_url(youtube, "youtube_url")

                if career_highlights and len(career_highlights) > 500:
                    errors["career_highlights"] = [
                        "Professional Bio cannot exceed 500 characters."
                    ]
                    transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                    return JsonResponse(
                        {
                            "status": "error",
                            "message": "Professional Bio cannot exceed 500 characters.",
                            "errors": errors,
                        },
                        status=400,
                    )

                if errors:
                    transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                    return JsonResponse(
                        {
                            "status": "error",
                            "message": "Validation failed",
                            "errors": errors,
                        },
                        status=422,
                    )

                # Check photos limits
                remove_photo_ids = request.POST.getlist(
                    "remove_photos[]"
                ) or request.POST.getlist("remove_photos")
                remove_photo_ids = [int(i) for i in remove_photo_ids if i.isdigit()]

                plan_text = str(
                    agent.activeSubscription.selected_plan
                    if agent.activeSubscription
                    else ""
                ).lower()
                max_achievement_photos = 10 if "professional" in plan_text else 5

                existing_photos_count = agent.achievementPhotos.count()
                removed_count = len(remove_photo_ids)
                new_photos = request.FILES.getlist("achievement_photos")
                new_photos_count = len(new_photos)

                projected_total = (
                    max(0, existing_photos_count - removed_count) + new_photos_count
                )
                if projected_total > max_achievement_photos:
                    transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                    return JsonResponse(
                        {
                            "status": "error",
                            "message": f"Achievement photo limit exceeded. Your current plan allows up to {max_achievement_photos} photos.",
                            "errors": {
                                "achievement_photos": [
                                    f"You can upload up to {max_achievement_photos} achievement photos."
                                ]
                            },
                        },
                        status=422,
                    )

                profile.website_url = website
                profile.social_links = {
                    "google_business": google_business,
                    "linkedin": linkedin,
                    "instagram": instagram,
                    "facebook": facebook,
                    "youtube": youtube,
                }
                profile.career_highlights = career_highlights
                profile.save()

                # Process photo removal
                if remove_photo_ids:
                    agent.achievementPhotos.filter(id__in=remove_photo_ids).delete()

                # Process photo uploads
                allowed_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
                for photo_file in new_photos:
                    file_content = photo_file.read()
                    photo_file.seek(0)
                    is_valid, error_msg = validate_magic_bytes(
                        file_content, photo_file.name
                    )
                    if not is_valid:
                        transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                        return JsonResponse(
                            {
                                "status": "error",
                                "message": f"Invalid file for achievement photo: {error_msg}",
                                "errors": {"achievement_photos": [error_msg]},
                            },
                            status=422,
                        )

                    file_ext = os.path.splitext(photo_file.name)[1].lower()
                    if file_ext not in allowed_extensions:
                        transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                        return JsonResponse(
                            {
                                "status": "error",
                                "message": "Invalid file extension. Only JPG, JPEG, PNG, GIF, and WEBP are allowed.",
                                "errors": {
                                    "achievement_photos": [
                                        "Invalid file extension. Only images are allowed."
                                    ]
                                },
                            },
                            status=422,
                        )

                    if photo_file.size > 5 * 1024 * 1024:
                        transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                        return JsonResponse(
                            {
                                "status": "error",
                                "message": "One of your photos exceeds 5MB size limit.",
                                "errors": {
                                    "achievement_photos": ["A photo exceeds 5MB."]
                                },
                            },
                            status=422,
                        )

                    from PIL import Image

                    try:
                        photo_file.seek(0)
                        img = Image.open(photo_file)
                        img.verify()
                        photo_file.seek(0)
                    except Exception:
                        transaction.set_rollback(True)  # audit AG5: a rejected save writes nothing
                        return JsonResponse(
                            {
                                "status": "error",
                                "message": "The uploaded file is not a valid image.",
                                "errors": {
                                    "achievement_photos": [
                                        "Invalid or corrupted image file."
                                    ]
                                },
                            },
                            status=422,
                        )

                    file_name = f"app/public/achievement/achievement_{agent.id}_{int(time.time())}_{uuid.uuid4().hex[:6]}{file_ext}"
                    saved_path = default_storage.save(file_name, photo_file)
                    AgentAchievementPhoto.objects.create(
                        agent=agent, photo_path=saved_path
                    )

                # Recreate career timelines
                agent.careerTimelines.all().delete()
                timeline_indices = set()
                for key in request.POST.keys():
                    match = re.match(r"career_timelines\[(\d+)\]\[event_text\]", key)
                    if match:
                        timeline_indices.add(int(match.group(1)))

                for idx in sorted(timeline_indices):
                    event_type = request.POST.get(
                        f"career_timelines[{idx}][type]", "Career Event"
                    ).strip()
                    event_text = request.POST.get(
                        f"career_timelines[{idx}][event_text]", ""
                    ).strip()
                    month = request.POST.get(
                        f"career_timelines[{idx}][month]", ""
                    ).strip()
                    year = request.POST.get(
                        f"career_timelines[{idx}][year]", ""
                    ).strip()
                    suggestion_key = (
                        request.POST.get(
                            f"career_timelines[{idx}][suggestion_key]", ""
                        ).strip()
                        or None
                    )
                    if event_text and year:
                        AgentCareerTimeline.objects.create(
                            agent=agent,
                            event_type=event_type,
                            event_text=event_text,
                            month=month,
                            year=year,
                            suggestion_key=suggestion_key,
                        )

            # ── Step 6: Lead Preferences ──
            if should_process(6):
                agent_plan = _resolve_agent_plan(agent.plan_type, agent=agent)
                can_edit_leads = is_admin_edit or (
                    agent_plan is None
                    or plan_shows_feature(
                        agent_plan, "show_lead_preferences", default=False
                    )
                )
                if can_edit_leads:
                    lead_types = request.POST.getlist(
                        "lead_types[]"
                    ) or request.POST.getlist("lead_types")
                    portfolio_charging = request.POST.get("portfolio_charging", "free")

                    portfolio_fee = 0.0
                    if portfolio_charging == "conditional":
                        portfolio_fee = float(
                            request.POST.get("portfolio_fee_conditional") or 0.0
                        )
                    elif portfolio_charging == "paid":
                        portfolio_fee = float(
                            request.POST.get("portfolio_fee_paid") or 0.0
                        )

                    claims_charging = request.POST.get("claims_charging", "free")
                    claims_fee_amount = (
                        float(request.POST.get("claims_fee_amount") or 0.0)
                        if claims_charging == "fee"
                        else 0.0
                    )
                    claims_percent = (
                        float(request.POST.get("claims_percent") or 0.0)
                        if claims_charging == "percentage"
                        else 0.0
                    )

                    allow_new = (
                        is_admin_edit
                        or agent_plan is None
                        or plan_shows_feature(
                            agent_plan, "show_new_business_leads", default=False
                        )
                    )
                    allow_portfolio = (
                        is_admin_edit
                        or agent_plan is None
                        or plan_shows_feature(
                            agent_plan, "show_lead_portfolio_analysis", default=False
                        )
                    )
                    allow_claims = (
                        is_admin_edit
                        or agent_plan is None
                        or plan_shows_feature(
                            agent_plan, "show_lead_claims_support", default=False
                        )
                    )
                    AgentLeadPreference.objects.update_or_create(
                        agent=agent,
                        defaults={
                            "leads_new_business": allow_new
                            and "new_business" in lead_types,
                            "leads_portfolio_analysis": allow_portfolio
                            and "portfolio_analysis" in lead_types,
                            "portfolio_charging": portfolio_charging,
                            "portfolio_fee": portfolio_fee,
                            "leads_claims_support": allow_claims
                            and "claims_support" in lead_types,
                            "claims_charging": claims_charging,
                            "claims_fee_amount": claims_fee_amount,
                            "claims_percent": claims_percent,
                        },
                    )

            # ── Step 7: Final Submission ──
            if not current_step or str(current_step) == "7":
                if not is_admin_edit:
                    agent.status = "pending_approval"
                    agent.save()

            if license_payloads:
                from django.core.files.base import ContentFile

                for field, content, ext, kind in license_payloads:
                    folder = "insurance" if kind == "irdai" else "investment"
                    doc_path = (
                        f"app/public/{folder}/{kind}_{agent.id}_{uuid.uuid4().hex}{ext}"
                    )
                    setattr(
                        profile,
                        field,
                        default_storage.save(doc_path, ContentFile(content)),
                    )
                profile.save()

            # Clear OG image cache so changes (like WhatsApp, Photo, Name) reflect immediately
            from django.core.cache import cache
            from apps.agents.models import og_image_cache_key

            cache.delete(og_image_cache_key(agent.id))

            try:
                with (
                    transaction.atomic()
                ):  # savepoint: a logging error must not roll back the profile save
                    _log_profile_edit(
                        request,
                        agent,
                        edit_snapshot_before,
                        _profile_edit_snapshot(agent, profile),
                        current_step,
                        is_admin_edit,
                    )
            except Exception:
                logger.exception("Profile edit log failed for agent_id=%s", agent.id)

            def _doc_url(field_file):
                name = str(field_file or "").strip()
                return f"/media/{name}" if name else None

            return JsonResponse(
                {
                    "status": "success",
                    "message": "Profile saved successfully"
                    if not current_step
                    else "Progress saved",
                    "redirect": None
                    if current_step and str(current_step) != "7"
                    else (
                        "/admin/agents/manage/" + str(agent.id) + "/"
                        if is_admin_edit
                        else "/agent/dashboard/"
                    ),
                    "profile_photo_url": profile.profile_photo_url,
                    "irdai_license_doc_url": _doc_url(profile.irdai_license_doc),
                    "amfi_license_doc_url": _doc_url(profile.amfi_license_doc),
                }
            )

    except Exception as e:
        import traceback

        logger.error(f"Profile update failed: {e}\n{traceback.format_exc()}")
        return JsonResponse(
            {
                "status": "error",
                "message": "An error occurred while updating your profile. Please try again.",
            },
            status=500,
        )
