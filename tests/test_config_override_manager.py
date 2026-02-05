"""Tests for ConfigOverrideManager (REQ-013)."""
import pytest
import json
from pathlib import Path
from src.utils.config_override_manager import (
    ConfigOverrideManager,
    TELEGRAM_EDITABLE_KEYS,
    CONFIG_OVERRIDE_FILE,
)


@pytest.fixture
def clean_override_file():
    """Ensure override file doesn't exist before test."""
    if CONFIG_OVERRIDE_FILE.exists():
        CONFIG_OVERRIDE_FILE.unlink()
    yield
    if CONFIG_OVERRIDE_FILE.exists():
        CONFIG_OVERRIDE_FILE.unlink()


def test_load_overrides_empty(clean_override_file):
    """Test loading when no override file exists."""
    overrides = ConfigOverrideManager.load_overrides()
    assert overrides == {}


def test_save_and_load_override(clean_override_file):
    """Test saving and loading a single override."""
    ConfigOverrideManager.save_override("theme_a_target", 0.40)

    overrides = ConfigOverrideManager.load_overrides()
    assert "theme_a_target" in overrides
    assert overrides["theme_a_target"] == 0.40


def test_save_invalid_key(clean_override_file):
    """Test that invalid keys (e.g. sensitive) are rejected."""
    with pytest.raises(ValueError, match="not editable via chat"):
        ConfigOverrideManager.save_override("api_secret_key", "test")


def test_multiple_overrides(clean_override_file):
    """Test saving multiple overrides."""
    ConfigOverrideManager.save_override("theme_a_target", 0.40)
    ConfigOverrideManager.save_override("option_dte_min", 45)
    ConfigOverrideManager.save_override("theme_underlyings_csv", "AAPL,MSFT")

    overrides = ConfigOverrideManager.load_overrides()
    assert len(overrides) == 3
    assert overrides["theme_a_target"] == 0.40
    assert overrides["option_dte_min"] == 45
    assert overrides["theme_underlyings_csv"] == "AAPL,MSFT"


def test_override_updates_existing_value(clean_override_file):
    """Test that saving an override updates the existing value."""
    ConfigOverrideManager.save_override("theme_a_target", 0.30)
    ConfigOverrideManager.save_override("theme_a_target", 0.45)

    overrides = ConfigOverrideManager.load_overrides()
    assert overrides["theme_a_target"] == 0.45  # Updated value


def test_clear_overrides(clean_override_file):
    """Test clearing all overrides."""
    ConfigOverrideManager.save_override("theme_a_target", 0.40)
    assert CONFIG_OVERRIDE_FILE.exists()

    ConfigOverrideManager.clear_overrides()
    assert not CONFIG_OVERRIDE_FILE.exists()


def test_load_corrupted_file(clean_override_file):
    """Test loading when override file is corrupted JSON."""
    CONFIG_OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_OVERRIDE_FILE, 'w') as f:
        f.write("{ invalid json ")

    # Should return empty dict instead of crashing
    overrides = ConfigOverrideManager.load_overrides()
    assert overrides == {}


def test_metadata_excluded_from_load(clean_override_file):
    """Test that _updated_at metadata is excluded from loaded overrides."""
    ConfigOverrideManager.save_override("theme_a_target", 0.40)

    overrides = ConfigOverrideManager.load_overrides()
    assert "_updated_at" not in overrides


def test_metadata_present_in_file(clean_override_file):
    """Test that _updated_at metadata is saved to file."""
    ConfigOverrideManager.save_override("theme_a_target", 0.40)

    with open(CONFIG_OVERRIDE_FILE, 'r') as f:
        data = json.load(f)

    assert "_updated_at" in data
    assert "theme_a_target" in data


def test_get_override_summary_empty(clean_override_file):
    """Test summary when no overrides exist."""
    summary = ConfigOverrideManager.get_override_summary()
    assert "No config overrides active" in summary


def test_get_override_summary_with_overrides(clean_override_file):
    """Test summary shows active overrides."""
    ConfigOverrideManager.save_override("theme_a_target", 0.40)
    ConfigOverrideManager.save_override("option_dte_min", 45)

    summary = ConfigOverrideManager.get_override_summary()
    assert "Active config overrides" in summary
    assert "theme_a_target" in summary
    assert "option_dte_min" in summary
    assert "0.4" in summary or "0.40" in summary
    assert "45" in summary


def test_whitelist_contains_expected_keys():
    """Test that whitelist contains all expected Telegram-editable keys."""
    # Whitelist includes at least the original allocation/option/theme keys
    expected_subset = {
        "theme_a_target", "theme_b_target", "theme_c_target",
        "moonshot_target", "cash_minimum",
        "option_dte_min", "option_dte_max",
        "strike_range_min", "strike_range_max",
        "theme_underlyings_csv",
    }
    assert expected_subset.issubset(TELEGRAM_EDITABLE_KEYS)


def test_file_created_in_data_directory(clean_override_file):
    """Test that override file is created in data/ directory."""
    ConfigOverrideManager.save_override("theme_a_target", 0.40)

    assert CONFIG_OVERRIDE_FILE.exists()
    assert CONFIG_OVERRIDE_FILE.parent.name == "data"
    assert CONFIG_OVERRIDE_FILE.name == "config_overrides.json"
