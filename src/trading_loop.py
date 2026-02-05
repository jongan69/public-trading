"""Trading loop state machine: research → strategy → execute → observe → adjust.

Runs periodically to do deep market research, implement strategy, execute (if enabled),
observe outcomes, and adjust based on performance—prioritizing balance increase over time.
Chat interface remains primary; loop runs in background or on demand.
"""
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional
import threading

from loguru import logger

from src.config import config

# Prevent overlapping cycles when job returns immediately and next trigger fires
_cycle_lock = threading.Lock()


# State machine states
STATE_IDLE = "idle"
STATE_RESEARCH = "research"
STATE_STRATEGY_PREVIEW = "strategy_preview"
STATE_EXECUTE = "execute"
STATE_OBSERVE = "observe"
STATE_ADJUST = "adjust"


def _set_state(storage: Any, state: str) -> None:
    """Persist current loop state."""
    try:
        storage.set_bot_state("trading_loop_state", state)
    except Exception as e:
        logger.debug(f"Could not persist trading_loop_state: {e}")


def _get_state(storage: Any) -> str:
    """Return current loop state from storage."""
    try:
        return storage.get_bot_state("trading_loop_state") or STATE_IDLE
    except Exception:
        return STATE_IDLE


def _store_research(storage: Any, summary: str, ideas: str = "") -> None:
    """Store research summary and trading ideas for chat/AI."""
    try:
        storage.set_bot_state("trading_loop_research_summary", summary[:8000] if summary else "")
        if ideas:
            storage.set_bot_state("trading_loop_ideas", ideas[:4000])
    except Exception as e:
        logger.debug(f"Could not store research: {e}")


def _store_outcome(storage: Any, outcome: str) -> None:
    """Store last cycle outcome."""
    try:
        storage.set_bot_state("trading_loop_last_outcome", outcome[:2000] if outcome else "")
        storage.set_bot_state("trading_loop_last_cycle_at", datetime.now(timezone.utc).isoformat())
    except Exception as e:
        logger.debug(f"Could not store outcome: {e}")


def _store_adjustments(storage: Any, suggestions: str) -> None:
    """Store suggested adjustments (e.g. reduce moonshot after drawdown)."""
    try:
        storage.set_bot_state("trading_loop_suggested_adjustments", suggestions[:2000] if suggestions else "")
    except Exception as e:
        logger.debug(f"Could not store adjustments: {e}")


