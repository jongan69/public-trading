"""Preset strategy profiles for quick reference (REQ-019)."""
from typing import Optional, Dict
from src.utils.strategy_math import StrategyProfile


PRESET_STRATEGIES = {
    "daily_3pct_grind": StrategyProfile(
        name="Daily 3% Grind",
        win_rate=0.58,
        avg_win=0.03,
        avg_loss=0.03,
        trades_per_year=220
    ),
    "high_conviction": StrategyProfile(
        name="High Conviction",
        win_rate=0.40,
        avg_win=0.40,
        avg_loss=0.15,
        trades_per_year=10
    ),
}


def get_preset(name: str) -> Optional[StrategyProfile]:
    """Retrieve a preset strategy profile by name (case-insensitive).

    Args:
        name: Preset name (e.g., "daily_3pct_grind", "high_conviction")

    Returns:
        StrategyProfile instance if found, None otherwise

    Example:
        >>> profile = get_preset("daily_3pct_grind")
        >>> if profile:
        ...     print(f"{profile.name}: {profile.win_rate*100:.0f}% win rate")
        Daily 3% Grind: 58% win rate
    """
    return PRESET_STRATEGIES.get(name.lower())


def list_presets() -> Dict[str, str]:
    """Return dict of available presets and their descriptions.

    Returns:
        Dict mapping preset key to human-readable name

    Example:
        >>> presets = list_presets()
        >>> for key, name in presets.items():
        ...     print(f"{key}: {name}")
        daily_3pct_grind: Daily 3% Grind
        high_conviction: High Conviction
    """
    return {name: profile.name for name, profile in PRESET_STRATEGIES.items()}
