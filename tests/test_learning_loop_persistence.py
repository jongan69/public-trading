"""Tests for REQ-011: Learning loop persistence (theme + realized P&L)."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.strategy import HighConvexityStrategy
from src.portfolio import PortfolioManager, Position
from src.market_data import MarketDataManager
from src.execution import ExecutionManager
from src.config import config
from public_api_sdk import InstrumentType


@pytest.fixture
def mock_components():
    """Create mock components for strategy."""
    client = Mock()
    data_manager = Mock(spec=MarketDataManager)
    portfolio_manager = Mock(spec=PortfolioManager)
    execution_manager = Mock(spec=ExecutionManager)
    return client, data_manager, portfolio_manager, execution_manager


def test_rebalance_orders_have_theme_tag(mock_components):
    """REQ-011: Rebalance orders should be tagged with theme (theme_a, theme_b, theme_c, moonshot)."""
    client, data_manager, portfolio_manager, execution_manager = mock_components

    # Setup
    portfolio_manager.get_equity.return_value = 1000.0
    portfolio_manager.get_current_allocations.return_value = {
        "theme_a": 0.10,  # Below 35% target
        "theme_b": 0.35,
        "theme_c": 0.15,
        "moonshot": 0.20,
        "cash": 0.20,
    }
    portfolio_manager.get_target_allocations.return_value = {
        "theme_a": 0.35,
        "theme_b": 0.35,
        "theme_c": 0.15,
        "moonshot": 0.20,
        "cash": 0.20,
    }
    portfolio_manager.calculate_rebalance_needs.return_value = {
        "theme_a": 250.0,  # Need to add
        "theme_b": 0.0,
        "theme_c": 0.0,
        "moonshot": 0.0,
    }

    data_manager.get_quote.return_value = 100.0
    data_manager.select_option_contract.return_value = {
        "osi_symbol": "UMC250117C00100000",
        "mid": 2.50,
        "strike": 100.0,
        "expiration": "2025-01-17",
    }

    strategy = HighConvexityStrategy(portfolio_manager, data_manager, execution_manager)

    # Execute
    orders = strategy.rebalance()

    # Verify
    assert len(orders) > 0
    buy_order = orders[0]
    assert "theme" in buy_order
    assert buy_order["theme"] == "theme_a"  # Should match first theme


def test_take_profit_orders_have_theme_and_entry_price(mock_components):
    """REQ-011: Take profit orders should have theme derived from underlying and entry_price."""
    client, data_manager, portfolio_manager, execution_manager = mock_components

    # Create position for UMC (theme A)
    position = Position(
        symbol="UMC250117C00100000",
        osi_symbol="UMC250117C00100000",
        underlying="UMC",
        quantity=1,
        entry_price=2.00,
        instrument_type=InstrumentType.OPTION,
        expiration="2025-01-17",
        strike=100.0,
    )

    portfolio_manager.positions = {"UMC250117C00100000": position}
    portfolio_manager.get_position_price.return_value = 4.50  # +125% profit
    portfolio_manager.get_position_sell_price.return_value = 4.40  # Bid

    strategy = HighConvexityStrategy(portfolio_manager, data_manager, execution_manager)

    # Execute
    orders = strategy.process_positions()

    # Verify
    assert len(orders) > 0
    sell_order = orders[0]
    assert sell_order["action"] == "SELL"
    assert "theme" in sell_order
    assert sell_order["theme"] == "theme_a"  # UMC is first theme underlying
    assert "entry_price" in sell_order
    assert sell_order["entry_price"] == 2.00


def test_moonshot_trim_has_theme_and_entry_price(mock_components):
    """REQ-011: Moonshot trim orders should be tagged with 'moonshot' theme and entry_price."""
    client, data_manager, portfolio_manager, execution_manager = mock_components

    # Create moonshot position at 35% (above 30% cap)
    position = Position(
        symbol="GME.WS",
        osi_symbol=None,
        underlying=None,
        quantity=10,
        entry_price=20.0,
        instrument_type=InstrumentType.EQUITY,
        expiration=None,
        strike=None,
    )

    portfolio_manager.get_equity.return_value = 1000.0
    portfolio_manager.get_current_allocations.return_value = {
        "theme_a": 0.35,
        "theme_b": 0.35,
        "theme_c": 0.00,
        "moonshot": 0.35,  # Above 30% cap
        "cash": 0.05,
    }
    portfolio_manager.get_positions_by_theme.return_value = {
        "theme_a": [],
        "theme_b": [],
        "theme_c": [],
        "moonshot": [position],
    }
    portfolio_manager.get_position_price.return_value = 35.0  # Current price
    portfolio_manager.get_position_sell_price.return_value = 35.0

    strategy = HighConvexityStrategy(portfolio_manager, data_manager, execution_manager)

    # Execute
    trim_order = strategy.check_moonshot_trim()

    # Verify
    assert trim_order is not None
    assert trim_order["action"] == "SELL"
    assert "theme" in trim_order
    assert trim_order["theme"] == "moonshot"
    assert "entry_price" in trim_order
    assert trim_order["entry_price"] == 20.0


def test_get_theme_for_underlying():
    """REQ-011: Strategy should correctly map underlyings to themes."""
    client = Mock()
    data_manager = Mock(spec=MarketDataManager)
    portfolio_manager = Mock(spec=PortfolioManager)
    execution_manager = Mock(spec=ExecutionManager)

    strategy = HighConvexityStrategy(portfolio_manager, data_manager, execution_manager)

    # Test theme A
    assert strategy.get_theme_for_underlying("UMC") == "theme_a"
    assert strategy.get_theme_for_underlying("umc") == "theme_a"  # Case insensitive

    # Test theme B
    assert strategy.get_theme_for_underlying("TE") == "theme_b"

    # Test theme C
    assert strategy.get_theme_for_underlying("AMPX") == "theme_c"

    # Test moonshot
    assert strategy.get_theme_for_underlying("GME.WS") == "moonshot"

    # Test unknown
    assert strategy.get_theme_for_underlying("AAPL") is None
    assert strategy.get_theme_for_underlying("") is None
