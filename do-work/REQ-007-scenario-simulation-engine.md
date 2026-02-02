---
id: REQ-007
title: Scenario and simulation engine
status: pending
created_at: 2025-02-02T00:00:00Z
user_request: UR-002
---

# Scenario and Simulation Engine

## What

Add a scenario/simulation layer so the AI can answer "How much should I hold?" with numbers. Capabilities: price ladders (e.g. underlying @ $30 / $60 / $100), option payoff at expiry, time-decay intuition, worst-case/best-case capital impact. Outputs: probability-weighted outcomes or simple ranges, expected value ranges, capital impact per scenario.

## Detailed Requirements

- New module or functions: e.g. scenario.py or under market_data. (1) Price ladder: given a symbol and a list of prices, return option value or position value at each price (using current positions + optional hypothetical). (2) Payoff at expiry: for an option, value at expiry for a range of underlying prices. (3) Time decay: optional simple theta-style decay for near-term options. Use existing quotes and option chain data; no external pricing model required for v1 (can use intrinsic + rough approximation).
- Expose via Telegram tool: e.g. get_scenario(symbol, prices[]) or what_if_position(symbol, quantity, prices[]). Return text summary: "At $X: value $Y; at $Z: value $W. Worst case: $A; best case: $B."
- AI uses this in "how much should I hold?" or "what if GME goes to $60?" conversations. Document in SYSTEM_PROMPT.

## Constraints

- Use existing data (quotes, chains); no new broker APIs. Approximations are acceptable for v1.

## Dependencies

- market_data.py, portfolio (position values), telegram_bot TOOLS + run_tool, config.

---
*Source: UR-002 – full bot completion*
