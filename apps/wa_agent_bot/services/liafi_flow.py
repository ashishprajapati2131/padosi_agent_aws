"""
WhatsApp flow for the LIAFI General Council Meeting (Vijayawada).

An agent types LIAFI (or anything, while event mode is ON in Admin → WhatsApp & OpenWA Hub):
welcome offer → optional language → name, email, LIAFI branch code → the agent and a Razorpay
link are created (same path as the bot's plan step) → profile-reserved menu
(activate / app / contest group / contacts). After payment, payment_service sends the
"activated" message from here.

Progress lives in session.session_context["liafi_step"]; the agent row carries
registration_draft["liafi"] so the profile can be previewed before payment and the Hub can count it.
"""

import json
import logging
import os
import re

from ..models import WaBotSession
from .validators import validate_email, validate_fullname, validate_mobile
from .site_url import bot_site_url
from . import flow_switches

logger = logging.getLogger(__name__)

TRIGGER_KEYWORD = "liafi"
PLAN_KEY = "starter"  # the ₹1999 "Digital Presence" plan named in the LIAFI messages
FIRST_GIFT_COUNT = 150
DRAW_EVERY = 15

# SiteSetting keys, edited in the Hub's LIAFI panel.
SETTING_GROUP_LINK = "liafi_group_link"
SETTING_SALES = "liafi_sales_number"
SETTING_SUPPORT = "liafi_support_number"
SETTING_APP_LINK = "liafi_app_link"

# PadosiAgent Sales / Support lines; the Hub panel overrides them.
DEFAULT_SALES = "+91 9898555837"
DEFAULT_SUPPORT = "+91 9898555437"

LANGUAGES = [
    ("en", "English"),
    ("hi", "हिंदी"),
    ("gu", "ગુજરાતી"),
    ("te", "తెలుగు"),
    ("ta", "தமிழ்"),
    ("kn", "ಕನ್ನಡ"),
    ("ml", "മലയാളം"),
    ("mr", "मराठी"),
]

with open(
    os.path.join(os.path.dirname(__file__), "liafi_i18n.json"), encoding="utf-8"
) as _f:
    TEXT = json.load(_f)

WELCOME = (
    "Hello {name}! 👋\n\n"
    "PadosiAgent warmly welcomes you to Vijayawada for the *LIAFI General Council Meeting*.\n\n"
    "🤝 LIAFI is fighting for your Rights.\n"
    "🚀 PadosiAgent empowers you with Digital Powers.\n\n"
    "In just 6 months, we have become the Digital Partner of *1,200+ Expert Insurance Agents*, "
    "helping them build relationships with *1,500+ new nearby customers*.\n\n"
    "Today, customers searching online for insurance services need experienced insurance professionals like YOU!\n"
    "It's time to become visible where your customers are searching.\n\n"
    "🎁 *SPECIAL EVENT OFFER*\n"
    "• Special Gift for the First 150 Expert Agents.\n"
    "• Exciting Lucky Draw after every 15 registrations!\n\n"
    "Let's get you started.\n\n"
    "1️⃣ 🚀 Register Now\n"
    "2️⃣ 🌐 Change Language\n"
    "3️⃣ 📞 Contact Us\n\n"
    "👉 Reply 1, 2 or 3"
)

LANGUAGE_MENU = (
    "Choose your preferred language to continue.\nPlease select your language. 👇\n\n"
    + "\n".join(f"{i}. {label}" for i, (_, label) in enumerate(LANGUAGES, 1))
    + "\n\n👉 Reply 1-8"
)


# ── Settings ────────────────────────────────────────────────────────────


def _setting(key):
    from apps.home.models.site_setting import SiteSetting

    return str(SiteSetting.get_value(key, "") or "").strip()


def event_mode_on():
    return flow_switches.is_on(flow_switches.LIAFI) and flow_switches.is_on(flow_switches.LIAFI_EVENT_MODE)


