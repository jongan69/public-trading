"""Monte Carlo simulation for strategy returns analysis (REQ-020)."""
from typing import Dict
import random
from loguru import logger
from src.utils.strategy_math import StrategyProfile


def monte_carlo_returns(
    strategy: StrategyProfile,
    initial_capital: float,
    risk_fraction: float,
    simulations: int = 5000,
    seed: int = None
) -> Dict[str, float]:
    """Run Monte Carlo simulation of strategy returns.

    Simulates multiple paths of trading a strategy over one year, returning
    statistical distribution of outcomes and risk metrics.

    Each simulation runs `strategy.trades_per_year` trades where:
    - Bet size = current_capital * risk_fraction
    - Win probability = strategy.win_rate
    - Win: add bet * strategy.avg_win
    - Loss: subtract bet * strategy.avg_loss
    - Capital is clamped to >= 0 (cannot go negative)

    Args:
        strategy: StrategyProfile with win/loss statistics
        initial_capital: Starting capital in dollars
        risk_fraction: Fraction of capital risked per trade (e.g., 0.10 = 10%)
        simulations: Number of Monte Carlo trials (default 5000)
        seed: Random seed for reproducibility (optional, for testing)

    Returns:
        Dict with keys:
            - median: Median terminal capital across simulations
            - mean: Mean terminal capital across simulations
            - 5pct: 5th percentile terminal capital (downside tail)
            - 95pct: 95th percentile terminal capital (upside tail)
            - max_drawdown_risk: Fraction of paths where capital falls below 50% of initial

    Example:
        >>> from src.utils.strategy_presets import get_preset
        >>> strategy = get_preset("daily_3pct_grind")
        >>> result = monte_carlo_returns(strategy, 10000, 0.02, simulations=1000, seed=42)
        >>> print(f"Median outcome: ${result['median']:.0f}")
        Median outcome: $10482
        >>> print(f"Downside (5th %ile): ${result['5pct']:.0f}")
        Downside (5th %ile): $9234
        >>> print(f"Risk of halving: {result['max_drawdown_risk']*100:.1f}%")
        Risk of halving: 0.0%

    Performance:
        5000 simulations × 220 trades completes in ~1-2 seconds.
        For faster results, reduce simulations to 1000-2000 (accuracy ±0.5%).
    """
    if seed is not None:
        random.seed(seed)

    logger.debug(
        f"Running Monte Carlo: {simulations} sims, {strategy.trades_per_year} trades/year, "
        f"initial capital ${initial_capital:.0f}, risk fraction {risk_fraction*100:.1f}%"
    )

    terminal_capitals = []
    ruin_threshold = initial_capital * 0.5
    ruin_count = 0

    for sim_idx in range(simulations):
        capital = initial_capital
        min_capital = capital  # Track minimum for max drawdown

        for trade_idx in range(strategy.trades_per_year):
            # Bet size is fraction of current capital
            bet = capital * risk_fraction

            # Simulate win or loss
            if random.random() < strategy.win_rate:
                # Win
                capital += bet * strategy.avg_win
            else:
                # Loss
                capital -= bet * strategy.avg_loss

            # Clamp to non-negative
            capital = max(capital, 0.0)

            # Track minimum for drawdown
            min_capital = min(min_capital, capital)

            # Early exit if ruined
            if capital == 0:
                break

        terminal_capitals.append(capital)

        # Check if this path fell below 50% at any point
        if min_capital < ruin_threshold:
            ruin_count += 1

    # Sort for percentile calculations
    terminal_capitals.sort()

    # Calculate statistics
    n = len(terminal_capitals)
    median = terminal_capitals[n // 2]
    mean = sum(terminal_capitals) / n
    pct_5 = terminal_capitals[int(n * 0.05)]
    pct_95 = terminal_capitals[int(n * 0.95)]
    max_drawdown_risk = ruin_count / simulations

    result = {
        "median": median,
        "mean": mean,
        "5pct": pct_5,
        "95pct": pct_95,
        "max_drawdown_risk": max_drawdown_risk,
    }

    logger.debug(
        f"Monte Carlo results: median=${median:.0f}, mean=${mean:.0f}, "
        f"5th %ile=${pct_5:.0f}, 95th %ile=${pct_95:.0f}, "
        f"max drawdown risk={max_drawdown_risk*100:.1f}%"
    )

    return result
