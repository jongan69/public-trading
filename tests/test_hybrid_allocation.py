"""Tests for smart hybrid allocation (REQ-021)."""
import pytest
from src.utils.hybrid_allocation import (
    smart_hybrid_allocation,
    apply_smart_hybrid,
    format_hybrid_results
)
from src.utils.strategy_math import StrategyProfile


def test_smart_hybrid_allocation_basic():
    """Test basic allocation split."""
    core, opp = smart_hybrid_allocation(10000, core_pct=0.75)

    assert core == 7500
    assert opp == 2500
    assert core + opp == 10000


def test_smart_hybrid_allocation_different_percentages():
    """Test allocation with different core percentages."""
    # 60/40 split
    core, opp = smart_hybrid_allocation(10000, core_pct=0.60)
    assert abs(core - 6000) < 0.01
    assert abs(opp - 4000) < 0.01

    # 90/10 split
    core, opp = smart_hybrid_allocation(10000, core_pct=0.90)
    assert abs(core - 9000) < 0.01
    assert abs(opp - 1000) < 0.01

    # 50/50 split
    core, opp = smart_hybrid_allocation(10000, core_pct=0.50)
    assert abs(core - 5000) < 0.01
    assert abs(opp - 5000) < 0.01


def test_smart_hybrid_allocation_invalid_percentage():
    """Test that invalid percentages raise ValueError."""
    with pytest.raises(ValueError):
        smart_hybrid_allocation(10000, core_pct=1.5)

    with pytest.raises(ValueError):
        smart_hybrid_allocation(10000, core_pct=-0.1)


def test_apply_smart_hybrid_basic():
    """Test basic apply_smart_hybrid with default strategies."""
    result = apply_smart_hybrid(
        portfolio_value=10000,
        simulations=1000,
        seed=42
    )

    # Check structure
    assert "portfolio_value" in result
    assert "core_pct" in result
    assert "opportunistic_pct" in result
    assert "allocation" in result
    assert "core" in result
    assert "opportunistic" in result

    # Check allocation
    assert result["portfolio_value"] == 10000
    assert result["core_pct"] == 0.75
    assert result["opportunistic_pct"] == 0.25
    assert result["allocation"]["core_capital"] == 7500
    assert result["allocation"]["opportunistic_capital"] == 2500

    # Check core bucket
    assert result["core"]["strategy_name"] == "High Conviction"
    assert 0 < result["core"]["kelly_fraction"] <= 0.25
    assert "median" in result["core"]["monte_carlo"]
    assert "mean" in result["core"]["monte_carlo"]
    assert "5pct" in result["core"]["monte_carlo"]
    assert "95pct" in result["core"]["monte_carlo"]
    assert "max_drawdown_risk" in result["core"]["monte_carlo"]

    # Check opportunistic bucket
    assert result["opportunistic"]["strategy_name"] == "Daily 3% Grind"
    assert 0 < result["opportunistic"]["kelly_fraction"] <= 0.25
    assert "median" in result["opportunistic"]["monte_carlo"]


def test_apply_smart_hybrid_custom_strategies():
    """Test apply_smart_hybrid with custom strategies."""
    core_strategy = StrategyProfile(
        name="Custom Core",
        win_rate=0.50,
        avg_win=0.20,
        avg_loss=0.10,
        trades_per_year=20
    )

    opp_strategy = StrategyProfile(
        name="Custom Opportunistic",
        win_rate=0.60,
        avg_win=0.05,
        avg_loss=0.04,
        trades_per_year=100
    )

    result = apply_smart_hybrid(
        portfolio_value=10000,
        core_strategy=core_strategy,
        opportunistic_strategy=opp_strategy,
        simulations=1000,
        seed=123
    )

    assert result["core"]["strategy_name"] == "Custom Core"
    assert result["opportunistic"]["strategy_name"] == "Custom Opportunistic"


