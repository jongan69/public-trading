---
id: REQ-012
title: Enforce cooldown in headless execution path
status: completed
created_at: 2026-02-02T00:00:00Z
completed_at: 2026-02-02T00:15:00Z
user_request: UR-002
---

# Enforce Cooldown in Headless Execution Path

## What

Cool-down after large loss is enforced only in the Telegram flow (run_daily_logic_and_execute, place_manual_trade). When running `python run.py` (scheduled headless), trades can still be placed during the cooldown window. Enforce cooldown in the main run path so behavior is consistent.

## Detailed Requirements

- **Main path:** In `main.py` `run_daily_logic()`, before the loop that calls `execution_manager.execute_order()` for each order, check `self.storage.is_in_cooldown()`. If true, skip placing new orders (log and return or skip execution loop); optionally still allow the strategy to run and log what would have been done.
- **Execution (optional):** In `execution.py` `execute_order()`, if `self.storage` is set and `self.storage.is_in_cooldown()` is true, return None and log a clear message. This ensures any future caller (main, CLI, etc.) respects cooldown without duplicating checks.
- **Trigger in headless:** Cooldown is currently set only from Telegram after a fill (`_check_and_trigger_cooldown`). When running headless, after a fill that realizes a loss above threshold, set cooldown (e.g. in main after execution_manager.execute_order returns and order is FILLED, call the same cooldown logic or a shared helper that uses config thresholds and storage.set_cooldown_until). Reuse config (cooldown_enabled, cooldown_loss_threshold_pct, cooldown_loss_threshold_usd, cooldown_duration_minutes).

## Constraints

- Cooldown remains optional (config.cooldown_enabled). When disabled, no behavior change.

## Dependencies

- main.py, execution.py (optional), storage (existing is_in_cooldown, set_cooldown_until), config.

---
*Source: Bot Missing Features Audit plan – implementation gap 1.2*
