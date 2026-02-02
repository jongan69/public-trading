---
id: REQ-018
title: Multi-asset portfolio model and allocation by type
status: pending
created_at: 2025-02-02T00:00:00Z
user_request: UR-002
---

# Multi-Asset Portfolio Model and Allocation by Type

## What

Extend portfolio representation to support **asset types** (equity, crypto, cash) and expose **allocation by type** so the AI and user can see how capital is split across asset classes, not just theme/moonshot buckets.

## Detailed Requirements

- **Position model:** Support an `asset_type` (or equivalent) per position: `equity`, `crypto`, `cash`. Map existing equity/option positions to `equity`; add mapping for cash and, if supported by broker, crypto.
- **Portfolio aggregate:** Provide `allocation_by_type() -> Dict[str, float]` returning dollar (or percentage) allocation per asset type, e.g. `{"equity": 40000, "crypto": 30000, "cash": 30000}` or normalized to fractions of total.
- **Data source:** Use existing portfolio/positions API; derive asset type from instrument type or symbol (e.g. USDC/cash). If broker does not expose crypto separately, document limitation and optionally treat as cash or single "other" bucket.
- **AI exposure:** Expose allocation-by-type in `get_portfolio_analysis` or a dedicated tool so the AI can report "X% equity, Y% crypto, Z% cash" and make recommendations by asset class.

## Constraints

- Minimal schema change; prefer deriving asset type from existing fields. No new tables required unless storing snapshots by type.
- If crypto is not supported by Public API, support at least equity + cash and document scope.

## Dependencies

- portfolio (Position/PortfolioManager), storage (optional snapshots), telegram_bot (tool response).

---
*Source: Example portfolio code – Position(value, asset_type), Portfolio.allocation_by_type()*
