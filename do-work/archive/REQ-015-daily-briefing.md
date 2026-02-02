---
id: REQ-015
title: Daily briefing (optional morning message)
status: pending
created_at: 2026-02-02T00:00:00Z
user_request: UR-002
---

# Daily Briefing (Optional Morning Message)

## What

Send an optional morning message (e.g. before market open / before rebalance) with portfolio health, today’s plan (rolls, trims, rebalance), and brief market context. User can enable/disable.

## Detailed Requirements

- **Content:** One message containing: (1) Portfolio health: equity, change vs yesterday or vs 30-day high, kill switch status, cash buffer %. (2) Today’s plan: output of run_daily_logic_preview (what orders would be placed) or a short summary (“No actions” vs “3 orders: roll UMC, trim moonshot, …”). (3) Optional: 1–2 line market watch (e.g. from get_market_news for theme symbols or “market”).
- **Timing:** Configurable time (e.g. BRIEFING_TIME_HOUR=9, BRIEFING_TIME_MINUTE=0, BRIEFING_TIMEZONE=America/New_York) so it runs before rebalance (e.g. 9:00 AM ET before 9:30 rebalance).
- **Delivery:** Only when Telegram bot is running. Send to a configured chat or the same mechanism as normal bot messages. Do not run full rebalance at briefing time unless that’s already scheduled; briefing is read-only (preview only).
- **Enable/disable:** Config flag e.g. DAILY_BRIEFING_ENABLED=false by default.

## Constraints

- Reuse existing tools (get_portfolio_analysis, run_daily_logic_preview, get_market_news). No new strategy execution at briefing time unless desired.

## Dependencies

- telegram_bot (scheduler or cron-like trigger, send message), config, portfolio, strategy (preview only), market_data or news.

---
*Source: Bot Missing Features Audit plan – missing feature 2.3*
