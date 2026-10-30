"""Open Graph context for agent profile / card share pages."""
from apps.agents.services.og_urls import agent_og_image_absolute_url, build_og_absolute_url


def profile_og_context(request, agent, *, display_name=None):
    """
    WhatsApp share text and link preview.

    Name | Licensed Insurance & Financial Advisor
    The profile URL is added by the share button, and WhatsApp shows the link.
    """
    name = (display_name or getattr(agent, 'fullname', None) or 'Insurance Advisor').strip()
    line = f'{name} | Licensed Insurance & Financial Advisor'
    return {
        'og_share_title': line,
        'og_share_description': line,
        'og_image_absolute_url': agent_og_image_absolute_url(request, agent.id),
        'og_page_absolute_url': build_og_absolute_url(request, request.get_full_path()),
    }
