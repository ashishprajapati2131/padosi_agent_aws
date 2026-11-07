"""Lenient parsing of request values for admin views."""


def parse_int(value, default):
    """int(value), or default when value is missing or not an integer (e.g. ?page=abc)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
