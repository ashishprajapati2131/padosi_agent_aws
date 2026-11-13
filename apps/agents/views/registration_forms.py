"""Registration pages and form steps: page context, referral landing, photo upload checks, slug/email checks, step 2, agent creation from a draft and the payment complete/failed pages."""

import json
import os
import time
import re
from decimal import Decimal
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.conf import settings
from apps.agents.models import Agent, AgentDraft, PromoCode, RegistrationActivityLog
from apps.home.models.pincode import Pincode

from .registration_common import (
    ALLOWED_SEGMENT_IDS,
    ALL_INDIAN_STATES,
    INSURANCE_SEGMENTS,
    LANGUAGE_OPTIONS,
    REGISTRATION_STAGE_STATUSES,
    REG_FORM_SHOWN_AT_KEY,
    STEP1_REUSABLE_STATUSES,
    _RESERVED_PROFILE_SLUGS,
    _int_or_zero,
    _post_payment_redirect_url,
    logger,
)
from .registration_fulfilment import _event_referral_register_hook


def _registration_min_fill_seconds():
    # Bots post the form instantly after loading it; people need longer.
    if getattr(settings, "TESTING", False):
        return 0
    return getattr(settings, "REGISTRATION_MIN_FILL_SECONDS", 3)


def _get_registration_context(request):
    """Build the template context based on current session state."""
    session = request.session
    session[REG_FORM_SHOWN_AT_KEY] = int(time.time())
    reg_step = session.get("reg_step", 0)
    email_verified = session.get("email_verified", False)
    verified_email = session.get("verified_email", "")

    # Load draft if exists
    draft = None
    draft_id = session.get("current_draft_id")
    if draft_id:
        try:
            draft = AgentDraft.objects.get(pk=draft_id)
        except AgentDraft.DoesNotExist:
            pass

    layout_template = "base.html"
    try:
        from apps.distributors.views.dashboard import is_distributor

        if request.user.is_authenticated and is_distributor(request.user):
            layout_template = "distributors/layout.html"
    except Exception:
        pass

    active_investment_types = []
    try:
        from apps.agents.models import InvestmentType

        active_investment_types = list(InvestmentType.objects.filter(is_active=True))
    except Exception as e:
        logger.warning(f"Error fetching active_investment_types: {e}")

    prefilled_promo = ""
    try:
        from apps.agents.models import PromoCode

        promo_param = (request.GET.get("promo") or "").strip().upper()
        if promo_param:
            p_obj = PromoCode.objects.filter(code__iexact=promo_param).first()
            if p_obj and p_obj.is_valid():
                prefilled_promo = p_obj.code
                request.session["applied_promo_code"] = p_obj.code
        elif request.session.get("applied_promo_code"):
            p_obj = PromoCode.objects.filter(
                code__iexact=request.session.get("applied_promo_code")
            ).first()
            if p_obj and p_obj.is_valid():
                prefilled_promo = p_obj.code
            else:
                request.session.pop("applied_promo_code", None)
    except Exception as e:
        logger.warning(f"Error resolving promo code in registration context: {e}")

    lead = None
    try:
        from apps.agents.services.registration_leads import session_lead

        lead = session_lead(request)
    except Exception:
        lead = None
    quick_name = (
        (lead.name if lead else "") or session.get("quick_reg_name") or ""
    ).strip()
    quick_phone = (
        (lead.phone if lead else "") or session.get("quick_reg_phone") or ""
    ).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._\-]{1,69}", quick_name):
        quick_name = ""
    if not re.fullmatch(r"[6-9]\d{9}", quick_phone):
        quick_phone = ""
    draft_phone = (getattr(draft, "mobile", "") or "").strip()
    require_quick_reg_gate = not bool(
        lead or quick_phone or re.fullmatch(r"[6-9]\d{9}", draft_phone)
    )

    swipe = {}
    try:
        from apps.admin_panel.views.content import get_registration_swipe_config

        swipe = get_registration_swipe_config(visible_only=True)
    except Exception as e:
        logger.warning(f"Error resolving registration swipe config: {e}")
        swipe = {"enabled": False, "slides": []}

    default_states = ALL_INDIAN_STATES
    try:
        fetched_states = list(
            Pincode.objects.values_list("state", flat=True).distinct().order_by("state")
        )
        if fetched_states:
            default_states = fetched_states
    except Exception as e:
        logger.warning(f"Error fetching pincodes table/states: {e}")

    return {
        "layout_template": layout_template,
        "reg_step": reg_step,
        "email_verified": email_verified,
        "verified_email": verified_email,
        "draft": draft,
        "default_states": default_states,
        "segments": INSURANCE_SEGMENTS,
        "language_options": LANGUAGE_OPTIONS,
        "agent_segments": getattr(draft, "segments", []) if draft else [],
        "agent_languages": getattr(draft, "languages", []) if draft else [],
        "active_investment_types": active_investment_types,
        "prefilledPromo": prefilled_promo,
        "prefilled_name": quick_name or getattr(draft, "fullname", "") or "",
        "prefilled_phone": quick_phone or draft_phone,
        "prefilled_whatsapp": quick_phone
        or getattr(draft, "whatsapp", "")
        or draft_phone,
        "prefilled_state": getattr(draft, "state", "") or "",
        "agent_segments_json": [
            s
            for s in (getattr(draft, "segments", None) or [])
            if s in ALLOWED_SEGMENT_IDS
        ],
        "require_quick_reg_gate": require_quick_reg_gate,
        "registration_swipe_enabled": bool(swipe.get("enabled"))
        and bool(swipe.get("slides")),
        "registration_swipe_slides": swipe.get("slides") or [],
        "preview_auto_advance_ms": int(swipe.get("preview_auto_advance_seconds") or 2)
        * 1000,
        "hide_site_nav": True,
        "hide_footer": True,
        "hide_chatbot": True,
        "hide_eligibility_popup": True,
        "event_referral_mode": False,
        "welcome_preview_mode": False,
        "registration_popup_only": False,
        "register_step1_url": reverse("agents:agent_register_step1"),
    }


