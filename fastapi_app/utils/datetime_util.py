from datetime import datetime, timezone, timedelta

def get_current_time() -> datetime:
    """
    Returns naive datetime in Asia/Kolkata (IST) timezone.
    Matches Django's timezone.now() when USE_TZ=False and TIME_ZONE='Asia/Kolkata'.
    """
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)
