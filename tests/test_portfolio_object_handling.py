"""Tests for portfolio object handling (BuyingPower, etc.)."""
import pytest
from unittest.mock import Mock
from src.portfolio import PortfolioManager
from src.market_data import MarketDataManager
from src.client import TradingClient


@pytest.fixture
def mock_client_object():
    """Create a mock trading client with object responses."""
    client = Mock(spec=TradingClient)
    client.client = Mock()
    client.account_number = "TEST_ACCOUNT"
    # Mock BuyingPower object (matching actual SDK structure)
    class MockBuyingPower:
        def __init__(self, value):
            from decimal import Decimal
            self.buying_power = Decimal(str(value))
            self.cash_only_buying_power = Decimal(str(value))
            self.options_buying_power = Decimal(str(value))
    
    portfolio_mock = Mock()
    portfolio_mock.equity = 1200.0
    portfolio_mock.buying_power = MockBuyingPower(600.0)
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
def portfolio_manager_object(mock_client_object, mock_data_manager):
    """Create a portfolio manager instance with object responses."""
    return PortfolioManager(mock_client_object, mock_data_manager)


def test_get_buying_power_from_object(portfolio_manager_object):
    """Test getting buying power when API returns an object."""
    buying_power = portfolio_manager_object.get_buying_power()
    assert buying_power == 600.0
    assert isinstance(buying_power, float)


def test_get_equity_from_object(portfolio_manager_object):
    """Test getting equity when API returns a regular value."""
    equity = portfolio_manager_object.get_equity()
    assert equity == 1200.0
    assert isinstance(equity, float)


def test_get_cash_from_object(portfolio_manager_object):
    """Test getting cash when API returns a regular value."""
    cash = portfolio_manager_object.get_cash()
    assert cash == 300.0
    assert isinstance(cash, float)


def test_get_equity_from_list_of_portfolio_equity(mock_client_object, mock_data_manager):
    """Test get_equity when API returns List[PortfolioEquity] (real SDK shape)."""
    from decimal import Decimal

    class MockPortfolioEquity:
        def __init__(self, value):
            self.value = Decimal(str(value))
            self.type = "STOCK"

    portfolio_mock = Mock()
    portfolio_mock.equity = [
        MockPortfolioEquity(500.0),
        MockPortfolioEquity(700.0),
        MockPortfolioEquity(100.0),
    ]
    portfolio_mock.buying_power = mock_client_object.client.get_portfolio.return_value.buying_power
    portfolio_mock.cash = 300.0
    portfolio_mock.positions = []
    mock_client_object.client.get_portfolio.return_value = portfolio_mock

    pm = PortfolioManager(mock_client_object, mock_data_manager)
    equity = pm.get_equity()
    assert equity == 1300.0
    assert isinstance(equity, float)


def test_get_cash_fallback_to_cash_only_buying_power(mock_client_object, mock_data_manager):
    """Test get_cash when portfolio has no .cash (real SDK) uses cash_only_buying_power."""
    # Use a simple object without .cash so hasattr(portfolio, 'cash') is False
    class PortfolioNoCash:
        equity = 1200.0
        positions = []

    portfolio_no_cash = PortfolioNoCash()
    portfolio_no_cash.buying_power = Mock()
    portfolio_no_cash.buying_power.cash_only_buying_power = 600.0
    mock_client_object.client.get_portfolio.return_value = portfolio_no_cash

    pm = PortfolioManager(mock_client_object, mock_data_manager)
    cash = pm.get_cash()
    assert cash == 600.0
    assert isinstance(cash, float)
