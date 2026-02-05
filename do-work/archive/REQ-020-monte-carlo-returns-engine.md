---
id: REQ-020
title: Monte Carlo returns engine
status: pending
created_at: 2025-02-02T00:00:00Z
user_request: UR-002
---

# Monte Carlo Returns Engine

## What

Add a **Monte Carlo simulation** that, given a strategy profile (win rate, avg win/loss, trades per year), initial capital, and risk fraction per trade, runs many paths and returns **median**, **mean**, **5th and 95th percentile** outcomes, and **max drawdown risk** (e.g. fraction of paths where capital falls below 50% of initial).

## Detailed Requirements

- **monte_carlo_returns(strategy, initial_capital, risk_fraction, simulations=5000):**
  - For each simulation: run `trades_per_year` steps; each step bet `capital * risk_fraction`; with probability `win_rate` add `bet * avg_win`, else subtract `bet * avg_loss`; clamp capital to ≥ 0.
  - Aggregate across simulations: median and mean terminal capital; 5th and 95th percentile (sorted results); `max_drawdown_risk` = fraction of paths where terminal capital < initial_capital * 0.5.
  - Return dict: `median`, `mean`, `5pct`, `95pct`, `max_drawdown_risk`.
- **Strategy input:** Accept StrategyProfile (or equivalent) with `win_rate`, `avg_win`, `avg_loss`, `trades_per_year`.
- **Determinism:** Use configurable or fixed seed for tests; production may use random.
- **AI exposure:** Expose via tool (e.g. "monte_carlo_returns" or as part of "compare_strategies") so the AI can report "Under this strategy, median outcome is $X, 5% tail is $Y, and risk of halving capital is Z%."

## Constraints

- No side effects; read-only simulation. Performance: 5000 simulations × 220 trades should complete in reasonable time (e.g. < 5s); optimize if needed (vectorization or fewer trials with disclaimer).

## Dependencies

- StrategyProfile (REQ-019), new module (e.g. `src/utils/monte_carlo.py` or under `src/risk.py`), telegram_bot for tool exposure.

---
*Source: Example code – monte_carlo_returns()*
