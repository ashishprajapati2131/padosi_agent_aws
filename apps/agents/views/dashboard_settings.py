"""Agent settings endpoints (split out of dashboard.py): private file serving,
profile visibility and Google review settings/tracking."""

import os
from apps.agents.models import (
    Agent,
    AgentProfile,
)
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from json import (
    JSONDecodeError as JSONDecodeError,
    loads as json_loads,
)
from apps.agents.views.dashboard_common import logger


def serve_private_file(request, file_path):
    """
    Secure serving of private invoices and uploaded files.
    """
    from django.http import FileResponse, HttpResponseForbidden, Http404
    from django.conf import settings

    import posixpath

    # 1. Normalise FIRST. Ownership used to be checked on the raw path, so
    #    "agents/<my id>/../../invoices/<other>.pdf" passed as "owner" and then
    #    resolved to another agent's invoice.
    private_root = os.path.abspath(os.path.join(settings.MEDIA_ROOT, "app", "private"))
    normalized_path = posixpath.normpath(str(file_path).replace("\\", "/")).lstrip("/")
    normalized_full_path = os.path.abspath(os.path.join(private_root, normalized_path))
    try:
        inside_root = (
            os.path.commonpath([normalized_full_path, private_root]) == private_root
        )
    except ValueError:
        inside_root = False
    if not inside_root or normalized_path.startswith(".."):
        return HttpResponseForbidden("Access Denied: Invalid path traversal attempt.")

    # 2. Access checks on the normalised path
    # Admin panel staff need the module permission for the file (Super Admin: all).
    from apps.wholesale.adapters.auth_bridge import admin_session_has_permission

    if normalized_path.startswith("wholesale/"):
        is_admin = admin_session_has_permission(request, "wholesale")
    else:
        is_admin = admin_session_has_permission(request, "agents", "subscriptions")
    if not is_admin and request.user.is_authenticated:
        if getattr(request.user, "is_staff", False) or getattr(
            request.user, "is_superuser", False
        ):
            is_admin = True

    is_owner = False
    if request.user.is_authenticated:
        from apps.agents.models import Agent, Invoice
        from apps.agents.services.account_auth import resolve_agent_for_user

        agent = (
            resolve_agent_for_user(request.user)
            or Agent.objects.filter(user=request.user).first()
        )
        if agent:
            invoice_exists = Invoice.objects.filter(
                agent=agent, pdf_path=normalized_path
            ).exists()
            if invoice_exists:
                is_owner = True
            elif normalized_path.startswith(
                f"agents/{agent.id}/"
            ) or normalized_path.startswith(f"agent_{agent.id}/"):
                is_owner = True

        # Check wholesale documents ownership
        if not is_owner and normalized_path.startswith("wholesale/documents/"):
            try:
                from apps.wholesale.models.profile import BusinessVerificationDocument

                doc_file_match = f"app/private/{normalized_path}"
                if BusinessVerificationDocument.objects.filter(
                    wholesaler__user=request.user,
                    document_file__in=[doc_file_match, normalized_path],
                ).exists():
                    is_owner = True
            except Exception:
                pass

        # Check wholesale RFQ attachment ownership
        if not is_owner and normalized_path.startswith("wholesale/rfq_attachments/"):
            try:
                from django.db.models import Q
                from apps.wholesale.models.inquiry import InquiryMessage

                doc_file_match = f"app/private/{normalized_path}"
                if (
                    InquiryMessage.objects.filter(
                        attachment__in=[doc_file_match, normalized_path]
                    )
                    .filter(
                        Q(inquiry__buyer_user=request.user)
                        | Q(inquiry__wholesaler__user=request.user)
                    )
                    .exists()
                ):
                    is_owner = True
            except Exception:
                pass

    if not is_admin and not is_owner:
        return HttpResponseForbidden(
            "Access Denied: You do not have permission to access this file."
        )

    if not os.path.exists(normalized_full_path):
        raise Http404("File not found")

    from apps.agents.utils.file_validation import UPLOAD_SANDBOX_CSP

    ext = os.path.splitext(normalized_path.lower())[1]
    inline = ext in (".pdf", ".png", ".jpg", ".jpeg", ".webp")
    response = FileResponse(
        open(normalized_full_path, "rb"),
        as_attachment=not inline,
        filename=os.path.basename(normalized_path),
    )
    response["X-Content-Type-Options"] = "nosniff"
    if ext != ".pdf":  # same PDF exemption as the public media route (browser viewer)
        response["Content-Security-Policy"] = UPLOAD_SANDBOX_CSP
    return response


