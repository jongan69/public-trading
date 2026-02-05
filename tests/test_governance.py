"""Tests for governance rules: kill switch, position limits, cash buffer."""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from src.utils.governance import check_governance
from src.portfolio import PortfolioManager, Position, InstrumentType


@pytest.fixture
def mock_storage():
    """Create a mock storage instance."""
    storage = Mock()
    storage.get_equity_high_last_n_days.return_value = 12000.0
    storage.get_bot_state.return_value = None
    return storage


@pytest.fixture
def mock_portfolio():
    """Create a mock portfolio manager."""
    portfolio = Mock(spec=PortfolioManager)
    portfolio.get_equity.return_value = 10000.0
    portfolio.get_cash.return_value = 2000.0
    portfolio.get_buying_power.return_value = 5000.0

    # Mock positions
    portfolio.positions = {
        "UMC": Position(
            symbol="UMC",
            quantity=100,
            entry_price=5.0,
            instrument_type=InstrumentType.EQUITY,
        ),
        "TE": Position(
            symbol="TE",
            quantity=50,
            entry_price=10.0,
            instrument_type=InstrumentType.EQUITY,
        ),
    }
    portfolio.get_position.side_effect = lambda s: portfolio.positions.get(s)

    return portfolio


class TestKillSwitch:
    """Tests for kill switch governance."""

    @patch("src.utils.governance.config")
    def test_kill_switch_blocks_buy_on_drawdown(self, mock_config, mock_portfolio, mock_storage):
        """Test kill switch blocks BUY orders during drawdown."""
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30
        mock_config.cash_minimum = 0.20

        # Set up large drawdown: equity 9000 vs high 12000 = 25% drawdown
        mock_portfolio.get_equity.return_value = 9000.0
        mock_storage.get_equity_high_last_n_days.return_value = 12000.0

        order_details = {
            "action": "BUY",
            "symbol": "AMPX",
            "quantity": 10,
            "price": 5.0,
        }

        allowed, reason = check_governance(mock_portfolio, mock_storage, order_details)

        assert allowed is False
        assert "kill switch" in reason.lower()

    @patch("src.utils.governance.config")
    def test_kill_switch_allows_sell_on_drawdown(self, mock_config, mock_portfolio, mock_storage):
        """Test kill switch allows SELL orders during drawdown."""
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30
        mock_config.cash_minimum = 0.20

        # Set up large drawdown
        mock_portfolio.get_equity.return_value = 9000.0
        mock_storage.get_equity_high_last_n_days.return_value = 12000.0

        order_details = {
            "action": "SELL",
            "symbol": "UMC",
            "quantity": 10,
            "price": 5.0,
        }

        allowed, reason = check_governance(mock_portfolio, mock_storage, order_details)

        # SELL should still be allowed to reduce risk
        assert allowed is True


class TestCashBuffer:
    """Tests for minimum cash buffer enforcement."""

    @patch("src.utils.governance.config")
    def test_cash_buffer_blocks_large_buy(self, mock_config, mock_portfolio, mock_storage):
        """Test that large BUY orders are blocked if they violate cash buffer."""
        mock_config.cash_minimum = 0.20  # 20% minimum cash
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30

        # Equity: 10000, cash: 2000 (20%)
        # Large order would reduce cash below minimum
        mock_portfolio.get_equity.return_value = 10000.0
        mock_portfolio.get_cash.return_value = 2100.0

        order_details = {
            "action": "BUY",
            "symbol": "AMPX",
            "quantity": 50,
            "price": 50.0,  # $2500 order
        }

        allowed, reason = check_governance(mock_portfolio, mock_storage, order_details)

        assert allowed is False
        assert "cash" in reason.lower() or "buffer" in reason.lower()

    @patch("src.utils.governance.config")
    def test_cash_buffer_allows_small_buy(self, mock_config, mock_portfolio, mock_storage):
        """Test that small BUY orders are allowed with sufficient cash."""
        mock_config.cash_minimum = 0.20
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30
        mock_config.max_single_position_pct = 0.30
        mock_config.max_correlated_pct = 0.60

        # Equity: 10000, cash: 5000 (50%)
        mock_portfolio.get_equity.return_value = 10000.0
        mock_portfolio.get_cash.return_value = 5000.0

        order_details = {
            "action": "BUY",
            "symbol": "AMPX",
            "quantity": 10,
            "price": 5.0,  # $50 order (tiny)
        }

        allowed, reason = check_governance(mock_portfolio, mock_storage, order_details)

        assert allowed is True


class TestPositionLimits:
    """Tests for position size limits."""

    @patch("src.utils.governance.config")
    def test_max_single_position_blocks_large_buy(self, mock_config, mock_portfolio, mock_storage):
        """Test that BUY orders are blocked if position would exceed max size."""
        mock_config.max_single_position_pct = 0.30  # 30% max per position
        mock_config.cash_minimum = 0.10
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30
        mock_config.max_correlated_pct = 0.60

        # Equity: 10000, UMC already at $500 (5%)
        # Order would add $3500 = total $4000 (40%)
        mock_portfolio.get_equity.return_value = 10000.0
        mock_portfolio.get_cash.return_value = 5000.0

        order_details = {
            "action": "BUY",
            "symbol": "UMC",
            "quantity": 700,
            "price": 5.0,  # $3500 order
        }

        allowed, reason = check_governance(mock_portfolio, mock_storage, order_details)

        assert allowed is False
        assert "position" in reason.lower() or "30%" in reason


