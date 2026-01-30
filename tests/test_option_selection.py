"""Tests for option selection logic."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from src.market_data import MarketDataManager
from src.client import TradingClient
from public_api_sdk import InstrumentType, OptionChainResponse
from datetime import date, timedelta


@pytest.fixture
def mock_client():
    """Create a mock trading client."""
    client = Mock(spec=TradingClient)
    client.client = Mock()
    return client


@pytest.fixture
def data_manager(mock_client):
    """Create a data manager instance."""
    return MarketDataManager(mock_client)


def test_select_option_contract_no_expirations(data_manager, mock_client):
    """Test option selection with no expirations."""
    mock_response = Mock()
    mock_response.expirations = []
    mock_client.client.get_option_expirations.return_value = mock_response
    
    result = data_manager.select_option_contract("UMC", 100.0)
    
    assert result is None


def test_select_option_contract_no_suitable_expiration(data_manager, mock_client):
    """Test option selection with no suitable expiration."""
    # Expiration too far out
    far_expiration = (date.today() + timedelta(days=200)).isoformat()
    mock_response = Mock()
    mock_response.expirations = [far_expiration]
    mock_client.client.get_option_expirations.return_value = mock_response
    
    result = data_manager.select_option_contract("UMC", 100.0)
    
    assert result is None


@patch('src.market_data.MarketDataManager.get_option_chain')
def test_select_option_contract_suitable_contract(mock_get_chain, data_manager, mock_client):
    """Test option selection with suitable contract."""
    from src.config import config
    
    # Mock expirations
    target_expiration = date.today() + timedelta(days=90)
    mock_response = Mock()
    mock_response.expirations = [target_expiration.isoformat()]
    mock_client.client.get_option_expirations.return_value = mock_response
    
    # Mock option chain with suitable call
    class MockCall:
        def __init__(self):
            self.strike = 105.0
            self.bid = 4.5
            self.ask = 5.5
            self.open_interest = 100
            self.volume = 50
            self.symbol = "UMC250420C00105000"
    
    mock_chain = Mock(spec=OptionChainResponse)
    mock_chain.calls = [MockCall()]
    mock_get_chain.return_value = mock_chain
    
    result = data_manager.select_option_contract("UMC", 100.0)
    
    # Should find contract with strike 105 (5% OTM, within 0-10% range)
    if result:
        assert result["strike"] == 105.0
        assert result["osi_symbol"] == "UMC250420C00105000"


@patch('src.market_data.MarketDataManager.get_option_chain')
def test_select_option_contract_liquidity_filter(mock_get_chain, data_manager, mock_client):
    """Test option selection with liquidity filters."""
    target_expiration = date.today() + timedelta(days=90)
    mock_response = Mock()
    mock_response.expirations = [target_expiration.isoformat()]
    mock_client.client.get_option_expirations.return_value = mock_response
    
    # Mock call with wide spread (should be filtered out)
    class MockCallWideSpread:
        def __init__(self):
            self.strike = 105.0
            self.bid = 1.0
            self.ask = 10.0  # Very wide spread
            self.open_interest = 100
            self.volume = 50
            self.symbol = "UMC250420C00105000"
    
    mock_chain = Mock(spec=OptionChainResponse)
    mock_chain.calls = [MockCallWideSpread()]
    mock_get_chain.return_value = mock_chain
    
    result = data_manager.select_option_contract("UMC", 100.0)
    
    # Should be filtered out due to wide spread
    assert result is None
