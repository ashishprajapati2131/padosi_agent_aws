"""Admin: Languages & Localization — everything about the multilingual site in one place:
master switch, IP (state) detection, browser detection, default language, Google Translate,
languages, state -> language map, website text per language, and CMS page translations.
Logic lives in apps/localization/services.py; access is gated by AdminPermissionMiddleware."""

import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.admin_panel.services.feature_flags import (
    is_feature_enabled,
    set_feature_flag_status,
)
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.home.models.page import Page
from apps.home.models.site_setting import SiteSetting
from apps.localization import services
from apps.localization.models import (
    ContentTranslation,
    LocalizationSettings,
    SiteLanguage,
    StateLanguage,
    UITranslation,
)

INDEX = "admin_localization"
TABS = ("settings", "languages", "states", "texts", "pages")
GOOGLE_TRANSLATE_FLAG = "enable_multilingual_regional_branding"
PAGE_FIELDS = (
    ("title", "Title"),
    ("meta_title", "SEO title"),
    ("meta_description", "SEO description"),
    ("content", "Page content (HTML)"),
)


def _back(tab, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items() if v not in (None, ""))
    return redirect(f"/admin/localization/?tab={tab}" + (f"&{query}" if query else ""))


def _field_key(msgid):
    return "t_" + hashlib.sha1(msgid.encode()).hexdigest()[:16]


def _site_settings():
    return LocalizationSettings.objects.get_or_create(
        pk=1, defaults={"default_language_id": settings.LANGUAGE_CODE}
    )[0]


def _language_or(code, fallback):
    return code if code in services.KNOWN_CODES else fallback


