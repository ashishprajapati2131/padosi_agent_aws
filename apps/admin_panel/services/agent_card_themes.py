"""Admin-managed themes for the shared agent card (templates/partials/agent-card.html).

One SiteSetting row ('agent_card_themes') holds every saved theme plus the active
theme id. The built-in 'default' theme is the original card and is never stored.
Nothing changes on the site unless the 'agent_card_themes_enabled' feature flag is ON.

Every value is validated here (hex colours, clamped numbers, enums, short plain
labels, our own media path), because the card template prints them inside <style>.
"""

import json
import re
import time

from django.conf import settings

from apps.home.models.site_setting import SiteSetting

STORE_KEY = "agent_card_themes"
FLAG_KEY = "agent_card_themes_enabled"
DEFAULT_THEME_ID = "default"
DECORATION_DIR = "agent_card_themes/"

COLOR_FIELDS = (
    "card_bg",
    "card_bg2",
    "border_color",
    "name_color",
    "star_color",
    "stat_bg",
    "stat_num_color",
    "profile_btn_bg",
    "whatsapp_btn_bg",
    "call_btn_bg",
    "btn_text_color",
    "greeting_color",
)
SHOW_FIELDS = (
    "show_badges",
    "show_rating",
    "show_distance",
    "show_match",
    "show_stats",
    "show_tags",
    "show_compare",
    "show_save",
    "show_profile_btn",
    "show_whatsapp_btn",
    "show_call_btn",
)
# Defaults are the exact texts the card has always printed.
LABEL_DEFAULTS = {
    "label_profile_mobile": "Profile",
    "label_profile_desktop": "View Profile",
    "label_whatsapp": "WhatsApp",
    "label_call": "Call Now",
    "label_compare": "Compare",
    "label_save": "Save",
    "label_years": "YEARS",
    "label_clients": "CLIENTS",
    "label_claims": "CLAIMS",
    "label_settled": "SETTLED",
}
SHADOWS = ("default", "none", "soft", "strong")
DECORATION_POSITIONS = ("top-right", "top-left", "bottom-right", "bottom-left")
LABEL_MAX = 24
GREETING_TITLE_MAX = 40
GREETING_TEXT_MAX = 140
IMAGE_FIELDS = ("decoration_image", "background_image")
SHARE_LAYOUTS = ("classic", "festive")  # share image: original layout, or framed festival card

DEFAULT_DESIGN = {
    **{f: "" for f in COLOR_FIELDS},  # '' = keep the built-in colour
    "radius": None,  # None = keep built-in (14px)
    "border_width": None,  # None = keep built-in (1px)
    "shadow": "default",
    **{f: True for f in SHOW_FIELDS},
    **LABEL_DEFAULTS,
    "decoration_image": "",
    "decoration_position": "top-right",
    "decoration_size": 64,
    # Festival artwork: cover-fit behind the share image and the directory card.
    "background_image": "",
    "panel_opacity": 88,  # % white behind the text so it stays readable
    "greeting_title": "",
    "greeting_text": "",
    "share_layout": "classic",
}

# Starter themes the admin can add with one click and then edit.
PRESETS = {
    "diwali": {
        "name": "Diwali",
        "design": {
            "card_bg": "#fff8e7",
            "card_bg2": "#ffe9c2",
            "border_color": "#f59e0b",
            "name_color": "#1e1b4b",
            "star_color": "#f59e0b",
            "stat_bg": "#fff3d6",
            "stat_num_color": "#9a3412",
            "profile_btn_bg": "#7c2d12",
            "whatsapp_btn_bg": "#16a34a",
            "call_btn_bg": "#b45309",
            "btn_text_color": "#ffffff",
            "radius": 16,
            "border_width": 2,
            "shadow": "soft",
            "greeting_title": "Happy Diwali",
            "greeting_text": "May this Diwali bring good health, happiness, prosperity and financial security to you and your family.",
            "greeting_color": "#c2410c",
            "panel_opacity": 80,
            "share_layout": "festive",
        },
        "assets": {
            "background_image": "img/card_themes/diwali_bg.jpg",
            "decoration_image": "img/card_themes/diwali_diya.png",
        },
    },
    "holi": {
        "name": "Holi",
        "design": {
            "card_bg": "#fdf2f8",
            "card_bg2": "#ecfeff",
            "border_color": "#db2777",
            "name_color": "#6d28d9",
            "star_color": "#f97316",
            "stat_bg": "#fef9c3",
            "stat_num_color": "#be185d",
            "profile_btn_bg": "#7c3aed",
            "whatsapp_btn_bg": "#16a34a",
            "call_btn_bg": "#db2777",
            "btn_text_color": "#ffffff",
            "radius": 18,
            "border_width": 2,
            "shadow": "soft",
            "greeting_title": "Happy Holi",
            "greeting_text": "Wishing you a colourful, safe and secure Holi with your loved ones.",
            "greeting_color": "#be185d",
            "panel_opacity": 80,
        },
    },
}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_THEME_ID = re.compile(r"^[a-z0-9-]{1,40}$")
_MEDIA_PATH = re.compile(r"^agent_card_themes/[A-Za-z0-9_-]+\.(png|jpe?g|webp|gif)$")


