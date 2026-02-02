---
id: REQ-022
title: AI tools — analyze_portfolio and compare_strategies
status: pending
created_at: 2025-02-02T00:00:00Z
user_request: UR-002
---

# AI Tools: analyze_portfolio and compare_strategies

## What

Expose two **AI-facing tool entry points** matching the example workflow: (1) **analyze_portfolio** — total value and allocation (by type and/or by theme); (2) **compare_strategies** — run Monte Carlo for two preset strategies (e.g. Daily Grind vs High Conviction) at given capital and return side-by-side results so the AI can compare and recommend.

## Detailed Requirements

- **analyze_portfolio(portfolio):** Input: current portfolio (from PortfolioManager or equivalent). Output: `total_value`, `allocation` (e.g. allocation_by_type from REQ-018 and/or existing theme/moonshot allocation). Used by AI to answer "How is my portfolio allocated?"
- **compare_strategies(capital: float):** Input: capital amount (e.g. current equity or user-specified). Output: dict with keys for each preset strategy (e.g. `daily_grind`, `high_conviction`), each value = monte_carlo_returns(...) for that strategy at given capital and its Kelly fraction. AI can say "At your capital, Daily Grind median is $X with 5% tail $Y; High Conviction median is $Z; drawdown risk is A% vs B%."
- **Telegram tools:** Register both as tools in the Telegram bot (e.g. `analyze_portfolio`, `compare_strategies`) with appropriate argument parsing (compare_strategies may take optional capital, defaulting to current equity).
- **Integration:** analyze_portfolio should use allocation_by_type if REQ-018 is implemented; compare_strategies should use StrategyProfile presets and monte_carlo_returns from REQ-019/REQ-020.

## Constraints

- If REQ-018 (allocation by type) is not yet done, analyze_portfolio can return only total_value and existing theme/moonshot allocation until multi-asset is added.
- compare_strategies is read-only; no trades.

## Dependencies

- portfolio (PortfolioManager), REQ-018 (allocation_by_type), REQ-019 (StrategyProfile, kelly_fraction), REQ-020 (monte_carlo_returns), telegram_bot (tool registration).

---
*Source: Example code – analyze_portfolio(), compare_strategies()*