def run_research(bot: Any) -> Dict[str, Any]:
    """Phase 1: Deep market research—portfolio, balance trend, news, alerts.

    Args:
        bot: TradingBot instance (main.TradingBot) with portfolio_manager, storage.

    Returns:
        Dict with research_summary (str), ideas (str), equity, drawdown_pct, alerts_count.
    """
    logger.info("Trading loop: RESEARCH — portfolio, balance trend, news, alerts")
    _set_state(bot.storage, STATE_RESEARCH)
    bot.portfolio_manager.refresh_portfolio()
    pm = bot.portfolio_manager
    equity = pm.get_equity()
    cash = pm.get_cash()
    bp = pm.get_buying_power()
    allocations = pm.get_current_allocations()

    bot.storage.save_equity_history(equity)
    bot.storage.save_portfolio_snapshot({
        "equity": equity,
        "buying_power": bp,
        "cash": cash,
        "allocations": allocations,
    })

    high_equity = bot.storage.get_equity_high_last_n_days(config.kill_switch_lookback_days)
    drawdown_pct = (equity - high_equity) / high_equity if high_equity and high_equity > 0 else 0.0

    trends = bot.storage.get_balance_trends(days=7, max_points=50)
    trend_7d = ""
    if len(trends) >= 2:
        eq_old = trends[-1].get("equity")
        eq_new = trends[0].get("equity")
        if eq_old and eq_new and eq_old > 0:
            chg = (eq_new - eq_old) / eq_old * 100
            trend_7d = f"7d balance trend: {chg:+.1f}% (${eq_old:,.0f} → ${eq_new:,.0f})"
    # Include last snapshot config for learning (correlate config with outcomes)
    last_config_line = ""
    if trends:
        cfg = trends[0].get("config") or {}
        if isinstance(cfg, dict) and cfg:
            ta = cfg.get("theme_a_target")
            tb = cfg.get("theme_b_target")
            ms = cfg.get("moonshot_target")
            if ta is not None and tb is not None and ms is not None:
                last_config_line = (
                    f"Last snapshot config: theme_a={ta*100:.0f}% theme_b={tb*100:.0f}% "
                    f"moonshot={ms*100:.0f}% (use get_balance_trends for full history)"
                )

    # Market news for SPY and theme underlyings
    news_lines: List[str] = []
    try:
        import yfinance as yf
        symbols = ["SPY"] + list(config.theme_underlyings)[:3]
        for sym in symbols:
            try:
                t = yf.Ticker(sym)
                news_list = getattr(t, "news", None) or []
                for n in news_list[:2]:
                    if hasattr(n, "get") and n.get("content"):
                        c = n["content"]
                        if isinstance(c, dict) and c.get("title"):
                            news_lines.append(f"  {sym}: {c['title'][:70]}...")
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"News fetch in loop: {e}")

    # Alerts
    alerts_list: List[str] = []
    if config.proactive_alerts_enabled:
        try:
            from src.alerts import AlertManager
            alert_mgr = AlertManager(bot.storage, pm)
            alerts = alert_mgr.check_all_alerts()
            for a in alerts:
                alerts_list.append(a.get("message", ""))
            if alerts:
                bot.storage.save_pending_alerts(alerts)
        except Exception as e:
            logger.debug(f"Alerts in loop: {e}")

    kill_active = drawdown_pct <= -config.kill_switch_drawdown_pct
    summary_parts = [
        f"Equity: ${equity:,.2f}  Cash: ${cash:,.2f}  BP: ${bp:,.2f}",
        f"High-water ({config.kill_switch_lookback_days}d): ${high_equity:,.2f}" if high_equity else "No HWM yet",
        f"Drawdown: {drawdown_pct*100:.2f}%  Kill switch: {'ACTIVE' if kill_active else 'inactive'}",
        trend_7d,
        f"Allocations: theme_a={allocations.get('theme_a',0)*100:.1f}% theme_b={allocations.get('theme_b',0)*100:.1f}% "
        f"moonshot={allocations.get('moonshot',0)*100:.1f}% cash={allocations.get('cash',0)*100:.1f}%",
    ]
    if news_lines:
        summary_parts.append("Recent headlines:\n" + "\n".join(news_lines[:6]))
    if alerts_list:
        summary_parts.append("Alerts: " + "; ".join(alerts_list[:3]))
    if last_config_line:
        summary_parts.append(last_config_line)

    # Optional: one-symbol fundamental snippet for research (when enabled). Throttled to once per hour.
    if getattr(config, "trading_loop_include_fundamental", False):
        theme_symbols = getattr(config, "theme_underlyings", None) or []
        if isinstance(theme_symbols, (list, tuple)) and theme_symbols:
            sym = theme_symbols[0] if theme_symbols else "SPY"
            try:
                last_ts = bot.storage.get_bot_state("trading_loop_last_fundamental_at")
                now_ts = datetime.now(timezone.utc)
                run_fundamental = True
                if last_ts:
                    try:
                        last = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                        run_fundamental = (now_ts - last).total_seconds() >= 3600  # 1 hour
                    except Exception as e:
                        logger.debug(f"Could not parse last fundamental timestamp: {e}")
                if run_fundamental:
                    from src.fundamental_analysis import FundamentalAnalysis
                    fa = FundamentalAnalysis()
                    analysis = fa.get_comprehensive_analysis(sym)
                    val = analysis.get("valuation_score") or {}
                    if isinstance(val, dict) and "valuation_score" in val:
                        score = val["valuation_score"]
                        summary_parts.append(f"Fundamental ({sym}): valuation score {score}/6 (0=overvalued, 6=undervalued)")
                    elif isinstance(val, (int, float)):
                        summary_parts.append(f"Fundamental ({sym}): valuation score {val}/6")
                    bot.storage.set_bot_state("trading_loop_last_fundamental_at", now_ts.isoformat())
            except Exception as e:
                logger.debug(f"Loop fundamental for {sym}: {e}")

    research_summary = "\n".join(summary_parts)
    ideas = (
        "Consider rebalance if allocations deviate from targets. "
        "Check rolls for near-DTE options. "
        "Reduce risk if drawdown > 15%."
    )
    _store_research(bot.storage, research_summary, ideas)
    headline_count = len(news_lines) if news_lines else 0
    hwm_str = f" HWM=${high_equity:,.0f}" if high_equity else ""
    logger.info(
        f"Trading loop: RESEARCH done — equity=${equity:,.0f} drawdown={drawdown_pct*100:.1f}%{hwm_str} "
        f"headlines={headline_count} alerts={len(alerts_list)}"
    )

    return {
        "research_summary": research_summary,
        "ideas": ideas,
        "equity": equity,
        "drawdown_pct": drawdown_pct,
        "alerts_count": len(alerts_list),
    }


