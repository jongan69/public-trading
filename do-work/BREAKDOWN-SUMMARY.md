# Pending Work Breakdown Summary

**Date**: 2026-02-05
**Action**: Broke down large planning documents into actionable requirements

---

## What Was Done

The two remaining pending items (REQ-010 and REQ-017) were **planning documents**, not actionable tasks:
- **REQ-010**: 1,092 lines - comprehensive vision doc covering 9 major feature categories
- **REQ-017**: 62 lines - collection of 20+ backlog items across 6 categories

These have been **moved to `do-work/backlog/`** and **broken down into 5 focused, implementable REQs**.

---

## New Actionable Requirements

### From REQ-010 (Universal Accessibility)

#### REQ-023: Onboarding & Setup Wizard
- **Priority**: High
- **Scope**: `/setup` command with 5-step interactive wizard
- **Size**: ~3.6KB spec
- **Features**:
  - Experience level selection (Autopilot/Guided/Managed/Advanced)
  - Risk profile quiz
  - Strategy template auto-configuration
  - Paper trading option
  - User profile storage in DB

#### REQ-024: Glossary & /explain Command
- **Priority**: Medium
- **Scope**: `/explain <term>` command with contextual help
- **Size**: ~4.1KB spec
- **Features**:
  - Instant definitions for 20+ trading terms
  - Natural language support ("What's DTE?")
  - Contextual help detection
  - `/glossary` command to list all terms
  - Examples + "why it matters" for each term

### From REQ-017 (Product Backlog)

#### REQ-025: /performance Command Shortcut
- **Priority**: Low
- **Difficulty**: Easy (1-2 hours)
- **Scope**: Quick command wrapper around existing `get_performance_summary`
- **Size**: ~2.7KB spec
- **Features**:
  - `/performance [days]` one-tap access to analytics
  - Reuses existing PerformanceAnalytics class

#### REQ-026: Payoff Diagram Images
- **Priority**: Medium
- **Scope**: Generate visual payoff diagrams as PNG charts
- **Size**: ~4.8KB spec
- **Features**:
  - matplotlib chart generation
  - P&L curves with profit/loss shading
  - Current price, strike, breakeven markers
  - Send as Telegram photo alongside text

#### REQ-027: Benchmark Comparison (vs SPY/QQQ)
- **Priority**: Medium
- **Scope**: Compare portfolio vs market benchmarks
- **Size**: ~5.5KB spec
- **Features**:
  - `/benchmark [symbol] [days]` command
  - Returns, drawdown, Sharpe ratio, beta
  - Alpha calculation (outperformance)
  - Verdict: outperforming vs underperforming

---

## Current Queue Status

### Pending (Ready to Implement)
```
do-work/pending/
├── REQ-023-onboarding-setup-wizard.md      (High priority, complex)
├── REQ-024-glossary-explain-command.md     (Medium priority)
├── REQ-025-performance-command.md          (Low priority, EASY)
├── REQ-026-payoff-diagram-images.md        (Medium priority)
└── REQ-027-benchmark-comparison.md         (Medium priority)
```

### Backlog (Planning/Vision Docs)
```
do-work/backlog/
├── REQ-010-universal-accessibility-feature-map.md  (33KB - vision doc)
└── REQ-017-product-backlog.md                      (2.8KB - backlog list)
```

**Note**: REQ-010 contains 7 more major feature categories that can be broken down into additional REQs as needed:
- Simplified User Interface
- Proactive AI Guidance
- Enhanced Scenario Engine
- Safety & Confirmations
- Learning Loop & Performance Analytics
- Community & Social Features
- Multi-Channel Access

---

## Recommended Next Steps

**Quick Win** (1-2 hours):
- Implement **REQ-025** (/performance command) - simple wrapper, immediate value

**High Impact** (1-2 days):
- Implement **REQ-024** (glossary/explain) - makes bot accessible to beginners

**Medium Impact** (2-4 days):
- Implement **REQ-027** (benchmark comparison) - validates strategy effectiveness
- Implement **REQ-026** (payoff diagrams) - visual learning aid

**Strategic** (1+ week):
- Implement **REQ-023** (onboarding wizard) - critical for new user experience

---

## Why This Breakdown?

**Before**: 2 massive documents (35KB total) covering 30+ features
**After**: 5 focused, implementable specs (20KB total) + 2 archived vision docs

**Benefits**:
- Clear scope boundaries
- Prioritization possible
- Can be tackled individually
- Each REQ has acceptance criteria
- Estimated effort included where clear
- Dependencies documented

**Process**:
- Large planning docs moved to `backlog/` (preserved for reference)
- Extracted high-priority, well-defined features into standalone REQs
- Each new REQ includes `parent:` field linking back to source
- Remaining features in backlog can be broken down on-demand
