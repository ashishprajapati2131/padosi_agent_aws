"""Admin: Agent Card Themes — design the shared agent card (Find Agents, city pages,
agent dashboard preview) and switch festival themes, behind the
'agent_card_themes_enabled' feature flag. Logic lives in services/agent_card_themes.py."""

import base64
import io
import json
import time

from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.views.decorators.http import require_POST

from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.admin_panel.services import agent_card_themes as svc
from apps.admin_panel.services.feature_flags import set_feature_flag_status
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.agents.utils.file_validation import validate_profile_photo

INDEX = "admin_agent_card_themes"
DECORATION_MAX_BYTES = 2 * 1024 * 1024
BACKGROUND_MAX_BYTES = 5 * 1024 * 1024  # validate_profile_photo also caps at 5 MB


def _design_from_post(post, current=None):
    """Form fields -> raw design dict (validated later by svc.sanitize_design)."""
    raw = {}
    for f in svc.COLOR_FIELDS:
        raw[f] = "" if post.get(f + "_default") else post.get(f, "")
    for f in svc.SHOW_FIELDS:
        raw[f] = post.get(f) == "1"
    for f in svc.LABEL_DEFAULTS:
        raw[f] = post.get(f, "")
    for f in (
        "radius",
        "border_width",
        "shadow",
        "decoration_position",
        "decoration_size",
        "panel_opacity",
        "greeting_title",
        "greeting_text",
        "share_layout",
    ):
        raw[f] = post.get(f, "")
    current = current or {}
    raw["decoration_image"] = "" if post.get("remove_decoration") else current.get("decoration_image", "")
    raw["background_image"] = "" if post.get("remove_background") else current.get("background_image", "")
    return raw


def _save_decoration(upload, name):
    """Validate (Pillow, raster only) and store a festival decoration image."""
    data = b"".join(upload.chunks())
    if len(data) > DECORATION_MAX_BYTES:
        raise ValueError("Decoration image must be under 2 MB.")
    ok, err, ext = validate_profile_photo(data, upload.name)
    if not ok:
        raise ValueError(err or "Invalid image file.")
    slug = "".join(c if c.isalnum() else "_" for c in name.lower())[:30] or "theme"
    return default_storage.save(
        f"{svc.DECORATION_DIR}{slug}_{int(time.time())}{ext}", ContentFile(data)
    )


def _save_background(upload, name):
    """Validate a festival artwork upload and store it cover-fitted to 1200x630 (any size works)."""
    from PIL import Image

    from apps.agents.services.og_image import _cover_crop

    data = b"".join(upload.chunks())
    if len(data) > BACKGROUND_MAX_BYTES:
        raise ValueError("Background image must be under 5 MB.")
    ok, err, _ext = validate_profile_photo(data, upload.name)
    if not ok:
        raise ValueError(err or "Invalid image file.")
    img = Image.open(io.BytesIO(data))
    img.seek(0)  # first frame of an animated GIF
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, (255, 255, 255))
        flat.paste(img, mask=img.split()[-1])
        img = flat
    out = io.BytesIO()
    _cover_crop(img.convert("RGB"), 1200, 630).save(out, "JPEG", quality=86, optimize=True)
    slug = "".join(c if c.isalnum() else "_" for c in name.lower())[:30] or "theme"
    return default_storage.save(
        f"{svc.DECORATION_DIR}{slug}_bg_{int(time.time())}.jpg", ContentFile(out.getvalue())
    )


def _delete_file(path):
    try:
        if (
            path
            and path.startswith(svc.DECORATION_DIR)
            and default_storage.exists(path)
        ):
            default_storage.delete(path)
    except Exception:
        pass