# ─── Views ──────────────────────────────────────────────────────────────────────


def _build_referring_agent_data(referring_agent, is_championship=False):
    """Build standardized dictionary for referring agent card and OG preview."""
    if not referring_agent:
        return None

    photo_url = "/static/img/avatar-icon.jpg"
    try:
        profile = getattr(referring_agent, "profile", None)
        if profile and hasattr(profile, "profile_photo_url"):
            photo_url = profile.profile_photo_url or photo_url
        elif referring_agent.photo:
            photo_url = referring_agent.photo.url
    except Exception:
        pass

    avg_rating = 0.0
    review_count = 0
    try:
        avg_rating = round(float(referring_agent.average_rating), 1)
        review_count = referring_agent.review_count
    except Exception:
        pass

    profile_slug = referring_agent.agent_slug
    profile_url = (
        f"/profile/{referring_agent.state_code}/{profile_slug}/" if profile_slug else ""
    )

    name = referring_agent.fullname or ""
    initials = "".join(word[0].upper() for word in name.split()[:2] if word) or "A"

    segments = []
    try:
        raw_segs = referring_agent.ordered_insurance_segments
        for seg_item in raw_segs:
            s_lower = str(seg_item).strip().lower()
            if s_lower == "sme":
                name_seg = "SME"
                badge_cls = "bg-purple-50 text-purple-700 border-purple-200/80"
            elif "health" in s_lower:
                name_seg = "Health"
                badge_cls = "bg-emerald-50 text-emerald-700 border-emerald-200/80"
            elif "life" in s_lower:
                name_seg = "Life"
                badge_cls = "bg-blue-50 text-blue-700 border-blue-200/80"
            elif "motor" in s_lower:
                name_seg = "Motor"
                badge_cls = "bg-amber-50 text-amber-700 border-amber-200/80"
            else:
                name_seg = s_lower.replace("_", " ").title()
                badge_cls = "bg-slate-100 text-slate-700 border-slate-200"
            segments.append({"id": s_lower, "name": name_seg, "badge_cls": badge_cls})
    except Exception:
        pass

    return {
        "id": referring_agent.id,
        "name": name,
        "fullname": referring_agent.fullname or name,
        "initials": initials,
        "photo_url": photo_url,
        "avg_rating": avg_rating if avg_rating > 0 else 5.0,
        "review_count": review_count,
        "profile_url": profile_url,
        "segments": segments,
        "slug": profile_slug,
        "is_championship": bool(is_championship),
        "og_image_url": "/static/img/championship_og.jpg"
        if is_championship
        else reverse("agents:agent_og_image", kwargs={"agent_id": referring_agent.id}),
    }


