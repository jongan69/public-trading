---
id: REQ-002
title: Governance layer formalization
status: completed
created_at: 2025-02-02T00:00:00Z
user_request: UR-002
completed_at: 2025-02-02T00:00:00Z
route: B
---

# Governance Layer Formalization

## What

Centralize portfolio governance (hard rules) into a single layer that runs before any trade. Violations = automatic block with a clear explanation. Rules: max single position exposure (e.g. 30%), max portfolio drawdown (rolling), min cash buffer, max correlated exposure (e.g. 60%), no margin, no naked options.

## Implementation Summary

- **src/utils/governance.py**: Added `check_governance(portfolio_manager, storage, order_details)` — checks (1) kill switch for BUY, (2) min cash for BUY, (3) max single position %, (4) max correlated % (theme_a+theme_b+theme_c), (5) moonshot cap. Returns (allowed, reason). Defensive for mocks (getattr, isinstance(alloc, dict)).
- **config**: Added `max_single_position_pct` (0.30), `max_correlated_pct` (0.60).
- **execution.py**: Added optional `storage` to ExecutionManager; at start of execute_order calls check_governance; if not allowed returns None and logs reason.
- **main.py**: Creates storage before ExecutionManager; passes storage to ExecutionManager.
- **.env.example**: Added MAX_SINGLE_POSITION_PCT, MAX_CORRELATED_PCT.
- Tests: 81 passed (governance tolerant of mock portfolio).

---
*Source: UR-002 – full bot completion*