def _bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "on", "yes")


def _int(v, lo, hi):
    if v in (None, ""):
        return None
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return None


def _label(v, default, max_len=LABEL_MAX):
    # Plain short text only; the template autoescapes it as well.
    text = re.sub(r"[<>{}\\]", "", str(v or "")).strip()[:max_len]
    return text or default


def sanitize_design(raw):
    """Return a complete, safe design dict from any (untrusted) input dict."""
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULT_DESIGN)
    for f in COLOR_FIELDS:
        v = str(raw.get(f) or "").strip()
        out[f] = v.lower() if _HEX.match(v) else ""
    out["radius"] = _int(raw.get("radius"), 0, 32)
    out["border_width"] = _int(raw.get("border_width"), 0, 4)
    out["shadow"] = raw.get("shadow") if raw.get("shadow") in SHADOWS else "default"
    for f in SHOW_FIELDS:
        out[f] = _bool(raw[f]) if f in raw else True
    for f, default in LABEL_DEFAULTS.items():
        out[f] = _label(raw.get(f), default)
    for f in IMAGE_FIELDS:
        img = str(raw.get(f) or "").strip()
        out[f] = img if _MEDIA_PATH.match(img) else ""
    pos = raw.get("decoration_position")
    out["decoration_position"] = pos if pos in DECORATION_POSITIONS else "top-right"
    out["decoration_size"] = _int(raw.get("decoration_size"), 24, 160) or 64
    out["panel_opacity"] = _int(raw.get("panel_opacity"), 50, 100) or 88
    out["greeting_title"] = _label(raw.get("greeting_title"), "", GREETING_TITLE_MAX)
    out["greeting_text"] = _label(raw.get("greeting_text"), "", GREETING_TEXT_MAX)
    out["share_layout"] = raw.get("share_layout") if raw.get("share_layout") in SHARE_LAYOUTS else "classic"
    return out


def _rgb_csv(hex_color):
    """'#rrggbb' -> 'r,g,b' for rgba() in CSS ('' when unset)."""
    if not hex_color:
        return ""
    return ",".join(str(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))


def _clean_name(name):
    return re.sub(r"[<>{}\\]", "", str(name or "")).strip()[:60]


def get_store():
    store = SiteSetting.get_value(STORE_KEY, None)
    if not isinstance(store, dict):
        store = {}
    themes = [
        t
        for t in store.get("themes") or []
        if isinstance(t, dict) and _THEME_ID.match(str(t.get("id", "")))
    ]
    active = store.get("active")
    if active != DEFAULT_THEME_ID and not any(t["id"] == active for t in themes):
        active = DEFAULT_THEME_ID
    return {"active": active, "themes": themes}


def _save_store(store):
    SiteSetting.set_value(STORE_KEY, store, group="agents")


def get_theme(theme_id):
    return next((t for t in get_store()["themes"] if t["id"] == theme_id), None)


def _new_id(name, existing):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "theme"
    tid, n = base, 2
    while tid in existing or tid == DEFAULT_THEME_ID:
        tid, n = f"{base}-{n}", n + 1
    return tid


def save_theme(name, design, theme_id=None):
    """Create (theme_id=None) or update a theme. Returns the theme id."""
    name = _clean_name(name)
    if not name:
        raise ValueError("Theme name is required.")
    store = get_store()
    ids = {t["id"] for t in store["themes"]}
    design = sanitize_design(design)
    if theme_id:
        theme = next((t for t in store["themes"] if t["id"] == theme_id), None)
        if not theme:
            raise ValueError("Theme not found.")
        theme.update(name=name, design=design, updated_at=int(time.time()))
    else:
        theme_id = _new_id(name, ids)
        store["themes"].append(
            {
                "id": theme_id,
                "name": name,
                "design": design,
                "updated_at": int(time.time()),
            }
        )
    _save_store(store)
    return theme_id


def delete_theme(theme_id):
    """Remove a theme; falls back to the default card if it was active.
    Returns the deleted theme's image paths so the caller can remove the files."""
    store = get_store()
    theme = next((t for t in store["themes"] if t["id"] == theme_id), None)
    if not theme:
        raise ValueError("Theme not found.")
    store["themes"].remove(theme)
    if store["active"] == theme_id:
        store["active"] = DEFAULT_THEME_ID
    _save_store(store)
    return [theme["design"].get(f) for f in IMAGE_FIELDS if theme["design"].get(f)]


