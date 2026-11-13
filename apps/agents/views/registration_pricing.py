"""Plan pricing: default tiers, plan UI features, scratch-card popup, GST/money helpers and checkout totals."""

from decimal import Decimal, ROUND_HALF_UP
from apps.agents.services.feature_unlock import PLAN_LABELS


_DEFAULT_PRICING = {
    "scratch_card_enabled": True,
    "social_discount_active": True,
    "social_discount_amount": 200,
    "starter": {
        "name": PLAN_LABELS["starter"],
        "full_price": 1999,
        "promo_price": 1499,
        "scratch_price": 1299,
        "description": "Perfect for New Agents",
        "badge": "STANDARD",
        "scratch_text": "SCRATCH",
        "scratch_enabled": True,
    },
    "professional": {
        "name": PLAN_LABELS["professional"],
        "full_price": 9999,
        "promo_price": 7999,
        "scratch_price": 7799,
        "description": "For Established Professionals",
        "badge": "RECOMMENDED",
        "scratch_text": "SCRATCH",
        "scratch_enabled": True,
    },
    "promo_discount_label": "Partner Promo Applied! Once in a lifetime offer!",
    "standard_label": "Get started with our standard partner plans",
    "choose_plan_heading": "Start your digital journey",
    "comparison_price_display": "original",
    "social_links": [
        {
            "platform": "Instagram",
            "url": "https://instagram.com/padosiagent",
            "icon": "fa-instagram",
        },
        {
            "platform": "Facebook",
            "url": "https://facebook.com/padosiagent",
            "icon": "fa-facebook",
        },
        {
            "platform": "YouTube",
            "url": "https://youtube.com/@padosiagent",
            "icon": "fa-youtube",
        },
        {
            "platform": "LinkedIn",
            "url": "https://linkedin.com/company/padosiagent",
            "icon": "fa-linkedin",
        },
    ],
    "follow_tiers": [
        {
            "follows": 1,
            "discount_amount": 100,
            "starter_discount": 100,
            "prof_discount": 100,
            "starter_price": 1399,
            "prof_price": 7899,
        },
        {
            "follows": 2,
            "discount_amount": 200,
            "starter_discount": 200,
            "prof_discount": 200,
            "starter_price": 1299,
            "prof_price": 7799,
        },
        {
            "follows": 3,
            "discount_amount": 300,
            "starter_discount": 300,
            "prof_discount": 300,
            "starter_price": 1199,
            "prof_price": 7699,
        },
        {
            "follows": 4,
            "discount_amount": 500,
            "starter_discount": 500,
            "prof_discount": 500,
            "starter_price": 999,
            "prof_price": 7499,
        },
    ],
}


_STARTER_PLAN_UI_FEATURES = [
    {
        "name": "Permanent<br>Webpage",
        "icon": "fa-globe",
        "color": "#16a34a",
        "bg_color": "#f0fdf4",
    },
    {
        "name": "Professional<br>Digital Card",
        "icon": "fa-id-card-clip",
        "color": "#6d28d9",
        "bg_color": "#f3e8ff",
    },
    {
        "name": "Licensed<br>Badge",
        "icon": "fa-shield-halved",
        "color": "#f59e0b",
        "bg_color": "#fffbeb",
    },
    {
        "name": "Call & WhatsApp<br>Buttons",
        "icon": "fa-phone",
        "color": "#16a34a",
        "bg_color": "#f0fdf4",
    },
    {
        "name": "Customer Review<br>& Rating",
        "icon": "fa-star",
        "color": "#6d28d9",
        "bg_color": "#f3e8ff",
    },
    {
        "name": "Profile<br>QR",
        "icon": "fa-qrcode",
        "color": "#3b82f6",
        "bg_color": "#eff6ff",
    },
    {
        "name": "Review & Rating<br>QR",
        "icon": "fa-comment-dots",
        "color": "#0d9488",
        "bg_color": "#f0fdfa",
    },
    {
        "name": "Product<br>Showcase",
        "icon": "fa-store",
        "color": "#3b82f6",
        "bg_color": "#eff6ff",
    },
    {
        "name": "Visibility in Your<br>Pin Code",
        "icon": "fa-location-dot",
        "color": "#e11d48",
        "bg_color": "#fff1f2",
    },
    {
        "name": "Downloadable<br>Digital Card",
        "icon": "fa-download",
        "color": "#6366f1",
        "bg_color": "#eef2ff",
    },
    {
        "name": "New Business<br>Leads",
        "icon": "fa-user-plus",
        "color": "#16a34a",
        "bg_color": "#f0fdf4",
    },
]