def localization_index(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    tab = request.GET.get("tab") if request.GET.get("tab") in TABS else "settings"
    languages = list(SiteLanguage.objects.all())
    context = {
        "tab": tab,
        "site": _site_settings(),
        "languages": languages,
        "active_languages": [lang for lang in languages if lang.is_active],
        "google_translate_on": is_feature_enabled(GOOGLE_TRANSLATE_FLAG, default=True),
        "geoip_ready": services._geoip_reader() is not None,
        "geoip_path": settings.GEOIP_CITY_DB,
        "source_language": settings.LANGUAGE_CODE,
    }
    if tab == "languages":
        website = services.website_messages()
        for lang in languages:
            done, total = services.translation_completion(lang.code, website)
            lang.completion = round(100 * done / total) if total else 0
            lang.completion_text = f"{done}/{total}"
    elif tab == "states":
        context["states"] = StateLanguage.objects.select_related("language")
    elif tab == "texts":
        code = _language_or(request.GET.get("lang"), "gu")
        shipped = services.po_translations(code)
        overrides = dict(
            UITranslation.objects.filter(language=code).values_list("msgid", "text")
        )
        context.update(
            text_language=code,
            text_rows=[
                {
                    "key": _field_key(msgid),
                    "msgid": msgid,
                    "shipped": msgid
                    if code == settings.LANGUAGE_CODE
                    else shipped.get(msgid, ""),
                    "value": overrides.get(msgid, ""),
                }
                for msgid in services.website_messages()
            ],
            seo_title=SiteSetting.get_value(f"seo_meta_title_{code}", "") or "",
            seo_description=SiteSetting.get_value(f"seo_meta_description_{code}", "")
            or "",
        )
    elif tab == "pages":
        code = _language_or(request.GET.get("lang"), "gu")
        if code == settings.LANGUAGE_CODE:
            code = "gu"
        pages = Page.objects.order_by("title")
        page = (
            pages.filter(pk=request.GET.get("page")).first()
            if str(request.GET.get("page", "")).isdigit()
            else None
        )
        context.update(pages=pages, page=page, page_language=code)
        if page:
            existing = {
                row.field: row
                for row in ContentTranslation.objects.filter(
                    content_type=ContentType.objects.get_for_model(Page),
                    object_id=str(page.pk),
                    language=code,
                )
            }
            context["page_fields"] = [
                {
                    "name": name,
                    "label": label,
                    "original": getattr(page, name) or "",
                    "value": existing[name].text if name in existing else "",
                }
                for name, label in PAGE_FIELDS
            ]
            context["page_approved"] = any(row.is_approved for row in existing.values())
        context["translated_page_ids"] = set(
            ContentTranslation.objects.filter(
                content_type=ContentType.objects.get_for_model(Page), language=code
            ).values_list("object_id", flat=True)
        )
    return render(request, "admin/localization/index.html", context)


@require_POST
def localization_settings_save(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    site = _site_settings()
    default = request.POST.get("default_language", settings.LANGUAGE_CODE)
    if not SiteLanguage.objects.filter(code=default, is_active=True).exists():
        messages.error(request, "Default language must be one of the active languages.")
        return _back("settings")
    site.enabled = request.POST.get("enabled") == "1"
    site.auto_detect_enabled = request.POST.get("auto_detect_enabled") == "1"
    site.browser_language_enabled = request.POST.get("browser_language_enabled") == "1"
    site.default_language_id = default
    site.save()
    google_on = request.POST.get("google_translate") == "1"
    if google_on != is_feature_enabled(GOOGLE_TRANSLATE_FLAG, default=True):
        set_feature_flag_status(GOOGLE_TRANSLATE_FLAG, google_on, request=request)
    AdminActivityLog.log(
        f"Localization settings: multilingual={'ON' if site.enabled else 'OFF'}, "
        f"IP detection={'ON' if site.auto_detect_enabled else 'OFF'}, "
        f"browser={'ON' if site.browser_language_enabled else 'OFF'}, default={default}, "
        f"Google Translate={'ON' if google_on else 'OFF'}",
        "Localization",
        request=request,
    )
    messages.success(request, "Settings saved. Live on the website now.")
    return _back("settings")


@require_POST
def localization_languages_save(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    errors = []
    with transaction.atomic():
        for lang in SiteLanguage.objects.select_for_update():
            name = request.POST.get(f"name_{lang.code}", "").strip()
            order = request.POST.get(f"order_{lang.code}", "").strip()
            if not name or len(name) > 50:
                errors.append(f"{lang.code}: name is required (max 50 characters).")
                continue
            if not order.isdigit() or int(order) > 999:
                errors.append(f"{lang.code}: order must be a number 0-999.")
                continue
            lang.native_name = name
            lang.sort_order = int(order)
            lang.is_active = request.POST.get(f"active_{lang.code}") == "1"
            lang.save()  # the source language is forced active in the model
    if errors:
        messages.error(request, "Some rows were not saved: " + " ".join(errors))
    site = _site_settings()
    if not site.default_language.is_active:
        messages.warning(
            request,
            f"The default language ({site.default_language_id}) is now off; visitors fall back to English.",
        )
    AdminActivityLog.log("Updated website languages", "Localization", request=request)
    messages.success(request, "Languages saved.")
    return _back("languages")


@require_POST
def localization_states_save(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    valid = set(SiteLanguage.objects.values_list("code", flat=True))
    with transaction.atomic():
        for state in StateLanguage.objects.select_for_update():
            code = request.POST.get(f"lang_{state.pk}", "")
            state.language_id = code if code in valid else None
            state.aliases = request.POST.get(f"aliases_{state.pk}", "").strip()[:255]
            state.save()
    AdminActivityLog.log(
        "Updated state -> language map", "Localization", request=request
    )
    messages.success(
        request,
        "State languages saved. New visitors get them now; visitors already detected switch within 24 hours.",
    )
    return _back("states")


@require_POST
def localization_texts_save(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    code = request.POST.get("lang", "")
    if code not in services.KNOWN_CODES:
        messages.error(request, "Unknown language.")
        return _back("texts")
    shipped = services.po_translations(code)
    changed = 0
    with transaction.atomic():
        for msgid in services.website_messages():
            raw = request.POST.get(_field_key(msgid))
            if raw is None:
                continue
            text = services.clean_ui_text(msgid, raw)
            default = (
                msgid if code == settings.LANGUAGE_CODE else shipped.get(msgid, "")
            )
            if not text or text == default:
                changed += UITranslation.objects.filter(
                    language=code, msgid=msgid
                ).delete()[0]
            else:
                UITranslation.objects.update_or_create(
                    language=code, msgid=msgid, defaults={"text": text}
                )
                changed += 1
        for key in ("seo_meta_title", "seo_meta_description"):
            value = request.POST.get(key, "").strip()[:500]
            if value != (SiteSetting.get_value(f"{key}_{code}", "") or ""):
                SiteSetting.set_value(f"{key}_{code}", value)
    services.clear_config_cache()  # deletes alone do not fire the save signal
    AdminActivityLog.log(
        f"Edited website text [{code}] ({changed} entries)",
        "Localization",
        request=request,
    )
    messages.success(request, "Website text saved. Live on the website now.")
    return _back("texts", lang=code)


@require_POST
def localization_page_save(request):
    if not _get_admin_from_session(request):
        return redirect("admin_login")
    code = request.POST.get("lang", "")
    page = Page.objects.filter(
        pk=request.POST.get("page")
        if str(request.POST.get("page", "")).isdigit()
        else None
    ).first()
    if not page or code not in services.KNOWN_CODES or code == settings.LANGUAGE_CODE:
        messages.error(request, "Choose a page and a language.")
        return _back("pages")
    content_type = ContentType.objects.get_for_model(Page)
    approved = request.POST.get("approved") == "1"
    with transaction.atomic():
        for name, _label in PAGE_FIELDS:
            text = request.POST.get(name, "").strip()
            rows = ContentTranslation.objects.filter(
                content_type=content_type,
                object_id=str(page.pk),
                field=name,
                language=code,
            )
            if not text:
                for row in rows:
                    row.delete()  # per-row delete so the cache signal fires
                continue
            ContentTranslation.objects.update_or_create(
                content_type=content_type,
                object_id=str(page.pk),
                field=name,
                language=code,
                defaults={"text": text, "is_approved": approved},
            )
    AdminActivityLog.log(
        f"Page translation [{code}] '{page.title}' ({'published' if approved else 'draft'})",
        "Localization",
        model_id=page.pk,
        request=request,
    )
    messages.success(
        request,
        "Translation saved and live."
        if approved
        else "Draft saved. Tick 'Publish' to show it on the website.",
    )
    return _back("pages", lang=code, page=page.pk)
