"""Tests for AlertManager (REQ-014)."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.alerts import AlertManager
from src.storage import StorageManager
from src.portfolio import PortfolioManager
from src.config import config


@pytest.fixture
def mock_storage():
    """Create mock storage."""
    storage = Mock(spec=StorageManager)
    storage.get_alert_last_triggered = Mock(return_value=None)
    storage.mark_alert_triggered = Mock()
    storage.get_pending_alerts = Mock(return_value=[])
    storage.save_pending_alerts = Mock()
    storage.clear_pending_alerts = Mock()
    return storage


@pytest.fixture
def mock_portfolio_manager():
    """Create mock portfolio manager."""
    pm = Mock(spec=PortfolioManager)
    pm.get_portfolio = Mock(return_value={})
    return pm


@pytest.fixture
def alert_manager(mock_storage, mock_portfolio_manager):
    """Create AlertManager instance."""
    return AlertManager(mock_storage, mock_portfolio_manager)


def test_alerts_disabled_when_config_flag_false(alert_manager, mock_portfolio_manager):
    """Test that alerts are not triggered when disabled in config."""
    with patch.object(config, 'proactive_alerts_enabled', False):
        # Set up portfolio with conditions that would trigger alerts
        mock_portfolio_manager.get_portfolio.return_value = {
            "drawdown": -0.22,
            "allocations": {"moonshot": 0.29},
            "positions": [],
        }

        alerts = alert_manager.check_all_alerts()
        assert alerts == []


def test_kill_switch_warning_at_threshold(alert_manager, mock_portfolio_manager):
    """Test kill switch warning triggers at -20% drawdown."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                # Set drawdown to -20.5% (below warning, above kill switch)
                mock_portfolio_manager.get_portfolio.return_value = {
                    "drawdown": -0.205,
                }

                alerts = alert_manager.check_all_alerts()

                assert len(alerts) == 1
                assert alerts[0]["type"] == "kill_switch_warning"
                assert alerts[0]["severity"] == "warning"
                assert "-20.5%" in alerts[0]["message"] or "-21%" in alerts[0]["message"]
                assert "Kill switch" in alerts[0]["message"]


def test_kill_switch_warning_not_triggered_above_threshold(alert_manager, mock_portfolio_manager):
    """Test kill switch warning does not trigger above threshold."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            # Set drawdown to -15% (above warning threshold)
            mock_portfolio_manager.get_portfolio.return_value = {
                "drawdown": -0.15,
            }

            alerts = alert_manager.check_all_alerts()

            # Should not have kill switch warning
            kill_switch_alerts = [a for a in alerts if a["type"] == "kill_switch_warning"]
            assert len(kill_switch_alerts) == 0


def test_kill_switch_warning_not_triggered_below_kill_switch(alert_manager, mock_portfolio_manager):
    """Test kill switch warning does not trigger when already past kill switch."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                # Set drawdown to -26% (below kill switch)
                mock_portfolio_manager.get_portfolio.return_value = {
                    "drawdown": -0.26,
                }

                alerts = alert_manager.check_all_alerts()

                # Should not have kill switch warning (already triggered)
                kill_switch_alerts = [a for a in alerts if a["type"] == "kill_switch_warning"]
                assert len(kill_switch_alerts) == 0


def test_roll_warning_at_67_dte(alert_manager, mock_portfolio_manager):
    """Test roll warning triggers at 67 DTE."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'roll_trigger_dte', 60):
            with patch.object(config, 'roll_warning_days_before', 7):
                # Set position at 65 DTE (between warning 67 and trigger 60)
                mock_portfolio_manager.get_portfolio.return_value = {
                    "positions": [
                        {
                            "asset_type": "option",
                            "symbol": "UMC250117C00100000",
                            "dte": 65,
                        }
                    ],
                }

                alerts = alert_manager.check_all_alerts()

                roll_alerts = [a for a in alerts if a["type"] == "roll_needed"]
                assert len(roll_alerts) == 1
                assert "UMC250117C00100000" in roll_alerts[0]["message"]
                assert "DTE=65" in roll_alerts[0]["message"]


def test_roll_warning_multiple_positions(alert_manager, mock_portfolio_manager):
    """Test roll warnings for multiple positions."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'roll_trigger_dte', 60):
            with patch.object(config, 'roll_warning_days_before', 7):
                # Multiple positions needing rolls
                mock_portfolio_manager.get_portfolio.return_value = {
                    "positions": [
                        {"asset_type": "option", "symbol": "AAPL250117C001000", "dte": 65},
                        {"asset_type": "option", "symbol": "MSFT250117C002000", "dte": 63},
                        {"asset_type": "option", "symbol": "TSLA250117C003000", "dte": 50},  # Below trigger
                    ],
                }

                alerts = alert_manager.check_all_alerts()

                roll_alerts = [a for a in alerts if a["type"] == "roll_needed"]
                assert len(roll_alerts) == 2  # Only first two


