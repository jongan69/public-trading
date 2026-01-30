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


def test_compute_max_pain():
    """Test max pain: strike that minimizes total option holder value at expiration."""
    chain = Mock(spec=OptionChainResponse)
    # Calls: K=100 OI=100, K=110 OI=50. Puts: K=90 OI=100, K=100 OI=50.
    # At S=90: calls 0, puts (100-90)*100*50 = 50000 -> total 50000
    # At S=100: calls 0, puts (90-100)*...=0 and (100-100)*...=0 -> total 0
    # At S=110: calls (110-100)*100*100 = 100000, puts 0 -> total 100000
    # So max pain = 100 (min total = 0)
    class Contract:
        def __init__(self, strike, oi):
            self.strike = strike
            self.open_interest = oi
    chain.calls = [Contract(100, 100), Contract(110, 50)]
    chain.puts = [Contract(90, 100), Contract(100, 50)]
    result = MarketDataManager.compute_max_pain(chain)
    assert result is not None
    strike, total = result
    assert strike == 100.0
    assert total == 0.0


def test_compute_max_pain_no_oi_returns_none():
    """Test max pain returns None when all OI is zero."""
    chain = Mock(spec=OptionChainResponse)
    class Contract:
        def __init__(self, strike):
            self.strike = strike
            self.open_interest = 0
    chain.calls = [Contract(100)]
    chain.puts = [Contract(90)]
    result = MarketDataManager.compute_max_pain(chain)
    assert result is None
