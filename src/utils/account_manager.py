"""Account selection and local storage management."""
import json
import sys
from typing import Optional, List, Dict
from pathlib import Path
from loguru import logger

from public_api_sdk import PublicApiClient, PublicApiClientConfiguration
from public_api_sdk.auth_config import ApiKeyAuthConfig

# Resolve relative to package (src/utils/) so project root is parent of src
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = _PROJECT_ROOT / "data" / "bot_config.json"


class AccountManager:
    """Manages account selection and local storage."""
    
    @staticmethod
    def get_saved_account() -> Optional[str]:
        """Get saved account number from local config file.
        
        Returns:
            Account number if saved, None otherwise
        """
        if not CONFIG_FILE.exists():
            return None
        
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get("account_number")
        except Exception as e:
            logger.warning(f"Error reading saved account: {e}")
            return None
    
    @staticmethod
    def save_account(account_number: str):
        """Save account number to local config file.
        
        Args:
            account_number: Account number to save
        """
        # Ensure directory exists
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        config = {
            "account_number": account_number
        }
        
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Account number saved: {account_number}")
        except Exception as e:
            logger.error(f"Error saving account number: {e}")
            raise
    
    @staticmethod
    def list_accounts(api_secret_key: str) -> List[Dict]:
        """List available accounts for the API key.
        
        Args:
            api_secret_key: API secret key
            
        Returns:
            List of account dictionaries
        """
        try:
            # Create temporary client to fetch accounts (without account number)
            client_config = PublicApiClientConfiguration()
            temp_client = PublicApiClient(
                ApiKeyAuthConfig(api_secret_key=api_secret_key),
                config=client_config
            )
            
            accounts_response = temp_client.get_accounts()
            temp_client.close()
            
            accounts = []
            for account in accounts_response.accounts:
                accounts.append({
                    "account_id": account.account_id,
                    "account_type": account.account_type,
                })
            
            return accounts
        except Exception as e:
            logger.error(f"Error fetching accounts: {e}")
            return []
    
    @staticmethod
    def select_account_interactive(api_secret_key: str) -> Optional[str]:
        """Interactively select an account. No-op if stdin is not a TTY (e.g. headless deploy).
        
        Args:
            api_secret_key: API secret key
            
        Returns:
            Selected account number or None if cancelled or non-interactive
        """
        if not sys.stdin.isatty():
            logger.warning("Cannot prompt for account selection: not running in a TTY (headless). Set PUBLIC_ACCOUNT_NUMBER.")
            return None
        
        # Try to get saved account first
        saved_account = AccountManager.get_saved_account()
        
        # Fetch available accounts
        accounts = AccountManager.list_accounts(api_secret_key)
        
        if not accounts:
            logger.error("No accounts found. Please check your API key.")
            return None
        
        print("\n" + "=" * 70)
        print("Account Selection")
        print("=" * 70)
        print("\nAvailable accounts:")
        
        for i, account in enumerate(accounts, 1):
            marker = " [SAVED]" if account["account_id"] == saved_account else ""
            print(f"  {i}. {account['account_id']} ({account['account_type']}){marker}")
        
        print(f"\n  0. Enter account number manually")
        
        while True:
            try:
                choice = input("\nSelect account (number or account ID): ").strip()
                
                # Check if it's a number (menu selection)
                if choice.isdigit():
                    choice_num = int(choice)
                    if choice_num == 0:
                        # Manual entry
                        account_id = input("Enter account number: ").strip()
                        if account_id:
                            AccountManager.save_account(account_id)
                            return account_id
                        continue
                    elif 1 <= choice_num <= len(accounts):
                        selected = accounts[choice_num - 1]["account_id"]
                        AccountManager.save_account(selected)
                        return selected
                    else:
                        print(f"Invalid choice. Please enter 0-{len(accounts)}")
                        continue
                else:
                    # Assume it's an account ID
                    if any(acc["account_id"] == choice for acc in accounts):
                        AccountManager.save_account(choice)
                        return choice
                    else:
                        print(f"Account '{choice}' not found in available accounts.")
                        confirm = input("Use this account anyway? (y/n): ").strip().lower()
                        if confirm == 'y':
                            AccountManager.save_account(choice)
                            return choice
                        continue
                        
            except KeyboardInterrupt:
                print("\nCancelled.")
                return None
            except Exception as e:
                print(f"Error: {e}")
                continue
