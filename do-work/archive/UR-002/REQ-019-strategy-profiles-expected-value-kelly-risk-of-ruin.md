---
id: REQ-019
title: Strategy profiles, expected value, Kelly fraction, and risk of ruin
status: pending
created_at: 2025-02-02T00:00:00Z
user_request: UR-002
---

# Strategy Profiles, Expected Value, Kelly Fraction, and Risk of Ruin

## What

Add **strategy-level math** so the bot can reason about trade statistics: define strategy profiles (win rate, average win/loss, trades per year), and provide **expected value**, **Kelly fraction** (conservative cap e.g. 25%), and **risk-of-ruin** (simulation-based) as tools for sizing and risk discussion.

## Detailed Requirements

- **StrategyProfile:** Data model or config: `name`, `win_rate`, `avg_win`, `avg_loss`, `trades_per_year`. Presets allowed (e.g. "Daily 3% Grind": win_rate=0.58, avg_win=0.03, avg_loss=0.03, trades=220; "High Conviction": win_rate=0.40, avg_win=0.40, avg_loss=0.15, trades=10).
- **expected_value(strategy):** EV = win_rate * avg_win - (1 - win_rate) * avg_loss. Expose as function and optionally in AI tool (e.g. "strategy_ev" or part of compare_strategies).
- **kelly_fraction(strategy):** Kelly = (b*p - q)/b with b = avg_win/avg_loss, p = win_rate, q = 1-p; cap at 0.25 (25%). Expose for sizing guidance.
- **risk_of_ruin(win_rate, win, loss, capital, risk_per_trade, trials=10000):** Simulate N trials of up to 1000 trades each; count fraction of trials where balance falls to ≤ 30% of initial capital. Return ruined/trials. Expose as tool so AI can say "At 2% risk per trade, risk of ruin is X%."
- **Config:** Optional env or config for preset strategy names and parameters so users can tune without code change.

## Constraints

- Pure math module preferred (e.g. `src/utils/strategy_math.py` or `src/risk.py`). No execution or order placement; advisory only.
- Risk of ruin is simulation-based; document trial count and ruin threshold (e.g. 30% of capital) in docstring.

## Dependencies

- New module (strategy_math/risk), config if presets are configurable, telegram_bot if exposing as tools.

---
*Source: Example code – StrategyProfile, expected_value(), kelly_fraction(), risk_of_ruin()*
