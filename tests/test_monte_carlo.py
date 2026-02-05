"""Tests for Monte Carlo returns engine (REQ-020)."""
import pytest
from src.utils.monte_carlo import monte_carlo_returns
from src.utils.strategy_math import StrategyProfile


def test_monte_carlo_returns_basic():
    """Test basic Monte Carlo simulation returns expected structure."""
    strategy = StrategyProfile(
        name="Test Strategy",
        win_rate=0.55,
        avg_win=0.03,
        avg_loss=0.03,
        trades_per_year=100
    )

    result = monte_carlo_returns(
        strategy=strategy,
        initial_capital=10000,
        risk_fraction=0.02,
        simulations=1000,
        seed=42
    )

    # Check all required keys are present
    assert "median" in result
    assert "mean" in result
    assert "5pct" in result
    assert "95pct" in result
    assert "max_drawdown_risk" in result

    # Check types
    assert isinstance(result["median"], float)
    assert isinstance(result["mean"], float)
    assert isinstance(result["5pct"], float)
    assert isinstance(result["95pct"], float)
    assert isinstance(result["max_drawdown_risk"], float)

    # Check reasonable ranges
    assert result["median"] > 0
    assert result["mean"] > 0
    assert result["5pct"] > 0
    assert result["95pct"] > result["median"]
    assert 0 <= result["max_drawdown_risk"] <= 1.0


def test_monte_carlo_positive_edge():
    """Test that positive-edge strategy tends to grow capital."""
    strategy = StrategyProfile(
        name="Positive Edge",
        win_rate=0.60,  # 60% win rate
        avg_win=0.05,   # 5% wins
        avg_loss=0.03,  # 3% losses
        trades_per_year=200
    )

    result = monte_carlo_returns(
        strategy=strategy,
        initial_capital=10000,
        risk_fraction=0.05,
        simulations=2000,
        seed=123
    )

    # With positive edge, median should be above initial capital
    assert result["median"] > 10000
    assert result["mean"] > 10000


def test_monte_carlo_negative_edge():
    """Test that negative-edge strategy tends to lose capital."""
    strategy = StrategyProfile(
        name="Negative Edge",
        win_rate=0.40,  # 40% win rate
        avg_win=0.03,   # 3% wins
        avg_loss=0.05,  # 5% losses (larger than wins)
        trades_per_year=200
    )

    result = monte_carlo_returns(
        strategy=strategy,
        initial_capital=10000,
        risk_fraction=0.05,
        simulations=2000,
        seed=456
    )

    # With negative edge, median should be below initial capital
    assert result["median"] < 10000
    assert result["mean"] < 10000


def test_monte_carlo_percentile_ordering():
    """Test that percentiles are properly ordered."""
    strategy = StrategyProfile(
        name="Test",
        win_rate=0.50,
        avg_win=0.04,
        avg_loss=0.04,
        trades_per_year=100
    )

    result = monte_carlo_returns(
        strategy=strategy,
        initial_capital=10000,
        risk_fraction=0.03,
        simulations=1000,
        seed=789
    )

    # 5th percentile should be less than median, median less than 95th
    assert result["5pct"] < result["median"]
    assert result["median"] < result["95pct"]


def test_monte_carlo_low_risk_fraction():
    """Test that low risk fraction produces tighter distribution."""
    strategy = StrategyProfile(
        name="Volatile",
        win_rate=0.50,
        avg_win=0.10,
        avg_loss=0.10,
        trades_per_year=200
    )

    # Low risk
    low_risk_result = monte_carlo_returns(
        strategy=strategy,
        initial_capital=10000,
        risk_fraction=0.01,  # 1% risk
        simulations=1000,
        seed=100
    )

    # High risk
    high_risk_result = monte_carlo_returns(
        strategy=strategy,
        initial_capital=10000,
        risk_fraction=0.10,  # 10% risk
        simulations=1000,
        seed=100
    )

    # High risk should have wider spread between percentiles
    low_risk_spread = low_risk_result["95pct"] - low_risk_result["5pct"]
    high_risk_spread = high_risk_result["95pct"] - high_risk_result["5pct"]
    assert high_risk_spread > low_risk_spread

    # Max drawdown risk should be >= for high risk (can be equal if both are low)
    assert high_risk_result["max_drawdown_risk"] >= low_risk_result["max_drawdown_risk"]


def test_monte_carlo_deterministic_with_seed():
    """Test that same seed produces same results."""
    strategy = StrategyProfile(
        name="Test",
        win_rate=0.55,
        avg_win=0.03,
        avg_loss=0.03,
        trades_per_year=100
    )

    result1 = monte_carlo_returns(
        strategy=strategy,
        initial_capital=10000,
        risk_fraction=0.02,
        simulations=500,
        seed=999
    )

    result2 = monte_carlo_returns(
        strategy=strategy,
        initial_capital=10000,
        risk_fraction=0.02,
        simulations=500,
        seed=999
    )

    # Results should be identical with same seed
    assert result1["median"] == result2["median"]
    assert result1["mean"] == result2["mean"]
    assert result1["5pct"] == result2["5pct"]
    assert result1["95pct"] == result2["95pct"]
    assert result1["max_drawdown_risk"] == result2["max_drawdown_risk"]


def test_monte_carlo_zero_capital_handling():
    """Test that simulation handles capital going to zero."""
    strategy = StrategyProfile(
        name="Risky",
        win_rate=0.30,  # Low win rate
        avg_win=0.05,
        avg_loss=0.20,  # Large losses
        trades_per_year=50
    )

    result = monte_carlo_returns(
        strategy=strategy,
        initial_capital=1000,
        risk_fraction=0.25,  # High risk
        simulations=500,
        seed=555
    )

    # Should complete without errors
    assert result["median"] >= 0
    assert result["5pct"] >= 0  # Can go to zero but not negative


def test_monte_carlo_preset_strategies():
    """Test Monte Carlo with preset strategies from strategy_presets."""
    from src.utils.strategy_presets import get_preset

    # Test Daily 3% Grind
    daily_grind = get_preset("daily_3pct_grind")
    result_grind = monte_carlo_returns(
        strategy=daily_grind,
        initial_capital=10000,
        risk_fraction=0.02,
        simulations=1000,
        seed=111
    )

    assert result_grind["median"] > 10000  # Should grow with positive edge

    # Test High Conviction
    high_conviction = get_preset("high_conviction")
    result_conviction = monte_carlo_returns(
        strategy=high_conviction,
        initial_capital=10000,
        risk_fraction=0.05,
        simulations=1000,
        seed=222
    )

    # High conviction has positive edge but fewer trades
    assert result_conviction["median"] > 0
    # Should have wider distribution (higher 95th percentile relative to median)
    spread_conviction = result_conviction["95pct"] - result_conviction["median"]
    spread_grind = result_grind["95pct"] - result_grind["median"]
    assert spread_conviction > spread_grind  # More volatile


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