def run_strategy_preview(bot: Any) -> Dict[str, Any]:
    """Phase 2: Run strategy in dry-run; no orders executed.

    Returns:
        Dict with order_count, order_summary (str).
    """
    logger.info("Trading loop: STRATEGY_PREVIEW — dry-run rebalance")
    _set_state(bot.storage, STATE_STRATEGY_PREVIEW)
    old_dry = config.dry_run
    config.dry_run = True
    orders: List[Dict[str, Any]] = []
    try:
        orders = bot.strategy.run_daily_logic()
    finally:
        config.dry_run = old_dry

    summary_lines = []
    for o in orders[:10]:
        action = o.get("action", "")
        symbol = o.get("symbol", "")
        qty = o.get("quantity", 0)
        price = o.get("price", 0)
        summary_lines.append(f"  {action} {qty} {symbol} @ ${price:.2f}")
    order_summary = "\n".join(summary_lines) if summary_lines else "No orders."
    logger.info(f"Trading loop: STRATEGY_PREVIEW done — orders_planned={len(orders)}")

    return {
        "order_count": len(orders),
        "order_summary": order_summary,
        "orders": orders,
    }


def run_execute(bot: Any, execute_trades: bool) -> Dict[str, Any]:
    """Phase 3: Execute strategy (if execute_trades and not dry_run).

    Uses bot.run_daily_logic(quiet=True) with short poll timeout so unfilled orders do not block the loop.
    Returns orders_planned, orders_skipped, orders_sent for accurate cycle summary.
    """
    logger.info("Trading loop: EXECUTE — " + ("running" if (execute_trades and not config.dry_run) else "skipped (dry_run or disabled)"))
    _set_state(bot.storage, STATE_EXECUTE)
    if not execute_trades or config.dry_run:
        return {"executed": False, "reason": "dry_run or loop execute disabled", "orders_planned": 0, "orders_skipped": 0, "orders_sent": 0}

    try:
        poll_timeout = getattr(config, "order_poll_timeout_loop_seconds", 30)
        run_result = bot.run_daily_logic(poll_timeout_seconds=poll_timeout, quiet=True)
        return {
            "executed": True,
            "orders_planned": run_result.get("orders_planned", 0),
            "orders_skipped": run_result.get("orders_skipped", 0),
            "orders_sent": run_result.get("orders_sent", 0),
        }
    except Exception as e:
        logger.exception("Trading loop execute failed")
        return {"executed": False, "error": str(e), "orders_planned": 0, "orders_skipped": 0, "orders_sent": 0}