@require_http_methods(["GET"])
def agent_registration(request):
    """Render the registration page. Shows OTP, Step 1, or Step 2 based on session."""
    try:
        request.session.pop("event_referral_registration", None)
        # A just-finished quick registration opens this form, even for a signed-in visitor.
        from_quick_registration = bool(request.session.pop("quick_reg_continue", False))
        if request.user.is_authenticated and not from_quick_registration:
            from apps.agents.services.account_auth import (
                resolve_agent_for_user,
                agent_can_access_dashboard,
            )

            if request.user.is_staff or request.user.is_superuser:
                return redirect("agents:agent_dashboard")
            agent = resolve_agent_for_user(request.user)
            if agent:
                if agent_can_access_dashboard(agent):
                    return redirect("agents:agent_dashboard")
                return redirect("agents:chooseplan")

        # Capture referral parameter if provided in GET query params (?ref= or ?refCode=)
        ref_param = request.GET.get("ref") or request.GET.get("refCode")
        referring_agent_data = None
        if ref_param:
            ref_val = str(ref_param).strip().upper()
            request.session["ref_code"] = ref_val
            referring_agent = None
            is_champ = False

            if ref_val.startswith("PA-"):
                try:
                    from apps.referral_championship.services.attribution_service import (
                        bind_referral_session,
                    )

                    bind_referral_session(request, ref_val)
                    from apps.referral_championship.models import (
                        ChampionshipParticipant,
                    )

                    participant = (
                        ChampionshipParticipant.objects.filter(referral_id=ref_val)
                        .select_related("agent")
                        .first()
                    )
                    if participant and participant.agent:
                        referring_agent = participant.agent
                        is_champ = True
                except Exception:
                    pass

            if not referring_agent:
                try:
                    from apps.distributors.models import SubDistributor

                    sub_dist = SubDistributor.objects.filter(
                        code=ref_val, status="active"
                    ).first()
                    if sub_dist:
                        request.session["sub_distributor_id"] = sub_dist.id
                        request.session["distributor_id"] = sub_dist.distributor_id
                        request.session["distributor_led_registration"] = True
                        request.session["ref_code"] = sub_dist.code
                except Exception:
                    pass

            if not referring_agent and not request.session.get("sub_distributor_id"):
                try:
                    from apps.admin_panel.models.referral_code import ReferralCode

                    ref_obj = (
                        ReferralCode.objects.filter(code=ref_val, is_active=True)
                        .select_related("agent")
                        .first()
                    )
                    if ref_obj:
                        if ref_obj.distributor_id:
                            request.session["distributor_id"] = ref_obj.distributor_id
                            request.session["distributor_led_registration"] = True
                        if ref_obj.agent:
                            referring_agent = ref_obj.agent
                except Exception:
                    pass

            if referring_agent:
                referring_agent_data = _build_referring_agent_data(
                    referring_agent, is_championship=is_champ
                )

        context = _get_registration_context(request)
        context["registration_popup_only"] = True
        context["require_quick_reg_gate"] = False
        if referring_agent_data:
            context["referring_agent"] = referring_agent_data

        if not context.get("event_referral_mode"):
            try:
                from apps.agents.services.registration_leads import (
                    capture_quick_lead,
                    session_lead,
                )

                lead = session_lead(request)
                draft = context.get("draft")
                if (
                    lead is None
                    and draft
                    and re.fullmatch(r"[6-9]\d{9}", (draft.mobile or "").strip() or "")
                ):
                    lead, _blocked = capture_quick_lead(
                        request,
                        name=draft.fullname or "",
                        phone=draft.mobile,
                        ref_code=request.session.get("ref_code") or "",
                        source_url=request.build_absolute_uri()[:500],
                    )
                if lead:
                    context["require_quick_reg_gate"] = False
            except Exception:
                logger.exception("Quick-registration gate status update failed")

        if ref_param:
            from apps.agents.services.og_urls import build_og_absolute_url

            ref_val = str(ref_param).strip().upper()
            if ref_val.startswith("EV-"):
                from apps.event_referral.services.og_meta import paldi_og_context

                ref_name = (
                    (referring_agent_data or {}).get("name")
                    if referring_agent_data
                    else None
                )
                context.update(paldi_og_context(request, referring_agent_name=ref_name))
                context["og_page_absolute_url"] = build_og_absolute_url(
                    request, request.get_full_path()
                )
                context["og_image_absolute_url"] = context.get("paldi_og_image_url")
            elif ref_val.startswith("PA-"):
                from apps.referral_championship.services.og_meta import (
                    championship_og_context,
                )

                ref_name = (
                    (referring_agent_data or {}).get("name")
                    if referring_agent_data
                    else None
                )
                context.update(
                    championship_og_context(request, referring_agent_name=ref_name)
                )
                context["og_page_absolute_url"] = build_og_absolute_url(
                    request, request.get_full_path()
                )

        return render(request, "agents/registration.html", context)
    except Exception as e:
        logger.exception(f"Error in agent_registration view: {e}")
        context = _get_registration_context(request)
        context["registration_popup_only"] = True
        context["require_quick_reg_gate"] = False
        return render(request, "agents/registration.html", context)


@require_http_methods(["GET"])
def welcome_preview(request):
    """Show the digital card + profile website preview after the public popup.

    Requires a session draft created by quick registration. Does not render the
    long registration form or redirect there.
    """
    draft_id = _resolve_chooseplan_draft_id(request)
    if not draft_id:
        return redirect("home:home")
    context = _get_registration_context(request)
    if not context.get("draft"):
        return redirect("home:home")
    context["welcome_preview_mode"] = True
    context["require_quick_reg_gate"] = False
    context["hide_eligibility_popup"] = True
    return render(request, "agents/registration.html", context)


@require_POST
@csrf_protect
def agent_registration_progress(request):
    """Mark the open lead as form started once the visitor types into the form."""
    if request.session.get("event_referral_registration"):
        return JsonResponse({"ok": True})
    from apps.admin_panel.models import RegistrationLead
    from apps.agents.services.registration_leads import (
        mark_form_started,
        session_lead,
        normalize_phone,
        bind_session,
    )

    lead = session_lead(request)
    if lead is None:
        phone = ""
        if request.content_type == "application/json" and request.body:
            try:
                import json

                payload = json.loads(request.body.decode("utf-8"))
                phone = normalize_phone(payload.get("phone"))
            except Exception:
                pass
        if not phone:
            phone = normalize_phone(request.POST.get("phone"))
        if phone:
            lead = RegistrationLead.objects.filter(phone=phone).first()
            if lead:
                bind_session(request, lead)
    if lead is None:
        return JsonResponse({"ok": False}, status=403)
    mark_form_started(request, lead)
    return JsonResponse({"ok": True})


def _bump_clicks(obj):
    """Atomic clicks + 1 in the database (concurrent visits lost updates)."""
    from django.db.models import F, Value
    from django.db.models.functions import Coalesce

    type(obj).objects.filter(pk=obj.pk).update(
        clicks=Coalesce(F("clicks"), Value(0)) + 1
    )


