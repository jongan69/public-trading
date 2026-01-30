"""Tests for TradingClient."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.client import TradingClient
from src.config import config


def test_client_initialization():
    """Test client initialization with account number."""
    with patch('src.client.PublicApiClient') as mock_client_class:
        mock_client_instance = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = TradingClient(
            api_secret_key="test_key",
            account_number="TEST123"
        )
        
        assert client.api_secret_key == "test_key"
        assert client.account_number == "TEST123"
        mock_client_class.assert_called_once()


def test_client_requires_account_number():
    """Test that client requires account number."""
    with pytest.raises(ValueError, match="Account number must be provided"):
        TradingClient(account_number=None)


def test_client_uses_config_api_key():
    """Test that client uses config API key if not provided."""
    with patch('src.client.PublicApiClient') as mock_client_class:
        mock_client_instance = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = TradingClient(account_number="TEST123")
        
        assert client.api_secret_key == config.api_secret_key
        assert client.account_number == "TEST123"


def test_client_close():
    """Test client close method."""
    with patch('src.client.PublicApiClient') as mock_client_class:
        mock_client_instance = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = TradingClient(account_number="TEST123")
        client.close()
        
        mock_client_instance.close.assert_called_once()


def test_client_context_manager():
    """Test client as context manager."""
    with patch('src.client.PublicApiClient') as mock_client_class:
        mock_client_instance = Mock()
        mock_client_class.return_value = mock_client_instance
        
        with TradingClient(account_number="TEST123") as client:
            assert client.account_number == "TEST123"
        
        mock_client_instance.close.assert_called_once()
