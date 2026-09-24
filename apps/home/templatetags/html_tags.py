from django import template
from django.utils.safestring import mark_safe

from apps.home.html_sanitizer import sanitize_html

register = template.Library()


@register.filter(name='clean_html')
def clean_html(value):
    """Render admin-authored HTML with script-capable markup removed.

    Use instead of `|safe` for CMS/editor content: formatting, styles, SVG
    icons, images and embeds are kept; scripts and event handlers are not.
    """
    return mark_safe(sanitize_html('' if value is None else str(value)))
