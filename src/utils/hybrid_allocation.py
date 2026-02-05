"""Smart hybrid allocation: core vs opportunistic buckets (REQ-021)."""
from typing import Dict, Tuple, Optional
from loguru import logger
from src.utils.strategy_math import StrategyProfile, kelly_fraction
from src.utils.monte_carlo import monte_carlo_returns
from src.utils.strategy_presets import get_preset


def smart_hybrid_allocation(
    portfolio_value: float,
    core_pct: float = 0.75
) -> Tuple[float, float]:
    """Split portfolio value into core and opportunistic buckets.

    Args:
        portfolio_value: Total portfolio value in dollars
        core_pct: Percentage allocated to core bucket (default 0.75 = 75%)

    Returns:
        Tuple of (core_capital, opportunistic_capital) in dollars

    Example:
        >>> core, opp = smart_hybrid_allocation(10000, core_pct=0.75)
        >>> print(f"Core: ${core:.0f}, Opportunistic: ${opp:.0f}")
        Core: $7500, Opportunistic: $2500
    """
    if not 0 <= core_pct <= 1.0:
        raise ValueError(f"core_pct must be between 0 and 1, got {core_pct}")

    core_capital = portfolio_value * core_pct
    opportunistic_capital = portfolio_value * (1 - core_pct)

    logger.debug(
        f"Hybrid allocation: ${portfolio_value:.0f} total -> "
        f"${core_capital:.0f} core ({core_pct*100:.0f}%), "
        f"${opportunistic_capital:.0f} opportunistic ({(1-core_pct)*100:.0f}%)"
    )

    return core_capital, opportunistic_capital


def apply_smart_hybrid(
    portfolio_value: float,
    core_strategy: Optional[StrategyProfile] = None,
    opportunistic_strategy: Optional[StrategyProfile] = None,
    core_pct: float = 0.75,
    opportunistic_kelly_throttle: float = 0.5,
    simulations: int = 5000,
    seed: Optional[int] = None
) -> Dict:
    """Apply smart hybrid allocation with Monte Carlo analysis for each bucket.

    Splits portfolio into core and opportunistic buckets, calculates Kelly fraction
    for each strategy, runs Monte Carlo simulations, and returns combined results.

    Args:
        portfolio_value: Total portfolio value in dollars
        core_strategy: Strategy for core bucket (default: "High Conviction" preset)
        opportunistic_strategy: Strategy for opportunistic bucket (default: "Daily 3% Grind" preset)
        core_pct: Percentage allocated to core bucket (default 0.75 = 75%)
        opportunistic_kelly_throttle: Multiplier for opportunistic Kelly (default 0.5 = 50%)
        simulations: Number of Monte Carlo simulations (default 5000)
        seed: Random seed for reproducibility (optional)

    Returns:
        Dict with keys:
            - portfolio_value: Total portfolio value
            - core_pct: Core allocation percentage
            - opportunistic_pct: Opportunistic allocation percentage
            - allocation: Dict with core_capital and opportunistic_capital
            - core: Dict with strategy_name, kelly_fraction, monte_carlo results
            - opportunistic: Dict with strategy_name, kelly_fraction, monte_carlo results

    Example:
        >>> result = apply_smart_hybrid(10000, simulations=1000, seed=42)
        >>> print(f"Core strategy: {result['core']['strategy_name']}")
        Core strategy: High Conviction
        >>> print(f"Core Kelly: {result['core']['kelly_fraction']*100:.1f}%")
        Core Kelly: 25.0%
        >>> print(f"Core median outcome: ${result['core']['monte_carlo']['median']:.0f}")
        Core median outcome: $8234

    Notes:
        - Core strategy defaults to "High Conviction" (40% win rate, 40% avg win, 15% avg loss)
        - Opportunistic strategy defaults to "Daily 3% Grind" (58% win rate, 3% avg win/loss)
        - Opportunistic Kelly is throttled by default (50% of full Kelly) for additional safety
        - Monte Carlo simulations run independently for each bucket
    """
    # Default strategies
    if core_strategy is None:
        core_strategy = get_preset("high_conviction")
        if core_strategy is None:
            raise ValueError("Could not load default 'high_conviction' preset")

    if opportunistic_strategy is None:
        opportunistic_strategy = get_preset("daily_3pct_grind")
        if opportunistic_strategy is None:
            raise ValueError("Could not load default 'daily_3pct_grind' preset")

    logger.info(
        f"Applying smart hybrid allocation: ${portfolio_value:.0f} portfolio, "
        f"core={core_strategy.name}, opportunistic={opportunistic_strategy.name}"
    )

    # Split allocation
    core_capital, opportunistic_capital = smart_hybrid_allocation(portfolio_value, core_pct)

    # Calculate Kelly fractions
    core_kelly = kelly_fraction(core_strategy)
    opportunistic_kelly_raw = kelly_fraction(opportunistic_strategy)
    opportunistic_kelly = opportunistic_kelly_raw * opportunistic_kelly_throttle

    logger.debug(
        f"Kelly fractions: core={core_kelly*100:.1f}%, "
        f"opportunistic={opportunistic_kelly*100:.1f}% (throttled from {opportunistic_kelly_raw*100:.1f}%)"
    )

    # Run Monte Carlo for core bucket
    core_mc = monte_carlo_returns(
        strategy=core_strategy,
        initial_capital=core_capital,
        risk_fraction=core_kelly,
        simulations=simulations,
        seed=seed
    )

    # Run Monte Carlo for opportunistic bucket (use different seed if provided)
    opp_seed = seed + 1000 if seed is not None else None
    opportunistic_mc = monte_carlo_returns(
        strategy=opportunistic_strategy,
        initial_capital=opportunistic_capital,
        risk_fraction=opportunistic_kelly,
        simulations=simulations,
        seed=opp_seed
    )

    # Build result
    result = {
        "portfolio_value": portfolio_value,
        "core_pct": core_pct,
        "opportunistic_pct": 1 - core_pct,
        "allocation": {
            "core_capital": core_capital,
            "opportunistic_capital": opportunistic_capital,
        },
        "core": {
            "strategy_name": core_strategy.name,
            "kelly_fraction": core_kelly,
            "monte_carlo": core_mc,
        },
        "opportunistic": {
            "strategy_name": opportunistic_strategy.name,
            "kelly_fraction": opportunistic_kelly,
            "kelly_fraction_unthrottled": opportunistic_kelly_raw,
            "monte_carlo": opportunistic_mc,
        },
    }

    logger.info(
        f"Hybrid allocation complete. Core: ${core_mc['median']:.0f} median, "
        f"Opportunistic: ${opportunistic_mc['median']:.0f} median"
    )

    return result