class TestCorrelatedLimit:
    """Tests for correlated positions limit (theme A+B+C)."""

    @patch("src.utils.governance.config")
    def test_max_correlated_blocks_theme_concentration(self, mock_config, mock_portfolio, mock_storage):
        """Test that orders are blocked if themes would be too concentrated."""
        mock_config.theme_underlyings = ["UMC", "TE", "AMPX"]
        mock_config.max_correlated_pct = 0.60  # 60% max for all themes combined
        mock_config.max_single_position_pct = 0.30
        mock_config.cash_minimum = 0.10
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30

        # Equity: 10000
        # UMC: $500 (5%), TE: $500 (5%) = 10% themes currently
        # Order AMPX for $5500 would bring themes to 65%
        mock_portfolio.get_equity.return_value = 10000.0
        mock_portfolio.get_cash.return_value = 5000.0

        order_details = {
            "action": "BUY",
            "symbol": "AMPX",
            "quantity": 1100,
            "price": 5.0,  # $5500 order
        }

        allowed, reason = check_governance(mock_portfolio, mock_storage, order_details)

        assert allowed is False
        assert "correlated" in reason.lower() or "theme" in reason.lower() or "60%" in reason


class TestGovernanceIntegration:
    """Integration tests for governance combining multiple rules."""

    @patch("src.utils.governance.config")
    def test_all_rules_pass(self, mock_config, mock_portfolio, mock_storage):
        """Test order passes when all governance rules are satisfied."""
        mock_config.cash_minimum = 0.20
        mock_config.max_single_position_pct = 0.30
        mock_config.max_correlated_pct = 0.60
        mock_config.theme_underlyings = ["UMC", "TE", "AMPX"]
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30

        # Equity: 10000, cash: 5000 (50%)
        # No kill switch (equity at high)
        mock_portfolio.get_equity.return_value = 10000.0
        mock_portfolio.get_cash.return_value = 5000.0
        mock_storage.get_equity_high_last_n_days.return_value = 10000.0

        # Small order
        order_details = {
            "action": "BUY",
            "symbol": "AMPX",
            "quantity": 10,
            "price": 5.0,  # $50 order
        }

        allowed, reason = check_governance(mock_portfolio, mock_storage, order_details)

        assert allowed is True

    @patch("src.utils.governance.config")
    def test_sell_orders_bypass_most_rules(self, mock_config, mock_portfolio, mock_storage):
        """Test that SELL orders bypass most governance restrictions."""
        mock_config.cash_minimum = 0.20
        mock_config.max_single_position_pct = 0.30
        mock_config.max_correlated_pct = 0.60
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30

        # Even with kill switch active
        mock_portfolio.get_equity.return_value = 9000.0
        mock_storage.get_equity_high_last_n_days.return_value = 12000.0

        order_details = {
            "action": "SELL",
            "symbol": "UMC",
            "quantity": 50,
            "price": 5.0,
        }

        allowed, reason = check_governance(mock_portfolio, mock_storage, order_details)

        # SELL should be allowed to reduce exposure
        assert allowed is True


class TestEdgeCases:
    """Test edge cases in governance."""

    @patch("src.utils.governance.config")
    def test_zero_equity_no_crash(self, mock_config, mock_portfolio, mock_storage):
        """Test governance handles zero equity gracefully."""
        mock_config.cash_minimum = 0.20
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30

        mock_portfolio.get_equity.return_value = 0.0
        mock_portfolio.get_cash.return_value = 0.0

        order_details = {
            "action": "BUY",
            "symbol": "UMC",
            "quantity": 1,
            "price": 5.0,
        }

        allowed, reason = check_governance(mock_portfolio, mock_storage, order_details)

        # Should not crash
        assert isinstance(allowed, bool)
        assert isinstance(reason, str)

    @patch("src.utils.governance.config")
    def test_no_equity_history_allows_trading(self, mock_config, mock_portfolio, mock_storage):
        """Test that missing equity history doesn't block all trading."""
        mock_config.cash_minimum = 0.20
        mock_config.max_single_position_pct = 0.30
        mock_config.max_correlated_pct = 0.60
        mock_config.kill_switch_drawdown_pct = 0.25
        mock_config.kill_switch_lookback_days = 30

        mock_portfolio.get_equity.return_value = 10000.0
        mock_portfolio.get_cash.return_value = 5000.0
        mock_storage.get_equity_high_last_n_days.return_value = None  # No history

        order_details = {
            "action": "BUY",
            "symbol": "UMC",
            "quantity": 10,
            "price": 5.0,
        }

        allowed, reason = check_governance(mock_portfolio, mock_storage, order_details)

        # Should allow trading when no history (new account)
        assert allowed is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
