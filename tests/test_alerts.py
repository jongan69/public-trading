"""Tests for AlertManager (REQ-014)."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from public_api_sdk import InstrumentType
from src.alerts import AlertManager
from src.storage import StorageManager
from src.portfolio import PortfolioManager
from src.config import config


def _make_mock_option_position(symbol: str, dte: int):
    """Create a mock option position with get_dte() and instrument_type."""
    pos = Mock()
    pos.symbol = symbol
    pos.instrument_type = InstrumentType.OPTION
    pos.get_dte = Mock(return_value=dte)
    return pos


@pytest.fixture
def mock_storage():
    """Create mock storage."""
    storage = Mock(spec=StorageManager)
    storage.get_alert_last_triggered = Mock(return_value=None)
    storage.mark_alert_triggered = Mock()
    storage.get_pending_alerts = Mock(return_value=[])
    storage.save_pending_alerts = Mock()
    storage.clear_pending_alerts = Mock()
    storage.get_equity_high_last_n_days = Mock(return_value=1000.0)
    return storage


@pytest.fixture
def mock_portfolio_manager():
    """Create mock portfolio manager (uses get_equity, get_current_allocations, positions)."""
    pm = Mock(spec=PortfolioManager)
    pm.get_equity = Mock(return_value=1000.0)
    pm.get_current_allocations = Mock(return_value={"moonshot": 0.0, "theme_a": 0.0, "theme_b": 0.0, "theme_c": 0.0, "cash": 0.0})
    pm.positions = {}
    return pm


@pytest.fixture
def alert_manager(mock_storage, mock_portfolio_manager):
    """Create AlertManager instance."""
    return AlertManager(mock_storage, mock_portfolio_manager)


def test_alerts_disabled_when_config_flag_false(alert_manager, mock_portfolio_manager):
    """Test that alerts are not triggered when disabled in config."""
    with patch.object(config, 'proactive_alerts_enabled', False):
        mock_portfolio_manager.get_equity.return_value = 780
        mock_portfolio_manager.get_current_allocations.return_value = {"moonshot": 0.29, "theme_a": 0.0, "theme_b": 0.0, "theme_c": 0.0, "cash": 0.0}

        alerts = alert_manager.check_all_alerts()
        assert alerts == []


def test_kill_switch_warning_at_threshold(alert_manager, mock_portfolio_manager, mock_storage):
    """Test kill switch warning triggers at -20% drawdown."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                mock_storage.get_equity_high_last_n_days.return_value = 1000.0
                mock_portfolio_manager.get_equity.return_value = 795.0  # -20.5% drawdown

                alerts = alert_manager.check_all_alerts()

                assert len(alerts) == 1
                assert alerts[0]["type"] == "kill_switch_warning"
                assert alerts[0]["severity"] == "warning"
                assert "-20.5%" in alerts[0]["message"] or "-21%" in alerts[0]["message"]
                assert "Kill switch" in alerts[0]["message"]


def test_kill_switch_warning_not_triggered_above_threshold(alert_manager, mock_portfolio_manager, mock_storage):
    """Test kill switch warning does not trigger above threshold."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            mock_storage.get_equity_high_last_n_days.return_value = 1000.0
            mock_portfolio_manager.get_equity.return_value = 850.0  # -15% drawdown

            alerts = alert_manager.check_all_alerts()

            kill_switch_alerts = [a for a in alerts if a["type"] == "kill_switch_warning"]
            assert len(kill_switch_alerts) == 0


def test_kill_switch_warning_not_triggered_below_kill_switch(alert_manager, mock_portfolio_manager, mock_storage):
    """Test kill switch warning does not trigger when already past kill switch."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                mock_storage.get_equity_high_last_n_days.return_value = 1000.0
                mock_portfolio_manager.get_equity.return_value = 740.0  # -26% drawdown

                alerts = alert_manager.check_all_alerts()

                kill_switch_alerts = [a for a in alerts if a["type"] == "kill_switch_warning"]
                assert len(kill_switch_alerts) == 0


def test_roll_warning_at_67_dte(alert_manager, mock_portfolio_manager):
    """Test roll warning triggers at 67 DTE."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'roll_trigger_dte', 60):
            with patch.object(config, 'roll_warning_days_before', 7):
                mock_portfolio_manager.positions = {
                    "UMC250117C00100000": _make_mock_option_position("UMC250117C00100000", 65),
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
                mock_portfolio_manager.positions = {
                    "AAPL250117C001000": _make_mock_option_position("AAPL250117C001000", 65),
                    "MSFT250117C002000": _make_mock_option_position("MSFT250117C002000", 63),
                    "TSLA250117C003000": _make_mock_option_position("TSLA250117C003000", 50),
                }

                alerts = alert_manager.check_all_alerts()

                roll_alerts = [a for a in alerts if a["type"] == "roll_needed"]
                assert len(roll_alerts) == 2


def test_roll_warning_not_triggered_for_stocks(alert_manager, mock_portfolio_manager):
    """Test roll warning does not trigger for stock positions."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'roll_trigger_dte', 60):
            with patch.object(config, 'roll_warning_days_before', 7):
                stock_pos = Mock()
                stock_pos.symbol = "AAPL"
                stock_pos.instrument_type = InstrumentType.EQUITY
                stock_pos.get_dte = Mock(return_value=None)
                mock_portfolio_manager.positions = {"AAPL": stock_pos}

                alerts = alert_manager.check_all_alerts()

                roll_alerts = [a for a in alerts if a["type"] == "roll_needed"]
                assert len(roll_alerts) == 0


