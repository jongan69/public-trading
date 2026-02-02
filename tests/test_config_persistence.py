"""Integration tests for config persistence (REQ-013)."""
import pytest
import os
from unittest.mock import patch
from src.config import HighConvexityConfig
from src.utils.config_override_manager import ConfigOverrideManager, CONFIG_OVERRIDE_FILE


@pytest.fixture
def clean_override_file():
    """Ensure override file doesn't exist before test."""
    if CONFIG_OVERRIDE_FILE.exists():
        CONFIG_OVERRIDE_FILE.unlink()
    yield
    if CONFIG_OVERRIDE_FILE.exists():
        CONFIG_OVERRIDE_FILE.unlink()


def test_config_loads_without_overrides(clean_override_file):
    """Test config loads normally when no overrides exist."""
    config = HighConvexityConfig.apply_overrides(HighConvexityConfig())
    # Should have default values (from .env or hardcoded)
    assert hasattr(config, "theme_a_target")
    assert hasattr(config, "option_dte_min")


def test_config_applies_overrides(clean_override_file):
    """Test config applies overrides correctly."""
    # Save overrides
    ConfigOverrideManager.save_override("theme_a_target", 0.50)
    ConfigOverrideManager.save_override("option_dte_min", 45)

    # Load config with overrides
    config = HighConvexityConfig.apply_overrides(HighConvexityConfig())

    # Check overrides applied
    assert config.theme_a_target == 0.50
    assert config.option_dte_min == 45


def test_override_precedence_over_default(clean_override_file):
    """Test that overrides take precedence over defaults."""
    # Create base config with default
    base_config = HighConvexityConfig()
    original_value = base_config.theme_a_target

    # Save override with different value
    new_value = 0.45 if original_value != 0.45 else 0.55
    ConfigOverrideManager.save_override("theme_a_target", new_value)

    # Apply overrides
    config_with_override = HighConvexityConfig.apply_overrides(HighConvexityConfig())

    # Override should win
    assert config_with_override.theme_a_target == new_value
    assert config_with_override.theme_a_target != original_value


def test_multiple_overrides_applied(clean_override_file):
    """Test that multiple overrides are all applied."""
    # Save multiple overrides
    overrides = {
        "theme_a_target": 0.40,
        "theme_b_target": 0.30,
        "option_dte_min": 50,
        "option_dte_max": 100,
        "strike_range_min": 1.05,
    }

    for key, value in overrides.items():
        ConfigOverrideManager.save_override(key, value)

    # Load config
    config = HighConvexityConfig.apply_overrides(HighConvexityConfig())

    # Verify all overrides applied
    assert config.theme_a_target == 0.40
    assert config.theme_b_target == 0.30
    assert config.option_dte_min == 50
    assert config.option_dte_max == 100
    assert config.strike_range_min == 1.05


def test_unoverridden_values_unchanged(clean_override_file):
    """Test that non-overridden values retain their defaults."""
    # Only override theme_a_target
    ConfigOverrideManager.save_override("theme_a_target", 0.50)

    # Load configs
    base_config = HighConvexityConfig()
    override_config = HighConvexityConfig.apply_overrides(HighConvexityConfig())

    # theme_a_target should be overridden
    assert override_config.theme_a_target == 0.50

    # Other values should match base config
    assert override_config.theme_b_target == base_config.theme_b_target
    assert override_config.option_dte_min == base_config.option_dte_min


def test_theme_underlyings_csv_override(clean_override_file):
    """Test overriding theme_underlyings_csv updates computed property."""
    # Save override
    new_symbols = "AAPL,MSFT,GOOGL"
    ConfigOverrideManager.save_override("theme_underlyings_csv", new_symbols)

    # Load config
    config = HighConvexityConfig.apply_overrides(HighConvexityConfig())

    # Check CSV is overridden
    assert config.theme_underlyings_csv == new_symbols

    # Check computed property updates
    assert config.theme_underlyings == ["AAPL", "MSFT", "GOOGL"]


def test_config_gracefully_handles_missing_override_file(clean_override_file):
    """Test that config loads without error when override file is missing."""
    # Ensure file doesn't exist
    assert not CONFIG_OVERRIDE_FILE.exists()

    # Should not raise exception
    config = HighConvexityConfig.apply_overrides(HighConvexityConfig())
    assert hasattr(config, "theme_a_target")


def test_config_gracefully_handles_corrupted_override_file(clean_override_file):
    """Test that config loads without error when override file is corrupted."""
    # Create corrupted file
    CONFIG_OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_OVERRIDE_FILE, 'w') as f:
        f.write("{ invalid json }")

    # Should not raise exception (logs warning instead)
    config = HighConvexityConfig.apply_overrides(HighConvexityConfig())
    assert hasattr(config, "theme_a_target")


def test_override_persists_across_config_reloads(clean_override_file):
    """Test that overrides persist across multiple config loads."""
    # Save override
    ConfigOverrideManager.save_override("theme_a_target", 0.42)

    # Load config multiple times
    config1 = HighConvexityConfig.apply_overrides(HighConvexityConfig())
    config2 = HighConvexityConfig.apply_overrides(HighConvexityConfig())
    config3 = HighConvexityConfig.apply_overrides(HighConvexityConfig())

    # All should have the override
    assert config1.theme_a_target == 0.42
    assert config2.theme_a_target == 0.42
    assert config3.theme_a_target == 0.42


def test_clearing_overrides_returns_to_defaults(clean_override_file):
    """Test that clearing overrides returns config to default values."""
    # Get default value
    base_config = HighConvexityConfig()
    default_value = base_config.theme_a_target

    # Override it
    ConfigOverrideManager.save_override("theme_a_target", 0.99)
    override_config = HighConvexityConfig.apply_overrides(HighConvexityConfig())
    assert override_config.theme_a_target == 0.99

    # Clear overrides
    ConfigOverrideManager.clear_overrides()

    # Load config again - should return to default
    restored_config = HighConvexityConfig.apply_overrides(HighConvexityConfig())
    assert restored_config.theme_a_target == default_value
