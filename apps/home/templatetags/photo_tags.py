from django import template

register = template.Library()


@register.filter
def agent_photo_url(path):
    """Public URL for a raw agents.profile_photo_path (admin pages pass SQL rows, not models).

    Same resolution as AgentProfile.profile_photo_url: /media/..., Cloudinary URL, or the default avatar.
    """
    from apps.agents.models import AgentProfile

    return AgentProfile(profile_photo_path=path or '').profile_photo_url
