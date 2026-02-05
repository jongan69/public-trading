---
id: REQ-025
title: /performance Command Shortcut
status: pending
created_at: 2026-02-05T00:00:00Z
parent: REQ-017
priority: low
difficulty: easy
---

# /performance Command Shortcut

## What

Add `/performance` command as a quick shortcut to `get_performance_summary` tool. Provides one-tap access to performance analytics (P&L by theme, win rate, execution quality) without needing to phrase a natural language request.

## Detailed Requirements

### Command Syntax
```
/performance [days]
```

**Examples**:
- `/performance` → Show last 30 days (default)
- `/performance 7` → Show last 7 days
- `/performance 90` → Show last 90 days

### Output

Calls existing `get_performance_summary(days)` tool and returns formatted output:
```
📊 Performance Summary (Last 30 Days)

Theme Performance:
  theme_a (UMC): +$523.45 (+5.2%) | 3 trades | 66.7% win rate
  theme_b (TE): -$102.30 (-1.0%) | 2 trades | 50.0% win rate
  moonshot (GME.WS): +$1,204.56 (+12.0%) | 1 trade | 100.0% win rate

Overall:
  Total P&L: +$1,625.71 (+8.1%)
  Win Rate: 71.4% (5/7 trades)
  Avg Win: +$520.12 | Avg Loss: -$102.30

Execution Quality:
  Avg Slippage: -0.2%
  Favorable Fills: 85.7%
```

### Implementation

Simple wrapper in telegram_bot.py:
```python
async def performance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /performance command."""
    try:
        # Parse optional days argument
        args = context.args
        days = int(args[0]) if args and args[0].isdigit() else 30
        days = min(days, 365)  # Cap at 365

        # Call existing tool
        analytics = PerformanceAnalytics(bot_instance.storage)
        result = analytics.get_performance_summary(days)

        await update.message.reply_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.exception("performance command failed")
        await update.message.reply_text(f"Error: {str(e)}")
```

## Constraints

- Must reuse existing `get_performance_summary` implementation (no duplication)
- Max days: 365 (same as tool)
- Default days: 30 (same as tool)
- Invalid arguments → use default (don't error)

## Dependencies

- Existing `PerformanceAnalytics` class
- Existing `get_performance_summary` tool
- Telegram bot command handler

## Acceptance Criteria

- [ ] `/performance` shows last 30 days performance
- [ ] `/performance 7` shows last 7 days
- [ ] `/performance 90` shows last 90 days
- [ ] `/performance 500` caps at 365 days (no error)
- [ ] `/performance abc` falls back to 30 days default
- [ ] Output format matches existing `get_performance_summary`

## Estimated Effort

**1-2 hours** - Simple command handler wrapper around existing tool.

---
*Source: REQ-017 Performance and Reporting*
