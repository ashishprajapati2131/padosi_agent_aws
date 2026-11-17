from django import template
from django.utils import timezone
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


@register.filter(name='compact_timesince')
def compact_timesince(value):
    """Compact relative time for dense mobile UIs: 2m ago, 3w ago, 1y ago."""
    if not value:
        return '-'
    try:
        now = timezone.now()
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        seconds = max(0, int((now - value).total_seconds()))
    except Exception:
        return '-'

    if seconds < 60:
        return 'just now'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes}m ago'
    hours = minutes // 60
    if hours < 24:
        return f'{hours}h ago'
    days = hours // 24
    if days < 7:
        return f'{days}d ago'
    weeks = days // 7
    if weeks < 5:
        return f'{weeks}w ago'
    months = days // 30
    if months < 12:
        return f'{months}mo ago'
    years = days // 365
    return f'{max(1, years)}y ago'