_PROFESSIONAL_PLAN_UI_FEATURES = [
    {
        "name": "Trusted<br>Badge",
        "icon": "fa-award",
        "color": "#f59e0b",
        "bg_color": "#fffbeb",
    },
    {
        "name": "Lead<br>Preferences",
        "icon": "fa-filter",
        "color": "#6366f1",
        "bg_color": "#eef2ff",
    },
    {
        "name": "SEO - Google<br>will know you",
        "icon": "fa-magnifying-glass",
        "color": "#3b82f6",
        "bg_color": "#eff6ff",
    },
    {
        "name": "AIO &<br>GEO",
        "icon": "fa-robot",
        "color": "#6d28d9",
        "bg_color": "#f3e8ff",
    },
    {
        "name": "Profile<br>Analytics",
        "icon": "fa-chart-column",
        "color": "#0d9488",
        "bg_color": "#f0fdfa",
    },
    {"name": "Gallery", "icon": "fa-images", "color": "#e11d48", "bg_color": "#fff1f2"},
    {
        "name": "AI Auto-fill &<br>Suggestions",
        "icon": "fa-wand-magic-sparkles",
        "color": "#8b5cf6",
        "bg_color": "#f5f3ff",
    },
]


_PLAN_COMPARISON_ROWS = [
    {"name": "Permanent Webpage", "starter": True, "professional": True},
    {"name": "Professional Digital Card", "starter": True, "professional": True},
    {"name": "Licensed Badge", "starter": True, "professional": True},
    {"name": "Call & WhatsApp Buttons", "starter": True, "professional": True},
    {"name": "Customer Review & Rating", "starter": True, "professional": True},
    {"name": "Profile QR", "starter": True, "professional": True},
    {"name": "Review & Rating QR", "starter": True, "professional": True},
    {"name": "Product Showcase", "starter": True, "professional": True},
    {"name": "Visibility in Your Pin Code", "starter": True, "professional": True},
    {"name": "Downloadable Digital Card", "starter": True, "professional": True},
    {"name": "New Business Leads", "starter": True, "professional": "priority"},
    {"name": "Trusted Badge", "starter": False, "professional": True},
    {"name": "Lead Preferences", "starter": False, "professional": True},
    {"name": "SEO – Google will know you", "starter": False, "professional": True},
    {"name": "AIO & GEO", "starter": False, "professional": True},
    {"name": "Profile Analytics", "starter": False, "professional": True},
    {"name": "Gallery", "starter": False, "professional": True},
    {"name": "AI Auto-fill & Suggestions", "starter": False, "professional": True},
]


_DEFAULT_SCRATCH_POPUP = {
    "overlay_bg": "rgba(15, 23, 42, 0.85)",
    "overlay_blur_px": 4,
    "modal_bg": "#ffffff",
    "modal_border_color": "#7c3aed",
    "modal_border_width_px": 3,
    "modal_radius_px": 28,
    "modal_shadow": "0 18px 50px rgba(88, 28, 135, 0.22)",
    "close_btn_bg": "#f1f5f9",
    "close_btn_color": "#64748b",
    "close_btn_hover_bg": "#e2e8f0",
    "close_btn_hover_color": "#0f172a",
    "urgency_line_1": "🔥 Hurry! Offer valid only for the first {total_seats} users!",
    "urgency_line_2": "🔥 {claimed_seats}/{total_seats} Claimed",
    "urgency_top_color": "#9f1239",
    "urgency_count_color": "#e11d48",
    "total_seats": 1000,
    "claimed_seats": 874,
    "strike_price_color": "#94a3b8",
    "current_price_color": "#16a34a",
    "discount_sticker_bg": "#e11d48",
    "discount_label": "OFF",
    "follower_discount_text": "Extra Follower Discount Applied!",
    "follower_discount_bg": "#d1fae5",
    "follower_discount_color": "#059669",
    "follower_discount_border": "#6ee7b7",
    "show_follower_discount_badge": True,
    "features_section_title": "What You'll Get",
    "features_section_accent": "#8b5cf6",
    "features_section_line": "#7c3aed",
    "social_section_title": "Follow on",
    "show_features_section": True,
    "show_social_section": True,
    "claim_btn_text": "Claim Offer",
    "claim_btn_bg": "#6d28d9",
    "claim_btn_color": "#ffffff",
    "claim_btn_hover_bg": "#5b21b6",
    "features": [
        {
            "name": "Permanent<br>Website",
            "icon": "fa-globe",
            "color": "#16a34a",
            "bg_color": "#f0fdf4",
        },
        {
            "name": "Digital<br>Card",
            "icon": "fa-id-card-clip",
            "color": "#6d28d9",
            "bg_color": "#f3e8ff",
        },
        {
            "name": "Licensed<br>Badge",
            "icon": "fa-shield-halved",
            "color": "#f97316",
            "bg_color": "#fff7ed",
        },
        {
            "name": "Call &<br>WhatsApp",
            "icon": "fa-phone",
            "color": "#16a34a",
            "bg_color": "#f0fdf4",
        },
        {
            "name": "Customer<br>Reviews",
            "icon": "fa-star",
            "color": "#6d28d9",
            "bg_color": "#f3e8ff",
        },
        {
            "name": "Product<br>Showcase",
            "icon": "fa-store",
            "color": "#3b82f6",
            "bg_color": "#eff6ff",
        },
    ],
}