@require_http_methods(["GET"])
def agent_registration_referral(request, ref_code):
    """
    Referral registration landing — /agent-registration/join/{ref_code}/
    Stores the referral code in session, looks up the referring agent,
    and renders the same registration page with the referring agent's card.
    The actual registration flow remains completely unchanged.
    """
    try:
        # If already logged in, redirect same as normal registration
        if request.user.is_authenticated:
            from apps.agents.services.account_auth import (
                resolve_agent_for_user,
                agent_can_access_dashboard,
            )

            if request.user.is_staff or request.user.is_superuser:
                return redirect("agents:agent_dashboard")
            agent = resolve_agent_for_user(request.user)
            if agent:
                if agent_can_access_dashboard(agent):
                    return redirect("agents:agent_dashboard")
                return redirect("agents:chooseplan")

        code_val = str(ref_code).strip().upper()

        # ── Store ref code in session for the existing flow to pick up ──
        request.session["ref_code"] = code_val
        # A referral page is the normal paid signup: drop a Paldi flag left on
        # a shared stall device (audit 2026-10-01 F-17d).
        request.session.pop("event_referral_registration", None)

        # ── Look up the referring agent ──
        referring_agent = None
        is_champ = False

        # 1. Event referral challenge (EV-XXXXXX)
        if code_val.startswith("EV-"):
            try:
                from apps.event_referral.models import EventReferralParticipant

                ev_part = (
                    EventReferralParticipant.objects.filter(
                        referral_code=code_val,
                    )
                    .select_related("agent")
                    .first()
                )
                if ev_part and ev_part.agent:
                    referring_agent = ev_part.agent
            except Exception:
                pass

        # 2. Try Championship participant code (PA-XXXXXX)
        if not referring_agent and code_val.startswith("PA-"):
            try:
                from apps.referral_championship.services.attribution_service import (
                    bind_referral_session,
                )

                bind_referral_session(request, code_val)
                from apps.referral_championship.models import ChampionshipParticipant

                participant = (
                    ChampionshipParticipant.objects.filter(referral_id=code_val)
                    .select_related("agent")
                    .first()
                )
                if participant and participant.agent:
                    referring_agent = participant.agent
                    is_champ = True
            except Exception:
                pass

        # 3. Try SubDistributor code
        if not referring_agent:
            try:
                from apps.distributors.models import SubDistributor

                sub_dist = SubDistributor.objects.filter(
                    code=code_val, status="active"
                ).first()
                if sub_dist:
                    _bump_clicks(sub_dist)
                    request.session["sub_distributor_id"] = sub_dist.id
                    request.session["distributor_id"] = sub_dist.distributor_id
                    request.session["distributor_led_registration"] = True
                    request.session["ref_code"] = sub_dist.code
            except Exception:
                pass

        # 4. Try legacy ReferralCode
        if not referring_agent and not request.session.get("sub_distributor_id"):
            try:
                from apps.admin_panel.models.referral_code import ReferralCode

                ref_obj = (
                    ReferralCode.objects.filter(code=code_val, is_active=True)
                    .select_related("agent")
                    .first()
                )
                if ref_obj:
                    # Increment clicks for tracking
                    _bump_clicks(ref_obj)
                    if ref_obj.distributor_id:
                        request.session["distributor_id"] = ref_obj.distributor_id
                        request.session["distributor_led_registration"] = True
                    if ref_obj.agent:
                        referring_agent = ref_obj.agent
            except Exception:
                pass

        # ── Build referring agent context for the card ──
        referring_agent_data = (
            _build_referring_agent_data(referring_agent, is_championship=is_champ)
            if referring_agent
            else None
        )

        # ── Build normal registration context + referring agent ──
        context = _get_registration_context(request)
        context["referring_agent"] = referring_agent_data
        context["og_share_title"] = "PadosiAgent"
        from apps.agents.services.og_urls import (
            agent_og_image_absolute_url,
            build_og_absolute_url,
        )

        if code_val.startswith("EV-"):
            from apps.event_referral.services.og_meta import paldi_og_context

            ref_name = (
                (referring_agent_data or {}).get("name")
                if referring_agent_data
                else None
            )
            context.update(paldi_og_context(request, referring_agent_name=ref_name))
            context["event_referral_share_landing"] = True
            context["og_page_absolute_url"] = build_og_absolute_url(
                request, request.get_full_path()
            )
        elif code_val.startswith("PA-"):
            from apps.referral_championship.services.og_meta import (
                championship_og_context,
            )

            ref_name = (
                (referring_agent_data or {}).get("name")
                if referring_agent_data
                else None
            )
            context.update(
                championship_og_context(request, referring_agent_name=ref_name)
            )
            context["og_page_absolute_url"] = build_og_absolute_url(
                request, request.get_full_path()
            )
        elif referring_agent_data and referring_agent_data.get("id"):
            context["og_image_absolute_url"] = agent_og_image_absolute_url(
                request,
                referring_agent_data["id"],
            )
            context["og_page_absolute_url"] = build_og_absolute_url(
                request, request.get_full_path()
            )
        return render(request, "agents/registration.html", context)
    except Exception as e:
        logger.exception(
            f"Error in agent_registration_referral view for ref_code {ref_code}: {e}"
        )
        context = _get_registration_context(request)
        return render(request, "agents/registration.html", context)


# Real image format (detected from the file bytes) -> extension it is saved with.
_PHOTO_FORMAT_EXTENSIONS = {
    "JPEG": ".jpg",
    "MPO": ".jpg",
    "PNG": ".png",
    "GIF": ".gif",
    "WEBP": ".webp",
    "BMP": ".bmp",
}