def format_hybrid_results(result: Dict) -> str:
    """Format smart hybrid allocation results as human-readable text.

    Args:
        result: Output from apply_smart_hybrid()

    Returns:
        Formatted string with allocation breakdown and Monte Carlo results

    Example:
        >>> result = apply_smart_hybrid(10000, simulations=1000, seed=42)
        >>> print(format_hybrid_results(result))
        Smart Hybrid Allocation
        Portfolio: $10,000
        ...
    """
    lines = [
        "Smart Hybrid Allocation",
        f"Portfolio: ${result['portfolio_value']:,.0f}",
        "",
        "Allocation:",
        f"  Core ({result['core_pct']*100:.0f}%): ${result['allocation']['core_capital']:,.0f}",
        f"  Opportunistic ({result['opportunistic_pct']*100:.0f}%): ${result['allocation']['opportunistic_capital']:,.0f}",
        "",
        f"Core Bucket ({result['core']['strategy_name']}):",
        f"  Kelly fraction: {result['core']['kelly_fraction']*100:.1f}%",
        f"  Median outcome: ${result['core']['monte_carlo']['median']:,.0f}",
        f"  Mean outcome: ${result['core']['monte_carlo']['mean']:,.0f}",
        f"  5th percentile: ${result['core']['monte_carlo']['5pct']:,.0f}",
        f"  95th percentile: ${result['core']['monte_carlo']['95pct']:,.0f}",
        f"  Max drawdown risk: {result['core']['monte_carlo']['max_drawdown_risk']*100:.1f}%",
        "",
        f"Opportunistic Bucket ({result['opportunistic']['strategy_name']}):",
        f"  Kelly fraction: {result['opportunistic']['kelly_fraction']*100:.1f}% (throttled)",
        f"  Median outcome: ${result['opportunistic']['monte_carlo']['median']:,.0f}",
        f"  Mean outcome: ${result['opportunistic']['monte_carlo']['mean']:,.0f}",
        f"  5th percentile: ${result['opportunistic']['monte_carlo']['5pct']:,.0f}",
        f"  95th percentile: ${result['opportunistic']['monte_carlo']['95pct']:,.0f}",
        f"  Max drawdown risk: {result['opportunistic']['monte_carlo']['max_drawdown_risk']*100:.1f}%",
        "",
        "Combined expected outcome (sum of medians):",
        f"  ${result['core']['monte_carlo']['median'] + result['opportunistic']['monte_carlo']['median']:,.0f}",
    ]

    return "\n".join(lines)
