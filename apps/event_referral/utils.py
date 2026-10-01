def format_duration_seconds(seconds):
    """Human-readable duration for admin tables."""
    total = int(seconds or 0)
    if total <= 0:
        return '—'
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f'{hours}h')
    if minutes or hours:
        parts.append(f'{minutes}m')
    if not hours:
        parts.append(f'{secs}s')
    return ' '.join(parts)
