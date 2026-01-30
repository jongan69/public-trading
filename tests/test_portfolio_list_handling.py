"""Tests for portfolio list handling."""
import pytest
from unittest.mock import Mock
from src.portfolio import PortfolioManager
from src.market_data import MarketDataManager
from src.client import TradingClient


@pytest.fixture
def mock_client_list():
    """Create a mock trading client with list responses."""
    client = Mock(spec=TradingClient)
    client.client = Mock()
    client.account_number = "TEST_ACCOUNT"
    portfolio_mock = Mock()
    portfolio_mock.equity = [1200.0]  # List format
    portfolio_mock.buying_power = [600.0]  # List format
    portfolio_mock.cash = [300.0]  # List format
    client.client.get_portfolio.return_value = portfolio_mock
    return client


@pytest.fixture
def mock_data_manager():
    """Create a mock data manager."""
    manager = Mock(spec=MarketDataManager)
    manager.get_quote.return_value = 100.0
    return manager


@pytest.fixture
def portfolio_manager_list(mock_client_list, mock_data_manager):
    """Create a portfolio manager instance with list responses."""
    return PortfolioManager(mock_client_list, mock_data_manager)


def test_get_equity_from_list(portfolio_manager_list):
    """Test getting equity when API returns a list."""
    equity = portfolio_manager_list.get_equity()
    assert equity == 1200.0
    assert isinstance(equity, float)


def test_get_buying_power_from_list(portfolio_manager_list):
    """Test getting buying power when API returns a list."""
    buying_power = portfolio_manager_list.get_buying_power()
    assert buying_power == 600.0
    assert isinstance(buying_power, float)


def test_get_cash_from_list(portfolio_manager_list):
    """Test getting cash when API returns a list."""
    cash = portfolio_manager_list.get_cash()
    assert cash == 300.0
    assert isinstance(cash, float)


def test_get_equity_empty_list():
    """Test getting equity when API returns empty list."""
    client = Mock(spec=TradingClient)
    client.client = Mock()
    client.account_number = "TEST_ACCOUNT"
    portfolio_mock = Mock()
    portfolio_mock.equity = []
    portfolio_mock.buying_power = 0.0
    client.client.get_portfolio.return_value = portfolio_mock
    
    data = Mock(spec=MarketDataManager)
    portfolio = PortfolioManager(client, data)
    
    equity = portfolio.get_equity()
    assert equity == 0.0


def test_get_equity_multiple_values_list():
    """Test getting equity when API returns list with multiple values."""
    client = Mock(spec=TradingClient)
    client.client = Mock()
    client.account_number = "TEST_ACCOUNT"
    portfolio_mock = Mock()
    portfolio_mock.equity = [1000.0, 200.0]  # Sum should be 1200
    client.client.get_portfolio.return_value = portfolio_mock
    
    data = Mock(spec=MarketDataManager)
    portfolio = PortfolioManager(client, data)
    
    equity = portfolio.get_equity()
    assert equity == 1200.0
