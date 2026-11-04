"""Display helpers for public-facing agent/location strings."""
import re

_TALUKA_SPACING = re.compile(r"(?i)(?<=[A-Za-z])(taluka|taluk)\b")
_LEADING_TRAIL_PUNCT = re.compile(r"^[,.\-;:'\"]+|[,.\-;:'\"]+$")


def normalize_location_spacing(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"\s+", " ", str(text).strip())
    text = _TALUKA_SPACING.sub(r" \1", text)
    return re.sub(r"\s+", " ", text).strip()


def sanitize_agent_display_name(name: str) -> str:
    if not name:
        return name
    text = re.sub(r"\s+", " ", str(name).strip())
    text = _LEADING_TRAIL_PUNCT.sub("", text)
    return text.strip()


def parse_success_rate_percent(value) -> float | None:
    """Parse success_rate from DB; strips a trailing % if present."""
    if value is None:
        return None
    val_str = str(value).strip().rstrip("%").strip()
    if not val_str:
        return None
    try:
        return float(val_str)
    except (TypeError, ValueError):
        return None


def format_success_rate_display(value, default: str = "98%") -> str:
    """Human-readable success rate with exactly one % suffix."""
    rate = parse_success_rate_percent(value)
    if rate is None:
        return default
    if rate <= 0:
        return default
    if rate == int(rate):
        return f"{int(rate)}%"
    text = f"{rate:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"