def _validated_photo_upload(upload):
    """Return the upload only if it is a real raster image (<=5MB), else None.

    Model ImageFields do not validate on assignment, so an anonymous visitor
    could store e.g. evil.html / script-laden SVG under /media/agent_photos/,
    which is then served same-origin.

    The check uses the file content, not its name, so real photos named
    .jfif / .JPG / without extension (Android pickers) keep working; the
    stored name gets the extension of the detected format.
    """
    if not upload:
        return None
    if upload.size > 5 * 1024 * 1024:
        return None
    from apps.agents.utils.file_validation import has_dangerous_extra_extension

    if has_dangerous_extra_extension(upload.name):
        return None
    try:
        from PIL import Image

        upload.seek(0)
        img = Image.open(upload)
        fmt = (img.format or "").upper()
        img.verify()
        upload.seek(0)
    except Exception:
        return None
    ext = _PHOTO_FORMAT_EXTENSIONS.get(fmt)
    if not ext:
        return None
    base = os.path.splitext(os.path.basename(upload.name or ""))[0]
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_")[:80] or "photo"
    upload.name = f"{base}{ext}"
    return upload


def _assign_step1_draft_fields(draft, request, extra=None):
    extra = extra or {}
    draft.fullname = extra.get("fullname", request.POST.get("fullname", "").strip())
    draft.mobile = extra.get("mobile", request.POST.get("mobile", "").strip())
    draft.agent_pincode = extra.get(
        "agent_pincode", request.POST.get("agent_pincode", "").strip()
    )
    draft.state = extra.get("state", request.POST.get("state", "").strip())
    exp_raw = extra.get("experience", request.POST.get("experience_range", ""))
    if exp_raw:
        try:
            exp_digits = re.sub(r"\D", "", str(exp_raw))
            if exp_digits and int(exp_digits) > 60:
                exp_raw = "60"
        except (TypeError, ValueError):
            pass
    draft.experience_range = exp_raw
    draft.segments = extra.get(
        "segments",
        request.POST.getlist("segments[]") or request.POST.getlist("segments"),
    )
    draft.investment_types = extra.get(
        "investment_types",
        request.POST.getlist("investment_types[]")
        or request.POST.getlist("investment_types"),
    )
    draft.promo_code = extra.get(
        "promo_code", request.POST.get("promo_code", "").strip()
    )
    draft.address = extra.get("address", request.POST.get("address", "").strip())
    draft.client_base = extra.get(
        "client_base", request.POST.get("client_base", "").strip()
    )
    draft.slug = extra.get("slug", request.POST.get("slug", "").strip())
    draft.whatsapp = extra.get("whatsapp", request.POST.get("whatsapp", "").strip())
    draft.pan_number = extra.get(
        "pan_number", request.POST.get("pan_number", "").strip().upper()
    )
    draft.claims_settled = extra.get(
        "claims_settled", _int_or_zero(request.POST.get("claims_settled"))
    )
    draft.claim_amount = extra.get(
        "claim_amount", request.POST.get("claim_amount", "").strip()
    )
    photo = _validated_photo_upload(request.FILES.get("photo"))
    if photo:
        draft.photo = photo

    # Capture sub-distributor / distributor binding from session
    sub_dist_id_from_session = request.session.get("sub_distributor_id")
    if sub_dist_id_from_session:
        draft.sub_distributor_id = sub_dist_id_from_session

    dist_id_from_session = request.session.get("distributor_id")
    if dist_id_from_session:
        draft.distributor_id = dist_id_from_session
        from apps.admin_panel.models.referral_code import ReferralCode

        ref_obj = ReferralCode.objects.filter(
            distributor_id=dist_id_from_session, is_active=True
        ).first()
        if ref_obj:
            draft.referred_by_code = ref_obj.code
    else:
        ref_code = request.session.get("ref_code") or request.session.get(
            "championship_ref_id"
        )
        if ref_code:
            from apps.distributors.models import SubDistributor

            sub_dist = SubDistributor.objects.filter(
                code=ref_code, status="active"
            ).first()
            if sub_dist:
                draft.sub_distributor_id = sub_dist.id
                draft.distributor_id = sub_dist.distributor_id
                draft.referred_by_code = sub_dist.code
            elif str(ref_code).startswith("PA-") or str(ref_code).startswith("EV-"):
                draft.referred_by_code = ref_code
            else:
                from apps.admin_panel.models.referral_code import ReferralCode

                ref_obj = ReferralCode.objects.filter(
                    code=ref_code, is_active=True
                ).first()
                if ref_obj:
                    draft.referred_by_code = ref_code
                    if ref_obj.distributor_id:
                        draft.distributor_id = ref_obj.distributor_id

    return draft


def _registration_slug_status(raw_slug):
    """Return (available, message, normalized_slug) for a claimed profile URL."""
    from django.utils.text import slugify
    from apps.agents.models import AgentProfile
    from apps.home.models.page import Page

    slug = slugify((raw_slug or "").strip())
    if (
        not slug
        or len(slug) < 3
        or len(slug) > 50
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)
        or slug in _RESERVED_PROFILE_SLUGS
    ):
        return (
            False,
            "Profile URL must be 3–50 characters and use only letters, numbers, and hyphens.",
            slug,
        )
    if (
        Page.objects.filter(slug=slug).exists()
        or AgentProfile.objects.filter(slug=slug).exists()
    ):
        return False, "This URL is already taken. Please choose another.", slug
    return True, "URL is available!", slug


@require_http_methods(["GET"])
def check_slug_availability(request):
    """Check if a custom slug is available for an agent profile."""
    raw_slug = request.GET.get("slug", "").strip()
    if not raw_slug:
        return JsonResponse(
            {"success": False, "available": False, "message": "Slug is required."}
        )

    available, message, slug = _registration_slug_status(raw_slug)
    return JsonResponse(
        {
            "success": True,
            "available": available,
            "slug": slug,
            "message": message,
        }
    )


