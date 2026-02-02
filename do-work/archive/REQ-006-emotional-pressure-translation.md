---
id: REQ-006
title: Emotional pressure translation layer
status: completed
created_at: 2025-02-02T00:00:00Z
claimed_at: 2026-02-02T19:47:00Z
completed_at: 2026-02-02T19:48:00Z
route: A
user_request: UR-002
---

# Emotional Pressure Translation Layer

## What

The AI must never amplify desperation. When the user uses desperation language, all-or-nothing framing, or stress escalation, the AI should convert emotion → numbers, narrow decisions to ranges, and prevent binary mistakes. Key rule: compress desperation into structure.

## Detailed Requirements

- SYSTEM_PROMPT: add a short "Emotional pressure" section. Instruct the model to (1) detect desperation language (e.g. "I need to win back", "all in", "can't afford to lose", "must", "last chance"); (2) respond by reframing in numbers (ranges, probabilities, caps); (3) never suggest increasing size or risk to "catch up"; (4) suggest cooling off or reducing exposure when stress is high.
- Optional: add a tool or prompt cue that returns "risk state" (e.g. drawdown %, kill switch status) so the model can say "Given current drawdown, consider waiting" without inventing numbers.
- Keep it prompt-only if possible; no heavy classifier. Goal: model behavior change, not new code paths.

## Constraints

- No change to execution or strategy logic; only prompt and optional lightweight context.

## Dependencies

- telegram_bot SYSTEM_PROMPT; optional: get_portfolio_analysis (already gives drawdown/kill switch).

---
*Source: UR-002 – full bot completion*

---

## Triage

**Route: A** - Simple

**Reasoning:** Clear prompt modification with specific requirements. The file to modify (telegram_bot.py SYSTEM_PROMPT) is explicitly mentioned, and the changes are well-defined prompt additions.

**Planning:** Not required

## Plan

**Planning not required** - Route A: Direct implementation

Rationale: Clear prompt modification with explicit file mentioned. No architectural decisions needed.

*Skipped by work action*

## Implementation Summary

Enhanced the existing emotional pressure section in telegram_bot.py SYSTEM_PROMPT (lines 231-237) with comprehensive 5-point framework:

1. **Convert emotion → numbers**: Use ranges, probabilities, caps, and specific targets
2. **Never suggest increasing size or risk to "catch up"**: Explicitly prohibit doubling down or revenge trades when stressed
3. **Use risk context**: Leverage existing `get_portfolio_analysis` tool to check drawdown % and kill switch status
4. **Suggest cooling off**: Recommend reducing exposure, stepping away, or paper trading when high stress is detected
5. **Compress desperation into structure**: Transform emotional statements into structured trade plans with defined risk parameters

The implementation detects desperation language patterns ("I need to win back", "all in", "can't afford to lose", "must", "last chance", "YOLO", "desperate", "broke", "final shot") and systematically converts emotional pressure into disciplined, risk-managed trading decisions.

*Completed by work action (Route A)*

## Testing

**Tests run:** pytest tests/test_emotional_pressure_translation.py -v
**Result:** ✓ All 15 tests passing (6 existing + 9 new)

**New tests added:**
- tests/test_emotional_pressure_translation.py - comprehensive coverage of emotional pressure detection and response framework

**Existing tests verified:**
- tests/test_telegram_data_consumption.py - all 6 tests still passing

*Verified by work action*
