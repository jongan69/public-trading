---
id: REQ-026
title: Payoff Diagram Images
status: pending
created_at: 2026-02-05T00:00:00Z
parent: REQ-017
priority: medium
---

# Payoff Diagram Images

## What

Generate and send payoff diagram images (visual charts) for options when user requests analysis. Converts existing `option_payoff_analysis` text output into a visual graph sent as an image in Telegram.

## Detailed Requirements

### User Experience

```
User: "Show me payoff for my GME calls"
Bot: [Sends image of payoff diagram chart]

     Breakeven: $52.50
     Max profit: Unlimited
     Max loss: $250 (premium paid)
```

### Chart Requirements

**X-axis**: Underlying price at expiration (range: -20% to +50% from current spot)
**Y-axis**: Profit/Loss in dollars

**Visual Elements**:
- Line graph showing P&L at each price point
- Horizontal line at $0 (breakeven reference)
- Vertical line at current spot price (labeled "Current Price")
- Shaded regions: green for profit, red for loss
- Strike price marked with vertical dashed line
- Breakeven price marked clearly

**Example visual structure**:
```
   P&L ($)
     |
  +500|     ________/
     |    /
     |   /
   $0|__/____________  ← Breakeven
     | /
 -250|/______________ ← Max Loss (premium)
     |
     +-----|-----|-----
      $45  $50  $60    Price
           ↑     ↑
        Strike Current
```

### Implementation Options

**Option 1: matplotlib** (recommended)
```python
import matplotlib.pyplot as plt
import io

def generate_payoff_diagram(option_symbol, strike, premium, option_type, spot):
    """Generate payoff diagram and return as BytesIO buffer."""
    # Calculate price range
    prices = np.linspace(spot * 0.8, spot * 1.5, 100)

    # Calculate P&L at each price
    if option_type == "CALL":
        payoffs = [max(p - strike, 0) - premium for p in prices]
    else:  # PUT
        payoffs = [max(strike - p, 0) - premium for p in prices]

    # Create plot
    plt.figure(figsize=(10, 6))
    plt.plot(prices, payoffs, linewidth=2, color='blue')
    plt.axhline(0, color='black', linestyle='--', alpha=0.3)
    plt.axvline(spot, color='green', linestyle='--', alpha=0.5, label=f'Current: ${spot:.2f}')
    plt.axvline(strike, color='red', linestyle='--', alpha=0.5, label=f'Strike: ${strike:.2f}')

    # Shade profit/loss regions
    plt.fill_between(prices, payoffs, 0, where=[p > 0 for p in payoffs],
                     color='green', alpha=0.2)
    plt.fill_between(prices, payoffs, 0, where=[p < 0 for p in payoffs],
                     color='red', alpha=0.2)

    plt.xlabel('Underlying Price at Expiration ($)')
    plt.ylabel('Profit/Loss ($)')
    plt.title(f'{option_symbol} Payoff Diagram')
    plt.legend()
    plt.grid(True, alpha=0.3)

    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close()

    return buf
```

**Option 2: plotly** (interactive, but larger file size)
**Option 3: ASCII art** (fallback for lightweight implementation)

### Integration with Telegram Bot

Modify `option_payoff_analysis` tool to return both text AND image:
```python
if tool_name == "option_payoff_analysis":
    # ... existing logic ...

    # Generate chart
    image_buffer = generate_payoff_diagram(
        option_symbol=osi_symbol,
        strike=strike,
        premium=premium,
        option_type=option_type,
        spot=spot
    )

    # Send image first
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=image_buffer,
        caption=f"Payoff Diagram: {osi_symbol}"
    )

    # Then send text summary
    return text_summary
```

### File Size Optimization

- Save as PNG (smaller than JPG for charts)
- DPI: 150 (good quality, reasonable size)
- Target: < 500KB per image
- Cache generated images (same option = same chart)

## Constraints

- Images must render in < 2 seconds
- File size < 500KB
- Chart must be readable on mobile (minimum 10pt font)
- Fallback to text if image generation fails
- No external image hosting required (send directly via Telegram)

## Dependencies

- matplotlib (new: `pip install matplotlib`)
- numpy (likely already installed)
- Existing `option_payoff_analysis` tool
- Telegram bot (photo sending capability)

## Acceptance Criteria

- [ ] Payoff diagrams generated as PNG images
- [ ] Charts show P&L curve, current price, strike, breakeven
- [ ] Profit regions shaded green, loss regions shaded red
- [ ] Images sent via Telegram when `option_payoff_analysis` called
- [ ] Text summary still provided alongside image
- [ ] Chart renders in < 2 seconds
- [ ] File size < 500KB
- [ ] Readable on mobile devices

## Future Enhancements

- Support multi-leg strategies (spreads, straddles)
- Add probability cone (implied volatility cone)
- Animate price movement over time
- Interactive charts (Plotly) with zoom/pan

---
*Source: REQ-017 Scenarios and Visualization*
