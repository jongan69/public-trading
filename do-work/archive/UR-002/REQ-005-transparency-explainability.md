---
id: REQ-005
title: Transparency and explainability
status: completed
created_at: 2025-02-02T00:00:00Z
claimed_at: 2025-02-02T00:00:00Z
completed_at: 2025-02-02T00:00:00Z
user_request: UR-002
route: A
---

# Transparency and Explainability

## What

Every trade (or suggested trade) must be explainable: why entered, what scenario it targets, what invalidates it, when it will be trimmed or rolled. Log and expose in chat.

## Detailed Requirements

- When strategy produces orders (run_daily_logic or preview), attach a short rationale per order: e.g. "Rebalance: theme_a below target", "Roll: DTE < 60", "Trim moonshot: over 30% cap", "Take profit: +100%". Store in order payload or return structure.
- Expose in run_daily_logic_preview output so the AI (and user) sees rationale alongside each order. Optionally: get_last_actions or get_rationale tool that returns last N executed/suggested actions with rationale (from storage or in-memory).
- Log rationale in storage when order is executed (e.g. in save_order or a new field). No new tables required if we extend existing order log with a rationale string.

## Constraints

- Minimal schema change; prefer extending existing order/execution log. If storage does not support rationale, append to preflight/order result and show in Telegram only.

## Dependencies

- strategy.py (attach rationale to order dict), execution.py, storage (optional rationale field), telegram_bot (preview formatting, optional get_rationale tool).

---
*Source: UR-002 – full bot completion*

---

## Triage

**Route: A** - Simple

**Reasoning:** Rationale per order and preview exposure already done in REQ-004. Only remaining work: persist rationale in storage (extend orders table) and optional get_last_actions tool. Clear scope, minimal schema change.

**Planning:** Not required

---

## Plan

**Planning not required** - Route A: Direct implementation

Rationale: Rationale per order and preview exposure already done in REQ-004. Only remaining work: extend orders table with rationale column, persist in save_order, and add get_last_actions tool.

*Skipped by work action*

---

## Implementation Summary

- **storage.py**: Added `_migrate_orders_rationale()` to add optional `rationale` column to orders table on init. Extended `save_order()` to persist `order.get("rationale")` (no new tables).
- **telegram_bot.py**: Added `get_last_actions` tool (limit param, default 10, max 50) that returns last N executed orders with symbol, side, quantity, status, created_at, and rationale from storage. When running daily logic and executing, result line now includes rationale from order_details for transparency.
- Strategy already attaches rationale per order (REQ-004); preview already shows rationale. No changes to strategy or execution.

*Completed by work action (Route A)*

---

## Testing

**Tests run:** `python3 -m pytest tests/ -q`
**Result:** ✓ All 81 tests passing

*Verified by work action*
