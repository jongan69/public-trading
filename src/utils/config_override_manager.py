"""Config override management for Telegram-edited settings (REQ-013).

This module provides persistence for config changes made via Telegram,
allowing settings to survive bot restarts. Non-sensitive settings can
also live in data/settings.json; overrides (from chat) in config_overrides.json.
"""
import json
from typing import Any, Dict, Set
from pathlib import Path
from datetime import datetime, timezone
from loguru import logger

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_OVERRIDE_FILE = _PROJECT_ROOT / "data" / "config_overrides.json"

# All non-sensitive config keys that can be updated in chat and saved
TELEGRAM_EDITABLE_KEYS: Set[str] = {
    "theme_underlyings_csv",
    "moonshot_symbol",
    "theme_a_target",
    "theme_b_target",
    "theme_c_target",
    "moonshot_target",
    "moonshot_max",
    "cash_minimum",
    "option_dte_min",
    "option_dte_max",
    "option_dte_fallback_min",
    "option_dte_fallback_max",
    "strike_range_min",
    "strike_range_max",
    "max_bid_ask_spread_pct",
    "min_open_interest",
    "min_volume",
    "use_max_pain_for_selection",
    "roll_trigger_dte",
    "roll_target_dte",
    "max_roll_debit_pct",
    "max_roll_debit_absolute",
    "take_profit_100_pct",
    "take_profit_200_pct",
    "take_profit_100_close_pct",
    "stop_loss_drawdown_pct",
    "stop_loss_underlying_pct",
    "close_if_dte_lt",
    "close_if_otm_dte_lt",
    "max_trades_per_day",
    "order_price_offset_pct",
    "order_poll_timeout_seconds",
    "order_poll_timeout_loop_seconds",
    "order_poll_interval_seconds",
    "use_sma_filter",
    "sma_period",
    "manual_mode_only",
    "trade_during_extended_hours",
    "rebalance_time_hour",
    "rebalance_time_minute",
    "rebalance_timezone",
    "kill_switch_drawdown_pct",
    "kill_switch_lookback_days",
    "kill_switch_cooldown_days",
    "max_single_position_pct",
    "max_correlated_pct",
    "db_path",
    "log_level",
    "log_file",
    "dry_run",
    "execution_tier",
    "confirm_trade_threshold_usd",
    "confirm_trade_threshold_contracts",
    "cooldown_enabled",
    "cooldown_loss_threshold_pct",
    "cooldown_loss_threshold_usd",
    "cooldown_duration_minutes",
    "proactive_alerts_enabled",
    "kill_switch_warning_pct",
    "roll_warning_days_before",
    "cap_warning_threshold_pct",
    "alert_coalescing_hours",
    "daily_briefing_enabled",
    "briefing_time_hour",
    "briefing_time_minute",
    "briefing_timezone",
    "briefing_include_market_news",
    "trading_loop_enabled",
    "trading_loop_interval_minutes",
    "trading_loop_execute_trades",
    "trading_loop_telegram_notify",
    "trading_loop_apply_adjustments",
    "trading_loop_include_fundamental",
}

