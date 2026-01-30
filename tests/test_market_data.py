"""Tests for MarketDataManager."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import date
from src.market_data import MarketDataManager
from src.client import TradingClient
from public_api_sdk import InstrumentType, OptionExpirationsResponse, OptionChainResponse


@pytest.fixture
def mock_client():
    """Create a mock trading client."""
    client = Mock(spec=TradingClient)
    client.client = Mock()
    return client


@pytest.fixture
def market_data_manager(mock_client):
    """Create a market data manager instance."""
    return MarketDataManager(mock_client)


def test_get_quotes(market_data_manager, mock_client):
    """Test getting quotes for multiple symbols."""
    # Mock quote response
    class MockQuote:
        def __init__(self, symbol, price):
            self.instrument = Mock()
            self.instrument.symbol = symbol
            self.last = price
    
    mock_client.client.get_quotes.return_value = [
        MockQuote("AAPL", 150.0),
        MockQuote("MSFT", 300.0)
    ]
    
    quotes = market_data_manager.get_quotes(["AAPL", "MSFT"])
    
    assert quotes["AAPL"] == 150.0
    assert quotes["MSFT"] == 300.0
    assert "AAPL" in market_data_manager._quote_cache


def test_get_quote_single(market_data_manager, mock_client):
    """Test getting quote for single symbol."""
    class MockQuote:
        def __init__(self):
            self.instrument = Mock()
            self.instrument.symbol = "AAPL"
            self.last = 150.0
    
    mock_client.client.get_quotes.return_value = [MockQuote()]
    
    quote = market_data_manager.get_quote("AAPL")
    assert quote == 150.0


def test_get_quote_error(market_data_manager, mock_client):
    """Test error handling in get_quote."""
    mock_client.client.get_quotes.side_effect = Exception("API Error")
    
    quote = market_data_manager.get_quote("AAPL")
    assert quote is None


def test_get_option_expirations(market_data_manager, mock_client):
    """Test getting option expirations."""
    mock_response = Mock(spec=OptionExpirationsResponse)
    mock_response.expirations = ["2025-01-17", "2025-02-21"]
    mock_client.client.get_option_expirations.return_value = mock_response
    
    expirations = market_data_manager.get_option_expirations("AAPL")
    
    assert len(expirations) == 2
    assert isinstance(expirations[0], date)


def test_get_option_chain(market_data_manager, mock_client):
    """Test getting option chain."""
    mock_chain = Mock(spec=OptionChainResponse)
    mock_chain.calls = []
    mock_client.client.get_option_chain.return_value = mock_chain
    
    expiration = date(2025, 1, 17)
    chain = market_data_manager.get_option_chain("AAPL", expiration)
    
    assert chain is not None
    mock_client.client.get_option_chain.assert_called_once()


def test_get_option_greeks_single(market_data_manager, mock_client):
    """Test getting Greeks for single option."""
    class MockGreek:
        def __init__(self):
            self.greeks = Mock()
            self.greeks.delta = 0.5
            self.greeks.gamma = 0.1
            self.greeks.theta = -0.05
            self.greeks.vega = 0.2
    
    mock_client.client.get_option_greek.return_value = MockGreek()
    
    greeks = market_data_manager.get_option_greeks(["AAPL250117C00150000"])
    
    assert "AAPL250117C00150000" in greeks
    assert greeks["AAPL250117C00150000"]["delta"] == 0.5


def test_clear_cache(market_data_manager):
    """Test clearing quote cache."""
    market_data_manager._quote_cache["AAPL"] = 150.0
    market_data_manager.clear_cache()
    
    assert len(market_data_manager._quote_cache) == 0


def test_select_option_contract_no_expirations(market_data_manager, mock_client):
    """Test option selection with no expirations."""
    mock_response = Mock(spec=OptionExpirationsResponse)
    mock_response.expirations = []
    mock_client.client.get_option_expirations.return_value = mock_response
    
    result = market_data_manager.select_option_contract("AAPL", 150.0)
    assert result is None


def test_select_option_contract_no_suitable(market_data_manager, mock_client):
    """Test option selection with no suitable contracts."""
    # Expiration too far out
    far_date = date.today()
    from datetime import timedelta
    far_date = far_date + timedelta(days=200)
    
    mock_exp_response = Mock(spec=OptionExpirationsResponse)
    mock_exp_response.expirations = [far_date.isoformat()]
    mock_client.client.get_option_expirations.return_value = mock_exp_response
    
    result = market_data_manager.select_option_contract("AAPL", 150.0)
    assert result is None