def _normalize_scratch_popup(raw=None, *, format_urgency=True):
    """Merge admin scratch-popup config with defaults for choose-plan gift modal."""
    cfg = dict(_DEFAULT_SCRATCH_POPUP)
    if isinstance(raw, dict):
        for key, val in raw.items():
            if key == "features":
                continue
            if val is not None and val != "":
                cfg[key] = val

    features = None
    if (
        isinstance(raw, dict)
        and isinstance(raw.get("features"), list)
        and raw["features"]
    ):
        features = raw["features"]
    cfg["features"] = features or list(_DEFAULT_SCRATCH_POPUP["features"])

    try:
        total_seats = int(cfg.get("total_seats") or 1000)
    except (TypeError, ValueError):
        total_seats = 1000
    try:
        claimed_seats = int(cfg.get("claimed_seats") or 874)
    except (TypeError, ValueError):
        claimed_seats = 874
    spots_left = max(0, total_seats - claimed_seats)
    cfg["total_seats"] = total_seats
    cfg["claimed_seats"] = claimed_seats
    cfg["spots_left"] = spots_left

    cfg["show_features_section"] = _parse_json_flag(
        cfg.get("show_features_section", True)
    )
    cfg["show_social_section"] = _parse_json_flag(cfg.get("show_social_section", True))
    cfg["show_follower_discount_badge"] = _parse_json_flag(
        cfg.get("show_follower_discount_badge", True)
    )

    if format_urgency:

        def _fmt(template, fallback):
            text = template or fallback
            try:
                return text.format(
                    total_seats=total_seats,
                    claimed_seats=claimed_seats,
                    spots_left=spots_left,
                )
            except (KeyError, ValueError, IndexError):
                return text

        cfg["urgency_line_1_display"] = _fmt(
            cfg.get("urgency_line_1"),
            _DEFAULT_SCRATCH_POPUP["urgency_line_1"],
        )
        cfg["urgency_line_2_display"] = _fmt(
            cfg.get("urgency_line_2"),
            _DEFAULT_SCRATCH_POPUP["urgency_line_2"],
        )
    else:
        cfg["urgency_line_1_display"] = (
            cfg.get("urgency_line_1") or _DEFAULT_SCRATCH_POPUP["urgency_line_1"]
        )
        cfg["urgency_line_2_display"] = (
            cfg.get("urgency_line_2") or _DEFAULT_SCRATCH_POPUP["urgency_line_2"]
        )

    return cfg


