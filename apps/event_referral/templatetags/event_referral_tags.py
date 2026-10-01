from django import template

from apps.event_referral.utils import format_duration_seconds as _format_duration_seconds

register = template.Library()


@register.filter(name='format_duration_seconds')
def format_duration_seconds_filter(seconds):
    return _format_duration_seconds(seconds)
