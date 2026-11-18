"""Template helpers for pre-drafted messages in 23 languages.

{% load message_lang_tags %}
{% message_lang_assets %}                      once per page, before the widgets are used
{% message_lang_select "waLang" selected %}    a <select> of the 23 languages
{% message_lang_editor "msgTextarea" "msg_i18n" translations %}
    "Other languages" panel under an existing textarea; posts {code: text} JSON as `msg_i18n`
"""

import json

from django import template

from apps.home.services.message_languages import LANGUAGES, clean_translations, pick

register = template.Library()


@register.inclusion_tag("partials/message_lang_assets.html", takes_context=True)
def message_lang_assets(context):
    # Several partials on one page include this; emit the script and CSS only once per request.
    request = context.get("request")
    if request is not None:
        if getattr(request, "_message_lang_assets_done", False):
            return {"skip": True}
        request._message_lang_assets_done = True
    return {"languages": [{"code": c, "name": n, "native": v} for c, n, v in LANGUAGES]}


@register.inclusion_tag("partials/message_lang_select.html")
def message_lang_select(
    select_id, selected="en", css_class="form-select form-select-sm"
):
    return {
        "select_id": select_id,
        "selected": selected or "en",
        "css_class": css_class,
        "languages": LANGUAGES,
    }


@register.inclusion_tag("partials/message_lang_editor.html")
def message_lang_editor(source_id, field_name, translations=None):
    return {
        "source_id": source_id,
        "field_name": field_name,
        # Plain string: autoescaped into the hidden input's value attribute.
        "translations_json": json.dumps(clean_translations(translations), ensure_ascii=False),
        "languages": [lang for lang in LANGUAGES if lang[0] != "en"],
    }


@register.simple_tag
def pick_lang(base_text, translations, lang):
    return pick(base_text, translations, lang)
