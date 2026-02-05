"""Theme change governance: rules that block theme changes when violated."""
from typing import Tuple
from datetime import datetime, timedelta, timezone
from loguru import logger

from src.config import config


def check_theme_change_governance(storage, proposal: dict) -> Tuple[bool, str]:
    """Check if theme change is allowed by governance rules.

    This function enforces strict rules to prevent inappropriate theme changes:
    1. Minimum confidence threshold
    2. Minimum recommendation score
    3. Cooldown period between changes
    4. Kill switch (no changes during drawdown)
    5. Approval required flag

    Args:
        storage: StorageManager instance
        proposal: Theme change proposal dictionary with keys:
            - theme_name: str
            - confidence: float
            - recommendation_score: float
            - status: str

    Returns:
        Tuple of (allowed: bool, reason: str)
        - If allowed=True, theme change can proceed
        - If allowed=False, reason explains why change is blocked
    """

    # Rule 1: Minimum confidence threshold
    confidence = proposal.get("confidence", 0.0)
    if confidence < config.theme_change_min_confidence:
        return False, (
            f"Confidence {confidence:.0%} below minimum "
            f"{config.theme_change_min_confidence:.0%}"
        )

    # Rule 2: Minimum recommendation score
    score = proposal.get("recommendation_score", 0.0)
    if score < config.theme_change_threshold:
        return False, (
            f"Recommendation score {score:.1f} "
            f"below threshold {config.theme_change_threshold}"
        )

    # Rule 3: Cooldown period between changes
    theme_name = proposal.get("theme_name")
    last_change_key = f"theme_change_last_{theme_name}"

    try:
        last_change_str = storage.get_bot_state(last_change_key)
        if last_change_str:
            last_change = datetime.fromisoformat(last_change_str)
            days_since = (datetime.now(timezone.utc) - last_change).days

            if days_since < config.theme_change_cooldown_days:
                return False, (
                    f"Cooldown active: {days_since} days since last change "
                    f"(minimum {config.theme_change_cooldown_days} days)"
                )
    except Exception as e:
        logger.warning(f"Could not parse last theme change date: {e}")

    # Rule 4: Kill switch - no theme changes during drawdown
    try:
        equity = storage.get_latest_equity()
        high_equity = storage.get_equity_high_last_n_days(config.kill_switch_lookback_days)

        if equity and high_equity and high_equity > 0:
            drawdown_pct = (equity - high_equity) / high_equity

            if drawdown_pct <= -config.kill_switch_drawdown_pct:
                return False, (
                    f"Kill switch active (drawdown {drawdown_pct*100:.1f}%). "
                    f"No theme changes during portfolio drawdown."
                )
    except Exception as e:
        logger.warning(f"Could not check drawdown for theme change: {e}")

    # Rule 5: Requires approval if flag is set
    status = proposal.get("status", "proposed")
    if config.theme_change_requires_approval and status not in ["approved", "executed"]:
        return False, "Theme changes require explicit user approval (set status='approved' to proceed)"

    # All checks passed
    return True, ""


def can_execute_theme_change(storage, proposal: dict) -> bool:
    """Check if theme change can be executed (simplified boolean check).

    Args:
        storage: StorageManager instance
        proposal: Theme change proposal dictionary

    Returns:
        True if change can proceed, False otherwise
    """
    allowed, _ = check_theme_change_governance(storage, proposal)
    return allowed


def get_theme_change_block_reason(storage, proposal: dict) -> str:
    """Get the reason why a theme change is blocked.

    Args:
        storage: StorageManager instance
        proposal: Theme change proposal dictionary

    Returns:
        Reason string, or empty string if change is allowed
    """
    _, reason = check_theme_change_governance(storage, proposal)
    return reason


def record_theme_change(storage, theme_name: str) -> None:
    """Record that a theme change was executed (for cooldown tracking).

    Args:
        storage: StorageManager instance
        theme_name: Name of theme that was changed
    """
    last_change_key = f"theme_change_last_{theme_name}"
    storage.set_bot_state(last_change_key, datetime.now(timezone.utc).isoformat())
    logger.info(f"Recorded theme change for {theme_name} at {datetime.now(timezone.utc)}")


def get_days_since_last_change(storage, theme_name: str) -> int:
    """Get number of days since last theme change.

    Args:
        storage: StorageManager instance
        theme_name: Name of theme to check

    Returns:
        Number of days since last change, or 9999 if never changed
    """
    last_change_key = f"theme_change_last_{theme_name}"

    try:
        last_change_str = storage.get_bot_state(last_change_key)
        if last_change_str:
            last_change = datetime.fromisoformat(last_change_str)
            days_since = (datetime.now(timezone.utc) - last_change).days
            return days_since
    except Exception as e:
        logger.warning(f"Could not get last theme change date: {e}")

    # Never changed
    return 9999


def get_cooldown_remaining_days(storage, theme_name: str) -> int:
    """Get number of days remaining in cooldown period.

    Args:
        storage: StorageManager instance
        theme_name: Name of theme to check

    Returns:
        Number of days remaining in cooldown, or 0 if no cooldown active
    """
    days_since = get_days_since_last_change(storage, theme_name)
    cooldown_days = config.theme_change_cooldown_days

    if days_since >= cooldown_days:
        return 0  # No cooldown

    return cooldown_days - days_since
