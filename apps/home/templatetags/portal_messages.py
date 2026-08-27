from django import template
from apps.home.services.portal_messages import message_is_for_portal, message_is_success

register = template.Library()


@register.filter
def for_portal(message, portal):
    return message_is_for_portal(message, portal)


@register.filter
def is_success_message(message):
    return message_is_success(message)
