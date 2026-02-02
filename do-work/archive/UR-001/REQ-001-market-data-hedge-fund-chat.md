---
id: REQ-001
title: Market data analysis chat – professional hedge fund manager for portfolio
status: completed
completed_at: 2025-02-02T00:00:00Z
created_at: 2025-02-02T00:00:00Z
user_request: UR-001
claimed_at: 2025-02-02T00:00:00Z
route: C
---

# Market Data Analysis Chat – Professional Hedge Fund Manager for Portfolio

## What

Build a **market data analysis chat** that behaves like a **professional hedge fund manager** for this portfolio. The chat should fully capture every aspect of the portfolio, deliver actionable recommendations, and provide tools for data retrieval and processing. Use Claude (or the existing AI stack) as needed to expand the bot so it is comprehensive and professional-grade.

## Detailed Requirements

- **Persona & behavior**: The bot should act as a professional hedge fund manager in conversation—synthesizing portfolio, market data, and risk in one place; giving clear, actionable recommendations; and explaining rationale in concise, institutional language where appropriate.
- **Portfolio coverage**: Expose and discuss every material aspect of the portfolio:
  - Current positions (equity + options), quantities, entry prices, current prices, P&amp;L ($ and %), market value, allocation vs target.
  - Cash, equity curve, drawdown vs high-water mark (if available).
  - Theme vs moonshot vs cash breakdown; drift from targets; kill switch / guardrail state.
  - Option-specific: DTE, strike vs spot, delta/Gamma/IV if available; roll/trim rules and whether any position is near a rule trigger.
- **Recommendations**: Provide concrete, professional-grade recommendations:
  - Rebalance actions (what to buy/sell/roll and why).
  - Risk adjustments (e.g. trim moonshot if over cap, add cash, adjust themes).
  - Optional trade ideas tied to news/Polymarket/options chain (with clear data source and limit-price guidance).
  - When to act now vs wait (e.g. "wait for expiration" or "act before earnings").
- **Data retrieval and processing**: Ensure the bot has (or gets) tools for:
  - Real-time or cached quotes, option chains, Greeks, expirations (existing + any gaps).
  - News and macro context (existing market news).
  - Prediction markets / Polymarket (existing).
  - Portfolio and allocation snapshots (existing).
  - Any additional data needed for "perfect" analysis (e.g. historical performance, correlation, sector exposure, volatility regime)—add tools or stubs as needed so the chat can offer institutional-quality context.
- **Chat experience**: Single conversational interface (Telegram) where the user can ask for "full portfolio analysis", "recommendations", "what should I do", "deep research on X", and get a synthesized answer that ties portfolio + market data + recommendations. Use Claude/AI to expand prompts and tool usage so the bot proactively gathers multiple data sources and weaves them into one response where appropriate.

## Constraints

- Must integrate with existing codebase: `src/telegram_bot.py`, `src/portfolio.py`, `src/market_data.py`, `src/strategy.py`, `src/execution.py`, and config.
- Preserve existing behavior: manual trades, rebalance preview/execute, config edits, dry run, etc.
- Keep Telegram as the primary interface; format replies for Telegram (no markdown tables, use bullets and short paragraphs).

## Dependencies

- Existing tools: get_portfolio, get_allocations, get_market_news, get_options_chain, get_option_expirations, get_polymarket_odds, get_config, run_daily_logic_*, place_manual_trade, update_*.
- May need new or extended tools for: drawdown/HWM, Greeks summary, roll/trim triggers, historical performance, or sector/vol context—explore during implementation.

## Assets

None.

---
*Source: [user request – kick off do work loop for perfect market data analysis chat, professional hedge fund manager for portfolio, expand bot to capture every aspect of portfolio and recommendations and tools for data retrieval and processing]*

---

## Triage

**Route: C** - Complex

**Reasoning:** New feature spanning multiple systems (persona, portfolio depth, new tools, recommendations flow). Requires planning, exploration, and phased implementation.

**Planning:** Required

---

## Plan

1. **New tool: get_portfolio_analysis** — Return equity, high-water mark (from storage), drawdown %, kill switch status/threshold. Persist current equity to history when called so HWM is up to date. Expose so the AI can describe "equity curve" and risk state.
2. **Enhance get_portfolio** — For each position: keep existing fields; for options add DTE, strike, spot (underlying price), strike_vs_spot_pct; add flags: near_roll (DTE &lt; roll_trigger_dte), trim_candidate (moonshot position when moonshot allocation &gt; moonshot_max). Use existing portfolio_manager and config.
3. **TOOLS + run_tool** — Register get_portfolio_analysis in TOOLS with description; implement in run_tool using bot_instance.storage and config.
4. **SYSTEM_PROMPT** — Rewrite persona to "professional hedge fund manager": synthesize portfolio + risk + allocations; give clear, actionable recommendations with rationale; for "full portfolio analysis", "recommendations", "what should I do" instruct the model to call get_portfolio (enhanced), get_allocations, get_config, get_portfolio_analysis, and optionally run_daily_logic_preview + get_market_news/get_options_chain/get_polymarket_odds, then synthesize one response with sections (Portfolio &amp; Risk, Allocations, Recommendations, Optional trade context). Keep Telegram formatting rules and option-trade accuracy rules.
5. **Keyboard / suggestions** — Optionally add "Full analysis" and "Recommendations" to START_KEYBOARD or leave to natural language.

Implementation order: (2) enhance get_portfolio, (1) get_portfolio_analysis tool, (3) TOOLS + run_tool, (4) SYSTEM_PROMPT.

---

## Implementation Summary

- **get_portfolio (enhanced):** Per-position detail for options: DTE, strike_vs_spot %, and flags `near_roll` (DTE < roll_trigger_dte), `trim_candidate` (moonshot position when moonshot allocation > moonshot_max). Uses portfolio_manager.get_position_price, position.get_dte(), data_manager.get_quote(underlying), config.roll_trigger_dte, config.moonshot_max.
- **get_portfolio_analysis (new tool):** Returns equity, high-water mark (from storage.get_equity_high_last_n_days), drawdown %, kill switch status and threshold. Saves current equity to storage when called so HWM is up to date. Registered in TOOLS and implemented in run_tool.
- **SYSTEM_PROMPT:** Rewritten to professional hedge fund manager persona. Explicit flow for "full portfolio analysis" / "recommendations": call get_portfolio, get_allocations, get_config, get_portfolio_analysis; optionally run_daily_logic_preview, get_market_news, get_options_chain, get_polymarket_odds; synthesize with sections Portfolio & Risk, Allocations, Positions, Recommendations. Clear guidance for actionable recommendations (trim, roll, wait, rebalance) and option-trade accuracy preserved.
- **START_KEYBOARD:** Added "Full analysis" and "Recommendations" as first row for one-tap hedge-fund flow.

## Testing

- Ran `python3 -m pytest tests/ -q`: 81 passed. No regressions. No linter errors on src/telegram_bot.py.