COLOR_LABELS = {
    "card_bg": "Card background",
    "card_bg2": "Background gradient end (optional)",
    "border_color": "Border",
    "name_color": "Agent name",
    "star_color": "Rating stars",
    "stat_bg": "Stat boxes background",
    "stat_num_color": "Stat numbers",
    "profile_btn_bg": "Profile button",
    "whatsapp_btn_bg": "WhatsApp button",
    "call_btn_bg": "Call button",
    "btn_text_color": "Button text",
    "greeting_color": "Greeting title (share image)",
}
# Colours the card uses today (agent-card-shared.css); shown in the picker when "Default" is ticked.
BUILTIN_COLORS = {
    "card_bg": "#ffffff", "card_bg2": "#ffffff", "border_color": "#e5e7eb", "name_color": "#111827",
    "star_color": "#f59e0b", "stat_bg": "#f8fafc", "stat_num_color": "#111827",
    "profile_btn_bg": "#1e3a8a", "whatsapp_btn_bg": "#22c55e", "call_btn_bg": "#1d4ed8", "btn_text_color": "#ffffff",
    "greeting_color": "#c2410c",
}
SHOW_LABELS = {
    "show_badges": "Badges (Verified / Licensed / Trusted)",
    "show_rating": "Rating stars",
    "show_distance": "Distance (km away)",
    "show_match": "Match %",
    "show_stats": "Stats (years, clients, claims)",
    "show_tags": "Insurance type tags",
    "show_compare": "Compare button",
    "show_save": "Save / favourite button",
    "show_profile_btn": "Profile button",
    "show_whatsapp_btn": "WhatsApp button",
    "show_call_btn": "Call button",
}


def _sample_agent():
    from apps.agents.models import Agent

    agent = (
        Agent.objects.filter(
            status="active", profile__isnull=False, is_blacklisted=False
        )
        .select_related("profile")
        .order_by("-id")
        .first()
    )
    if agent:
        agent.distance = 2.5  # show the distance pill in the preview
    return agent


