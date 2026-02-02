---
id: REQ-009
title: Learning loop (safe, no autonomous strategy change)
status: completed
created_at: 2025-02-02T00:00:00Z
completed_at: 2026-02-02T15:20:00Z
user_request: UR-002
---

# Learning Loop (Safe)

## What

Track strategy performance and execution quality for transparency and tuning—without allowing the AI to change strategy or remove constraints. Allowed: performance tracking (e.g. P&L by theme, roll timing), execution quality (slippage, fills). Forbidden: autonomous strategy invention, removing safety constraints, increasing leverage on losses.

## Detailed Requirements

- Storage: persist per-trade or per-day metrics (e.g. theme, symbol, side, quantity, fill price, timestamp, realized P&L if closing). Use existing orders/fills tables; extend if needed (e.g. theme tag, outcome).
- Analytics (read-only): add a tool or script that summarizes (1) P&L by theme/moonshot over last N days, (2) roll success (e.g. rolled vs held to expiry), (3) execution quality (limit vs fill, slippage if data available). Expose via get_performance_summary tool in Telegram or a CLI report. No automatic strategy changes based on this data.
- SYSTEM_PROMPT: state that the AI may use performance data to inform discussion but must not suggest removing or loosening governance rules, increasing position size after losses, or inventing new strategies without user request.

## Constraints

- Read-only analytics. No code path that modifies strategy or config based on performance. Human interprets and decides.

## Dependencies

- storage (orders, fills; optional new fields), portfolio/strategy (tag orders by theme), telegram_bot (optional get_performance_summary), config.

---
*Source: UR-002 – full bot completion*