def _parse_scratch_popup_from_post(post):
    """Build scratch_popup dict from admin plans form POST."""
    pf_names = post.getlist("sp_feature_name[]")
    pf_icons = post.getlist("sp_feature_icon[]")
    pf_colors = post.getlist("sp_feature_color[]")
    pf_bg_colors = post.getlist("sp_feature_bg_color[]")
    features = []
    for i, name in enumerate(pf_names):
        name = (name or "").strip()
        if not name:
            continue
        features.append(
            {
                "name": name,
                "icon": (pf_icons[i] if i < len(pf_icons) else "fa-star").strip()
                or "fa-star",
                "color": (pf_colors[i] if i < len(pf_colors) else "#16a34a").strip()
                or "#16a34a",
                "bg_color": (
                    pf_bg_colors[i] if i < len(pf_bg_colors) else "#f0fdf4"
                ).strip()
                or "#f0fdf4",
            }
        )

    def _int(key, default):
        try:
            return int(post.get(key, default) or default)
        except (TypeError, ValueError):
            return default

    return {
        "overlay_bg": (
            post.get("sp_overlay_bg") or _DEFAULT_SCRATCH_POPUP["overlay_bg"]
        ).strip(),
        "overlay_blur_px": _int(
            "sp_overlay_blur_px", _DEFAULT_SCRATCH_POPUP["overlay_blur_px"]
        ),
        "modal_bg": (
            post.get("sp_modal_bg") or _DEFAULT_SCRATCH_POPUP["modal_bg"]
        ).strip(),
        "modal_border_color": (
            post.get("sp_modal_border_color")
            or _DEFAULT_SCRATCH_POPUP["modal_border_color"]
        ).strip(),
        "modal_border_width_px": _int(
            "sp_modal_border_width_px", _DEFAULT_SCRATCH_POPUP["modal_border_width_px"]
        ),
        "modal_radius_px": _int(
            "sp_modal_radius_px", _DEFAULT_SCRATCH_POPUP["modal_radius_px"]
        ),
        "modal_shadow": (
            post.get("sp_modal_shadow") or _DEFAULT_SCRATCH_POPUP["modal_shadow"]
        ).strip(),
        "close_btn_bg": (
            post.get("sp_close_btn_bg") or _DEFAULT_SCRATCH_POPUP["close_btn_bg"]
        ).strip(),
        "close_btn_color": (
            post.get("sp_close_btn_color") or _DEFAULT_SCRATCH_POPUP["close_btn_color"]
        ).strip(),
        "close_btn_hover_bg": (
            post.get("sp_close_btn_hover_bg")
            or _DEFAULT_SCRATCH_POPUP["close_btn_hover_bg"]
        ).strip(),
        "close_btn_hover_color": (
            post.get("sp_close_btn_hover_color")
            or _DEFAULT_SCRATCH_POPUP["close_btn_hover_color"]
        ).strip(),
        "urgency_line_1": (
            post.get("sp_urgency_line_1") or _DEFAULT_SCRATCH_POPUP["urgency_line_1"]
        ).strip(),
        "urgency_line_2": (
            post.get("sp_urgency_line_2") or _DEFAULT_SCRATCH_POPUP["urgency_line_2"]
        ).strip(),
        "urgency_top_color": (
            post.get("sp_urgency_top_color")
            or _DEFAULT_SCRATCH_POPUP["urgency_top_color"]
        ).strip(),
        "urgency_count_color": (
            post.get("sp_urgency_count_color")
            or _DEFAULT_SCRATCH_POPUP["urgency_count_color"]
        ).strip(),
        "total_seats": _int("sp_total_seats", _DEFAULT_SCRATCH_POPUP["total_seats"]),
        "claimed_seats": _int(
            "sp_claimed_seats", _DEFAULT_SCRATCH_POPUP["claimed_seats"]
        ),
        "strike_price_color": (
            post.get("sp_strike_price_color")
            or _DEFAULT_SCRATCH_POPUP["strike_price_color"]
        ).strip(),
        "current_price_color": (
            post.get("sp_current_price_color")
            or _DEFAULT_SCRATCH_POPUP["current_price_color"]
        ).strip(),
        "discount_sticker_bg": (
            post.get("sp_discount_sticker_bg")
            or _DEFAULT_SCRATCH_POPUP["discount_sticker_bg"]
        ).strip(),
        "discount_label": (
            post.get("sp_discount_label") or _DEFAULT_SCRATCH_POPUP["discount_label"]
        ).strip()[:12]
        or "OFF",
        "follower_discount_text": (
            post.get("sp_follower_discount_text")
            or _DEFAULT_SCRATCH_POPUP["follower_discount_text"]
        ).strip(),
        "follower_discount_bg": (
            post.get("sp_follower_discount_bg")
            or _DEFAULT_SCRATCH_POPUP["follower_discount_bg"]
        ).strip(),
        "follower_discount_color": (
            post.get("sp_follower_discount_color")
            or _DEFAULT_SCRATCH_POPUP["follower_discount_color"]
        ).strip(),
        "follower_discount_border": (
            post.get("sp_follower_discount_border")
            or _DEFAULT_SCRATCH_POPUP["follower_discount_border"]
        ).strip(),
        "show_follower_discount_badge": "sp_show_follower_discount_badge" in post,
        "features_section_title": (
            post.get("sp_features_section_title")
            or _DEFAULT_SCRATCH_POPUP["features_section_title"]
        ).strip(),
        "features_section_accent": (
            post.get("sp_features_section_accent")
            or _DEFAULT_SCRATCH_POPUP["features_section_accent"]
        ).strip(),
        "features_section_line": (
            post.get("sp_features_section_line")
            or _DEFAULT_SCRATCH_POPUP["features_section_line"]
        ).strip(),
        "social_section_title": (
            post.get("sp_social_section_title")
            or _DEFAULT_SCRATCH_POPUP["social_section_title"]
        ).strip(),
        "show_features_section": "sp_show_features_section" in post,
        "show_social_section": "sp_show_social_section" in post,
        "claim_btn_text": (
            post.get("sp_claim_btn_text") or _DEFAULT_SCRATCH_POPUP["claim_btn_text"]
        ).strip()[:40]
        or "Claim Offer",
        "claim_btn_bg": (
            post.get("sp_claim_btn_bg") or _DEFAULT_SCRATCH_POPUP["claim_btn_bg"]
        ).strip(),
        "claim_btn_color": (
            post.get("sp_claim_btn_color") or _DEFAULT_SCRATCH_POPUP["claim_btn_color"]
        ).strip(),
        "claim_btn_hover_bg": (
            post.get("sp_claim_btn_hover_bg")
            or _DEFAULT_SCRATCH_POPUP["claim_btn_hover_bg"]
        ).strip(),
        "features": features or list(_DEFAULT_SCRATCH_POPUP["features"]),
    }


