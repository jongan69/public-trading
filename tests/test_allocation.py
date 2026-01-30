"""Tests for allocation math."""
import pytest
from unittest.mock import Mock, MagicMock
from src.portfolio import PortfolioManager, Position
from src.market_data import MarketDataManager
from src.client import TradingClient
from public_api_sdk import InstrumentType


@pytest.fixture
def mock_client():
    """Create a mock trading client."""
    client = Mock(spec=TradingClient)
    client.client = Mock()
    client.account_number = "TEST_ACCOUNT"
    portfolio_mock = Mock()
    portfolio_mock.equity = 1200.0
    portfolio_mock.buying_power = 600.0
    portfolio_mock.cash = 300.0
    client.client.get_portfolio.return_value = portfolio_mock
    return client


@pytest.fixture
def mock_data_manager():
    """Create a mock data manager."""
    manager = Mock(spec=MarketDataManager)
    manager.get_quote.return_value = 100.0
    return manager


@pytest.fixture
def portfolio_manager(mock_client, mock_data_manager):
    """Create a portfolio manager instance."""
    return PortfolioManager(mock_client, mock_data_manager)


def test_get_equity(portfolio_manager, mock_client):
    """Test getting equity."""
    equity = portfolio_manager.get_equity()
    assert equity == 1200.0


def test_get_current_allocations_empty(portfolio_manager):
    """Test allocations with no positions."""
    allocations = portfolio_manager.get_current_allocations()
    
    assert allocations["theme_a"] == 0.0
    assert allocations["theme_b"] == 0.0
    assert allocations["theme_c"] == 0.0
    assert allocations["moonshot"] == 0.0
    assert allocations["cash"] == 0.25  # 300 / 1200


def test_get_current_allocations_with_positions(portfolio_manager, mock_data_manager):
    """Test allocations with positions."""
    # Add a theme A position
    position = Position(
        symbol="UMC250117C00100000",
        quantity=1,
        entry_price=50.0,
        instrument_type=InstrumentType.OPTION,
        osi_symbol="UMC250117C00100000",
        underlying="UMC",
        expiration="2025-01-17",
        strike=100.0
    )
    
    portfolio_manager.add_position(position)
    
    # Mock current price
    mock_data_manager.get_quote.return_value = 60.0
    
    allocations = portfolio_manager.get_current_allocations()
    
    # Position value: 1 * 60 = 60
    # Equity: 1200
    # Allocation: 60 / 1200 = 0.05
    assert allocations["theme_a"] == pytest.approx(0.05, abs=0.01)


def test_calculate_rebalance_needs(portfolio_manager, mock_data_manager):
    """Test rebalancing needs calculation."""
    from src.config import config
    
    # Add a small position
    position = Position(
        symbol="UMC250117C00100000",
        quantity=1,
        entry_price=50.0,
        instrument_type=InstrumentType.OPTION,
        osi_symbol="UMC250117C00100000",
        underlying="UMC",
        expiration="2025-01-17",
        strike=100.0
    )
    
    portfolio_manager.add_position(position)
    mock_data_manager.get_quote.return_value = 60.0
    
    needs = portfolio_manager.calculate_rebalance_needs()
    
    # Target for theme_a: 1200 * 0.35 = 420
    # Current: 60
    # Need: 420 - 60 = 360
    assert needs["theme_a"] == pytest.approx(360.0, abs=10.0)


def test_get_target_allocations():
    """Test target allocations."""
    from src.portfolio import PortfolioManager
    from src.client import TradingClient
    from src.market_data import MarketDataManager
    
    client = Mock(spec=TradingClient)
    data = Mock(spec=MarketDataManager)
    portfolio = PortfolioManager(client, data)
    
    targets = portfolio.get_target_allocations()
    
    assert targets["theme_a"] == 0.35
    assert targets["theme_b"] == 0.35
    assert targets["moonshot"] == 0.20
    assert targets["cash"] >= 0.20
