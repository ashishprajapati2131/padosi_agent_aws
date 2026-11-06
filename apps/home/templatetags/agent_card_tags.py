from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def agent_card_theme(context):
    """Active agent-card theme. Looked up once per request (the card is rendered
    once per agent). The admin preview passes a draft as `agent_card_theme_override`."""
    override = context.get("agent_card_theme_override")
    if override is not None:
        return override
    request = context.get("request")
    theme = getattr(request, "_agent_card_theme", None)
    if theme is None:
        from apps.admin_panel.services.agent_card_themes import get_active_card_theme

        theme = get_active_card_theme()
        if request is not None:
            request._agent_card_theme = theme
    return theme


@register.inclusion_tag("partials/agent-card-theme-style.html", takes_context=True)
def agent_card_theme_style(context, theme):
    """Theme <style> block, printed once per request (or once per preview)."""
    request = context.get("request")
    show = bool(theme.get("enabled"))
    if (
        show
        and context.get("agent_card_theme_override") is None
        and request is not None
    ):
        show = not getattr(request, "_agent_card_theme_style_done", False)
        request._agent_card_theme_style_done = True
    return {"t": theme, "show": show}