def test_cap_warning_at_28_percent(alert_manager, mock_portfolio_manager):
    """Test cap warning triggers at 28% allocation."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'cap_warning_threshold_pct', 0.28):
            with patch.object(config, 'moonshot_max', 0.30):
                mock_portfolio_manager.get_current_allocations.return_value = {
                    "moonshot": 0.285, "theme_a": 0.0, "theme_b": 0.0, "theme_c": 0.0, "cash": 0.0
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
            mock_portfolio_manager.get_current_allocations.return_value = {
                "moonshot": 0.25, "theme_a": 0.0, "theme_b": 0.0, "theme_c": 0.0, "cash": 0.0
            }

            alerts = alert_manager.check_all_alerts()

            cap_alerts = [a for a in alerts if a["type"] == "cap_approaching"]
            assert len(cap_alerts) == 0


def test_cap_warning_not_triggered_above_cap(alert_manager, mock_portfolio_manager):
    """Test cap warning does not trigger when already above cap."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'cap_warning_threshold_pct', 0.28):
            with patch.object(config, 'moonshot_max', 0.30):
                mock_portfolio_manager.get_current_allocations.return_value = {
                    "moonshot": 0.31, "theme_a": 0.0, "theme_b": 0.0, "theme_c": 0.0, "cash": 0.0
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
                    mock_storage.get_equity_high_last_n_days.return_value = 1000.0
                    mock_portfolio_manager.get_equity.return_value = 790.0  # -21% drawdown

                    alerts1 = alert_manager.check_all_alerts()
                    assert len(alerts1) == 1

                    mock_storage.get_alert_last_triggered = Mock(
                        return_value=datetime.now() - timedelta(hours=1)
                    )

                    alerts2 = alert_manager.check_all_alerts()
                    assert len(alerts2) == 0


def test_coalescing_allows_alert_after_24_hours(alert_manager, mock_storage, mock_portfolio_manager):
    """Test coalescing allows alert after coalescing period."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                with patch.object(config, 'alert_coalescing_hours', 24):
                    mock_storage.get_equity_high_last_n_days.return_value = 1000.0
                    mock_portfolio_manager.get_equity.return_value = 790.0

                    mock_storage.get_alert_last_triggered = Mock(
                        return_value=datetime.now() - timedelta(hours=25)
                    )

                    alerts = alert_manager.check_all_alerts()
                    assert len(alerts) == 1


def test_multiple_alerts_triggered_simultaneously(alert_manager, mock_portfolio_manager, mock_storage):
    """Test multiple alerts can trigger at once."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                with patch.object(config, 'cap_warning_threshold_pct', 0.28):
                    with patch.object(config, 'moonshot_max', 0.30):
                        with patch.object(config, 'roll_trigger_dte', 60):
                            with patch.object(config, 'roll_warning_days_before', 7):
                                mock_storage.get_equity_high_last_n_days.return_value = 1000.0
                                mock_portfolio_manager.get_equity.return_value = 790.0
                                mock_portfolio_manager.get_current_allocations.return_value = {
                                    "moonshot": 0.29, "theme_a": 0.0, "theme_b": 0.0, "theme_c": 0.0, "cash": 0.0
                                }
                                mock_portfolio_manager.positions = {
                                    "TEST": _make_mock_option_position("TEST", 65),
                                }

                                alerts = alert_manager.check_all_alerts()

                                assert len(alerts) == 3
                                alert_types = {a["type"] for a in alerts}
                                assert alert_types == {"kill_switch_warning", "roll_needed", "cap_approaching"}


def test_alert_structure(alert_manager, mock_portfolio_manager, mock_storage):
    """Test alert objects have correct structure."""
    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                mock_storage.get_equity_high_last_n_days.return_value = 1000.0
                mock_portfolio_manager.get_equity.return_value = 790.0

                alerts = alert_manager.check_all_alerts()

                assert len(alerts) == 1
                alert = alerts[0]

                assert "type" in alert
                assert "severity" in alert
                assert "message" in alert
                assert "triggered_at" in alert
                assert "details" in alert
                assert alert["severity"] == "warning"
                assert isinstance(alert["details"], dict)


def test_storage_integration(mock_storage, mock_portfolio_manager):
    """Test alert manager integrates correctly with storage."""
    alert_manager = AlertManager(mock_storage, mock_portfolio_manager)

    with patch.object(config, 'proactive_alerts_enabled', True):
        with patch.object(config, 'kill_switch_warning_pct', 0.20):
            with patch.object(config, 'kill_switch_drawdown_pct', 0.25):
                mock_storage.get_equity_high_last_n_days.return_value = 1000.0
                mock_portfolio_manager.get_equity.return_value = 790.0

                alerts = alert_manager.check_all_alerts()

                assert mock_storage.get_alert_last_triggered.called
                assert mock_storage.mark_alert_triggered.called