def app_link():
    """Hub override first, else the Android store link from Admin → App Version."""
    link = _setting(SETTING_APP_LINK)
    if link:
        return link
    from apps.admin_panel.models.app_version import AppVersion

    row = AppVersion.objects.filter(platform="android").exclude(store_url="").first()
    return row.store_url if row else ""


def contact_numbers():
    """(sales, support): the Hub value, else PadosiAgent's own lines."""
    return _setting(SETTING_SALES) or DEFAULT_SALES, _setting(SETTING_SUPPORT) or DEFAULT_SUPPORT


def get_settings():
    sales, support = contact_numbers()
    return {
        "group_link": _setting(SETTING_GROUP_LINK),
        "sales_number": _setting(SETTING_SALES),
        "support_number": _setting(SETTING_SUPPORT),
        "app_link_override": _setting(SETTING_APP_LINK),
        "app_link": app_link(),
        "sales_effective": sales,
        "support_effective": support,
    }


# ── Text helpers ────────────────────────────────────────────────────────


def _lang(session):
    lang = (session.registration_data or {}).get("liafi", {}).get("language", "en")
    return lang if lang in TEXT else "en"


def _t(lang, key):
    return TEXT.get(lang, TEXT["en"]).get(key) or TEXT["en"][key]


def _fill(text, **values):
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def _contacts(lang):
    sales, support = contact_numbers()
    return _fill(_t(lang, "contacts"), sales=sales or "—", support=support or "—")


def _profile_menu(lang, intro=""):
    labels = _t(lang, "profileButtons") + [_t(lang, "contactLabel")]
    menu = "\n".join(f"{i}️⃣ {label}" for i, label in enumerate(labels, 1))
    return (intro + "\n\n" if intro else "") + menu + "\n\n👉 1 / 2 / 3 / 4"


def _profile_url(agent):
    from .broadcast import profile_link

    return profile_link(agent, base=bot_site_url())


# ── Flow ────────────────────────────────────────────────────────────────


def wants_liafi(text_lower):
    if not flow_switches.is_on(flow_switches.LIAFI):
        return False
    # Whole word, so "LIAFI.", "LIAFI!" and "hi liafi" count but "liafix" doesn't.
    return re.search(r"\bliafi\b", text_lower) is not None


def start(session):
    session.state = WaBotSession.STATE_LIAFI
    session.registration_data = {"liafi": {"language": "en"}}
    session.session_context = {**(session.session_context or {}), "liafi_step": "menu"}
    session.save()
    return _fill(WELCOME, name="there")


def _set_step(session, step):
    session.session_context = {**(session.session_context or {}), "liafi_step": step}
    session.save()


def handle(session, text, text_lower):
    step = (session.session_context or {}).get("liafi_step", "menu")
    lang = _lang(session)
    data = session.registration_data or {}

    if step == "menu":
        if text_lower in ("1", "register", "register now"):
            _set_step(session, "name")
            return _t(lang, "regIntro") + "\n\n" + _t(lang, "askName")
        if text_lower in ("2", "language", "change language"):
            _set_step(session, "lang")
            return LANGUAGE_MENU
        if text_lower in ("3", "contact", "contact us"):
            return _contacts(lang) + "\n\n👉 1 / 2 / 3"
        return _fill(WELCOME, name="there")

    if step == "lang":
        codes = [code for code, _ in LANGUAGES]
        labels = {label.lower(): code for code, label in LANGUAGES}
        choice = (
            codes[int(text) - 1]
            if text.isdigit() and 1 <= int(text) <= len(codes)
            else labels.get(text_lower)
        )
        if not choice:
            return LANGUAGE_MENU
        data.setdefault("liafi", {})["language"] = choice
        session.registration_data = data
        session.session_context = {
            **(session.session_context or {}),
            "liafi_step": "name",
        }
        session.save()
        return _t(choice, "regIntro") + "\n\n" + _t(choice, "askName")

    if step == "name":
        ok, result = validate_fullname(text)
        if not ok:
            return f"❌ {result}\n\n" + _t(lang, "askName")
        data["fullname"] = result
        session.registration_data = data
        _set_step(session, "email")
        return _t(lang, "askEmail")

    if step == "email":
        ok, result = validate_email(text)
        if not ok:
            return _t(lang, "emailRetry")
        from apps.agents.models import Agent

        if (
            Agent.objects.filter(email=result)
            .exclude(pk=session.agent_id or 0)
            .exists()
        ):
            return _t(lang, "emailTaken")
        data["email"] = result
        session.registration_data = data
        _set_step(session, "branch")
        return _t(lang, "askBranch")

    if step == "branch":
        code = text.strip()[:40]
        if not code:
            return _t(lang, "askBranch")
        data.setdefault("liafi", {})["branch_code"] = code
        ok, mobile = validate_mobile(session.phone_number)
        data["mobile"] = mobile if ok else ""
        session.registration_data = data
        session.save()
        return _reserve_profile(session, lang)

    if step == "profile":
        return _handle_profile_menu(session, text_lower, lang)

    _set_step(session, "menu")
    return _fill(WELCOME, name="there")


