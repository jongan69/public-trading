---
id: REQ-014
title: Proactive alerts (kill switch, roll needed, caps)
status: pending
created_at: 2026-02-02T00:00:00Z
user_request: UR-002
---

# Proactive Alerts (Kill Switch, Roll Needed, Caps)

## What

Bot is reactive only; users are not notified when risks approach. Add optional proactive alerts when approaching kill switch, when positions need rolling soon, or when a position nears a cap (e.g. moonshot 28%).

## Detailed Requirements

- **Kill switch approaching:** When equity drawdown from 30-day high is within a threshold of the kill switch (e.g. drawdown between 20% and 25% where 25% triggers kill switch), send an alert (e.g. Telegram message or log event). Message: equity, high-water mark, current drawdown %, and that kill switch will activate at X%. Config: optional ALERT_DRAWDOWN_WARNING_PCT (e.g. 0.20) or use fixed offset from kill_switch_drawdown_pct.
- **Roll needed soon:** When any theme or option position has DTE below a warning threshold (e.g. DTE &lt; 7 days before roll_trigger_dte, or DTE in [roll_trigger_dte - 7, roll_trigger_dte]), send an alert listing positions and DTE. Run this check from a scheduled point (e.g. same daily run as rebalance, or a separate morning check) or when user opens Telegram.
- **Position near cap:** When moonshot (or any single position) allocation is within a few percent of max (e.g. &gt; 28% when cap is 30%), send an alert that auto-trim may soon trigger.
- **Delivery:** Prefer Telegram push if bot is running (e.g. from run_telegram.py); alternatively write to a dedicated log or “pending alerts” that get shown on next user message. Config flag to enable/disable proactive alerts (e.g. PROACTIVE_ALERTS_ENABLED).

## Constraints

- Do not spam; coalesce (e.g. one daily summary of warnings). Respect user preference (config or per-user if multi-user later).

## Dependencies

- telegram_bot (send message or surface alerts), storage (equity history), portfolio (allocations, positions, DTE), config.

---
*Source: Bot Missing Features Audit plan – missing feature 2.3*
