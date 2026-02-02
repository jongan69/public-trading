"""Config override management for Telegram-edited settings (REQ-013).

This module provides persistence for config changes made via Telegram,
allowing settings to survive bot restarts.
"""
import json
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timezone
from loguru import logger

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_OVERRIDE_FILE = _PROJECT_ROOT / "data" / "config_overrides.json"

# Keys that can be persisted via Telegram (whitelist)
TELEGRAM_EDITABLE_KEYS = {
    # update_allocation_targets
    "theme_a_target",
    "theme_b_target",
    "theme_c_target",
    "moonshot_target",
    "cash_minimum",
    # update_option_rules
    "option_dte_min",
    "option_dte_max",
    "strike_range_min",
    "strike_range_max",
    # update_theme_symbols
    "theme_underlyings_csv",
}


class ConfigOverrideManager:
    """Manages config overrides from Telegram edits."""

    @staticmethod
    def load_overrides() -> Dict[str, Any]:
        """Load config overrides from JSON file.

        Returns:
            Dict of config overrides (empty if file doesn't exist or is invalid)
        """
        if not CONFIG_OVERRIDE_FILE.exists():
            return {}

        try:
            with open(CONFIG_OVERRIDE_FILE, "r") as f:
                data = json.load(f)
                # Remove metadata before returning
                data.pop("_updated_at", None)
                # Filter to only allowed keys
                return {k: v for k, v in data.items() if k in TELEGRAM_EDITABLE_KEYS}
        except Exception as e:
            logger.warning(f"Error loading config overrides: {e}")
            return {}

    @staticmethod
    def save_override(key: str, value: Any):
        """Save a single config override to JSON file.

        Args:
            key: Config key to override
            value: New value for the config key

        Raises:
            ValueError: If key is not in the whitelist
        """
        if key not in TELEGRAM_EDITABLE_KEYS:
            raise ValueError(f"Key '{key}' is not Telegram-editable")

        # Load existing overrides
        overrides = ConfigOverrideManager.load_overrides()

        # Update with new value
        overrides[key] = value
        overrides["_updated_at"] = datetime.now(timezone.utc).isoformat()

        # Ensure directory exists
        CONFIG_OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(CONFIG_OVERRIDE_FILE, "w") as f:
                json.dump(overrides, f, indent=2)
            logger.info(f"Config override saved: {key}={value}")
        except Exception as e:
            logger.error(f"Error saving config override: {e}")
            raise

    @staticmethod
    def clear_overrides():
        """Clear all config overrides (reset to .env defaults)."""
        if CONFIG_OVERRIDE_FILE.exists():
            CONFIG_OVERRIDE_FILE.unlink()
            logger.info("Config overrides cleared")

    @staticmethod
    def get_override_summary() -> str:
        """Get human-readable summary of active overrides.

        Returns:
            Formatted string describing active overrides
        """
        overrides = ConfigOverrideManager.load_overrides()
        if not overrides:
            return "No config overrides active (using .env defaults)"

        lines = ["Active config overrides (from Telegram):"]
        for key, value in sorted(overrides.items()):
            lines.append(f"  {key} = {value}")
        lines.append("\nTo reset: delete data/config_overrides.json")
        return "\n".join(lines)