@login_required
@require_POST
def agent_update_visibility(request):
    """
    Allow agents to toggle visibility of sections on their public profile.
    """
    try:
        data = json_loads(request.body)
        field = data.get("field")
        value = 1 if data.get("value") else 0
    except JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON"})

    valid_fields = [
        "show_certificates",
        "show_achievements",
        "show_reviews",
        "show_experience",
        "show_claims_stats",
        "show_client_base",
        "show_ratings",
        "show_languages",
        "show_gallery",
        "show_contact_info",
        "show_social_links",
    ]
    if field not in valid_fields:
        return JsonResponse({"success": False, "message": "Invalid field"})

    try:
        from apps.agents.services.account_auth import resolve_agent_for_user

        agent = (
            resolve_agent_for_user(request.user)
            or Agent.objects.filter(user=request.user).first()
        )
        if not agent:
            return JsonResponse(
                {"success": False, "message": "Agent profile not found"}
            )

        profile = AgentProfile.objects.filter(agent=agent).first()
        if not profile:
            return JsonResponse(
                {"success": False, "message": "Agent profile not found"}
            )

        setattr(profile, field, value)
        profile.save(update_fields=[field])
        return JsonResponse({"success": True})
    except Exception as e:
        logger.error(f"Error updating agent visibility: {e}")
        return JsonResponse({"success": False, "message": "Database error"})


