"""Public.com API client wrapper."""
from public_api_sdk import PublicApiClient, PublicApiClientConfiguration
from public_api_sdk.auth_config import ApiKeyAuthConfig
from typing import Optional
from loguru import logger

from src.config import config


class TradingClient:
    """Wrapper around PublicApiClient with enhanced error handling."""
    
    def __init__(
        self, 
        api_secret_key: Optional[str] = None, 
        account_number: Optional[str] = None
    ):
        """Initialize the trading client.
        
        Args:
            api_secret_key: API secret key (defaults to config)
            account_number: Account number (required if not in config)
        """
        self.api_secret_key = api_secret_key or config.api_secret_key
        
        if account_number is None:
            raise ValueError("Account number must be provided")
        
        self.account_number = account_number
        
        client_config = PublicApiClientConfiguration(
            default_account_number=self.account_number
        )
        
        self.client = PublicApiClient(
            ApiKeyAuthConfig(api_secret_key=self.api_secret_key),
            config=client_config
        )
        
        logger.info(f"Trading client initialized for account: {self.account_number}")
    
    def close(self):
        """Close the client and clean up resources."""
        self.client.close()
        logger.info("Trading client closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
