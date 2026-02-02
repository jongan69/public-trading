"""Tests for strategy math module (REQ-019)."""
import pytest
from src.utils.strategy_math import StrategyProfile, expected_value, kelly_fraction, risk_of_ruin
from src.utils.strategy_presets import get_preset, list_presets


def test_strategy_profile_creation():
    """Test creating StrategyProfile dataclass."""
    profile = StrategyProfile(
        name="Test Strategy",
        win_rate=0.55,
        avg_win=0.05,
        avg_loss=0.03,
        trades_per_year=100
    )
    assert profile.name == "Test Strategy"
    assert profile.win_rate == 0.55
    assert profile.avg_win == 0.05
    assert profile.avg_loss == 0.03
    assert profile.trades_per_year == 100


def test_expected_value_positive():
    """Test EV calculation for positive-expectancy strategy."""
    profile = StrategyProfile(
        name="Winning Strategy",
        win_rate=0.60,
        avg_win=0.05,
        avg_loss=0.03,
        trades_per_year=100
    )
    ev = expected_value(profile)
    # EV = 0.60 * 0.05 - 0.40 * 0.03 = 0.03 - 0.012 = 0.018
    assert ev == pytest.approx(0.018, abs=0.001)


def test_expected_value_negative():
    """Test EV for negative-expectancy strategy."""
    profile = StrategyProfile(
        name="Losing Strategy",
        win_rate=0.40,
        avg_win=0.03,
        avg_loss=0.05,
        trades_per_year=100
    )
    ev = expected_value(profile)
    # EV = 0.40 * 0.03 - 0.60 * 0.05 = 0.012 - 0.03 = -0.018
    assert ev == pytest.approx(-0.018, abs=0.001)


def test_expected_value_zero():
    """Test EV for breakeven strategy."""
    profile = StrategyProfile(
        name="Breakeven Strategy",
        win_rate=0.50,
        avg_win=0.03,
        avg_loss=0.03,
        trades_per_year=100
    )
    ev = expected_value(profile)
    # EV = 0.50 * 0.03 - 0.50 * 0.03 = 0.015 - 0.015 = 0.0
    assert ev == pytest.approx(0.0, abs=0.001)


def test_kelly_fraction_positive_edge():
    """Test Kelly calculation for positive-edge strategy."""
    profile = StrategyProfile(
        name="Test",
        win_rate=0.55,
        avg_win=0.06,
        avg_loss=0.04,
        trades_per_year=100
    )
    kelly = kelly_fraction(profile)
    # b = 0.06/0.04 = 1.5, p = 0.55, q = 0.45
    # Kelly = (1.5*0.55 - 0.45)/1.5 = (0.825 - 0.45)/1.5 = 0.25
    assert kelly == pytest.approx(0.25, abs=0.01)


def test_kelly_fraction_capped():
    """Test that Kelly is capped at 25%."""
    profile = StrategyProfile(
        name="High Edge",
        win_rate=0.70,
        avg_win=0.10,
        avg_loss=0.02,
        trades_per_year=50
    )
    kelly = kelly_fraction(profile)
    # Raw Kelly would be higher, but should be capped at 0.25
    assert kelly <= 0.25


def test_kelly_fraction_zero_loss():
    """Test Kelly handles zero avg_loss gracefully."""
    profile = StrategyProfile(
        name="Zero Loss",
        win_rate=0.60,
        avg_win=0.05,
        avg_loss=0.0,
        trades_per_year=100
    )
    kelly = kelly_fraction(profile)
    assert kelly == 0.0


def test_kelly_fraction_negative_edge():
    """Test Kelly for negative-edge strategy."""
    profile = StrategyProfile(
        name="Losing Strategy",
        win_rate=0.40,
        avg_win=0.03,
        avg_loss=0.05,
        trades_per_year=100
    )
    kelly = kelly_fraction(profile)
    # Negative edge should give Kelly near zero or negative (clamped to 0)
    assert kelly == 0.0


def test_risk_of_ruin_low_risk():
    """Test ROR with conservative risk (should be low)."""
    ror = risk_of_ruin(
        win_rate=0.55,
        win=100.0,
        loss=100.0,
        capital=10000,
        risk_per_trade=100.0,  # 1% risk
        trials=1000  # Use fewer trials for speed
    )
    # With positive edge and low risk, ROR should be near 0%
    assert ror < 0.10