def _tier_optional_float(tier, key):
    """Return a float from a tier field, or None if missing/blank."""
    if not isinstance(tier, dict) or key not in tier:
        return None
    val = tier.get(key)
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _tier_plan_discount(tier, plan_key, default_discount=0):
    """Extra ₹ OFF for starter or professional. Per-plan fields win over shared discount_amount."""
    specific_key = "starter_discount" if plan_key == "starter" else "prof_discount"
    specific = _tier_optional_float(tier, specific_key)
    if specific is not None:
        return specific
    shared = _tier_optional_float(tier, "discount_amount")
    if shared is not None:
        return shared
    try:
        return float(default_discount or 0)
    except (TypeError, ValueError):
        return 0.0


def _tier_plan_charged_price(tier, plan_key, initial_price, default_discount=0):
    """Price charged for a plan at this follow tier (excl. GST)."""
    price_key = "starter_price" if plan_key == "starter" else "prof_price"
    saved = _tier_optional_float(tier, price_key)
    if saved is not None and saved > 0:
        return saved
    try:
        initial = float(initial_price or 0)
    except (TypeError, ValueError):
        initial = 0.0
    return max(0.0, initial - _tier_plan_discount(tier, plan_key, default_discount))


def _get_tier_prices(pricing_config, follow_count):
    """Compute tier pricing and discounts based on the number of accounts followed."""
    if not isinstance(pricing_config, dict):
        pricing_config = dict(_DEFAULT_PRICING)

    starter_cfg = pricing_config.get("starter", _DEFAULT_PRICING["starter"])
    prof_cfg = pricing_config.get("professional", _DEFAULT_PRICING["professional"])

    starter_full = float(starter_cfg.get("full_price", 1999) or 1999)
    starter_promo = float(starter_cfg.get("promo_price", 1499) or 1499)
    starter_scratch = float(
        starter_cfg.get("scratch_price", starter_promo) or starter_promo
    )
    starter_scratch_enabled = _is_scratch_enabled(starter_cfg)

    prof_full = float(prof_cfg.get("full_price", 9999) or 9999)
    prof_promo = float(prof_cfg.get("promo_price", 7999) or 7999)
    prof_scratch = float(prof_cfg.get("scratch_price", prof_promo) or prof_promo)
    prof_scratch_enabled = _is_scratch_enabled(prof_cfg)

    starter_initial = starter_scratch if starter_scratch_enabled else starter_promo
    prof_initial = prof_scratch if prof_scratch_enabled else prof_promo

    social_active = pricing_config.get("social_discount_active", True)
    default_discount = float(pricing_config.get("social_discount_amount", 200) or 200)
    follow_tiers = [
        t for t in (pricing_config.get("follow_tiers") or []) if isinstance(t, dict)
    ]

    starter_price = starter_initial
    prof_price = prof_initial
    applied_discount = 0.0
    starter_applied_discount = 0.0
    prof_applied_discount = 0.0

    if social_active and follow_count > 0:
        if follow_tiers:
            sorted_tiers = sorted(follow_tiers, key=_tier_follow_count, reverse=True)
            matched = False
            for tier in sorted_tiers:
                if follow_count >= _tier_follow_count(tier):
                    starter_applied_discount = _tier_plan_discount(
                        tier, "starter", default_discount
                    )
                    prof_applied_discount = _tier_plan_discount(
                        tier, "professional", default_discount
                    )
                    starter_price = _tier_plan_charged_price(
                        tier, "starter", starter_initial, default_discount
                    )
                    prof_price = _tier_plan_charged_price(
                        tier, "professional", prof_initial, default_discount
                    )
                    applied_discount = starter_applied_discount
                    matched = True
                    break
            if not matched:
                starter_price = max(0.0, starter_initial - default_discount)
                prof_price = max(0.0, prof_initial - default_discount)
                applied_discount = default_discount
                starter_applied_discount = default_discount
                prof_applied_discount = default_discount
        else:
            starter_price = max(0.0, starter_initial - default_discount)
            prof_price = max(0.0, prof_initial - default_discount)
            applied_discount = default_discount
            starter_applied_discount = default_discount
            prof_applied_discount = default_discount

    starter_base = int(round(starter_price))
    starter_gst = round(starter_base * 0.18, 2)
    starter_total = int(round(starter_base + starter_gst))

    prof_base = int(round(prof_price))
    prof_gst = round(prof_base * 0.18, 2)
    prof_total = int(round(prof_base + prof_gst))

    return {
        "starter_full": starter_full,
        "starter_price": starter_price,
        "starter_base": starter_base,
        "starter_gst": starter_gst,
        "starter_total": starter_total,
        "starter_scratch_price": starter_scratch,
        "prof_full": prof_full,
        "prof_price": prof_price,
        "prof_base": prof_base,
        "prof_gst": prof_gst,
        "prof_total": prof_total,
        "prof_scratch_price": prof_scratch,
        "applied_discount": applied_discount,
        "starter_applied_discount": starter_applied_discount,
        "prof_applied_discount": prof_applied_discount,
        "follow_count": follow_count,
    }