def run_observe(bot: Any) -> Dict[str, Any]:
    """Phase 4: Observe outcomes—performance summary, balance trend.

    Returns:
        Dict with outcome_summary (str), equity, balance_trend_7d.
    """
    logger.info("Trading loop: OBSERVE — performance, balance trend")
    _set_state(bot.storage, STATE_OBSERVE)
    pm = bot.portfolio_manager
    equity = pm.get_equity()
    trends = bot.storage.get_balance_trends(days=7, max_points=50)
    trend_str = ""
    if len(trends) >= 2:
        eq_old = trends[-1].get("equity")
        eq_new = trends[0].get("equity")
        if eq_old and eq_new and eq_old > 0:
            chg = (eq_new - eq_old) / eq_old * 100
            trend_str = f"7d: ${eq_old:,.0f} → ${eq_new:,.0f} ({chg:+.1f}%)"

    perf = ""
    try:
        from src.analytics import PerformanceAnalytics
        analytics = PerformanceAnalytics(bot.storage)
        perf = analytics.get_performance_summary(days=14)
        if len(perf) > 500:
            perf = perf[:500] + "\n..."
    except Exception as e:
        logger.debug(f"Performance summary in loop: {e}")

    outcome_parts = [f"Equity: ${equity:,.2f}", trend_str]
    if perf:
        outcome_parts.append(perf)
    outcome_summary = "\n".join(outcome_parts)
    _store_outcome(bot.storage, outcome_summary)

    return {
        "outcome_summary": outcome_summary,
        "equity": equity,
        "balance_trend_7d": trend_str,
    }


