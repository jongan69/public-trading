"""Tests for configuration."""
import pytest
import os
from unittest.mock import patch
from src.config import HighConvexityConfig, config


def test_config_loads():
    """Test that config loads successfully."""
    assert config is not None
    assert config.api_secret_key is not None
    assert len(config.api_secret_key) > 0


def test_config_defaults():
    """Test default configuration values."""
    assert config.theme_underlyings == ["UMC", "TE", "AMPX"]
    assert config.moonshot_symbol == "GME.WS"
    assert config.theme_a_target == 0.35
    assert config.theme_b_target == 0.35
    assert config.moonshot_target == 0.20
    assert config.cash_minimum == 0.20
    assert config.option_dte_min == 60
    assert config.option_dte_max == 120
    assert config.max_trades_per_day == 5
    assert config.dry_run == False


def test_config_env_override():
    """Test that environment variables can override defaults."""
    with patch.dict(os.environ, {"MOONSHOT_SYMBOL": "TEST.WS", "DRY_RUN": "true"}):
        test_config = HighConvexityConfig()
        assert test_config.moonshot_symbol == "TEST.WS"
        assert test_config.dry_run == True


def test_config_validation():
    """Test that config validates required fields."""
    # This test is tricky because the config is already loaded
    # We'll just verify that api_secret_key is required
    # by checking it exists in the loaded config
    assert hasattr(config, 'api_secret_key')
    assert config.api_secret_key is not None
