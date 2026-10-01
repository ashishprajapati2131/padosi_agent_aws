"""Choose-plan prices for the mobile plans API.

The numbers come from the admin pricing_config (the same source as the
website choose-plan page). 1999 and 9999 are the list prices before scratch.
Scratch and social-follow discounts are applied only after this agent has
recorded them.
"""
import json
from typing import Any, Optional

from fastapi_app.models.agent_plan_offer import AgentPlanOffer
from fastapi_app.models.site_setting import SiteSetting

MOBILE_PLAN_SLUGS = ("starter", "professional")

DEFAULT_PRICING = {
    "social_discount_active": True,
    "social_discount_amount": 200,
    "starter": {
        "name": "Starter's Plan",
        "full_price": 1999,
        "promo_price": 1499,
        "scratch_price": 1299,
        "description": "Perfect for New Agents",
        "badge": "STANDARD",
        "scratch_enabled": True,
    },
    "professional": {
        "name": "Professional's Plan",
        "full_price": 9999,
        "promo_price": 7999,
        "scratch_price": 7799,
        "description": "For Established Professionals",
        "badge": "RECOMMENDED",
        "scratch_enabled": True,
    },
    "social_links": [
        {"platform": "Instagram", "url": "https://instagram.com/padosiagent"},
        {"platform": "Facebook", "url": "https://facebook.com/padosiagent"},
        {"platform": "YouTube", "url": "https://youtube.com/@padosiagent"},
        {"platform": "LinkedIn", "url": "https://linkedin.com/company/padosiagent"},
    ],
    "follow_tiers": [
        {"follows": 1, "discount_amount": 100, "starter_discount": 100, "prof_discount": 100, "starter_price": 1399, "prof_price": 7899},
        {"follows": 2, "discount_amount": 200, "starter_discount": 200, "prof_discount": 200, "starter_price": 1299, "prof_price": 7799},
        {"follows": 3, "discount_amount": 300, "starter_discount": 300, "prof_discount": 300, "starter_price": 1199, "prof_price": 7699},
        {"follows": 4, "discount_amount": 500, "starter_discount": 500, "prof_discount": 500, "starter_price": 999, "prof_price": 7499},
    ],
}

ALLOWED_FOLLOW_PLATFORMS = frozenset({
    "instagram", "facebook", "x", "twitter", "linkedin", "youtube",
    "whatsapp", "telegram", "threads", "pinterest",
})