@require_POST
def save_google_review_settings(request):
    """
    Agent endpoint: Save/update Google review URL, rating, count, place name,
    is_enabled status, and up to 5 reviews.
    """
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Authentication required."}, status=401
        )

    from apps.agents.services.account_auth import resolve_agent_for_user

    agent = (
        resolve_agent_for_user(request.user)
        or Agent.objects.filter(user=request.user).first()
    )
    if not agent:
        return JsonResponse(
            {"success": False, "message": "Agent profile not found."}, status=404
        )

    from apps.agents.services.google_review import (
        agent_can_use_google_reviews,
        get_agent_google_review_config,
        get_google_review_system_config,
    )
    from decimal import Decimal, InvalidOperation

    if not agent_can_use_google_reviews(agent):
        return JsonResponse(
            {
                "success": False,
                "message": "Your current plan does not include the Google Review feature. Please upgrade your plan.",
            },
            status=403,
        )

    cfg = get_agent_google_review_config(agent)
    if not cfg:
        return JsonResponse(
            {"success": False, "message": "Could not initialize Google review config."},
            status=500,
        )

    url = request.POST.get("google_review_url", "").strip()
    if url and not (url.startswith("http://") or url.startswith("https://")):
        return JsonResponse(
            {
                "success": False,
                "message": "Google review URL must start with http:// or https://.",
            },
            status=400,
        )
    is_enabled = request.POST.get("is_enabled") in ("1", "true", "on", True)
    rating_raw = request.POST.get("google_rating", "").strip()
    count_raw = request.POST.get("google_review_count", "").strip()
    place_name = request.POST.get("google_place_name", "").strip()

    # Parse rating (e.g. 4.8)
    google_rating = None
    if rating_raw:
        try:
            val = float(rating_raw)
            if 1.0 <= val <= 5.0:
                google_rating = Decimal(str(round(val, 1)))
        except (ValueError, TypeError, InvalidOperation):
            pass

    # Parse review count
    try:
        google_review_count = max(0, int(count_raw)) if count_raw else 0
    except (ValueError, TypeError):
        google_review_count = 0

    # Parse reviews array
    import json

    reviews_json_raw = request.POST.get("reviews_json")
    reviews_list = []
    if reviews_json_raw:
        try:
            parsed = json.loads(reviews_json_raw)
            if isinstance(parsed, list):
                reviews_list = parsed
        except Exception:
            pass

    if not reviews_list:
        authors = request.POST.getlist("review_author[]") or request.POST.getlist(
            "review_author"
        )
        ratings = request.POST.getlist("review_rating[]") or request.POST.getlist(
            "review_rating"
        )
        texts = request.POST.getlist("review_text[]") or request.POST.getlist(
            "review_text"
        )
        times = request.POST.getlist("review_time[]") or request.POST.getlist(
            "review_time"
        )

        for i in range(len(texts)):
            t = texts[i].strip() if i < len(texts) else ""
            if not t:
                continue
            a = authors[i].strip() if i < len(authors) and authors[i] else "Client"
            try:
                r_num = min(5, max(1, int(ratings[i]))) if i < len(ratings) else 5
            except (ValueError, TypeError):
                r_num = 5
            tm = times[i].strip() if i < len(times) and times[i] else ""
            reviews_list.append(
                {
                    "author": a,
                    "rating": r_num,
                    "text": t,
                    "time": tm,
                }
            )

    sys_cfg = get_google_review_system_config()
    max_reviews = sys_cfg.get("max_reviews_shown", 5)
    reviews_list = reviews_list[:max_reviews]

    cfg.google_review_url = url
    cfg.is_enabled = is_enabled
    cfg.google_rating = google_rating
    cfg.google_review_count = google_review_count
    cfg.google_place_name = place_name
    cfg.cached_reviews = reviews_list
    cfg.save()

    return JsonResponse(
        {
            "success": True,
            "message": "Google Review settings saved successfully!",
            "is_enabled": cfg.is_enabled,
            "review_count": len(reviews_list),
        }
    )


@require_POST
def toggle_agent_google_review(request):
    """Agent endpoint: Quick ON/OFF toggle for profile Google review display."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Authentication required."}, status=401
        )

    from apps.agents.services.account_auth import resolve_agent_for_user

    agent = (
        resolve_agent_for_user(request.user)
        or Agent.objects.filter(user=request.user).first()
    )
    if not agent:
        return JsonResponse(
            {"success": False, "message": "Agent profile not found."}, status=404
        )

    from apps.agents.services.google_review import (
        agent_can_use_google_reviews,
        get_agent_google_review_config,
    )

    if not agent_can_use_google_reviews(agent):
        return JsonResponse(
            {
                "success": False,
                "message": "Your current plan does not include the Google Review feature. Please upgrade your plan.",
            },
            status=403,
        )

    cfg = get_agent_google_review_config(agent)
    cfg.is_enabled = not cfg.is_enabled
    cfg.save(update_fields=["is_enabled", "updated_at"])

    status_str = "enabled" if cfg.is_enabled else "disabled"
    return JsonResponse(
        {
            "success": True,
            "is_enabled": cfg.is_enabled,
            "message": f"Google Reviews showcase is now {status_str} on your public profile.",
        }
    )


@require_POST
def track_google_review_click_view(request):
    """Public or client endpoint: Tracks when a user clicks 'Review on Google'."""
    agent_id = request.POST.get("agent_id")
    if not agent_id:
        import json

        try:
            body = json.loads(request.body.decode("utf-8"))
            agent_id = body.get("agent_id")
        except Exception:
            agent_id = None

    if not agent_id:
        return JsonResponse(
            {"success": False, "message": "Missing agent_id"}, status=400
        )

    try:
        from apps.agents.services.google_review import track_google_review_click

        clicks = track_google_review_click(int(agent_id))
        return JsonResponse({"success": True, "clicks": clicks})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)
