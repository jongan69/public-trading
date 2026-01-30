"""Tests for AccountManager."""
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.utils.account_manager import AccountManager, CONFIG_FILE


@pytest.fixture
def temp_config_file(tmp_path, monkeypatch):
    """Create a temporary config file."""
    config_file = tmp_path / "bot_config.json"
    monkeypatch.setattr("src.utils.account_manager.CONFIG_FILE", config_file)
    yield config_file
    if config_file.exists():
        config_file.unlink()


def test_get_saved_account_none(temp_config_file):
    """Test getting saved account when none exists."""
    account = AccountManager.get_saved_account()
    assert account is None


def test_save_and_get_account(temp_config_file):
    """Test saving and retrieving account."""
    AccountManager.save_account("TEST123")
    
    account = AccountManager.get_saved_account()
    assert account == "TEST123"


def test_list_accounts(temp_config_file):
    """Test listing available accounts."""
    with patch('src.utils.account_manager.PublicApiClient') as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        class MockAccount:
            def __init__(self, account_id, account_type):
                self.account_id = account_id
                self.account_type = account_type
        
        class MockAccountsResponse:
            def __init__(self):
                self.accounts = [
                    MockAccount("ACC1", "CASH"),
                    MockAccount("ACC2", "MARGIN")
                ]
        
        mock_client.get_accounts.return_value = MockAccountsResponse()
        
        accounts = AccountManager.list_accounts("test_key")
        
        assert len(accounts) == 2
        assert accounts[0]["account_id"] == "ACC1"
        assert accounts[1]["account_id"] == "ACC2"
        
        mock_client.close.assert_called_once()


def test_list_accounts_error(temp_config_file):
    """Test error handling in list_accounts."""
    with patch('src.utils.account_manager.PublicApiClient') as mock_client_class:
        mock_client_class.side_effect = Exception("API Error")
        
        accounts = AccountManager.list_accounts("test_key")
        assert accounts == []


def test_select_account_interactive_no_accounts(temp_config_file, monkeypatch):
    """Test interactive selection with no accounts."""
    with patch('src.utils.account_manager.AccountManager.list_accounts') as mock_list:
        mock_list.return_value = []
        
        with patch('builtins.input', return_value=""):
            result = AccountManager.select_account_interactive("test_key")
            assert result is None


def test_select_account_interactive_menu_selection(temp_config_file, monkeypatch):
    """Test interactive selection via menu."""
    with patch('src.utils.account_manager.AccountManager.list_accounts') as mock_list:
        mock_list.return_value = [
            {"account_id": "ACC1", "account_type": "CASH"},
            {"account_id": "ACC2", "account_type": "MARGIN"}
        ]
        
        with patch('builtins.input', return_value="1"):
            with patch('builtins.print'):  # Suppress print output
                result = AccountManager.select_account_interactive("test_key")
                assert result == "ACC1"
                
                # Verify account was saved
                saved = AccountManager.get_saved_account()
                assert saved == "ACC1"


def test_select_account_interactive_manual_entry(temp_config_file, monkeypatch):
    """Test interactive selection with manual entry."""
    with patch('src.utils.account_manager.AccountManager.list_accounts') as mock_list:
        mock_list.return_value = [
            {"account_id": "ACC1", "account_type": "CASH"}
        ]
        
        # Simulate: user enters "0" for manual, then "MANUAL123"
        input_values = iter(["0", "MANUAL123"])
        with patch('builtins.input', lambda _: next(input_values)):
            with patch('builtins.print'):  # Suppress print output
                result = AccountManager.select_account_interactive("test_key")
                # The function should return the manual entry
                assert result == "MANUAL123"
                # Verify account was saved
                saved = AccountManager.get_saved_account()
                assert saved == "MANUAL123"