@require_http_methods(["GET"])
def check_email_availability(request):
    """Tell the registration form if this email already belongs to an active/paid agent."""
    from apps.agents.models import Agent, Invoice

    email = (request.GET.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return JsonResponse(
            {
                "success": False,
                "registered": False,
                "valid": False,
                "message": "Please enter a valid email address.",
            }
        )

    registered = (
        Invoice.objects.filter(
            agent_email__iexact=email, payment_status="paid"
        ).exists()
        or Agent.objects.filter(
            email__iexact=email, status__in=["active", "pending_approval"]
        ).exists()
    )
    message = f"You are already registered with {email}. Please login to access your dashboard."
    if not registered:
        # Same rule as register_step1: step 1 only reuses a registration still
        # in progress, so say so before the preview opens instead of failing
        # on "Claim" (e.g. a Paldi challenger signing up again from another
        # device; they must log in).
        existing = (
            Agent.objects.filter(email__iexact=email).only("status", "user_id").first()
        )
        if existing and existing.status not in STEP1_REUSABLE_STATUSES:
            owns = bool(
                request.user.is_authenticated
                and existing.user_id
                and existing.user_id == request.user.pk
            )
            if not (owns and existing.status == "event_challenge"):
                registered = True
                from apps.agents.services.account_auth import BLOCKED_DASHBOARD_STATUSES

                if existing.status in BLOCKED_DASHBOARD_STATUSES:
                    message = (
                        "This email cannot be used to register. Please contact support."
                    )
    if registered:
        return JsonResponse(
            {
                "success": True,
                "registered": True,
                "valid": True,
                "message": message,
                "login_url": reverse("agents:agent_login"),
            }
        )
    return JsonResponse(
        {
            "success": True,
            "registered": False,
            "valid": True,
            "message": "",
        }
    )


@require_POST
@csrf_protect
def register_step2(request):
    """Save Step 2 (profile details) → advance to plan selection."""
    draft_id = request.session.get("current_draft_id")
    if not draft_id:
        return JsonResponse(
            {
                "success": False,
                "message": "Registration session not found. Please start over.",
            },
            status=400,
        )

    try:
        draft = AgentDraft.objects.get(pk=draft_id)
    except AgentDraft.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Registration data not found."}, status=400
        )

    # Extract form data
    about = request.POST.get("about", "").strip()
    languages = request.POST.getlist("languages[]") or request.POST.getlist("languages")
    certifications = request.POST.get("certifications", "").strip()

    # Handle photo upload
    raw_photo = request.FILES.get("photo")
    photo = _validated_photo_upload(raw_photo)
    if raw_photo and not photo:
        return JsonResponse(
            {
                "success": False,
                "message": "Profile photo must be a JPG, PNG, GIF or WEBP image under 5MB.",
            },
            status=422,
        )
    if photo:
        draft.photo = photo

    draft.about = about
    draft.languages = languages
    draft.certifications = certifications
    draft.registration_step = 2
    draft.save()

    request.session["reg_step"] = 3  # Ready for payment/plans

    logger.info(f"Agent Step 2 saved — draft #{draft.pk}")

    return JsonResponse(
        {
            "success": True,
            "message": "Profile saved! Redirecting to plans...",
            "redirect": "/chooseplan/",
        }
    )


def _resolve_chooseplan_draft_id(request):
    """Restore choose-plan draft from session or logged-in email.

    Never by phone (cookie or lead): a phone number does not prove ownership
    of the draft's name/email.
    """
    draft_id = request.session.get("current_draft_id")
    if draft_id:
        return draft_id
    if not request.user.is_authenticated:
        return None
    try:
        from apps.agents.services.account_auth import resolve_agent_for_user

        logged_in = resolve_agent_for_user(request.user)
    except Exception:
        return None
    if not logged_in:
        return None
    from apps.agents.models import AgentDraft

    draft = (
        AgentDraft.objects.filter(email__iexact=logged_in.email)
        .order_by("-updated_at")
        .first()
    )
    if not draft:
        from apps.agents.services.subscription_expiry import expiry_enforced

        if expiry_enforced() and logged_in.status not in STEP1_REUSABLE_STATUSES:
            # Renewal after expiry for an agent who never had a draft.
            if not request.session.session_key:
                request.session.create()
            draft = AgentDraft.objects.create(
                session_key=request.session.session_key,
                email=logged_in.email,
                email_verified=True,
                fullname=(logged_in.fullname or "")[:70],
                mobile=(logged_in.mobile or "")[:15],
                agent_pincode=(logged_in.agent_pincode or "")[:6],
                experience_range=logged_in.experience_range or "",
                registration_step=2,
            )
    if draft:
        request.session["current_draft_id"] = draft.pk
        return draft.pk
    return None


