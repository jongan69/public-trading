"""Tests for HighConvexityStrategy."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import date, timedelta
from src.strategy import HighConvexityStrategy
from src.portfolio import PortfolioManager, Position
from src.market_data import MarketDataManager
from src.execution import ExecutionManager
from public_api_sdk import InstrumentType


@pytest.fixture
def mock_components():
    """Create mock components."""
    portfolio = Mock(spec=PortfolioManager)
    data = Mock(spec=MarketDataManager)
    execution = Mock(spec=ExecutionManager)
    
    return portfolio, data, execution


@pytest.fixture
def strategy(mock_components):
    """Create strategy instance."""
    portfolio, data, execution = mock_components
    return HighConvexityStrategy(portfolio, data, execution)


def test_check_entry_signal_manual_mode(strategy):
    """Test entry signal check in manual mode."""
    from src.config import config
    original_manual = config.manual_mode_only
    
    try:
        config.manual_mode_only = True
        result = strategy.check_entry_signal("AAPL", 150.0)
        assert result == True
    finally:
        config.manual_mode_only = original_manual


def test_should_take_profit_100_pct(strategy, mock_components):
    """Test take profit at +100%."""
    portfolio, data, execution = mock_components
    
    position = Position(
        symbol="AAPL250117C00150000",
        quantity=2,
        entry_price=50.0,
        instrument_type=InstrumentType.OPTION
    )
    
    # Current price: 100.0 (100% gain)
    should_tp, qty = strategy.should_take_profit(position, 100.0)
    
    assert should_tp == True
    assert qty == 1  # Close 50% (1 of 2 contracts)


def test_should_take_profit_200_pct(strategy, mock_components):
    """Test take profit at +200%."""
    portfolio, data, execution = mock_components
    
    position = Position(
        symbol="AAPL250117C00150000",
        quantity=1,
        entry_price=50.0,
        instrument_type=InstrumentType.OPTION
    )
    
    # Current price: 150.0 (200% gain)
    should_tp, qty = strategy.should_take_profit(position, 150.0)
    
    assert should_tp == True
    assert qty == 1  # Close all


def test_should_stop_loss_drawdown(strategy, mock_components):
    """Test stop loss on drawdown."""
    portfolio, data, execution = mock_components
    
    position = Position(
        symbol="AAPL250117C00150000",
        quantity=1,
        entry_price=50.0,
        instrument_type=InstrumentType.OPTION,
        underlying="AAPL",
        strike=150.0
    )
    
    # Current price: 20.0 (-60% drawdown)
    data.get_quote.return_value = 140.0  # Underlying below strike
    
    should_sl = strategy.should_stop_loss(position, 20.0)
    assert should_sl == True


def test_should_stop_loss_dte(strategy, mock_components):
    """Test stop loss on DTE."""
    portfolio, data, execution = mock_components
    
    expiration = date.today() + timedelta(days=25)
    position = Position(
        symbol="AAPL250117C00150000",
        quantity=1,
        entry_price=50.0,
        instrument_type=InstrumentType.OPTION,
        underlying="AAPL",
        strike=150.0,
        expiration=expiration.isoformat()
    )
    
    # DTE < 30 and OTM
    data.get_quote.return_value = 140.0  # Underlying below strike (OTM)
    
    should_sl = strategy.should_stop_loss(position, 30.0)
    assert should_sl == True


def test_should_roll_dte_too_high(strategy, mock_components):
    """Test roll decision when DTE is too high."""
    portfolio, data, execution = mock_components
    
    expiration = date.today() + timedelta(days=90)
    position = Position(
        symbol="AAPL250117C00150000",
        quantity=1,
        entry_price=50.0,
        instrument_type=InstrumentType.OPTION,
        underlying="AAPL",
        expiration=expiration.isoformat()
    )
    
    should_roll, new_contract = strategy.should_roll(position, 60.0)
    assert should_roll == False


def test_check_moonshot_trim_over_max(strategy, mock_components):
    """Test moonshot trim when over max."""
    portfolio, data, execution = mock_components
    
    # Mock portfolio with moonshot > 35% (strategy trims when > 0.35)
    portfolio.get_equity.return_value = 1200.0
    portfolio.get_current_allocations.return_value = {
        "moonshot": 0.36  # 36% > 35% trim threshold
    }
    
    position = Position(
        symbol="GME.WS",
        quantity=100,
        entry_price=10.0,
        instrument_type=InstrumentType.EQUITY
    )
    
    themes = {
        "theme_a": [],
        "theme_b": [],
        "theme_c": [],
        "moonshot": [position]
    }
    portfolio.get_positions_by_theme.return_value = themes
    portfolio.get_position_price.return_value = 12.0
    portfolio.get_position_sell_price.return_value = 12.0  # required for trim order

    trim_order = strategy.check_moonshot_trim()
    
    assert trim_order is not None
    assert trim_order["action"] == "SELL"
    assert trim_order["symbol"] == "GME.WS"


def test_check_moonshot_trim_within_range(strategy, mock_components):
    """Test moonshot trim when within acceptable range."""
    portfolio, data, execution = mock_components
    
    portfolio.get_current_allocations.return_value = {
        "moonshot": 0.25  # 25% within 20-30% range
    }
    
    trim_order = strategy.check_moonshot_trim()
    assert trim_order is None


def test_rebalance_no_orders(strategy, mock_components):
    """Test rebalancing with no orders needed."""
    portfolio, data, execution = mock_components
    
    portfolio.get_equity.return_value = 1200.0
    portfolio.get_current_allocations.return_value = {
        "theme_a": 0.35,
        "theme_b": 0.35,
        "theme_c": 0.15,
        "moonshot": 0.20,
        "cash": 0.20
    }
    portfolio.calculate_rebalance_needs.return_value = {
        "theme_a": 0.0,
        "theme_b": 0.0,
        "theme_c": 0.0,
        "moonshot": 0.0
    }
    
    orders = strategy.rebalance()
    assert len(orders) == 0
