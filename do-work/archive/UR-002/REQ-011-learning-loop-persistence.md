---
id: REQ-011
title: Learning loop persistence (theme + realized P&L)
status: completed
created_at: 2026-02-02T00:00:00Z
completed_at: 2026-02-02T15:31:00Z
user_request: UR-002
---

# Learning Loop Persistence (Theme + Realized P&L)

## What

Fix the learning loop so P&L by theme and execution quality analytics are accurate. Storage has columns `theme`, `outcome`, `entry_price`, `realized_pnl` but strategy never tags orders with theme and `save_order` does not persist them; realized P&L is never computed on close.

## Detailed Requirements

- **Strategy:** Add a `theme` key to every order dict produced by strategy (e.g. `theme_a`, `theme_b`, `theme_c` for rebalance; `moonshot` for trim; infer from position/underlying for process_positions: take profit, stop loss, roll). Use portfolio theme mapping (theme_name, underlying) to set theme on rebalance and moonshot trim; for process_positions derive theme from position's underlying vs config theme underlyings.
- **Storage:** Extend `save_order()` to persist `theme`, `entry_price`, `realized_pnl`, `outcome` when present in the order dict. Ensure orders table has these columns (migrations already add them); include them in INSERT/REPLACE.
- **Realized P&L:** When an order is a closing trade (e.g. SELL that reduces or closes a position), compute realized P&L (e.g. from entry cost and fill price × quantity) and pass it into the payload saved to storage. Entry cost can come from order_details (e.g. position entry_price) or from existing position data; fill price from execution result. Do this in main after execution when saving order, or in execution when updating status—ensure the saved order row gets `realized_pnl` and optionally `outcome` (e.g. "win" / "loss").
- **Outcome:** Optionally set `outcome` on save (e.g. "win" if realized_pnl > 0, "loss" if < 0) for analytics.

## Constraints

- No new tables; use existing orders table and migrations. Read-only analytics remain; no strategy changes driven by this data.

## Dependencies

- strategy.py (theme on order dict), storage.py (save_order columns), main.py or execution.py (realized P&L computation and pass-through to save_order).

---
*Source: Bot Missing Features Audit plan – implementation gap 1.1*
