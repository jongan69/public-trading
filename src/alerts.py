"""Proactive alerts for approaching thresholds (REQ-014).

This module checks for approaching risk thresholds and generates alerts:
- Kill switch warning: Drawdown approaching -25% trigger
- Roll needed: Option positions approaching 60 DTE roll trigger
- Cap approaching: Moonshot allocation approaching 30% cap
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from loguru import logger

from src.storage import StorageManager
from src.portfolio import PortfolioManager
from src.config import config


class AlertManager:
    """Manages proactive alerts for approaching thresholds."""

    def __init__(self, storage: StorageManager, portfolio_manager: PortfolioManager):
        """Initialize AlertManager.

        Args:
            storage: Storage instance for persisting alert state
            portfolio_manager: Portfolio manager for checking positions
        """
        self.storage = storage
        self.portfolio_manager = portfolio_manager

    def check_all_alerts(self) -> List[Dict[str, Any]]:
        """Check all alert conditions and return triggered alerts.

        Returns:
            List of alert dictionaries for newly triggered alerts
        """
        if not config.proactive_alerts_enabled:
            return []

        alerts = []

        # Check kill switch warning
        kill_switch_alert = self._check_kill_switch_warning()
        if kill_switch_alert:
            alerts.append(kill_switch_alert)

        # Check roll needed warnings
        roll_alerts = self._check_roll_needed_warnings()
        alerts.extend(roll_alerts)

        # Check cap warning
        cap_alert = self._check_cap_warning()
        if cap_alert:
            alerts.append(cap_alert)

        return alerts

    def _check_kill_switch_warning(self) -> Optional[Dict[str, Any]]:
        """Check if drawdown is approaching kill switch threshold.

        Returns:
            Alert dict if warning should trigger, None otherwise
        """
        # Get current drawdown
        portfolio = self.portfolio_manager.get_portfolio()
        if not portfolio or "drawdown" not in portfolio:
            return None

        drawdown = portfolio["drawdown"]
        warning_threshold = -config.kill_switch_warning_pct
        kill_switch_threshold = -config.kill_switch_drawdown_pct

        # Trigger if drawdown is below warning threshold but above kill switch
        if drawdown <= warning_threshold and drawdown > kill_switch_threshold:
            # Check coalescing
            if not self._should_trigger_alert("kill_switch_warning"):
                return None

            # Mark as triggered
            self.storage.mark_alert_triggered("kill_switch_warning")

            return {
                "type": "kill_switch_warning",
                "severity": "warning",
                "message": f"Drawdown warning: {drawdown:.1%} (threshold: {warning_threshold:.1%}). Kill switch activates at {kill_switch_threshold:.1%}.",
                "triggered_at": datetime.now(timezone.utc).isoformat(),
                "details": {
                    "current_drawdown": drawdown,
                    "warning_threshold": warning_threshold,
                    "kill_switch_threshold": kill_switch_threshold,
                },
            }

        return None

    def _check_roll_needed_warnings(self) -> List[Dict[str, Any]]:
        """Check if any option positions are approaching roll trigger.

        Returns:
            List of alert dicts for positions needing rolls
        """
        alerts = []

        # Get current positions
        portfolio = self.portfolio_manager.get_portfolio()
        if not portfolio or "positions" not in portfolio:
            return alerts

        roll_trigger_dte = config.roll_trigger_dte
        warning_dte = roll_trigger_dte + config.roll_warning_days_before

        # Check each position
        for pos in portfolio["positions"]:
            # Skip if not an option
            if pos.get("asset_type") != "option":
                continue

            symbol = pos.get("symbol")
            dte = pos.get("dte")

            if dte is None or not symbol:
                continue

            # Trigger if DTE is between warning and roll trigger
            if warning_dte >= dte > roll_trigger_dte:
                # Check coalescing (per-position)
                alert_key = f"roll_warning_{symbol}"
                if not self._should_trigger_alert(alert_key):
                    continue

                # Mark as triggered
                self.storage.mark_alert_triggered(alert_key)

                alerts.append({
                    "type": "roll_needed",
                    "severity": "warning",
                    "message": f"Position {symbol} approaching roll: DTE={dte} (roll trigger: {roll_trigger_dte})",
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                    "details": {
                        "symbol": symbol,
                        "current_dte": dte,
                        "roll_trigger_dte": roll_trigger_dte,
                        "warning_dte": warning_dte,
                    },
                })

        return alerts

    def _check_cap_warning(self) -> Optional[Dict[str, Any]]:
        """Check if moonshot allocation is approaching cap.

        Returns:
            Alert dict if warning should trigger, None otherwise
        """
        # Get current allocations
        portfolio = self.portfolio_manager.get_portfolio()
        if not portfolio or "allocations" not in portfolio:
            return None

        allocations = portfolio["allocations"]
        moonshot_alloc = allocations.get("moonshot", 0.0)

        warning_threshold = config.cap_warning_threshold_pct
        cap = config.moonshot_max

        # Trigger if allocation is between warning and cap
        if moonshot_alloc >= warning_threshold and moonshot_alloc < cap:
            # Check coalescing
            if not self._should_trigger_alert("cap_approaching"):
                return None

            # Mark as triggered
            self.storage.mark_alert_triggered("cap_approaching")

            return {
                "type": "cap_approaching",
                "severity": "warning",
                "message": f"Moonshot allocation approaching cap: {moonshot_alloc:.1%} (warning: {warning_threshold:.1%}, hard cap: {cap:.1%})",
                "triggered_at": datetime.now(timezone.utc).isoformat(),
                "details": {
                    "current_allocation": moonshot_alloc,
                    "warning_threshold": warning_threshold,
                    "cap": cap,
                },
            }

        return None

    def _should_trigger_alert(self, alert_key: str) -> bool:
        """Check if alert should trigger based on coalescing rules.

        Args:
            alert_key: Alert type identifier

        Returns:
            True if alert should trigger, False if coalescing blocks it
        """
        last_triggered = self.storage.get_alert_last_triggered(alert_key)
        if not last_triggered:
            return True

        # Check if enough time has passed
        coalescing_duration = timedelta(hours=config.alert_coalescing_hours)
        time_since_last = datetime.now() - last_triggered.replace(tzinfo=None)

        return time_since_last >= coalescing_duration
