"""Tests for main TradingBot orchestration."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from src.main import TradingBot


@pytest.fixture
def mock_client():
    """Create a mock trading client."""
    client = Mock()
    client.account_number = "TEST123"
    return client


@pytest.fixture
def mock_storage():
    """Create a mock storage instance."""
    storage = Mock()
    storage.get_equity_high_last_n_days.return_value = 12000.0
    storage.get_bot_state.return_value = None
    storage.set_bot_state.return_value = None
    storage.save_order.return_value = None
    storage.update_order_status.return_value = None
    storage.save_fill.return_value = None
    storage.get_orders_by_status.return_value = []
    return storage


@pytest.fixture
@patch("src.main.PortfolioManager")
@patch("src.main.ExecutionManager")
@patch("src.main.MarketDataManager")
@patch("src.main.Strategy")
@patch("src.main.Storage")
def mock_bot(mock_storage_cls, mock_strategy_cls, mock_market_cls, mock_exec_cls, mock_portfolio_cls, mock_client):
    """Create a TradingBot instance with mocked dependencies."""
    mock_storage_instance = Mock()
    mock_storage_instance.get_equity_high_last_n_days.return_value = 12000.0
    mock_storage_cls.return_value = mock_storage_instance

    mock_portfolio_instance = Mock()
    mock_portfolio_instance.get_equity.return_value = 10000.0
    mock_portfolio_cls.return_value = mock_portfolio_instance

    mock_exec_instance = Mock()
    mock_exec_cls.return_value = mock_exec_instance

    mock_market_instance = Mock()
    mock_market_cls.return_value = mock_market_instance

    mock_strategy_instance = Mock()
    mock_strategy_instance.trades_today = 0
    mock_strategy_cls.return_value = mock_strategy_instance

    bot = TradingBot(mock_client)
    return bot


class TestKillSwitch:
    """Tests for kill switch functionality."""

    @patch("src.main.config")
    def test_kill_switch_inactive_no_drawdown(self, mock_config, mock_bot):
        """Test kill switch remains inactive when no drawdown."""
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30

        mock_bot.portfolio_manager.get_equity.return_value = 11500.0
        mock_bot.storage.get_equity_high_last_n_days.return_value = 12000.0

        result = mock_bot.check_kill_switch()

        assert result is False

    @patch("src.main.config")
    def test_kill_switch_activates_on_large_drawdown(self, mock_config, mock_bot):
        """Test kill switch activates when drawdown exceeds threshold."""
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30

        mock_bot.portfolio_manager.get_equity.return_value = 8500.0  # 29% down from 12000
        mock_bot.storage.get_equity_high_last_n_days.return_value = 12000.0

        result = mock_bot.check_kill_switch()

        assert result is True

    @patch("src.main.config")
    def test_kill_switch_first_month_no_history(self, mock_config, mock_bot):
        """Test kill switch doesn't crash when no equity history exists."""
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30

        mock_bot.portfolio_manager.get_equity.return_value = 5000.0
        mock_bot.storage.get_equity_high_last_n_days.return_value = None

        result = mock_bot.check_kill_switch()

        # Should not activate (returns False) when no history
        assert result is False


class TestCooldown:
    """Tests for cooldown functionality."""

    @patch("src.main.config")
    def test_cooldown_not_triggered_small_loss(self, mock_config, mock_bot):
        """Test cooldown not triggered on small loss."""
        mock_config.cooldown_enabled = True
        mock_config.cooldown_loss_threshold_pct = 0.10
        mock_config.cooldown_loss_threshold_usd = 500.0

        order_details = {
            "action": "SELL",
            "entry_price": 5.0,
        }
        result = {
            "price": 4.8,
            "quantity": 10,
        }

        triggered = mock_bot.check_and_trigger_cooldown(order_details, result)

        assert triggered is False

    @patch("src.main.config")
    def test_cooldown_triggered_large_loss_pct(self, mock_config, mock_bot):
        """Test cooldown triggered on large percentage loss."""
        mock_config.cooldown_enabled = True
        mock_config.cooldown_loss_threshold_pct = 0.10
        mock_config.cooldown_loss_threshold_usd = 500.0
        mock_config.cooldown_duration_minutes = 60

        order_details = {
            "action": "SELL",
            "entry_price": 10.0,
        }
        result = {
            "price": 8.0,  # 20% loss
            "quantity": 10,
        }

        triggered = mock_bot.check_and_trigger_cooldown(order_details, result)

        assert triggered is True

    @patch("src.main.config")
    def test_cooldown_triggered_large_loss_usd(self, mock_config, mock_bot):
        """Test cooldown triggered on large dollar loss."""
        mock_config.cooldown_enabled = True
        mock_config.cooldown_loss_threshold_pct = 0.10
        mock_config.cooldown_loss_threshold_usd = 500.0
        mock_config.cooldown_duration_minutes = 60

        order_details = {
            "action": "SELL",
            "entry_price": 100.0,
        }
        result = {
            "price": 94.0,  # $600 loss
            "quantity": 10,
        }

        triggered = mock_bot.check_and_trigger_cooldown(order_details, result)

        assert triggered is True


