---
id: REQ-007
title: Scenario and simulation engine
status: completed
created_at: 2025-02-02T00:00:00Z
claimed_at: 2026-02-02T19:48:30Z
completed_at: 2026-02-02T19:51:45Z
route: B
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

---

## Triage

**Route: B** - Medium

**Reasoning:** Requires new module creation (scenario.py), multiple functions (price ladders, payoff analysis, time decay), integration with existing systems (market_data, portfolio, telegram_bot), and adding new tools. More than simple prompt changes but not requiring architectural overhaul.

## Plan

1. **Create scenario.py module** with core simulation functions
2. **Implement price ladder functionality** using existing market data
3. **Add option payoff calculation** at expiry
4. **Create time decay approximation** for theta analysis
5. **Add Telegram tool integration** (get_scenario, what_if_position)
6. **Update SYSTEM_PROMPT** to document scenario capabilities
7. **Create comprehensive tests** for scenario engine
8. **Test integration** with Telegram bot

## Implementation Summary

Successfully created comprehensive scenario and simulation engine with full Telegram integration:

### Core Implementation:
1. **src/scenario.py** - Complete scenario engine with:
   - `ScenarioEngine` class integrating with market data and portfolio managers
   - `price_ladder_analysis()` - Current position analysis at different price points
   - `option_payoff_at_expiry()` - Option payoff calculation across price ranges
   - `time_decay_analysis()` - Theta-based time decay approximation
   - `capital_impact_analysis()` - Portfolio-level impact analysis
   - OSI symbol parsing and option type detection
   - Human-readable formatting with `format_scenario_summary()`

### Telegram Integration:
2. **Enhanced telegram_bot.py** with 3 new tools:
   - `get_scenario(symbol, price_points)` - Analysis of current positions
   - `what_if_position(symbol, quantity, price_points)` - Hypothetical position modeling
   - `option_payoff_analysis(osi_symbol)` - Option payoff at expiration
   - Updated SYSTEM_PROMPT with scenario capabilities documentation

### Features Delivered:
- **Price ladders**: Analyze position values at different underlying prices
- **Option payoff at expiry**: Intrinsic value calculation across price ranges
- **Time decay intuition**: Theta-based approximation for near-term options
- **Capital impact analysis**: Worst-case/best-case portfolio impact
- **Existing data integration**: Uses current quotes, option chains, no new APIs
- **Approximations acceptable**: V1 implementation using intrinsic + rough estimates

*Completed by work action (Route B)*

## Testing

**Tests run:** pytest tests/test_scenario_engine.py -v
**Result:** ✓ All 15 tests passing

**New tests added:**
- tests/test_scenario_engine.py - comprehensive scenario engine test suite covering:
  - Price ladder analysis (basic and with options)
  - Hypothetical position analysis
  - Option payoff calculation (calls and puts)
  - Time decay analysis
  - Capital impact analysis
  - OSI symbol parsing
  - Position value calculations
  - Error handling scenarios
  - Result formatting

**All tests verified:** pytest tests/ -v shows 105 total tests passing (90 existing + 15 new)

*Verified by work action*
