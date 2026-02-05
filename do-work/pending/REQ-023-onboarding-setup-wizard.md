---
id: REQ-023
title: Onboarding & Setup Wizard
status: pending
created_at: 2026-02-05T00:00:00Z
parent: REQ-010
priority: high
---

# Onboarding & Setup Wizard

## What

Interactive setup wizard (`/setup` command) that guides new users through account connection, experience level selection, risk profile configuration, and safety settings. Makes the bot accessible to beginners while auto-configuring optimal settings.

## Detailed Requirements

### 1. `/setup` Command Flow

**Step 1: Welcome & Account**
- Welcome message explaining the bot's purpose
- Guide user through API key setup (if not already configured)
- Test connection before proceeding

**Step 2: Experience Level Selection**
- "I'm brand new to trading" → AUTOPILOT mode (minimal decisions)
- "I understand stocks" → GUIDED mode (explanations + approvals)
- "I trade options regularly" → MANAGED mode (standard config)
- "I want full control" → ADVANCED mode (current power-user experience)

**Step 3: Risk Profile Quiz**
- "What's your account size?" → determines position sizing
- "How much loss can you stomach?" → maps to drawdown % and kill switch
- "What's your goal?" (income/growth/moonshot) → adjusts allocation template

**Step 4: Paper Trading Option**
- "Want to practice with fake money first?" → sets DRY_RUN=true
- "I'm ready for real trading" → sets DRY_RUN=false
- Clarify that user can switch anytime with `/dry_run on|off`

**Step 5: Safety Review**
- Show configured kill switches and max position sizes
- Display allocation targets based on risk profile
- User confirms understanding with "I understand" button

### 2. User Profile Storage

Create `user_profiles` table in database:
```sql
CREATE TABLE user_profiles (
    user_id INTEGER PRIMARY KEY,
    telegram_user_id INTEGER UNIQUE,
    experience_level TEXT, -- autopilot, guided, managed, advanced
    risk_tolerance TEXT, -- conservative, moderate, aggressive
    account_size_range TEXT, -- small (<5k), medium (5k-50k), large (>50k)
    goals TEXT, -- income, growth, moonshot
    setup_completed BOOLEAN DEFAULT 0,
    setup_completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3. Strategy Template Selection

Based on risk profile, auto-select one of these templates:
- **Conservative**: 70% cash, 30% ATM calls, no moonshot, tight stop losses
- **Balanced**: Current default (35/35/15 themes, 20% moonshot, 20% cash)
- **Aggressive**: 30/30/30 themes, 30% moonshot, 10% cash

Save selected template to `config_overrides.json`

### 4. UI/UX Details

- Use Telegram inline buttons for all choices
- Progress indicator: "Step 2 of 5"
- Allow `/setup restart` to start over
- Store partial progress (can resume if interrupted)
- Show summary at end with `/config` output

## Constraints

- Setup must complete in < 5 minutes for beginners
- All selections must be changeable later via commands
- No breaking changes to existing configuration for users who skip setup
- Must work even if `.env` is not fully configured (detect missing keys)

## Dependencies

- Storage (new `user_profiles` table)
- Telegram bot (inline buttons, multi-step conversation)
- Config system (strategy templates)
- ConfigOverrideManager (persist choices)

## Acceptance Criteria

- [ ] `/setup` command launches interactive wizard
- [ ] All 5 steps work with inline button navigation
- [ ] User profile stored in database
- [ ] Strategy auto-configured based on selections
- [ ] Can resume interrupted setup
- [ ] `/setup restart` clears progress and starts over
- [ ] Skipping setup still allows bot usage (uses defaults)

---
*Source: REQ-010 Section 1 - Onboarding & Setup Wizard*
