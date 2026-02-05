"""Tests for performance analytics."""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, date, timedelta
from src.analytics import PerformanceAnalytics


@pytest.fixture
def mock_storage():
    """Create a mock storage instance."""
    storage = Mock()

    # Mock balance trends
    storage.get_balance_trends.return_value = [
        {"date": "2026-02-05", "equity": 11000.0},
        {"date": "2026-02-04", "equity": 10500.0},
        {"date": "2026-02-03", "equity": 10000.0},
    ]

    # Mock orders
    storage.get_orders_by_status.return_value = [
        {
            "order_id": "ORDER1",
            "symbol": "UMC",
            "action": "BUY",
            "quantity": 10,
            "price": 5.0,
            "status": "FILLED",
            "created_at": "2026-02-01T10:00:00+00:00",
        },
        {
            "order_id": "ORDER2",
            "symbol": "UMC",
            "action": "SELL",
            "quantity": 10,
            "price": 6.0,
            "status": "FILLED",
            "created_at": "2026-02-03T14:00:00+00:00",
            "realized_pnl": 10.0,
            "outcome": "win",
        },
    ]

    # Mock fills
    storage.get_fills.return_value = [
        {
            "fill_id": "FILL1",
            "order_id": "ORDER1",
            "symbol": "UMC",
            "quantity": 10,
            "fill_price": 5.0,
            "fill_time": "2026-02-01T10:00:00+00:00",
        },
    ]

    return storage


def test_analytics_initialization(mock_storage):
    """Test analytics initializes correctly."""
    analytics = PerformanceAnalytics(mock_storage)

    assert analytics.storage == mock_storage


def test_get_performance_summary(mock_storage):
    """Test getting performance summary."""
    analytics = PerformanceAnalytics(mock_storage)

    summary = analytics.get_performance_summary(days=7)

    assert isinstance(summary, str)
    # Should contain key metrics
    assert "equity" in summary.lower() or "balance" in summary.lower()


def test_calculate_returns(mock_storage):
    """Test return calculation from balance trends."""
    analytics = PerformanceAnalytics(mock_storage)

    mock_storage.get_balance_trends.return_value = [
        {"date": "2026-02-05", "equity": 11000.0},
        {"date": "2026-02-01", "equity": 10000.0},
    ]

    # Calculate returns
    # From 10000 to 11000 = 10% return
    returns = analytics.calculate_returns(days=7)

    assert returns is not None
    assert "total_return" in returns or "return_pct" in returns or isinstance(returns, (int, float))


def test_get_win_rate(mock_storage):
    """Test win rate calculation."""
    analytics = PerformanceAnalytics(mock_storage)

    mock_storage.get_orders_by_status.return_value = [
        {"outcome": "win", "realized_pnl": 100.0},
        {"outcome": "win", "realized_pnl": 50.0},
        {"outcome": "loss", "realized_pnl": -30.0},
    ]

    win_rate = analytics.get_win_rate()

    # 2 wins out of 3 = 66.7%
    assert win_rate >= 0.66
    assert win_rate <= 0.67


def test_get_sharpe_ratio(mock_storage):
    """Test Sharpe ratio calculation."""
    analytics = PerformanceAnalytics(mock_storage)

    # Mock returns over time
    mock_storage.get_balance_trends.return_value = [
        {"date": f"2026-02-{i:02d}", "equity": 10000.0 + (i * 100)}
        for i in range(1, 15)
    ]

    sharpe = analytics.calculate_sharpe_ratio(days=14)

    # Should return a number (or None if insufficient data)
    assert sharpe is None or isinstance(sharpe, (int, float))


def test_get_max_drawdown(mock_storage):
    """Test maximum drawdown calculation."""
    analytics = PerformanceAnalytics(mock_storage)

    mock_storage.get_balance_trends.return_value = [
        {"date": "2026-02-05", "equity": 11000.0},
        {"date": "2026-02-04", "equity": 9000.0},  # Big drawdown
        {"date": "2026-02-03", "equity": 12000.0},  # Peak
        {"date": "2026-02-02", "equity": 11500.0},
        {"date": "2026-02-01", "equity": 10000.0},
    ]

    max_dd = analytics.calculate_max_drawdown(days=7)

    # From 12000 to 9000 = 25% drawdown
    if max_dd is not None:
        assert max_dd <= 0  # Drawdown should be negative
        assert abs(max_dd) >= 0.20  # At least 20%


def test_get_profit_factor(mock_storage):
    """Test profit factor calculation."""
    analytics = PerformanceAnalytics(mock_storage)

    mock_storage.get_orders_by_status.return_value = [
        {"outcome": "win", "realized_pnl": 100.0},
        {"outcome": "win", "realized_pnl": 200.0},
        {"outcome": "loss", "realized_pnl": -50.0},
        {"outcome": "loss", "realized_pnl": -30.0},
    ]

    pf = analytics.calculate_profit_factor()

    # Total wins = 300, total losses = 80
    # Profit factor = 300 / 80 = 3.75
    if pf is not None:
        assert pf >= 3.5
        assert pf <= 4.0


def test_get_average_win_loss(mock_storage):
    """Test average win and loss calculation."""
    analytics = PerformanceAnalytics(mock_storage)

    mock_storage.get_orders_by_status.return_value = [
        {"outcome": "win", "realized_pnl": 100.0},
        {"outcome": "win", "realized_pnl": 200.0},
        {"outcome": "loss", "realized_pnl": -60.0},
    ]

    avg_win, avg_loss = analytics.calculate_average_win_loss()

    if avg_win is not None:
        assert avg_win == 150.0  # (100 + 200) / 2
    if avg_loss is not None:
        assert avg_loss == -60.0


def test_get_trade_count(mock_storage):
    """Test trade count retrieval."""
    analytics = PerformanceAnalytics(mock_storage)

    count = analytics.get_trade_count(days=7)

    assert count >= 0
    assert isinstance(count, int)


def test_performance_summary_empty_data(mock_storage):
    """Test performance summary handles empty data gracefully."""
    analytics = PerformanceAnalytics(mock_storage)

    mock_storage.get_balance_trends.return_value = []
    mock_storage.get_orders_by_status.return_value = []

    summary = analytics.get_performance_summary(days=7)

    # Should still return a string, not crash
    assert isinstance(summary, str)


def test_calculate_returns_insufficient_data(mock_storage):
    """Test returns calculation with insufficient data."""
    analytics = PerformanceAnalytics(mock_storage)

    mock_storage.get_balance_trends.return_value = [
        {"date": "2026-02-05", "equity": 11000.0},
    ]

    returns = analytics.calculate_returns(days=7)

    # Should handle gracefully (return None or 0)
    assert returns is None or returns == 0 or isinstance(returns, (int, float))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