def _exclusive_base_price(exclusive_config, follow_count=0, discount_unlocked=False):
    """Price shown/charged for the exclusive plan. Matches social-follow + discount-status."""
    config = exclusive_config or {}
    base_price = float(config.get("base_price", 0) or 0)
    follow_tiers = list(config.get("follow_tiers") or [])
    if follow_tiers:
        follow_tiers.sort(key=lambda t: int(t.get("follows", 0) or 0), reverse=True)
        for tier in follow_tiers:
            if follow_count >= int(tier.get("follows", 0) or 0):
                return float(tier.get("price", base_price) or base_price)
        if discount_unlocked:
            easiest = follow_tiers[-1]
            return float(
                easiest.get("price", config.get("discounted_price", base_price))
                or base_price
            )
        return base_price
    if discount_unlocked:
        return float(config.get("discounted_price", base_price) or base_price)
    return base_price


def _to_money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _gst_bundle_from_base(base_amount):
    """GST-exclusive base → (base_rupees, gst, gst_inclusive_total). Matches chooseplan display."""
    base = int(round(float(base_amount or 0)))
    gst = round(base * 0.18, 2)
    total = int(round(base + gst, 0))
    return base, gst, total


def _tier_follow_count(tier):
    try:
        return int((tier or {}).get("follows", 0) or 0)
    except (TypeError, ValueError, AttributeError):
        return 0


def _scratch_session_key(plan_type):
    return f"scratch_revealed_{plan_type}"


