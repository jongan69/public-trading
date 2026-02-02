---
id: REQ-021
title: Smart hybrid allocation (core vs opportunistic)
status: pending
created_at: 2025-02-02T00:00:00Z
user_request: UR-002
---

# Smart Hybrid Allocation (Core vs Opportunistic)

## What

Implement **smart hybrid allocation**: split portfolio value into **core** and **opportunistic** buckets (e.g. 75% core / 25% opportunistic), each sized with its own strategy profile and Kelly fraction, and run **Monte Carlo** for each bucket. Expose a single combined view (allocation + core/opportunistic MC results) for the AI and user.

## Detailed Requirements

- **smart_hybrid_allocation(portfolio_value, core_pct=0.75):** Return `core_capital`, `opportunistic_capital` (dollars). Configurable `core_pct` via env or config.
- **apply_smart_hybrid(portfolio, core_strategy, opportunistic_strategy):**
  - Compute total portfolio value; get allocation from smart_hybrid_allocation.
  - For core: compute Kelly for core_strategy; run monte_carlo_returns(core_strategy, core_capital, core_kelly).
  - For opportunistic: compute Kelly for opportunistic_strategy; optionally throttle (e.g. opp_kelly * 0.5); run monte_carlo_returns(opportunistic_strategy, opportunistic_capital, throttled_kelly).
  - Return combined result: portfolio_value, allocation dict, core (strategy name, kelly_fraction, monte_carlo dict), opportunistic (strategy name, kelly_fraction, monte_carlo dict).
- **Presets:** Allow default core = "High Conviction", opportunistic = "Daily 3% Grind" (or configurable).
- **AI exposure:** Tool (e.g. "get_smart_hybrid" or "apply_smart_hybrid") so the AI can summarize "75% core ($X) with strategy A, 25% opportunistic ($Y) with strategy B; core median outcome $Z, opportunistic median $W."

## Constraints

- Depends on StrategyProfile and monte_carlo_returns (REQ-019, REQ-020). Advisory only; no automatic rebalancing into core/opportunistic unless explicitly tied to execution later.
- If current bot uses theme_a/b/c/moonshot, smart hybrid can sit alongside as an alternative view or optional allocation mode.

## Dependencies

- REQ-019 (StrategyProfile, kelly_fraction), REQ-020 (monte_carlo_returns), portfolio (total value), config, telegram_bot.

---
*Source: Example code – smart_hybrid_allocation(), apply_smart_hybrid()*