def _reserve_profile(session, lang):
    """Create the agent + Razorpay link (pending payment) and send the profile-reserved message."""
    from .payment_service import create_plan_payment_link

    info = create_plan_payment_link(session, PLAN_KEY)
    if not info.get("success"):
        # Only failure mode is an email owned by another account: ask for a different one.
        _set_step(session, "email")
        return _t(lang, "emailTaken")

    agent = info["agent"]
    draft = (
        agent.registration_draft if isinstance(agent.registration_draft, dict) else {}
    )
    draft["liafi"] = {
        "branch_code": session.registration_data["liafi"].get("branch_code", ""),
        "language": lang,
    }
    agent.registration_draft = draft
    agent.save(update_fields=["registration_draft"])

    _set_step(session, "profile")
    intro = _fill(_t(lang, "profile"), name=agent.fullname, link=_profile_url(agent))
    return _profile_menu(lang, intro)


def _handle_profile_menu(session, text_lower, lang):
    data = session.registration_data or {}
    if text_lower == "1":
        return _profile_menu(
            lang, _fill(_t(lang, "activate"), url=data.get("payment_link", ""))
        )
    if text_lower == "2":
        link = app_link()
        return _profile_menu(
            lang, _fill(_t(lang, "app"), url=link) if link else _contacts(lang)
        )
    if text_lower == "3":
        link = _setting(SETTING_GROUP_LINK)
        return _profile_menu(
            lang, _fill(_t(lang, "group"), url=link) if link else _contacts(lang)
        )
    if text_lower == "4":
        return _profile_menu(lang, _contacts(lang))
    return _profile_menu(lang)


def activated_message(session, agent):
    """Message 05, sent after the LIAFI agent's payment is captured; None for non-LIAFI sessions."""
    liafi = (session.registration_data or {}).get("liafi") if session else None
    if not liafi:
        return None
    lang = liafi.get("language") if liafi.get("language") in TEXT else "en"
    parts = [_fill(_t(lang, "activatedIntro"), name=agent.fullname)]
    steps = [
        ("activatedApp", app_link()),
        ("activatedGroup", _setting(SETTING_GROUP_LINK)),
    ]
    n = 0
    for key, url in steps:
        if url:
            n += 1
            parts.append(_fill(_t(lang, key), n=n, url=url))
    parts.append(_fill(_t(lang, "activatedShare"), n=n + 1, link=_profile_url(agent)))
    parts.append(_t(lang, "activatedOutro"))
    return "\n\n".join(parts)


def stats():
    """Counts for the Hub panel: registrations, paid, first-150 gifts and lucky-draw progress."""
    from apps.agents.models import Agent

    registered = Agent.objects.filter(registration_draft__has_key="liafi")
    total = registered.count()
    paid = registered.exclude(status__in=("incomplete", "pending_payment")).count()
    return {
        "registered": total,
        "paid": paid,
        "gifts_left": max(FIRST_GIFT_COUNT - total, 0),
        "draws_due": total // DRAW_EVERY,
        "to_next_draw": DRAW_EVERY - (total % DRAW_EVERY),
    }
