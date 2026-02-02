---
id: REQ-013
title: Config persistence for Telegram-edited settings
status: completed
created_at: 2026-02-02T00:00:00Z
completed_at: 2026-02-02T16:30:00Z
user_request: UR-002
---

# Config Persistence for Telegram-Edited Settings

## What

Updates from Telegram (update_allocation_targets, update_option_rules, update_theme_symbols) only change in-memory config; after restart all changes are lost. Either document clearly that edits are session-only or add optional persistence so strategy params survive restart.

## Detailed Requirements

- **Option A (documentation):** In README and in tool responses, state clearly that allocation/option/theme edits from Telegram apply for the current session only and must be set in `.env` to persist. No code change.
- **Option B (persistence):** Add a persisted config overlay (e.g. `data/bot_config.json` or similar) that stores strategy params when user changes them via Telegram. On load, config reads from env first then overlays from file (so file overrides env for those keys). When update_allocation_targets, update_option_rules, or update_theme_symbols is called, write the updated values to the overlay file. Document that editing `.env` still works and that file takes precedence for overlayed keys.
- **Scope:** Only strategy-related params that Telegram can change: theme underlyings, allocation targets, option_dte_min/max, strike_range_min/max. Do not persist secrets (API keys) in the overlay.

## Constraints

- If implementing Option B: no overwriting of entire `.env`; use a separate overlay file. Clear warning if user might be confused about precedence.

## Dependencies

- config.py (load overlay after env), telegram_bot (write overlay on update_*), README.

---
*Source: Bot Missing Features Audit plan – implementation gap 1.3*
