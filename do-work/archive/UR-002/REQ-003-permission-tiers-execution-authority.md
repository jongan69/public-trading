---
id: REQ-003
title: Permission tiers and execution authority
status: completed
created_at: 2025-02-02T00:00:00Z
user_request: UR-002
completed_at: 2025-02-02T00:00:00Z
route: A
---

# Permission Tiers and Execution Authority

## What

Implement a permission model: Tier 1 (read_only = no trades), Tier 2 (managed = current behavior). Human can set EXECUTION_TIER=read_only to pause trading.

## Implementation Summary

- **config**: Added `execution_tier` (default "managed"); env EXECUTION_TIER.
- **telegram_bot run_tool**: Before run_daily_logic_and_execute and place_manual_trade, if config.execution_tier.lower() == "read_only", return "Trading paused; read-only mode. Set EXECUTION_TIER=managed in .env to allow trades."
- **get_config**: Now includes execution_tier and governance params (max_single_position_pct, max_correlated_pct).
- **.env.example**: Added EXECUTION_TIER=managed.
- Emergency tier (liquidate/freeze) stubbed for future.

---
*Source: UR-002 – full bot completion*
