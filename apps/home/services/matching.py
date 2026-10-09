"""Shared match-percent assignment for directory and homepage agent lists."""


def _as_float(value, default=0.0):
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def assign_match_percents(agents, claim_company_lower=''):
    """
    Set agent.match_percent from padosi_smart_rank (and optional claim-company tier).
    Mirrors find-agents logic in fetch_filtered_agents_list.
    """
    if not agents:
        return agents

    max_smart_rank = max([_as_float(a.padosi_smart_rank, 0) for a in agents]) if agents else 165
    if max_smart_rank <= 0:
        max_smart_rank = 165

    for agent in agents:
        rank = _as_float(agent.padosi_smart_rank, 0)
        match_flag = getattr(agent, 'has_claim_company_match', None)
        if match_flag is True:
            agent.match_percent = int(min(99.0, max(88.0, 88.0 + (rank / max_smart_rank) * 11.0)))
        elif match_flag is False:
            agent.match_percent = int(min(85.0, max(72.0, 72.0 + (rank / max_smart_rank) * 13.0)))
        else:
            agent.match_percent = int(min(99.0, max(80.0, 80.0 + (rank / max_smart_rank) * 19.0)))
    return agents