def _parse_json_flag(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _parse_displayed_total(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_scratch_enabled(cfg, default=True):
    if not isinstance(cfg, dict) or "scratch_enabled" not in cfg:
        return default
    return _parse_json_flag(cfg.get("scratch_enabled"))


def _amounts_match(left, right, tolerance=1):
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def _clear_scratch_reveal_session(request):
    """Plans page always starts at full price until the ribbon is scratched again."""
    changed = False
    for plan_type in ("starter", "professional"):
        key = _scratch_session_key(plan_type)
        if key in request.session:
            request.session.pop(key, None)
            changed = True
    if changed:
        request.session.modified = True


def _scratch_revealed_for_checkout(
    request, data, plan_type, full_total, discounted_total=None
):
    """
    Apply the scratch discount only when this page actually revealed it
    and the order summary is showing that discounted total.
    """
    displayed = _parse_displayed_total((data or {}).get("displayed_total"))
    if displayed is not None and full_total and _amounts_match(displayed, full_total):
        return False
    session_revealed = bool(request.session.get(_scratch_session_key(plan_type)))
    client_revealed = _parse_json_flag((data or {}).get("scratch_revealed"))
    if not (session_revealed and client_revealed):
        return False
    if discounted_total is not None and displayed is not None:
        return _amounts_match(displayed, discounted_total)
    return True


def _plan_payable_total(
    pricing_config, follow_count, plan_type, scratch_revealed=False, promo_obj=None
):
    """
    Charge the amount shown on the card.
    Scratch-enabled plans stay at full_price + GST until the ribbon is revealed.
    """
    if not isinstance(pricing_config, dict):
        pricing_config = dict(_DEFAULT_PRICING)
    starter_cfg = pricing_config.get("starter") or _DEFAULT_PRICING["starter"]
    prof_cfg = pricing_config.get("professional") or _DEFAULT_PRICING["professional"]
    starter_full = float(starter_cfg.get("full_price", 1999) or 1999)
    prof_full = float(prof_cfg.get("full_price", 9999) or 9999)
    tier_info = _get_tier_prices(pricing_config, follow_count)

    if plan_type == "starter":
        if (
            promo_obj
            and not promo_obj.is_free_trial_code()
            and promo_obj.is_valid("basic")
        ):
            base = max(0.0, starter_full - promo_obj.calculate_discount(starter_full))
            return _gst_bundle_from_base(base)[2]
        if _is_scratch_enabled(starter_cfg) and not scratch_revealed:
            return _gst_bundle_from_base(starter_full)[2]
        return tier_info["starter_total"]

    if plan_type == "professional":
        if (
            promo_obj
            and not promo_obj.is_free_trial_code()
            and promo_obj.is_valid("professional")
        ):
            base = max(0.0, prof_full - promo_obj.calculate_discount(prof_full))
            return _gst_bundle_from_base(base)[2]
        if _is_scratch_enabled(prof_cfg) and not scratch_revealed:
            return _gst_bundle_from_base(prof_full)[2]
        return tier_info["prof_total"]

    return 0


def _checkout_total_for_plan(
    pricing_config, follow_count, plan_type, request, data, promo_obj=None
):
    """Razorpay amount must match the on-screen order summary."""
    revealed_total = _plan_payable_total(
        pricing_config,
        follow_count,
        plan_type,
        scratch_revealed=True,
        promo_obj=promo_obj,
    )
    unrevealed_total = _plan_payable_total(
        pricing_config,
        follow_count,
        plan_type,
        scratch_revealed=False,
        promo_obj=promo_obj,
    )
    cfg_key = "starter" if plan_type == "starter" else "professional"
    default_full = 1999 if plan_type == "starter" else 9999
    full = float(
        (pricing_config.get(cfg_key) or {}).get("full_price", default_full)
        or default_full
    )
    full_total = _gst_bundle_from_base(full)[2]
    if _scratch_revealed_for_checkout(
        request, data, plan_type, full_total, revealed_total
    ):
        return revealed_total
    return unrevealed_total


def _paise_amounts_match(paid, expected, tolerance=100):
    """Allow ₹1 GST rounding difference between order amount and stored fee."""
    try:
        return abs(int(paid) - int(expected)) <= tolerance
    except (TypeError, ValueError):
        return False