def set_active(theme_id):
    store = get_store()
    if theme_id != DEFAULT_THEME_ID and not any(
        t["id"] == theme_id for t in store["themes"]
    ):
        raise ValueError("Theme not found.")
    store["active"] = theme_id
    _save_store(store)


def add_preset(preset_key):
    """Add a starter theme; its bundled sample images are copied into media so the
    theme owns them like uploaded ones (edit or delete without touching static files)."""
    import os

    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    preset = PRESETS.get(preset_key)
    if not preset:
        raise ValueError("Unknown preset.")
    design = dict(preset["design"])
    for field, static_rel in preset.get("assets", {}).items():
        src = os.path.join(settings.BASE_DIR, "static", *static_rel.split("/"))
        if os.path.isfile(src):
            with open(src, "rb") as fh:
                ext = os.path.splitext(src)[1]
                design[field] = default_storage.save(
                    f"{DECORATION_DIR}{preset_key}_{field.split('_')[0]}_{int(time.time())}{ext}", ContentFile(fh.read())
                )
    return save_theme(preset["name"], design)


def export_theme(theme_id):
    theme = get_theme(theme_id)
    if not theme:
        raise ValueError("Theme not found.")
    design = dict(theme["design"])
    for f in IMAGE_FIELDS:
        design[f] = ""  # image files are not part of the JSON file
    return {"padosi_agent_card_theme": 1, "name": theme["name"], "design": design}


def import_theme(raw_bytes):
    """Create a theme from an exported JSON file. Returns the new theme id."""
    if not raw_bytes or len(raw_bytes) > 64 * 1024:
        raise ValueError("Theme file must be a JSON file under 64 KB.")
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Theme file is not valid JSON.")
    if not isinstance(data, dict) or not isinstance(data.get("design"), dict):
        raise ValueError('Theme file has no "design" section.')
    design = {k: v for k, v in data["design"].items() if k not in IMAGE_FIELDS}
    return save_theme(data.get("name") or "Imported theme", design)


def is_enabled():
    # Same value is_feature_enabled() returns for this system flag, but one settings
    # read instead of building every flag (this runs on every Find Agents request).
    from apps.admin_panel.services.feature_flags import _parse_bool_value

    return _parse_bool_value(SiteSetting.get_value(FLAG_KEY, None), False)


def build_card_theme(design, enabled=True):
    """Template-ready dict for the card: the design plus derived values."""
    d = sanitize_design(design)
    d["enabled"] = enabled and d != DEFAULT_DESIGN
    d["decoration_url"] = (
        (settings.MEDIA_URL + d["decoration_image"]) if d["decoration_image"] else ""
    )
    d["background_url"] = (
        (settings.MEDIA_URL + d["background_image"]) if d["background_image"] else ""
    )
    d["panel_alpha"] = "%.2f" % (d["panel_opacity"] / 100)  # string: never locale-formatted in CSS
    # Over a background image the card colours become the see-through tint (white if unset).
    d["tint1"] = _rgb_csv(d["card_bg"]) or "255,255,255"
    d["tint2"] = _rgb_csv(d["card_bg2"]) or d["tint1"]
    return d


def get_active_card_theme():
    """Theme for the live site; the untouched default card when the flag is OFF."""
    if not is_enabled():
        return build_card_theme({}, enabled=False)
    store = get_store()
    theme = next((t for t in store["themes"] if t["id"] == store["active"]), None)
    return build_card_theme(theme["design"] if theme else {})


def share_theme_signature(theme=None):
    """Short id of what the active theme changes on the share image ('' = original
    image). Part of the share-image cache key and URL so a theme switch refreshes it."""
    import hashlib

    theme = theme or get_active_card_theme()
    if not theme.get("enabled"):
        return ""
    keys = ("background_image", "panel_opacity", "greeting_title", "greeting_text", "greeting_color", "name_color",
            "share_layout", "decoration_image")
    if not any(theme.get(k) and theme.get(k) != DEFAULT_DESIGN[k] for k in keys):
        return ""
    raw = json.dumps({k: theme.get(k) for k in keys}, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def image_file_path(rel):
    """Absolute path of one of our theme images (validated media path), or None."""
    import os

    rel = rel or ""
    if not _MEDIA_PATH.match(rel):
        return None
    path = os.path.join(settings.MEDIA_ROOT, rel.replace("/", os.sep))
    return path if os.path.isfile(path) else None


def background_file_path(theme):
    return image_file_path((theme or {}).get("background_image"))