def test_risk_of_ruin_high_risk():
    """Test ROR with aggressive risk (should be higher)."""
    ror = risk_of_ruin(
        win_rate=0.55,
        win=500.0,
        loss=500.0,
        capital=10000,
        risk_per_trade=1000.0,  # 10% risk
        trials=1000
    )
    # With high risk per trade, ROR should be elevated
    assert ror > 0.05


def test_risk_of_ruin_negative_edge():
    """Test ROR with negative edge (should be high)."""
    ror = risk_of_ruin(
        win_rate=0.40,
        win=100.0,
        loss=100.0,
        capital=10000,
        risk_per_trade=200.0,
        trials=1000
    )
    # Negative edge means high probability of ruin
    assert ror > 0.20


def test_risk_of_ruin_guaranteed_ruin():
    """Test ROR with very negative edge (nearly 100% ruin)."""
    ror = risk_of_ruin(
        win_rate=0.10,
        win=100.0,
        loss=200.0,
        capital=5000,
        risk_per_trade=500.0,
        trials=500
    )
    # Terrible edge + high risk = very high ROR
    assert ror > 0.70


def test_get_preset_daily_grind():
    """Test retrieving daily_3pct_grind preset."""
    profile = get_preset("daily_3pct_grind")
    assert profile is not None
    assert profile.name == "Daily 3% Grind"
    assert profile.win_rate == 0.58
    assert profile.avg_win == 0.03
    assert profile.avg_loss == 0.03
    assert profile.trades_per_year == 220


def test_get_preset_high_conviction():
    """Test retrieving high_conviction preset."""
    profile = get_preset("high_conviction")
    assert profile is not None
    assert profile.name == "High Conviction"
    assert profile.win_rate == 0.40
    assert profile.avg_win == 0.40
    assert profile.avg_loss == 0.15
    assert profile.trades_per_year == 10


def test_get_preset_case_insensitive():
    """Test that preset lookup is case-insensitive."""
    profile1 = get_preset("Daily_3Pct_Grind")
    profile2 = get_preset("DAILY_3PCT_GRIND")
    profile3 = get_preset("daily_3pct_grind")

    # All should return the same preset
    assert profile1 is profile2 is profile3
    assert profile1.name == "Daily 3% Grind"


def test_get_preset_not_found():
    """Test retrieving non-existent preset."""
    profile = get_preset("nonexistent_strategy")
    assert profile is None


def test_list_presets():
    """Test listing all available presets."""
    presets = list_presets()

    assert "daily_3pct_grind" in presets
    assert "high_conviction" in presets
    assert presets["daily_3pct_grind"] == "Daily 3% Grind"
    assert presets["high_conviction"] == "High Conviction"
    assert len(presets) >= 2


def test_kelly_fraction_custom_cap():
    """Test Kelly with custom cap."""
    profile = StrategyProfile(
        name="Test",
        win_rate=0.60,
        avg_win=0.10,
        avg_loss=0.05,
        trades_per_year=100
    )

    # Test with 10% cap
    kelly_10 = kelly_fraction(profile, cap=0.10)
    assert kelly_10 <= 0.10

    # Test with 50% cap
    kelly_50 = kelly_fraction(profile, cap=0.50)
    assert kelly_50 <= 0.50
    assert kelly_50 >= kelly_10


def test_risk_of_ruin_custom_threshold():
    """Test ROR with custom ruin threshold."""
    # Test with 50% threshold (less conservative)
    ror_50 = risk_of_ruin(
        win_rate=0.55,
        win=100.0,
        loss=100.0,
        capital=10000,
        risk_per_trade=500.0,
        ruin_threshold=0.50,
        trials=500
    )

    # Test with 20% threshold (more conservative)
    ror_20 = risk_of_ruin(
        win_rate=0.55,
        win=100.0,
        loss=100.0,
        capital=10000,
        risk_per_trade=500.0,
        ruin_threshold=0.20,
        trials=500
    )

    # More conservative threshold should show higher ROR
    assert ror_20 >= ror_50
