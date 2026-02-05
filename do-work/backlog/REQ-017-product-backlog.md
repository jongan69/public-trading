---
id: REQ-017
title: Product backlog (remaining plan items)
status: pending
created_at: 2026-02-02T00:00:00Z
user_request: UR-002
---

# Product Backlog (Remaining Plan Items)

## What

Capture remaining “missing features” from the Bot Missing Features Audit as a single backlog request. These are lower priority or larger scope; implement when capacity allows or split into separate REQs later.

## Backlog Items

### Onboarding and setup
- Setup wizard: `/setup` or guided flow (account connection, experience level, risk quiz, paper vs live).
- Strategy templates: pre-built Conservative / Balanced / Aggressive; `/choose_strategy`.
- Paper trading P&L: dedicated tracking of “would-have” P&L when DRY_RUN is on (separate equity curve or summary).

### Education and clarity
- Glossary / explain: `/explain <term>` or contextual help (DTE, roll, max pain).
- Trade rationale cards: rich format with education snippet and buttons (Approve / Learn more).
- Tutorials: `/tutorial basics|strategy|risk` step-by-step.

### Scenarios and visualization
- Pre-built scenario library: menu of scenarios (“Market crash -20%”, “Moonshot doubles”) or natural-language run_scenario(description).
- Payoff diagrams as images: generate chart from option_payoff_analysis and send image in Telegram.
- Web dashboard: local web UI (Flask/FastAPI) with equity curve, allocation pie, risk metrics, trade timeline (see REQ-010).

### Safety and control
- Smart confirmation tiers: low/medium/high/critical with different UX (notify after vs countdown vs explicit approve).
- Undo / rollback: `/undo` for recent actions with cost warning.
- Emergency stop options: choice of “Liquidate all” vs “Pause only” in one flow.

### Performance and reporting
- `/performance` command: one-tap summary (reuse get_performance_summary).
- Benchmarking: compare portfolio vs SPY/QQQ (return, drawdown, risk-adjusted).
- AI insights: proactive pattern messages (“Moonshot best performer”, “Theme C losing—consider rotating”).

### Operations and scale
- Backup: automated DB backup or export of critical state.
- Multi-account: account switcher or multi-account view (currently single saved account).
- Run frequency: configurable intraday schedule (e.g. every 4 hours) in addition to once-daily rebalance.
- Tax reporting: tax-lot or cost-basis export for tax prep.

### UX and accessibility (REQ-010)
- Mode-adaptive UI: AUTOPILOT / GUIDED / MANAGED / ADVANCED with different tool sets or wording.
- Shortcuts: mode-specific quick actions or fewer buttons for beginners.

## Constraints

- No commitment to implement all; use as a source for future REQs. Prioritize by user demand.

## Dependencies

- Various: telegram_bot, config, storage, portfolio, analytics, REQ-010 universal accessibility feature map.

---
*Source: Bot Missing Features Audit plan – remaining missing features 2.1–2.8*