class TestOrderExecution:
    """Tests for order execution flow."""

    @patch("src.main.config")
    def test_order_execution_respects_max_trades_per_day(self, mock_config, mock_bot):
        """Test that max trades per day is enforced."""
        mock_config.max_trades_per_day = 5
        mock_config.dry_run = False

        # Set strategy to already have 5 trades today
        mock_bot.strategy.trades_today = 5
        mock_bot.strategy.run_daily_logic.return_value = [
            {"action": "BUY", "symbol": "UMC", "quantity": 1, "price": 5.0},
        ]

        result = mock_bot.run_daily_logic()

        # No orders should be sent (0 because max reached)
        assert result["orders_sent"] == 0

    @patch("src.main.config")
    def test_order_execution_logs_large_trades(self, mock_config, mock_bot):
        """Test that large trades are logged for visibility."""
        mock_config.max_trades_per_day = 10
        mock_config.dry_run = False
        mock_config.confirm_trade_threshold_usd = 500.0
        mock_config.confirm_trade_threshold_contracts = 10

        mock_bot.strategy.trades_today = 0
        mock_bot.strategy.run_daily_logic.return_value = [
            {"action": "BUY", "symbol": "UMC", "quantity": 20, "price": 50.0},  # $1000 order
        ]
        mock_bot.execution_manager.execute_order.return_value = {
            "order_id": "ORDER123",
            "symbol": "UMC",
            "quantity": 20,
            "price": 50.0,
            "status": "FILLED",
        }

        with patch("src.main.logger") as mock_logger:
            result = mock_bot.run_daily_logic()

            # Should log warning for large trade
            warning_calls = [call for call in mock_logger.warning.call_args_list if "Large trade" in str(call)]
            assert len(warning_calls) > 0

    @patch("src.main.config")
    def test_order_blocked_by_preflight(self, mock_config, mock_bot):
        """Test order execution handles preflight blocks correctly."""
        mock_config.max_trades_per_day = 10
        mock_config.dry_run = False

        mock_bot.strategy.trades_today = 0
        mock_bot.strategy.run_daily_logic.return_value = [
            {"action": "BUY", "symbol": "INVALID", "quantity": 1, "price": 5.0},
        ]

        # Execution manager returns error (preflight failed)
        mock_bot.execution_manager.execute_order.return_value = {
            "ok": False,
            "error": "Preflight check failed"
        }

        result = mock_bot.run_daily_logic()

        # No orders should be sent
        assert result["orders_sent"] == 0


class TestRebalanceScheduling:
    """Tests for scheduled rebalancing."""

    @patch("src.main.config")
    @patch("src.main.datetime")
    def test_should_rebalance_today_correct_time(self, mock_datetime, mock_config, mock_bot):
        """Test rebalance triggers at correct time."""
        from datetime import datetime
        import pytz

        mock_config.rebalance_time_hour = 9
        mock_config.rebalance_time_minute = 30
        mock_config.rebalance_timezone = "America/New_York"

        # Set current time to 9:35 AM ET (after rebalance time)
        et_tz = pytz.timezone("America/New_York")
        current_time = et_tz.localize(datetime(2026, 2, 5, 9, 35))
        mock_datetime.now.return_value = current_time

        # No previous rebalance today
        mock_bot._last_rebalance_date = None

        result = mock_bot.should_rebalance_today()

        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
