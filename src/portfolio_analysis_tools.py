"""Portfolio analysis tools for AI integration (REQ-022)."""
from typing import Dict, Any
from loguru import logger
from src.portfolio import PortfolioManager
from src.utils.strategy_math import kelly_fraction
from src.utils.strategy_presets import PRESET_STRATEGIES
from src.utils.monte_carlo import monte_carlo_returns


def analyze_portfolio(portfolio_manager: PortfolioManager) -> Dict[str, Any]:
    """Analyze current portfolio: total value and allocation by type and theme.

    This is the main entry point for AI to get portfolio composition,
    combining both asset-type allocation (equity, crypto, bonds, etc.) and
    theme-based allocation (theme_a, theme_b, moonshot, etc.).

    Args:
        portfolio_manager: PortfolioManager instance with current portfolio data

    Returns:
        Dict with keys:
            - total_value: Total portfolio equity
            - cash: Available cash
            - buying_power: Total buying power
            - allocation_by_type: Dict mapping asset type to {pct, value}
            - allocation_by_theme: Dict mapping theme to percentage (decimal)

    Example:
        >>> pm = PortfolioManager(...)
        >>> result = analyze_portfolio(pm)
        >>> print(f"Total: ${result['total_value']:,.0f}")
        Total: $10,523
        >>> print(f"Equity: {result['allocation_by_type']['equity']['pct']*100:.1f}%")
        Equity: 72.5%
    """
    logger.info("Running analyze_portfolio")

    # Refresh portfolio to get latest data
    portfolio_manager.refresh_portfolio()

    # Get total value
    total_value = portfolio_manager.get_equity()
    cash = portfolio_manager.get_cash()
    buying_power = portfolio_manager.get_buying_power()

    # Get allocation by type (equity, crypto, bonds, alt, cash)
    allocation_by_type = portfolio_manager.get_allocations_by_type()

    # Get allocation by theme (theme_a, theme_b, theme_c, moonshot, cash)
    allocation_by_theme = portfolio_manager.get_current_allocations()

    result = {
        "total_value": total_value,
        "cash": cash,
        "buying_power": buying_power,
        "allocation_by_type": allocation_by_type,
        "allocation_by_theme": allocation_by_theme,
    }

    logger.debug(
        f"Portfolio analysis: ${total_value:,.0f} total, "
        f"{len(allocation_by_type)} asset types, "
        f"{len(allocation_by_theme)} theme allocations"
    )

    return result


def compare_strategies(
    capital: float,
    simulations: int = 5000,
    seed: int = None
) -> Dict[str, Dict[str, Any]]:
    """Compare preset strategies using Monte Carlo simulations.

    Runs Monte Carlo analysis for all available preset strategies at the given
    capital level, allowing AI to compare and recommend strategies based on
    expected outcomes, risk profiles, and drawdown probabilities.

    Args:
        capital: Capital to analyze (e.g., current equity or user-specified amount)
        simulations: Number of Monte Carlo simulations per strategy (default 5000)
        seed: Random seed for reproducibility (optional)

    Returns:
        Dict mapping strategy key to result dict with:
            - strategy_name: Human-readable strategy name
            - kelly_fraction: Recommended position sizing
            - monte_carlo: Monte Carlo results (median, mean, percentiles, drawdown risk)
            - capital: Capital used for simulation

    Example:
        >>> results = compare_strategies(10000, simulations=1000, seed=42)
        >>> daily_grind = results["daily_3pct_grind"]
        >>> print(f"{daily_grind['strategy_name']}: ${daily_grind['monte_carlo']['median']:,.0f} median")
        Daily 3% Grind: $10,482 median
    """
    logger.info(f"Running compare_strategies with ${capital:,.0f} capital")

    results = {}

    for strategy_key, strategy_profile in PRESET_STRATEGIES.items():
        logger.debug(f"Analyzing strategy: {strategy_profile.name}")

        # Calculate Kelly fraction for this strategy
        kelly = kelly_fraction(strategy_profile)

        # Run Monte Carlo simulation
        # Use different seed for each strategy if seed provided
        strategy_seed = None
        if seed is not None:
            strategy_seed = seed + hash(strategy_key) % 10000

        mc_result = monte_carlo_returns(
            strategy=strategy_profile,
            initial_capital=capital,
            risk_fraction=kelly,
            simulations=simulations,
            seed=strategy_seed
        )

        results[strategy_key] = {
            "strategy_name": strategy_profile.name,
            "kelly_fraction": kelly,
            "monte_carlo": mc_result,
            "capital": capital,
        }

    logger.info(f"Strategy comparison complete: {len(results)} strategies analyzed")

    return results


def format_portfolio_analysis(result: Dict[str, Any]) -> str:
    """Format analyze_portfolio results as human-readable text.

    Args:
        result: Output from analyze_portfolio()

    Returns:
        Formatted string with portfolio breakdown
    """
    lines = [
        "Portfolio Analysis",
        f"Total Value: ${result['total_value']:,.2f}",
        f"Cash: ${result['cash']:,.2f}",
        f"Buying Power: ${result['buying_power']:,.2f}",
        "",
        "Allocation by Asset Type:",
    ]

    # Sort by value descending
    sorted_types = sorted(
        result['allocation_by_type'].items(),
        key=lambda x: x[1]["value"],
        reverse=True
    )

    for asset_type, data in sorted_types:
        if data["pct"] > 0.001:  # Only show if > 0.1%
            lines.append(f"  {asset_type}: {data['pct']*100:.1f}% (${data['value']:,.2f})")

    lines.extend([
        "",
        "Allocation by Theme:",
    ])

    # Sort themes by value
    sorted_themes = sorted(
        result['allocation_by_theme'].items(),
        key=lambda x: x[1],
        reverse=True
    )

    for theme, pct in sorted_themes:
        if pct > 0.001:
            lines.append(f"  {theme}: {pct*100:.1f}%")

    return "\n".join(lines)


def format_strategy_comparison(results: Dict[str, Dict[str, Any]]) -> str:
    """Format compare_strategies results as human-readable text.

    Args:
        results: Output from compare_strategies()

    Returns:
        Formatted string comparing all strategies
    """
    lines = [
        f"Strategy Comparison (${results[list(results.keys())[0]]['capital']:,.0f} capital)",
        "",
    ]

    for strategy_key, data in results.items():
        name = data["strategy_name"]
        kelly = data["kelly_fraction"]
        mc = data["monte_carlo"]

        lines.extend([
            f"{name}:",
            f"  Kelly fraction: {kelly*100:.1f}%",
            f"  Median outcome: ${mc['median']:,.0f}",
            f"  Mean outcome: ${mc['mean']:,.0f}",
            f"  5th percentile: ${mc['5pct']:,.0f}",
            f"  95th percentile: ${mc['95pct']:,.0f}",
            f"  Max drawdown risk: {mc['max_drawdown_risk']*100:.1f}%",
            "",
        ])

    return "\n".join(lines)