def run_adjust(bot: Any, research: Dict[str, Any], observe: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 5: Suggest adjustments based on performance—prioritize balance increase.

    Rule-based: e.g. if drawdown > 15%, suggest reducing moonshot; if trend negative, suggest caution.
    When trading_loop_apply_adjustments is True, applies safe config changes (reduce moonshot on drawdown).
    """
    logger.info("Trading loop: ADJUST — suggestions, optional config apply")
    _set_state(bot.storage, STATE_ADJUST)
    suggestions = []
    drawdown_pct = research.get("drawdown_pct") or 0
    trend_str = observe.get("balance_trend_7d", "")
    applied_changes: List[str] = []

    if drawdown_pct <= -0.15:
        suggestions.append(
            "Drawdown > 15%: consider reducing moonshot target (e.g. 20% → 15%) or increasing cash until recovery."
        )
    if drawdown_pct <= -0.20:
        suggestions.append("Drawdown > 20%: avoid new speculative positions; focus on rolls and trims.")
    if trend_str and "(-" in trend_str:
        suggestions.append("Balance trend negative over 7d: consider tightening risk or pausing new buys.")
    if not suggestions:
        suggestions.append("No automatic adjustments suggested; strategy parameters unchanged.")

    # Optionally apply safe config changes (only tighten risk, never loosen).
    # Apply at most once per drawdown episode: reduce when crossing -15%, then do not reduce again until recovery (drawdown > -12%).
    apply_enabled = getattr(config, "trading_loop_apply_adjustments", False)
    if apply_enabled and drawdown_pct <= -0.15:
        try:
            already_reduced = bot.storage.get_bot_state("trading_loop_drawdown_reduced") == "true"
            if not already_reduced:
                from src.utils.config_override_manager import ConfigOverrideManager
                current_moonshot = getattr(config, "moonshot_target", 0.20)
                new_moonshot = max(0.10, current_moonshot - 0.05)
                if new_moonshot < current_moonshot:
                    ConfigOverrideManager.save_override("moonshot_target", new_moonshot)
                    setattr(config, "moonshot_target", new_moonshot)
                    bot.storage.set_bot_state("trading_loop_drawdown_reduced", "true")
                    applied_changes.append(f"moonshot_target {current_moonshot*100:.0f}% → {new_moonshot*100:.0f}%")
                    suggestions.append(f"[APPLIED] Reduced moonshot target to {new_moonshot*100:.0f}% (drawdown > 15%).")
        except Exception as e:
            logger.warning(f"Loop apply_adjustments failed: {e}")
    # Clear "reduced" flag when recovered so we can reduce again if drawdown returns
    if drawdown_pct > -0.12:
        try:
            if bot.storage.get_bot_state("trading_loop_drawdown_reduced") == "true":
                bot.storage.set_bot_state("trading_loop_drawdown_reduced", "false")
        except Exception as e:
            logger.debug(f"Could not reset drawdown_reduced flag: {e}")

    suggestions_text = " ".join(suggestions)
    _store_adjustments(bot.storage, suggestions_text)
    _set_state(bot.storage, STATE_IDLE)

    return {
        "suggestions": suggestions_text,
        "applied": len(applied_changes) > 0,
        "applied_changes": applied_changes,
    }


def run_cycle(
    bot: Any,
    execute_trades: bool = False,
) -> Dict[str, Any]:
    """Run one full cycle: RESEARCH → STRATEGY_PREVIEW → (EXECUTE if enabled) → OBSERVE → ADJUST.

    Only one cycle runs at a time; if a cycle is already running, returns immediately with skipped=True.

    Args:
        bot: TradingBot instance.
        execute_trades: If True and not config.dry_run, run_daily_logic() will execute real orders.

    Returns:
        Summary dict for chat/Telegram: state, research_summary, order_count, executed, outcome, adjustments.
    """
    summary = {
        "state": STATE_IDLE,
        "research_summary": "",
        "order_count": 0,
        "executed": False,
        "outcome": "",
        "adjustments": "",
        "adjustments_applied": [],
        "error": None,
        "skipped": False,
    }

    if not _cycle_lock.acquire(blocking=False):
        logger.info("Trading loop: cycle skipped — previous cycle still running")
        summary["skipped"] = True
        summary["outcome"] = "Previous cycle still running; next run will start when ready."
        return summary

    logger.info("Trading loop: cycle START — research → strategy_preview → execute → observe → adjust")
    try:
        research = run_research(bot)
        summary["research_summary"] = research.get("research_summary", "")[:500]

        preview = run_strategy_preview(bot)
        summary["order_count"] = preview.get("order_count", 0)

        exec_result = run_execute(bot, execute_trades=execute_trades)
        summary["executed"] = exec_result.get("executed", False)
        summary["orders_planned"] = exec_result.get("orders_planned", 0)
        summary["orders_skipped"] = exec_result.get("orders_skipped", 0)
        summary["orders_sent"] = exec_result.get("orders_sent", 0)

        observe = run_observe(bot)
        summary["outcome"] = observe.get("outcome_summary", "")[:500]

        adjust_result = run_adjust(bot, research, observe)
        summary["adjustments"] = adjust_result.get("suggestions", "")
        summary["adjustments_applied"] = adjust_result.get("applied_changes") or []

    except Exception as e:
        logger.exception("Trading loop cycle failed")
        summary["error"] = str(e)
        _set_state(bot.storage, STATE_IDLE)
    finally:
        _cycle_lock.release()

    applied = summary.get("adjustments_applied") or []
    orders_planned = summary.get("orders_planned", summary.get("order_count", 0))
    orders_skipped = summary.get("orders_skipped", 0)
    orders_sent = summary.get("orders_sent", 0)
    logger.info(
        f"Trading loop: cycle DONE — research=ok orders_planned={orders_planned} "
        f"orders_skipped={orders_skipped} orders_sent={orders_sent} adjustments_applied={len(applied)}"
    )
    return summary


def get_loop_status(bot: Any) -> Dict[str, Any]:
    """Return current loop state and last cycle info for chat/AI."""
    state = _get_state(bot.storage)
    last_cycle = bot.storage.get_bot_state("trading_loop_last_cycle_at")
    last_outcome = bot.storage.get_bot_state("trading_loop_last_outcome") or ""
    research = bot.storage.get_bot_state("trading_loop_research_summary") or ""
    ideas = bot.storage.get_bot_state("trading_loop_ideas") or ""
    adjustments = bot.storage.get_bot_state("trading_loop_suggested_adjustments") or ""

    return {
        "state": state,
        "last_cycle_at": last_cycle,
        "last_outcome": last_outcome[:600],
        "research_summary": research[:600],
        "ideas": ideas[:400],
        "suggested_adjustments": adjustments[:400],
    }
