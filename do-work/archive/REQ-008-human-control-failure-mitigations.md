---
id: REQ-008
title: Human control and failure-mode mitigations
status: completed
created_at: 2025-02-02T00:00:00Z
completed_at: 2026-02-02T15:15:00Z
user_request: UR-002
---

# Human Control and Failure-Mode Mitigations

## What

Add emergency stop, optional cool-down after large loss, and confirmation prompts for large or irreversible trades. Richer "what if" controls in Telegram (e.g. what if I trim moonshot to 25%?).

## Detailed Requirements

- Emergency stop: already partially covered by REQ-003 (read_only tier). Add explicit "Emergency stop" or "Pause all trading" button/label in README and optional Telegram command (e.g. /pause) that sets TRADING_PAUSED or EXECUTION_TIER=read_only. If env is file-based, document manual edit; optional: persist pause state in data/bot_config.json so user can toggle via chat.
- Confirmations: for place_manual_trade when quantity or notional is above a threshold (e.g. > $500 or > 10 contracts), optional two-step: "Confirm: sell 20 contracts of X at $Y? Reply YES to execute." Can be v2; v1 = document "review before sending" in prompt.
- Cool-down: optional. After a single trade that realizes a loss above X% or $Y, block new trades for N minutes (config). Implement only if simple (e.g. last_fill_loss and timestamp in storage).
- What-if: add tool what_if_trim(symbol, target_pct) or what_if_rebalance() that returns "If you trim X to 25%, you would sell N shares at ~$P; new allocation: ...". Uses current portfolio + quotes; no execution.

## Constraints

- Emergency stop must be easy and documented. Confirmations and cool-down can be minimal or deferred.

## Dependencies

- config, telegram_bot (run_tool, optional /pause), storage (optional pause state), portfolio + market_data (what-if).

---
*Source: UR-002 – full bot completion*