def agent_card_themes_index(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    store = svc.get_store()
    edit_id = request.GET.get("edit")
    editing = svc.get_theme(edit_id) if edit_id else None
    if request.GET.get("new"):
        editing = {"id": "", "name": "", "design": dict(svc.DEFAULT_DESIGN)}
    rows = {}
    if editing:
        d = svc.build_card_theme(editing["design"])
        editing = dict(editing, design=d)
        # The template cannot index a dict by a variable, so hand it ready rows.
        rows = {
            "color_rows": [(f, COLOR_LABELS[f], d[f], BUILTIN_COLORS[f]) for f in svc.COLOR_FIELDS],
            "show_rows": [(f, SHOW_LABELS[f], d[f]) for f in svc.SHOW_FIELDS],
            "label_rows": [
                (f, default, d[f]) for f, default in svc.LABEL_DEFAULTS.items()
            ],
        }
    return render(
        request,
        "admin/agent_card_themes/index.html",
        {
            **rows,
            "flag_enabled": svc.is_enabled(),
            "active_id": store["active"],
            "themes": store["themes"],
            "presets": svc.PRESETS,
            "editing": editing,
            "shadows": svc.SHADOWS,
            "positions": svc.DECORATION_POSITIONS,
            "share_layouts": svc.SHARE_LAYOUTS,
            "has_sample_agent": _sample_agent() is not None,
        },
    )


@require_POST
def agent_card_theme_save(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    theme_id = request.POST.get("theme_id") or None
    name = request.POST.get("name", "")
    current = (
        svc.get_theme(theme_id)["design"]
        if theme_id and svc.get_theme(theme_id)
        else {}
    )
    design = _design_from_post(request.POST, current)
    new_files = []
    try:
        for field, upload_name, saver in (
            ("decoration_image", "decoration_file", _save_decoration),
            ("background_image", "background_file", _save_background),
        ):
            if request.FILES.get(upload_name):
                design[field] = saver(request.FILES[upload_name], name)
                new_files.append(design[field])
        theme_id = svc.save_theme(name, design, theme_id)
    except ValueError as exc:
        for path in new_files:
            _delete_file(path)
        messages.error(request, str(exc))
        return redirect(
            f"/admin/agent-card-themes/?{'edit=' + theme_id if theme_id else 'new=1'}"
        )
    saved = svc.get_theme(theme_id)["design"]
    for field in svc.IMAGE_FIELDS:
        if current.get(field) and current[field] != saved[field]:
            _delete_file(current[field])
    AdminActivityLog.log(
        f"Saved agent card theme '{svc.get_theme(theme_id)['name']}'",
        "SiteSetting",
        request=request,
    )
    messages.success(request, "Theme saved.")
    return redirect(f"/admin/agent-card-themes/?edit={theme_id}")


@require_POST
def agent_card_theme_activate(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    theme_id = request.POST.get("theme_id", "")
    try:
        svc.set_active(theme_id)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(INDEX)
    AdminActivityLog.log(
        f"Activated agent card theme '{theme_id}'", "SiteSetting", request=request
    )
    messages.success(
        request,
        "Active theme updated."
        + ("" if svc.is_enabled() else " Turn the feature ON to show it on the site."),
    )
    return redirect(INDEX)


@require_POST
def agent_card_theme_delete(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    theme_id = request.POST.get("theme_id", "")
    try:
        for path in svc.delete_theme(theme_id):
            _delete_file(path)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(INDEX)
    AdminActivityLog.log(
        f"Deleted agent card theme '{theme_id}'", "SiteSetting", request=request
    )
    messages.success(request, "Theme deleted.")
    return redirect(INDEX)


@require_POST
def agent_card_theme_preset(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    try:
        theme_id = svc.add_preset(request.POST.get("preset", ""))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(INDEX)
    AdminActivityLog.log(
        f"Added agent card theme preset '{theme_id}'", "SiteSetting", request=request
    )
    messages.success(request, "Preset added. Edit it below, then activate it.")
    return redirect(f"/admin/agent-card-themes/?edit={theme_id}")


@require_POST
def agent_card_theme_import(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    upload = request.FILES.get("theme_file")
    is_json = bool(upload) and (
        upload.name.lower().endswith(".json") or "json" in (upload.content_type or "")
    )
    new_file = None
    try:
        if not upload:
            raise ValueError("Choose a festival image or a theme .json file.")
        if is_json:
            theme_id = svc.import_theme(upload.read(64 * 1024 + 1))
        else:
            # A festival image becomes a new theme with that image as its background.
            name = request.POST.get("name", "").strip() or upload.name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
            new_file = _save_background(upload, name)
            theme_id = svc.save_theme(name, {"background_image": new_file, "panel_opacity": 80})
    except ValueError as exc:
        _delete_file(new_file)
        messages.error(request, str(exc))
        return redirect(INDEX)
    AdminActivityLog.log(
        f"Imported agent card theme '{theme_id}'", "SiteSetting", request=request
    )
    messages.success(
        request,
        "Theme imported. Add a decoration image if you want, then activate it."
        if is_json
        else "Image uploaded and fitted to the card. Add a greeting (e.g. Happy Diwali), Save, then Activate.",
    )
    return redirect(f"/admin/agent-card-themes/?edit={theme_id}")


def agent_card_theme_export(request, theme_id):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    try:
        data = svc.export_theme(theme_id)
    except ValueError:
        messages.error(request, "Theme not found.")
        return redirect(INDEX)
    resp = HttpResponse(json.dumps(data, indent=2), content_type="application/json")
    resp["Content-Disposition"] = (
        f'attachment; filename="agent-card-theme-{theme_id}.json"'
    )
    return resp


@require_POST
def agent_card_theme_flag(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    set_feature_flag_status(
        svc.FLAG_KEY, request.POST.get("enabled") == "1", request=request
    )
    messages.success(
        request,
        "Agent card themes turned "
        + ("ON." if svc.is_enabled() else "OFF — the original card is shown."),
    )
    return redirect(INDEX)


@require_POST
def agent_card_theme_preview(request):
    """Render the real shared card with the draft design (unsaved) for the editor iframe."""
    if not _get_admin_from_session(request):
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=403)
    agent = _sample_agent()
    if not agent:
        return HttpResponse(
            '<p style="font-family:sans-serif;color:#64748b">Add at least one active agent to see a preview.</p>'
        )
    theme_id = request.POST.get("theme_id") or None
    current = (
        svc.get_theme(theme_id)["design"]
        if theme_id and svc.get_theme(theme_id)
        else {}
    )
    theme = svc.build_card_theme(_design_from_post(request.POST, current))
    # A find-agents style request so the match pill shows; no real visitor data.
    fake = RequestFactory().get("/find-agents/?pincode=380001")
    fake.user, fake.session = AnonymousUser(), {}
    card = render_to_string(
        "partials/agent-card.html",
        {
            "agent": agent,
            "favorite_ids": [],
            "agent_card_theme_override": theme,
        },
        request=fake,
    )
    from apps.agents.services.og_image import _render_agent_og_jpeg_pillow

    share = _render_agent_og_jpeg_pillow(agent, theme=theme if svc.share_theme_signature(theme) else None)
    return render(request, "admin/agent_card_themes/preview.html", {
        "card": card,
        "share_img": "data:image/jpeg;base64," + base64.b64encode(share).decode("ascii"),
    })