def create_agent_from_draft(draft, plan_type, plan_name, status="pending_payment"):
    import re
    import time
    from decimal import Decimal, InvalidOperation
    from django.core.files.storage import default_storage
    from django.utils.text import slugify
    from apps.agents.models import (
        Agent,
        AgentProfile,
        AgentInsuranceSegment,
        AgentPerformanceStat,
    )

    def _claim_amount_from_draft(raw):
        if not raw:
            return Decimal("0")
        cleaned = re.sub(r"[^\d.]", "", str(raw).strip())
        if not cleaned:
            return Decimal("0")
        try:
            return Decimal(cleaned) * Decimal("100000")
        except InvalidOperation:
            return Decimal("0")

    now = timezone.now()

    agent, created = Agent.objects.get_or_create(
        email=draft.email,
        defaults={
            "fullname": draft.fullname,
            "mobile": draft.mobile,
            "user_types": ["insurance_agent"],
            "insurance_companies": draft.insurance_companies or [],
            "experience_range": draft.experience_range or "",
            "client_base": draft.client_base or "",
            "registration_step": 2,
            "status": status,
            "plan_type": plan_type,
            "agent_pincode": draft.agent_pincode,
            "email_verified_at": now,
            "distributor_id": getattr(draft, "distributor_id", None),
            "sub_distributor_id": getattr(draft, "sub_distributor_id", None),
            "referred_by_code": getattr(draft, "referred_by_code", "") or "",
        },
    )

    if not created and agent.status not in REGISTRATION_STAGE_STATUSES:
        # Paid / awaiting approval / blocked: a checkout must not rewrite the
        # agent (it used to reset a paid agent back to pending_payment).
        return agent

    if not created:
        agent.fullname = draft.fullname
        agent.mobile = draft.mobile
        agent.insurance_companies = draft.insurance_companies or []
        agent.experience_range = draft.experience_range or ""
        agent.client_base = draft.client_base or ""
        agent.status = status
        agent.plan_type = plan_type
        agent.agent_pincode = draft.agent_pincode
        agent.email_verified_at = now
        if getattr(draft, "distributor_id", None):
            agent.distributor_id = draft.distributor_id
        if getattr(draft, "sub_distributor_id", None):
            agent.sub_distributor_id = draft.sub_distributor_id
        # First-touch protection: never overwrite an already-set referral code
        if getattr(draft, "referred_by_code", None) and not agent.referred_by_code:
            agent.referred_by_code = draft.referred_by_code
        agent.save()

    # ── Event: PENDING_FOR_REGISTRATION ─────────────────────────────────────
    if status == "pending_payment":
        RegistrationActivityLog.log(
            RegistrationActivityLog.EVENT_PENDING_REGISTRATION,
            agent=agent,
            draft_id=draft.pk,
            extra_details={
                "plan_type": plan_type,
                "plan_name": plan_name,
                "draft_email": draft.email,
                "created_new": created,
            },
        )

    # Create insurance segments (delete + bulk insert)
    AgentInsuranceSegment.objects.filter(agent=agent).delete()
    if draft.segments:
        AgentInsuranceSegment.objects.bulk_create(
            [
                AgentInsuranceSegment(agent=agent, segment_type=seg)
                for seg in draft.segments
            ]
        )

    # Write registration_draft JSON (matching PHP Step 2)
    agent.registration_draft = {
        "license_number": draft.license_number or "",
        "pan_number": draft.pan_number or "",
        "software_name": draft.software_name or "",
        "portfolio_breakdown": {
            "life_insurance": draft.life_insurance or 0,
            "health_insurance": draft.health_insurance or 0,
            "general_insurance": draft.general_insurance or 0,
            "motor": draft.motor or 0,
        },
        "desired_services": draft.desired_services or [],
    }
    agent.save(update_fields=["registration_draft", "updated_at"])

    profile, p_created = AgentProfile.objects.get_or_create(
        agent=agent,
        defaults={
            "license_number": draft.license_number or "",
            "license_valid_till": draft.license_valid_till,
            "arn_number": draft.arn_number or "",
            "euin_number": draft.euin_number or "",
            "investment_valid_till": draft.investment_valid_till,
            "investment_types": draft.investment_types or [],
            "pan_number": draft.pan_number or "",
            "software_name": draft.software_name or "",
            "portfolio_breakdown": {
                "life_insurance": draft.life_insurance or 0,
                "health_insurance": draft.health_insurance or 0,
                "general_insurance": draft.general_insurance or 0,
                "motor": draft.motor or 0,
            },
            "desired_services": draft.desired_services or [],
            "whatsapp": draft.whatsapp or "",
            "address": draft.address or "",
            "state": draft.state or "",
            "service_pincodes": [draft.agent_pincode] if draft.agent_pincode else [],
        },
    )
    if not p_created:
        profile.license_number = draft.license_number or ""
        profile.license_valid_till = draft.license_valid_till
        profile.arn_number = draft.arn_number or ""
        profile.euin_number = draft.euin_number or ""
        profile.investment_valid_till = draft.investment_valid_till
        profile.investment_types = draft.investment_types or []
        profile.pan_number = draft.pan_number or ""
        profile.software_name = draft.software_name or ""
        profile.portfolio_breakdown = {
            "life_insurance": draft.life_insurance or 0,
            "health_insurance": draft.health_insurance or 0,
            "general_insurance": draft.general_insurance or 0,
            "motor": draft.motor or 0,
        }
        profile.desired_services = draft.desired_services or []
        profile.whatsapp = draft.whatsapp or profile.whatsapp or ""
        profile.address = draft.address or profile.address or ""
        profile.state = draft.state or profile.state or ""
        if draft.agent_pincode:
            profile.service_pincodes = [draft.agent_pincode]
        profile.save()

    if not profile.slug or draft.slug:
        base_slug = (
            slugify(draft.slug)
            or slugify(draft.fullname)
            or slugify((draft.email or "").split("@")[0])
            or "agent"
        )
        unique_slug = base_slug
        count = 1
        while (
            AgentProfile.objects.filter(slug=unique_slug)
            .exclude(pk=profile.pk)
            .exists()
        ):
            unique_slug = f"{base_slug}-{count}"
            count += 1
        profile.slug = unique_slug
        profile.save(update_fields=["slug", "updated_at"])

    if draft.languages:
        langs = draft.languages
        if isinstance(langs, list):
            profile.languages = ", ".join(
                str(l).strip() for l in langs if str(l).strip()
            )
        elif langs:
            profile.languages = str(langs)
        profile.save(update_fields=["languages", "updated_at"])

    if draft.about:
        profile.career_highlights = draft.about
        profile.save(update_fields=["career_highlights", "updated_at"])

    if draft.photo:
        ext = os.path.splitext(draft.photo.name)[1].lower() or ".jpg"
        file_name = f"app/public/profile/agent_{agent.id}_{int(time.time())}{ext}"
        saved_path = default_storage.save(file_name, draft.photo)
        profile.profile_photo_path = saved_path
        profile.save(update_fields=["profile_photo_path", "updated_at"])

    claims_settled = int(draft.claims_settled or 0)
    claims_amount = _claim_amount_from_draft(draft.claim_amount)
    if claims_settled or claims_amount:
        AgentPerformanceStat.objects.update_or_create(
            agent=agent,
            defaults={
                "claims_settled": claims_settled,
                "claims_processed": claims_settled,
                "claims_amount": claims_amount,
            },
        )

    # Clear registration_draft after committing to profile (matching PHP)
    agent.registration_draft = None
    agent.save(update_fields=["registration_draft", "updated_at"])

    try:
        _event_referral_register_hook(agent)
    except Exception as hook_err:
        logger.warning(
            "Event referral register hook failed for agent #%s: %s", agent.id, hook_err
        )

    return agent


