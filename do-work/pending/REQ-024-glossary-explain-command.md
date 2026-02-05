---
id: REQ-024
title: Glossary & /explain Command
status: pending
created_at: 2026-02-05T00:00:00Z
parent: REQ-010, REQ-017
priority: medium
---

# Glossary & /explain Command

## What

Add `/explain <term>` command and contextual help system that provides clear, beginner-friendly explanations of trading terms, strategy concepts, and bot features. Detects when user might be confused and proactively offers help.

## Detailed Requirements

### 1. `/explain <term>` Command

Provide instant definitions for common terms:

```
/explain DTE
→ "DTE = Days To Expiration. It's how many days until the option expires and becomes worthless.

   Example: If today is Jan 1 and your option expires Jan 31, DTE = 30.

   Why it matters: Low DTE (<30) means time is running out. The bot automatically rolls positions when DTE drops below 60 to avoid time decay."

/explain roll
→ "Roll = Close an expiring option and open a new one further out in time.

   Example: You have a March call (30 DTE). The bot sells it and buys a June call (90 DTE).

   Why it matters: Rolling extends your position's lifespan without losing your theme allocation. The bot only rolls if it costs <35% of position value."

/explain max pain
→ "Max Pain = The strike price where option holders lose the most money at expiration. Often acts as a 'price magnet' due to dealer hedging.

   Example: If max pain is $50, the stock tends to drift toward $50 by expiration.

   How the bot uses it: When enabled (USE_MAX_PAIN_FOR_SELECTION=true), the bot prefers strikes near max pain for better fill probability and dealer positioning."
```

### 2. Glossary Database

Create `glossary` table:
```sql
CREATE TABLE glossary (
    id INTEGER PRIMARY KEY,
    term TEXT UNIQUE NOT NULL,
    short_definition TEXT NOT NULL,
    detailed_explanation TEXT,
    example TEXT,
    why_it_matters TEXT,
    related_terms TEXT, -- comma-separated
    category TEXT, -- options, strategy, risk, execution
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Seed with essential terms:
- **Options**: DTE, strike, OTM/ATM/ITM, call, put, premium, theta, delta
- **Strategy**: roll, trim, rebalance, convexity, theme, moonshot
- **Risk**: kill switch, drawdown, stop loss, take profit, Kelly fraction
- **Execution**: limit order, fill, slippage, bid-ask spread, liquidity

### 3. Contextual Help Detection

Monitor user messages for confusion indicators:
- Question words: "why", "what", "how", "when"
- Confusion phrases: "don't understand", "confused", "what does X mean"
- Terms without `/explain`: detect technical terms in user messages

When detected, offer help:
```
User: "Why did you close my UMC position?"
Bot: "I closed 50% at +100% profit (take-profit rule).

     🎓 Want to learn more about take-profit rules? [Explain] [No thanks]"
```

### 4. `/glossary` Command

Show all available terms by category:
```
/glossary
→ "📚 Available Terms:

   Options Basics:
   • /explain DTE
   • /explain strike
   • /explain call
   [...]

   Strategy Concepts:
   • /explain roll
   • /explain convexity
   [...]

   Or just ask 'What's X?' and I'll explain!"
```

### 5. Natural Language Support

Support variations:
- "What's DTE?"
- "What does roll mean?"
- "Explain convexity"
- "What is max pain?"

All trigger the same `/explain <term>` logic.

## Constraints

- Explanations must be < 300 characters for short_definition
- Use simple language (8th grade reading level)
- Always include real example
- Link to related terms when relevant
- No jargon without explanation

## Dependencies

- Storage (new `glossary` table)
- Telegram bot (inline buttons, message parsing)
- NLP detection (simple keyword matching, not LLM)

## Acceptance Criteria

- [ ] `/explain <term>` returns definition for 20+ seeded terms
- [ ] `/glossary` shows all available terms by category
- [ ] Natural language variations work ("What's X?", "Explain X")
- [ ] Related terms are linked in explanations
- [ ] Contextual help offers `/explain` when user seems confused
- [ ] All explanations include example + "why it matters"

---
*Source: REQ-010 Section 2 - Intelligent Education Layer, REQ-017 Education and Clarity*
