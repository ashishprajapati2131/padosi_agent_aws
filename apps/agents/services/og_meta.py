"""Open Graph context for agent profile / card share pages."""
from apps.agents.services.og_urls import agent_og_image_absolute_url, build_og_absolute_url


def profile_og_context(request, agent, *, display_name=None):
    """
    WhatsApp share text and link preview.

    Name | Licensed Insurance & Financial Advisor ('Licensed' only with a license/ARN number)
    The profile URL is added by the share button, and WhatsApp shows the link.
    """
    name = (display_name or getattr(agent, 'fullname', None) or 'Insurance Advisor').strip()
    profile = getattr(agent, 'profile', None) if hasattr(agent, 'profile') else None
    licensed = bool(profile and ((profile.license_number or '').strip() or (profile.arn_number or '').strip()))
    # 'Licensed' only when the agent entered a license / ARN number.
    line = f"{name} | {'Licensed ' if licensed else ''}Insurance & Financial Advisor"
    return {
        'og_share_title': line,
        'og_share_description': line,
        'og_image_absolute_url': agent_og_image_absolute_url(request, agent.id),
        'og_page_absolute_url': build_og_absolute_url(request, request.get_full_path()),
    }