def test_roll_warning_not_triggered_for_stocks(alert_manager, mock_portfolio_manager):
    """Test roll warning does not trigger for stock positions."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'roll_trigger_dte', 60):
            with patch.object(config, 'roll_warning_days_before', 7):
                # Stock position (no DTE)
                mock_portfolio_manager.get_portfolio.return_value = {
                    "positions": [
                        {"asset_type": "stock", "symbol": "AAPL", "quantity": 100},
                    ],
                }

                alerts = alert_manager.check_all_alerts()

                roll_alerts = [a for a in alerts if a["type"] == "roll_needed"]
                assert len(roll_alerts) == 0


def test_cap_warning_at_28_percent(alert_manager, mock_portfolio_manager):
    """Test cap warning triggers at 28% allocation."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'cap_warning_threshold_pct', 0.28):
            with patch.object(config, 'moonshot_max', 0.30):
                # Set moonshot allocation to 28.5%
                mock_portfolio_manager.get_portfolio.return_value = {
                    "allocations": {"moonshot": 0.285},
                }

                alerts = alert_manager.check_all_alerts()

                cap_alerts = [a for a in alerts if a["type"] == "cap_approaching"]
                assert len(cap_alerts) == 1
                assert "28.5%" in cap_alerts[0]["message"] or "29%" in cap_alerts[0]["message"]
                assert "Moonshot" in cap_alerts[0]["message"]


def test_cap_warning_not_triggered_below_threshold(alert_manager, mock_portfolio_manager):
    """Test cap warning does not trigger below threshold."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'cap_warning_threshold_pct', 0.28):
            # Set moonshot allocation to 25%
            mock_portfolio_manager.get_portfolio.return_value = {
                "allocations": {"moonshot": 0.25},
            }

            alerts = alert_manager.check_all_alerts()

            cap_alerts = [a for a in alerts if a["type"] == "cap_approaching"]
            assert len(cap_alerts) == 0


def test_cap_warning_not_triggered_above_cap(alert_manager, mock_portfolio_manager):
    """Test cap warning does not trigger when already above cap."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'cap_warning_threshold_pct', 0.28):
            with patch.object(config, 'moonshot_max', 0.30):
                # Set moonshot allocation to 31% (above cap)
                mock_portfolio_manager.get_portfolio.return_value = {
                    "allocations": {"moonshot": 0.31},
                }

                alerts = alert_manager.check_all_alerts()

                cap_alerts = [a for a in alerts if a["type"] == "cap_approaching"]
                assert len(cap_alerts) == 0


def test_coalescing_blocks_duplicate_alerts(alert_manager, mock_storage, mock_portfolio_manager):
    """Test coalescing prevents duplicate alerts within 24 hours."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                with patch.object(config, 'alert_coalescing_hours', 24):
                    # Set drawdown to trigger alert
                    mock_portfolio_manager.get_portfolio.return_value = {
                        "drawdown": -0.21,
                    }

                    # First call - should trigger
                    alerts1 = alert_manager.check_all_alerts()
                    assert len(alerts1) == 1

                    # Mock that alert was just triggered
                    mock_storage.get_alert_last_triggered = Mock(
                        return_value=datetime.now() - timedelta(hours=1)
                    )

                    # Second call within 24 hours - should not trigger
                    alerts2 = alert_manager.check_all_alerts()
                    assert len(alerts2) == 0


def test_coalescing_allows_alert_after_24_hours(alert_manager, mock_storage, mock_portfolio_manager):
    """Test coalescing allows alert after coalescing period."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                with patch.object(config, 'alert_coalescing_hours', 24):
                    # Set drawdown to trigger alert
                    mock_portfolio_manager.get_portfolio.return_value = {
                        "drawdown": -0.21,
                    }

                    # Mock that alert was triggered 25 hours ago
                    mock_storage.get_alert_last_triggered = Mock(
                        return_value=datetime.now() - timedelta(hours=25)
                    )

                    # Should trigger again
                    alerts = alert_manager.check_all_alerts()
                    assert len(alerts) == 1


def test_multiple_alerts_triggered_simultaneously(alert_manager, mock_portfolio_manager):
    """Test multiple alerts can trigger at once."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                with patch.object(config, 'cap_warning_threshold_pct', 0.28):
                    with patch.object(config, 'moonshot_max', 0.30):
                        with patch.object(config, 'roll_trigger_dte', 60):
                            with patch.object(config, 'roll_warning_days_before', 7):
                                # Set conditions to trigger all 3 alert types
                                mock_portfolio_manager.get_portfolio.return_value = {
                                    "drawdown": -0.21,  # Kill switch warning
                                    "allocations": {"moonshot": 0.29},  # Cap warning
                                    "positions": [
                                        {"asset_type": "option", "symbol": "TEST", "dte": 65},  # Roll warning
                                    ],
                                }

                                alerts = alert_manager.check_all_alerts()

                                assert len(alerts) == 3
                                alert_types = {a["type"] for a in alerts}
                                assert alert_types == {"kill_switch_warning", "roll_needed", "cap_approaching"}


def test_alert_structure(alert_manager, mock_portfolio_manager):
    """Test alert objects have correct structure."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                mock_portfolio_manager.get_portfolio.return_value = {
                    "drawdown": -0.21,
                }

                alerts = alert_manager.check_all_alerts()

                assert len(alerts) == 1
                alert = alerts[0]

                # Check required fields
                assert "type" in alert
                assert "severity" in alert
                assert "message" in alert
                assert "triggered_at" in alert
                assert "details" in alert

                # Check values
                assert alert["severity"] == "warning"
                assert isinstance(alert["details"], dict)


def test_storage_integration(mock_storage, mock_portfolio_manager):
    """Test alert manager integrates correctly with storage."""
    alert_manager = AlertManager(mock_storage, mock_portfolio_manager)

    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                mock_portfolio_manager.get_portfolio.return_value = {
                    "drawdown": -0.21,
                }

                alerts = alert_manager.check_all_alerts()

                # Should have called storage methods
                assert mock_storage.get_alert_last_triggered.called
                assert mock_storage.mark_alert_triggered.called