# Coerce string values from chat to correct type when saving
BOOL_KEYS = {
    "use_max_pain_for_selection",
    "use_sma_filter",
    "manual_mode_only",
    "trade_during_extended_hours",
    "dry_run",
    "cooldown_enabled",
    "proactive_alerts_enabled",
    "daily_briefing_enabled",
    "briefing_include_market_news",
    "trading_loop_enabled",
    "trading_loop_execute_trades",
    "trading_loop_telegram_notify",
    "trading_loop_apply_adjustments",
    "trading_loop_include_fundamental",
}
INT_KEYS = {
    "option_dte_min", "option_dte_max", "option_dte_fallback_min", "option_dte_fallback_max",
    "min_open_interest", "min_volume",
    "roll_trigger_dte", "roll_target_dte",
    "close_if_dte_lt", "close_if_otm_dte_lt",
    "max_trades_per_day", "order_poll_timeout_seconds", "order_poll_timeout_loop_seconds",
    "order_poll_interval_seconds", "sma_period",
    "rebalance_time_hour", "rebalance_time_minute",
    "kill_switch_lookback_days", "kill_switch_cooldown_days",
    "confirm_trade_threshold_contracts", "cooldown_duration_minutes",
    "roll_warning_days_before", "briefing_time_hour", "briefing_time_minute",
    "trading_loop_interval_minutes", "alert_coalescing_hours",
}
FLOAT_KEYS = {
    "theme_a_target", "theme_b_target", "theme_c_target", "moonshot_target", "moonshot_max",
    "cash_minimum", "strike_range_min", "strike_range_max", "max_bid_ask_spread_pct",
    "max_roll_debit_pct", "max_roll_debit_absolute",
    "take_profit_100_pct", "take_profit_200_pct", "take_profit_100_close_pct",
    "stop_loss_drawdown_pct", "stop_loss_underlying_pct",
    "order_price_offset_pct", "kill_switch_drawdown_pct", "max_single_position_pct",
    "max_correlated_pct", "confirm_trade_threshold_usd", "cooldown_loss_threshold_pct",
    "cooldown_loss_threshold_usd", "kill_switch_warning_pct", "cap_warning_threshold_pct",
}


def _coerce_value(key: str, value: Any) -> Any:
    """Coerce value to the correct type for the config key."""
    if key in BOOL_KEYS:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "on")
        return bool(value)
    if key in INT_KEYS:
        return int(float(value)) if value is not None else 0
    if key in FLOAT_KEYS:
        return float(value) if value is not None else 0.0
    return value if isinstance(value, str) else str(value)


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
            data.pop("_updated_at", None)
            result = {}
            for k, v in data.items():
                if k in TELEGRAM_EDITABLE_KEYS:
                    result[k] = _coerce_value(k, v)
            return result
        except Exception as e:
            logger.warning(f"Error loading config overrides: {e}")
            return {}

    @staticmethod
    def save_override(key: str, value: Any) -> None:
        """Save a single config override to JSON file.

        Args:
            key: Config key to override
            value: New value for the config key

        Raises:
            ValueError: If key is not in the whitelist
        """
        if key not in TELEGRAM_EDITABLE_KEYS:
            raise ValueError(f"Key '{key}' is not editable via chat")
        ConfigOverrideManager.save_overrides({key: value})

    @staticmethod
    def save_overrides(overrides: Dict[str, Any]) -> None:
        """Save multiple config overrides to JSON file.

        Args:
            overrides: Dict of key -> value to save
        """
        existing = ConfigOverrideManager.load_overrides()
        for key, value in overrides.items():
            if key not in TELEGRAM_EDITABLE_KEYS:
                raise ValueError(f"Key '{key}' is not editable via chat")
            existing[key] = _coerce_value(key, value)
        existing["_updated_at"] = datetime.now(timezone.utc).isoformat()
        CONFIG_OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(CONFIG_OVERRIDE_FILE, "w") as f:
                json.dump(existing, f, indent=2)
            logger.info(f"Config overrides saved: {list(overrides.keys())}")
        except Exception as e:
            logger.error(f"Error saving config overrides: {e}")
            raise

    @staticmethod
    def clear_overrides() -> None:
        """Clear all config overrides (reset to settings.json / .env defaults)."""
        if CONFIG_OVERRIDE_FILE.exists():
            CONFIG_OVERRIDE_FILE.unlink()
            logger.info("Config overrides cleared")

    @staticmethod
    def get_override_summary() -> str:
        """Get human-readable summary of active overrides."""
        overrides = ConfigOverrideManager.load_overrides()
        if not overrides:
            return "No config overrides active (using data/settings.json or .env defaults)"

        lines = ["Active config overrides (saved from chat):"]
        for key, value in sorted(overrides.items()):
            lines.append(f"  {key} = {value}")
        lines.append("\nTo reset: delete data/config_overrides.json")
        return "\n".join(lines)