def test_apply_smart_hybrid_custom_allocation():
    """Test apply_smart_hybrid with custom core percentage."""
    result = apply_smart_hybrid(
        portfolio_value=10000,
        core_pct=0.60,
        simulations=1000,
        seed=456
    )

    assert result["core_pct"] == 0.60
    assert result["opportunistic_pct"] == 0.40
    assert result["allocation"]["core_capital"] == 6000
    assert result["allocation"]["opportunistic_capital"] == 4000


def test_apply_smart_hybrid_opportunistic_throttle():
    """Test that opportunistic Kelly is properly throttled."""
    result = apply_smart_hybrid(
        portfolio_value=10000,
        opportunistic_kelly_throttle=0.5,
        simulations=1000,
        seed=789
    )

    # Check that throttled Kelly is less than unthrottled
    assert result["opportunistic"]["kelly_fraction"] < result["opportunistic"]["kelly_fraction_unthrottled"]
    assert abs(
        result["opportunistic"]["kelly_fraction"] -
        result["opportunistic"]["kelly_fraction_unthrottled"] * 0.5
    ) < 0.001


def test_apply_smart_hybrid_deterministic():
    """Test that same seed produces same results."""
    result1 = apply_smart_hybrid(
        portfolio_value=10000,
        simulations=500,
        seed=999
    )

    result2 = apply_smart_hybrid(
        portfolio_value=10000,
        simulations=500,
        seed=999
    )

    # Core Monte Carlo should be identical
    assert result1["core"]["monte_carlo"]["median"] == result2["core"]["monte_carlo"]["median"]
    assert result1["core"]["monte_carlo"]["mean"] == result2["core"]["monte_carlo"]["mean"]

    # Opportunistic Monte Carlo should be identical
    assert result1["opportunistic"]["monte_carlo"]["median"] == result2["opportunistic"]["monte_carlo"]["median"]
    assert result1["opportunistic"]["monte_carlo"]["mean"] == result2["opportunistic"]["monte_carlo"]["mean"]


def test_format_hybrid_results():
    """Test formatting of hybrid allocation results."""
    result = apply_smart_hybrid(
        portfolio_value=10000,
        simulations=1000,
        seed=42
    )

    formatted = format_hybrid_results(result)

    # Check that output contains key information
    assert "Smart Hybrid Allocation" in formatted
    assert "$10,000" in formatted
    assert "Core" in formatted
    assert "Opportunistic" in formatted
    assert "High Conviction" in formatted
    assert "Daily 3% Grind" in formatted
    assert "Median outcome" in formatted
    assert "Kelly fraction" in formatted
    assert "Max drawdown risk" in formatted


def test_apply_smart_hybrid_positive_outcomes():
    """Test that both buckets generally grow with positive-edge strategies."""
    result = apply_smart_hybrid(
        portfolio_value=10000,
        simulations=2000,
        seed=111
    )

    # With positive-edge strategies, median should generally be positive
    core_median = result["core"]["monte_carlo"]["median"]
    opp_median = result["opportunistic"]["monte_carlo"]["median"]

    # Check that outcomes are reasonable (not zero or wildly off)
    assert core_median > 0
    assert opp_median > 0

    # Combined median should be positive
    combined_median = core_median + opp_median
    assert combined_median > 0


def test_apply_smart_hybrid_percentile_ordering():
    """Test that percentiles are properly ordered in both buckets."""
    result = apply_smart_hybrid(
        portfolio_value=10000,
        simulations=1000,
        seed=222
    )

    # Core bucket percentiles should be ordered
    core_mc = result["core"]["monte_carlo"]
    assert core_mc["5pct"] < core_mc["median"]
    assert core_mc["median"] < core_mc["95pct"]

    # Opportunistic bucket percentiles should be ordered
    opp_mc = result["opportunistic"]["monte_carlo"]
    assert opp_mc["5pct"] < opp_mc["median"]
    assert opp_mc["median"] < opp_mc["95pct"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
