"""Portfolio governance: hard rules that block orders when violated."""
from typing import Dict, Optional, Tuple

from loguru import logger

from src.config import config
from src.portfolio import PortfolioManager


def check_governance(
    portfolio_manager: PortfolioManager,
    storage: Optional[object],
    order_details: Optional[Dict] = None,
) -> Tuple[bool, str]:
    """Run governance checks. Violations = block with reason.

    Args:
        portfolio_manager: Portfolio manager (current state).
        storage: StorageManager for equity history (kill switch). If None, kill switch is skipped.
        order_details: Optional order dict (action, symbol, quantity, price). If provided and action is BUY,
            checks include post-order state where applicable.

    Returns:
        (allowed, reason). allowed is False iff a hard rule is violated.
    """
    refresh = getattr(portfolio_manager, "refresh_portfolio", None)
    if refresh:
        refresh()
    equity = portfolio_manager.get_equity()
    if equity <= 0:
        return True, ""

    # 1. Kill switch: block new positions (BUY) if drawdown exceeds threshold
    action = (order_details or {}).get("action")
    if action == "BUY" and storage is not None:
        try:
            storage.save_equity_history(equity)
            high_equity = storage.get_equity_high_last_n_days(config.kill_switch_lookback_days)
            if high_equity is not None and high_equity > 0:
                drawdown_pct = (equity - high_equity) / high_equity
                if drawdown_pct <= -config.kill_switch_drawdown_pct:
                    return False, (
                        f"Blocked: kill switch active (drawdown {drawdown_pct*100:.1f}% vs "
                        f"{config.kill_switch_drawdown_pct*100:.0f}% threshold). No new positions."
                    )
        except Exception as e:
            logger.warning(f"Governance kill-switch check failed: {e}")

    # 2. Min cash buffer: block BUY when cash would go below minimum (execution also checks per-order)
    if action == "BUY":
        cash = portfolio_manager.get_cash()
        min_cash = equity * config.cash_minimum
        if cash < min_cash - 0.01:
            return False, (
                f"Blocked: cash ${cash:,.2f} below minimum ${min_cash:,.2f} "
                f"({config.cash_minimum*100:.0f}% of equity). No new buys."
            )

    # 3. Max single position: no position > equity * max_single_position_pct
    positions = getattr(portfolio_manager, "positions", None) or {}
    max_single_pct = config.max_single_position_pct
    get_position_price = getattr(portfolio_manager, "get_position_price", None)
    for sym, pos in positions.items():
        if get_position_price and hasattr(pos, "get_market_value"):
            price = get_position_price(pos)
            mv = pos.get_market_value(price)
            pct = mv / equity if equity else 0
            if pct > max_single_pct:
                return False, (
                    f"Blocked: position {sym} is {pct*100:.1f}% of equity "
                    f"(max {max_single_pct*100:.0f}%). Trim before adding."
                )

    # 4. Max correlated exposure: theme_a + theme_b + theme_c <= max_correlated_pct
    max_correlated_pct = config.max_correlated_pct
    get_alloc = getattr(portfolio_manager, "get_current_allocations", None)
    alloc = get_alloc() if get_alloc else {}
    if not isinstance(alloc, dict):
        alloc = {}
    correlated = alloc.get("theme_a", 0) + alloc.get("theme_b", 0) + alloc.get("theme_c", 0)
    if correlated > max_correlated_pct + 0.001:
        return False, (
            f"Blocked: correlated exposure (themes A+B+C) is {correlated*100:.1f}% "
            f"(max {max_correlated_pct*100:.0f}%)."
        )

    # 5. Moonshot cap (already enforced in strategy; redundant but explicit)
    if alloc.get("moonshot", 0) > config.moonshot_max + 0.001:
        return False, (
            f"Blocked: moonshot allocation {alloc.get('moonshot', 0)*100:.1f}% "
            f"exceeds cap {config.moonshot_max*100:.0f}%. Trim moonshot first."
        )

    return True, ""