def payment_complete(request):
    """Brief success message after verified payment, then auto-redirect to dashboard."""
    if not request.user.is_authenticated:
        return redirect("agents:chooseplan")

    from apps.agents.services.account_auth import (
        resolve_agent_for_user,
        agent_can_access_dashboard,
    )

    try:
        agent = resolve_agent_for_user(request.user)
    except Exception:
        agent = None

    if not agent or not agent_can_access_dashboard(agent):
        return redirect("agents:chooseplan")

    handoff_plan = request.session.get("app_upgrade_handoff_plan")
    redirect_url = _post_payment_redirect_url(request, agent)
    request.session.pop("app_upgrade_handoff_plan", None)
    request.session.pop("post_payment_landing", None)
    return render(
        request,
        "agents/payment_complete.html",
        {
            "agent_name": (getattr(agent, "fullname", "") or "").strip(),
            "redirect_url": redirect_url,
            "is_plan_upgrade": bool(handoff_plan),
            "hide_chatbot": True,
        },
    )


def referral_join(request, ref_code):
    """
    Referral link landing - captures ref code in session, increments clicks, and redirects to registration.
    Ported from Laravel route /join/{refCode}.
    Supports both legacy Free Trial ReferralCode and National Championship codes (PA-XXXXXX).
    """
    code_val = str(ref_code).strip().upper()

    # If code is for Referral Championship (PA-XXXXXX)
    if code_val.startswith("EV-"):
        from apps.event_referral.models import EventReferralParticipant

        if EventReferralParticipant.objects.filter(referral_code=code_val).exists():
            request.session["ref_code"] = code_val
            url = reverse(
                "agents:agent_registration_referral", kwargs={"ref_code": code_val}
            )
            return redirect(url)

    if code_val.startswith("PA-"):
        from apps.referral_championship.models import ChampionshipParticipant

        if ChampionshipParticipant.objects.filter(referral_id=code_val).exists():
            return redirect("championship:public_landing", ref_id=code_val)

    # If code is for a SubDistributor
    from apps.distributors.models import SubDistributor

    sub_dist = SubDistributor.objects.filter(code=code_val, status="active").first()
    if sub_dist:
        _bump_clicks(sub_dist)
        request.session["ref_code"] = sub_dist.code
        request.session["sub_distributor_id"] = sub_dist.id
        request.session["distributor_id"] = sub_dist.distributor_id
        request.session["distributor_led_registration"] = True
        url = reverse("agents:agent_registration") + f"?ref={code_val}&show_trial=1"
        return redirect(url)

    from apps.admin_panel.models.referral_code import ReferralCode

    code = ReferralCode.objects.filter(code=code_val, is_active=True).first()
    if code:
        _bump_clicks(
            code
        )  # a full save() rewrote total_referrals etc. from a stale read
        request.session["ref_code"] = code.code
        if code.distributor_id:
            request.session["distributor_id"] = code.distributor_id
            request.session["distributor_led_registration"] = True

    # Redirect to registration page with query params
    url = reverse("agents:agent_registration") + f"?ref={code_val}&show_trial=1"
    return redirect(url)


def agent_register_failed(request):
    """
    Render payment failed page.
    """
    from apps.agents.models import Agent

    # Session only: ?agent_id= exposed any agent's name/email/mobile.
    pending = request.session.get("pending_checkout") or {}
    agent_id = request.session.get("current_agent_id") or pending.get("agent_id")
    agent = Agent.objects.filter(id=agent_id).first() if agent_id else None

    return render(request, "agents/failed.html", {"agent": agent})
