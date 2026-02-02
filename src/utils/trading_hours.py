"""Trading hours and exchange cutoffs (e.g. Public.com same-day option rule)."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Public.com does not allow opening same-day expiring option positions after 3:30 PM ET
SAME_DAY_OPTION_CUTOFF_TIME = time(15, 30)  # 3:30 PM ET


def now_et() -> datetime:
    """Current time in Eastern (America/New_York)."""
    return datetime.now(ET)


def is_after_same_day_option_cutoff_et() -> bool:
    """True if current time in ET is at or after 3:30 PM ET.
    Public does not allow opening same-day expiring option positions after this time.
    """
    return now_et().time() >= SAME_DAY_OPTION_CUTOFF_TIME