def _flag(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _money(value, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if number < 0:
        return float(fallback)
    return number


def _optional_float(tier, key):
    if not isinstance(tier, dict) or key not in tier:
        return None
    val = tier.get(key)
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def gst_bundle(base_amount):
    """GST-exclusive base → base, gst, payable total. Same rounding as the website."""
    base = int(round(float(base_amount or 0)))
    if base <= 0:
        return 0, 0.0, 0
    gst = round(base * 0.18, 2)
    total = int(round(base + gst))
    return base, gst, total


def load_pricing_config(db) -> dict:
    row = None
    if db is not None:
        row = db.query(SiteSetting).filter(SiteSetting.key == "pricing_config").first()
    raw = getattr(row, "value", None) if row else None
    parsed = None
    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
    config = dict(DEFAULT_PRICING)
    if isinstance(parsed, dict):
        config.update(parsed)
        for slug in MOBILE_PLAN_SLUGS:
            merged = dict(DEFAULT_PRICING[slug])
            custom = parsed.get(slug)
            if isinstance(custom, dict):
                merged.update(custom)
            config[slug] = merged
        if not isinstance(config.get("follow_tiers"), list):
            config["follow_tiers"] = list(DEFAULT_PRICING["follow_tiers"])
        if not isinstance(config.get("social_links"), list):
            config["social_links"] = list(DEFAULT_PRICING["social_links"])
    return config


def allowed_platforms(config) -> set:
    names = set(ALLOWED_FOLLOW_PLATFORMS)
    for link in config.get("social_links") or []:
        if isinstance(link, dict) and link.get("platform"):
            names.add(str(link["platform"]).strip().lower())
    return names


def _tier_discount(tier, slug, default_discount):
    specific_key = "starter_discount" if slug == "starter" else "prof_discount"
    specific = _optional_float(tier, specific_key)
    if specific is not None:
        return specific
    shared = _optional_float(tier, "discount_amount")
    if shared is not None:
        return shared
    return float(default_discount or 0)


def _tier_price(tier, slug, initial_price, default_discount):
    price_key = "starter_price" if slug == "starter" else "prof_price"
    saved = _optional_float(tier, price_key)
    if saved is not None and saved > 0:
        return saved
    return max(0.0, float(initial_price or 0) - _tier_discount(tier, slug, default_discount))


def deal_base(config, slug, follow_count):
    """Price excl. GST after scratch, including the follow tier the admin set."""
    defaults = DEFAULT_PRICING[slug]
    cfg = config.get(slug) if isinstance(config.get(slug), dict) else defaults
    promo = _money(cfg.get("promo_price"), defaults["promo_price"])
    scratch = _money(cfg.get("scratch_price"), promo)
    scratch_on = _flag(cfg.get("scratch_enabled"), True)
    initial = scratch if scratch_on else promo

    social_on = _flag(config.get("social_discount_active"), True)
    default_discount = _money(config.get("social_discount_amount"), 200)
    tiers = [t for t in (config.get("follow_tiers") or []) if isinstance(t, dict)]
    price = initial
    discount = 0.0

    if social_on and follow_count > 0:
        matched = None
        for tier in sorted(tiers, key=lambda t: int(t.get("follows") or 0), reverse=True):
            try:
                need = int(tier.get("follows") or 0)
            except (TypeError, ValueError):
                need = 0
            if follow_count >= need:
                matched = tier
                break
        if matched is not None:
            price = _tier_price(matched, slug, initial, default_discount)
            discount = _tier_discount(matched, slug, default_discount)
        else:
            price = max(0.0, initial - default_discount)
            discount = default_discount
    return price, discount, scratch_on, scratch


def quote_plan(config, slug, *, scratched, follow_count, force_rupee=False):
    defaults = DEFAULT_PRICING[slug]
    cfg = config.get(slug) if isinstance(config.get(slug), dict) else defaults
    full = _money(cfg.get("full_price"), defaults["full_price"])
    deal, follow_discount, scratch_on, scratch_price = deal_base(config, slug, follow_count)
    revealed = bool(scratched) or not scratch_on
    payable = deal if revealed else full
    if force_rupee and slug == "professional":
        payable = 1
        deal = 1
    base, gst, total = gst_bundle(payable)
    if force_rupee and slug == "professional":
        base, gst, total = 1, 0.0, 1
    off = max(0.0, full - payable)
    pct = int(round((off / full) * 100)) if full > 0 and off > 0 else 0
    if force_rupee and slug == "professional":
        pct = 99
    return {
        "name": str(cfg.get("name") or defaults["name"]),
        "description": str(cfg.get("description") or defaults["description"]),
        "badge": cfg.get("badge") or defaults["badge"],
        "full_price": full,
        "display_price": float(base),
        "price_after_scratch": float(int(round(deal))),
        "scratch_enabled": scratch_on,
        "scratch_revealed": bool(scratched),
        "scratch_price": float(scratch_price),
        "follow_count": int(follow_count or 0),
        "follow_discount": float(follow_discount if scratched or not scratch_on else 0),
        "payable_base": base,
        "gst_amount": gst,
        "payable_total": total,
        "discount_pct": pct,
    }


def load_offer(db, agent):
    if db is None or agent is None or not getattr(agent, "id", None):
        return None
    return db.query(AgentPlanOffer).filter(AgentPlanOffer.agent_id == agent.id).first()


def offer_state(offer):
    scratched = set()
    followed = []
    if offer is not None:
        if offer.scratched_starter:
            scratched.add("starter")
        if offer.scratched_professional:
            scratched.add("professional")
        raw = offer.followed_platforms or []
        if isinstance(raw, list):
            followed = [str(p).strip().lower() for p in raw if str(p).strip()]
    return scratched, followed


def get_or_create_offer(db, agent):
    row = load_offer(db, agent)
    if row is not None:
        return row
    row = AgentPlanOffer(
        agent_id=agent.id,
        scratched_starter=False,
        scratched_professional=False,
        followed_platforms=[],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
