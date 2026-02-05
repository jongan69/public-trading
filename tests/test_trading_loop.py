"""Tests for trading loop state machine."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from src.trading_loop import (
    run_research,
    run_strategy_preview,
    run_execute,
    run_observe,
    run_adjust,
    run_cycle,
    get_loop_status,
    STATE_IDLE,
    STATE_RESEARCH,
    STATE_STRATEGY_PREVIEW,
    STATE_EXECUTE,
    STATE_OBSERVE,
    STATE_ADJUST,
)


@pytest.fixture
def mock_bot():
    """Create a mock trading bot for testing."""
    bot = Mock()
    bot.portfolio_manager = Mock()
    bot.portfolio_manager.get_equity.return_value = 10000.0
    bot.portfolio_manager.get_cash.return_value = 2000.0
    bot.portfolio_manager.get_buying_power.return_value = 5000.0
    bot.portfolio_manager.get_current_allocations.return_value = {
        "theme_a": 0.35,
        "theme_b": 0.35,
        "moonshot": 0.20,
        "cash": 0.10,
    }

    bot.storage = Mock()
    bot.storage.save_equity_history.return_value = None
    bot.storage.save_portfolio_snapshot.return_value = None
    bot.storage.get_equity_high_last_n_days.return_value = 11000.0
    bot.storage.get_balance_trends.return_value = [
        {"equity": 10000.0, "config": {"theme_a_target": 0.35}},
        {"equity": 9500.0, "config": {"theme_a_target": 0.35}},
    ]
    bot.storage.get_bot_state.return_value = None
    bot.storage.set_bot_state.return_value = None
    bot.storage.save_pending_alerts.return_value = None

    bot.strategy = Mock()
    bot.strategy.run_daily_logic.return_value = []

    bot.run_daily_logic = Mock(return_value={
        "orders_planned": 0,
        "orders_skipped": 0,
        "orders_sent": 0,
    })

    return bot


@patch("src.trading_loop.config")
def test_run_research(mock_config, mock_bot):
    """Test research phase of trading loop."""
    mock_config.kill_switch_lookback_days = 30
    mock_config.theme_underlyings = ["UMC", "TE"]
    mock_config.proactive_alerts_enabled = False

    result = run_research(mock_bot)

    assert "research_summary" in result
    assert "equity" in result
    assert result["equity"] == 10000.0
    assert "drawdown_pct" in result

    # Verify portfolio was refreshed
    mock_bot.portfolio_manager.refresh_portfolio.assert_called_once()

    # Verify equity was saved
    mock_bot.storage.save_equity_history.assert_called_once()


@patch("src.trading_loop.config")
def test_run_strategy_preview(mock_config, mock_bot):
    """Test strategy preview phase."""
    mock_config.dry_run = False

    # Mock strategy to return some orders
    mock_bot.strategy.run_daily_logic.return_value = [
        {"action": "BUY", "symbol": "UMC", "quantity": 1, "price": 5.0},
        {"action": "SELL", "symbol": "TE", "quantity": 1, "price": 10.0},
    ]

    result = run_strategy_preview(mock_bot)

    assert result["order_count"] == 2
    assert "order_summary" in result
    assert "BUY" in result["order_summary"]

    # Verify dry_run was temporarily set to True
    mock_bot.strategy.run_daily_logic.assert_called_once()


@patch("src.trading_loop.config")
def test_run_execute_dry_run(mock_config, mock_bot):
    """Test execute phase skips when dry_run is enabled."""
    mock_config.dry_run = True

    result = run_execute(mock_bot, execute_trades=True)

    assert result["executed"] is False
    assert "dry_run" in result["reason"]


@patch("src.trading_loop.config")
def test_run_execute_disabled(mock_config, mock_bot):
    """Test execute phase skips when execute_trades is False."""
    mock_config.dry_run = False

    result = run_execute(mock_bot, execute_trades=False)

    assert result["executed"] is False


@patch("src.trading_loop.config")
def test_run_execute_success(mock_config, mock_bot):
    """Test execute phase runs when enabled."""
    mock_config.dry_run = False
    mock_config.order_poll_timeout_loop_seconds = 30

    mock_bot.run_daily_logic.return_value = {
        "orders_planned": 2,
        "orders_skipped": 0,
        "orders_sent": 2,
    }

    result = run_execute(mock_bot, execute_trades=True)

    assert result["executed"] is True
    assert result["orders_sent"] == 2


def test_run_observe(mock_bot):
    """Test observe phase."""
    result = run_observe(mock_bot)

    assert "outcome_summary" in result
    assert "equity" in result
    assert result["equity"] == 10000.0


@patch("src.trading_loop.config")
def test_run_adjust_no_suggestions(mock_config, mock_bot):
    """Test adjust phase with no drawdown."""
    mock_config.trading_loop_apply_adjustments = False

    research = {"drawdown_pct": -0.05}
    observe = {"balance_trend_7d": "+5%"}

    result = run_adjust(mock_bot, research, observe)

    assert "suggestions" in result
    assert result["applied"] is False


@patch("src.trading_loop.config")
def test_run_adjust_drawdown_warning(mock_config, mock_bot):
    """Test adjust phase suggests changes on large drawdown."""
    mock_config.trading_loop_apply_adjustments = False

    research = {"drawdown_pct": -0.18}
    observe = {"balance_trend_7d": "-10%"}

    result = run_adjust(mock_bot, research, observe)

    assert "suggestions" in result
    assert "15%" in result["suggestions"]


@patch("src.trading_loop.config")
@patch("src.trading_loop.ConfigOverrideManager")
def test_run_adjust_applies_changes(mock_override_mgr, mock_config, mock_bot):
    """Test adjust phase applies config changes when enabled."""
    mock_config.trading_loop_apply_adjustments = True
    mock_config.moonshot_target = 0.20

    mock_bot.storage.get_bot_state.return_value = None

    research = {"drawdown_pct": -0.18}
    observe = {"balance_trend_7d": "-10%"}

    result = run_adjust(mock_bot, research, observe)

    assert result["applied"] is True
    assert len(result["applied_changes"]) > 0


@patch("src.trading_loop._cycle_lock")
def test_run_cycle_concurrent_skip(mock_lock, mock_bot):
    """Test that concurrent cycles are prevented."""
    # Simulate lock already acquired
    mock_lock.acquire.return_value = False

    result = run_cycle(mock_bot, execute_trades=False)

    assert result["skipped"] is True
    assert "running" in result["outcome"].lower()


@patch("src.trading_loop.config")
@patch("src.trading_loop._cycle_lock")
def test_run_cycle_full(mock_lock, mock_config, mock_bot):
    """Test full cycle execution."""
    mock_lock.acquire.return_value = True
    mock_config.kill_switch_lookback_days = 30
    mock_config.theme_underlyings = ["UMC"]
    mock_config.proactive_alerts_enabled = False
    mock_config.dry_run = True
    mock_config.trading_loop_apply_adjustments = False

    result = run_cycle(mock_bot, execute_trades=False)

    assert "research_summary" in result
    assert "order_count" in result
    assert "executed" in result
    assert "outcome" in result
    assert "adjustments" in result

    # Verify lock was released
    mock_lock.release.assert_called_once()


@patch("src.trading_loop.config")
@patch("src.trading_loop._cycle_lock")
def test_run_cycle_exception_releases_lock(mock_lock, mock_config, mock_bot):
    """Test that lock is released even when exception occurs."""
    mock_lock.acquire.return_value = True
    mock_config.kill_switch_lookback_days = 30

    # Make portfolio refresh raise an exception
    mock_bot.portfolio_manager.refresh_portfolio.side_effect = Exception("API error")

    result = run_cycle(mock_bot, execute_trades=False)

    assert "error" in result

    # Verify lock was still released
    mock_lock.release.assert_called_once()


def test_get_loop_status(mock_bot):
    """Test getting loop status."""
    mock_bot.storage.get_bot_state.side_effect = lambda key: {
        "trading_loop_state": STATE_RESEARCH,
        "trading_loop_last_cycle_at": datetime.now(timezone.utc).isoformat(),
        "trading_loop_last_outcome": "Equity: $10,000",
        "trading_loop_research_summary": "All good",
        "trading_loop_ideas": "Consider rebalance",
        "trading_loop_suggested_adjustments": "No changes needed",
    }.get(key)

    status = get_loop_status(mock_bot)

    assert status["state"] == STATE_RESEARCH
    assert "last_cycle_at" in status
    assert "last_outcome" in status
    assert "research_summary" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
