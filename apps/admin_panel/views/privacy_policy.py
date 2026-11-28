"""Admin CRUD for the public privacy policy (/privacy/)."""
from datetime import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.home.html_sanitizer import sanitize_html
from apps.home.models.privacy_policy import PrivacyPolicy
from apps.home.privacy_content import (
    ADDRESS,
    COMPANY_NAME,
    CONTACT_EMAIL,
    DEFAULT_PRIVACY_BODY,
    EFFECTIVE_DATE,
    GRIEVANCE_EMAIL,
)


def _blank_policy():
    return {
        "title": "Privacy Policy",
        "effective_date": EFFECTIVE_DATE.isoformat(),
        "company_name": COMPANY_NAME,
        "address": ADDRESS,
        "contact_email": CONTACT_EMAIL,
        "grievance_email": GRIEVANCE_EMAIL,
        "content": DEFAULT_PRIVACY_BODY,
        "is_published": True,
    }


def _publish_policy(policy):
    """Make this the only live policy. The previous live one becomes a draft."""
    with transaction.atomic():
        PrivacyPolicy.objects.exclude(pk=policy.pk).update(is_published=False)
        if not policy.is_published:
            policy.is_published = True
            policy.save(update_fields=["is_published", "updated_at"])


def _policy_form(policy):
    return {
        "title": policy.title,
        "effective_date": policy.effective_date.isoformat(),
        "company_name": policy.company_name,
        "address": policy.address,
        "contact_email": policy.contact_email,
        "grievance_email": policy.grievance_email,
        "content": policy.content,
        "is_published": policy.is_published,
    }


def _clean_post(request):
    title = request.POST.get("title", "").strip()
    company_name = request.POST.get("company_name", "").strip()
    address = request.POST.get("address", "").strip()
    contact_email = request.POST.get("contact_email", "").strip()
    grievance_email = request.POST.get("grievance_email", "").strip()
    content = sanitize_html(request.POST.get("content", "")).strip()
    raw_date = request.POST.get("effective_date", "").strip()
    is_published = "is_published" in request.POST

    if not title:
        return None, "Title is required."
    if len(title) > 255:
        return None, "Title must be 255 characters or fewer."
    if not company_name or len(company_name) > 255:
        return None, "Company name is required and must be 255 characters or fewer."
    if not address or len(address) > 500:
        return None, "Address is required and must be 500 characters or fewer."
    for label, value in (("Contact email", contact_email), ("Grievance email", grievance_email)):
        try:
            validate_email(value)
        except ValidationError:
            return None, f"{label} is not a valid email address."
    try:
        effective_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return None, "Effective date is required."
    if not content:
        return None, "Policy text is required."

    return {
        "title": title,
        "company_name": company_name,
        "address": address,
        "contact_email": contact_email,
        "grievance_email": grievance_email,
        "effective_date": effective_date,
        "content": content,
        "is_published": is_published,
    }, None


def _render_form(request, policy, form):
    return render(request, "admin/privacy/form.html", {"policy": policy, "form": form})


def privacy_index(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")
    policies = PrivacyPolicy.objects.all()
    return render(request, "admin/privacy/index.html", {
        "policies": policies,
        "has_published": policies.filter(is_published=True).exists(),
    })


def privacy_create(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")
    return _render_form(request, None, _blank_policy())


def privacy_store(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")
    if request.method != "POST":
        return redirect("admin_privacy_policies")

    cleaned, error = _clean_post(request)
    if error:
        messages.error(request, error)
        posted = _blank_policy()
        posted.update({k: request.POST.get(k, posted.get(k, "")) for k in posted})
        posted["is_published"] = "is_published" in request.POST
        return _render_form(request, None, posted)

    with transaction.atomic():
        policy = PrivacyPolicy.objects.create(**cleaned)
        if policy.is_published:
            _publish_policy(policy)
    AdminActivityLog.log(
        f"Created privacy policy #{policy.id}: {policy.title}",
        "PrivacyPolicy",
        model_id=policy.id,
        request=request,
    )
    if policy.is_published:
        messages.success(request, "Privacy policy published. It is now the page at /privacy/.")
    else:
        messages.success(request, "Privacy policy saved as a draft.")
    return redirect("admin_privacy_policies")


def privacy_edit(request, policy_id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")
    policy = get_object_or_404(PrivacyPolicy, id=policy_id)
    return _render_form(request, policy, _policy_form(policy))


def privacy_update(request, policy_id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")
    policy = get_object_or_404(PrivacyPolicy, id=policy_id)
    if request.method != "POST":
        return redirect("admin_privacy_policies")

    cleaned, error = _clean_post(request)
    if error:
        messages.error(request, error)
        return _render_form(request, policy, {
            **_policy_form(policy),
            "title": request.POST.get("title", ""),
            "effective_date": request.POST.get("effective_date", ""),
            "company_name": request.POST.get("company_name", ""),
            "address": request.POST.get("address", ""),
            "contact_email": request.POST.get("contact_email", ""),
            "grievance_email": request.POST.get("grievance_email", ""),
            "content": request.POST.get("content", ""),
            "is_published": "is_published" in request.POST,
        })

    with transaction.atomic():
        for key, value in cleaned.items():
            setattr(policy, key, value)
        policy.save()
        if policy.is_published:
            _publish_policy(policy)
    AdminActivityLog.log(
        f"Updated privacy policy #{policy.id}: {policy.title}",
        "PrivacyPolicy",
        model_id=policy.id,
        request=request,
    )
    if policy.is_published:
        messages.success(request, "Privacy policy updated and published.")
    else:
        messages.success(request, "Privacy policy updated and kept as a draft.")
    return redirect("admin_privacy_policies")


def privacy_publish(request, policy_id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")
    policy = get_object_or_404(PrivacyPolicy, id=policy_id)
    if request.method != "POST":
        return redirect("admin_privacy_policies")
    _publish_policy(policy)
    AdminActivityLog.log(
        f"Published privacy policy #{policy.id}: {policy.title}",
        "PrivacyPolicy",
        model_id=policy.id,
        request=request,
    )
    messages.success(request, f"“{policy.title}” is now the live privacy policy.")
    return redirect("admin_privacy_policies")


def privacy_delete(request, policy_id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")
    policy = get_object_or_404(PrivacyPolicy, id=policy_id)
    if request.method != "POST":
        return redirect("admin_privacy_policies")

    title = policy.title
    was_published = policy.is_published
    policy_pk = policy.pk
    with transaction.atomic():
        policy.delete()
        if was_published:
            nxt = PrivacyPolicy.objects.order_by("-updated_at", "-id").first()
            if nxt is not None:
                PrivacyPolicy.objects.exclude(pk=nxt.pk).update(is_published=False)
                nxt.is_published = True
                nxt.save(update_fields=["is_published", "updated_at"])
    AdminActivityLog.log(
        f"Deleted privacy policy #{policy_pk}: {title}",
        "PrivacyPolicy",
        model_id=policy_pk,
        request=request,
    )
    if was_published and PrivacyPolicy.objects.filter(is_published=True).exists():
        messages.success(request, "Published policy deleted. The newest remaining policy is now live.")
    elif was_published:
        messages.success(request, "Published policy deleted. The public page is using the built-in policy.")
    else:
        messages.success(request, "Draft privacy policy deleted.")
    return redirect("admin_privacy_policies")
