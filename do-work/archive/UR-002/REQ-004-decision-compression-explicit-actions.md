---
id: REQ-004
title: Decision compression and explicit actions
status: completed
created_at: 2025-02-02T00:00:00Z
user_request: UR-002
completed_at: 2025-02-02T00:00:00Z
route: B
---

# Decision Compression and Explicit Actions

## What

Ensure strategy and chat output explicit, numbered actions with no ambiguity. Examples: "Hold 90–110 warrants", "Trim moonshot to 25%", "Roll if cost < 35% of option value", "Exit if drawdown > 40%". No vibes—just numbers.

## Detailed Requirements

- run_daily_logic_preview output: include one-line rationale per order (e.g. "Trim moonshot: current 32%, cap 30%" or "Roll UMC call: DTE 55 < 60"). If no orders: "No actions: portfolio within targets and rules."
- SYSTEM_PROMPT: reinforce that recommendations must be concrete (ranges, percentages, conditions). Examples in prompt: "Hold X–Y", "Trim to Z%", "Roll if ...", "Exit if ...".
- Optional: add a "recommendation format" section in get_portfolio_analysis or a dedicated tool that returns current suggested actions (hold/trim/roll/exit) with numbers, so the AI can cite them.

## Implementation Summary

- **strategy.py**: Added `rationale` to every order dict:
  - process_positions: Take profit → "Take profit: +X% (close all)" or "(close N)"; Stop loss → "Stop loss: pnl X%, DTE=N"; Roll close → "Roll: UNDERLYING DTE=N < 60 (close)"; Roll open → "Roll: UNDERLYING (open new)".
  - rebalance: BUY → "Rebalance: theme_X below target (add UNDERLYING)"; SELL reduce → "Rebalance: theme_X above target (reduce)".
  - check_moonshot_trim: "Trim moonshot: current X%, cap Y%".
- **telegram_bot run_daily_logic_preview**: Output format changed to numbered lines with rationale per order: "1. BUY symbol x qty @ $price — rationale". If no orders: "No actions: portfolio within targets and rules."
- **SYSTEM_PROMPT**: Already had decision compression examples (Hold X–Y, Trim to Z%, Exit if ...) from earlier REQ-006/004 prompt work.

## Testing

- python3 -m pytest tests/ -q: 81 passed. No linter errors.

---
*Source: UR-002 – full bot completion*
