---
id: REQ-027
title: Benchmark Comparison (vs SPY/QQQ)
status: pending
created_at: 2026-02-05T00:00:00Z
parent: REQ-017
priority: medium
---

# Benchmark Comparison (vs SPY/QQQ)

## What

Compare portfolio performance against market benchmarks (SPY, QQQ) to assess whether the strategy is outperforming a simple buy-and-hold approach. Shows relative returns, drawdown comparison, and risk-adjusted metrics (Sharpe ratio).

## Detailed Requirements

### User Commands

```
/benchmark
→ Compare last 30 days vs SPY

/benchmark 90
→ Compare last 90 days vs SPY

/benchmark QQQ
→ Compare last 30 days vs QQQ

/benchmark SPY 180
→ Compare last 180 days vs SPY
```

### Output Format

```
📊 Benchmark Comparison: Portfolio vs SPY (Last 30 Days)

Returns:
  Portfolio:  +8.5% ($10,000 → $10,850)
  SPY:        +3.2%
  Outperformance: +5.3% (alpha)

Drawdown:
  Portfolio:  -5.2% (max)
  SPY:        -2.1% (max)
  Risk:       2.5x more volatile

Risk-Adjusted (Sharpe Ratio):
  Portfolio:  1.24
  SPY:        0.89
  Result:     Portfolio has better risk-adjusted returns 🎯

Correlation:
  Beta vs SPY: 1.8 (more volatile than market)

Verdict: ✅ Portfolio is outperforming SPY on both absolute and risk-adjusted basis.
```

### Implementation

**Data Collection**:
1. Get portfolio equity snapshots from `portfolio_snapshots` table
2. Fetch benchmark (SPY/QQQ) historical prices via market data API
3. Normalize both to percentage changes from start date

**Calculations**:
```python
def calculate_benchmark_comparison(
    portfolio_snapshots: List[Dict],
    benchmark_prices: List[float],
    days: int
) -> Dict:
    """Compare portfolio vs benchmark performance."""

    # 1. Calculate returns
    portfolio_return = (final_equity - initial_equity) / initial_equity
    benchmark_return = (final_price - initial_price) / initial_price
    alpha = portfolio_return - benchmark_return

    # 2. Calculate max drawdown for both
    portfolio_dd = calculate_max_drawdown(portfolio_snapshots)
    benchmark_dd = calculate_max_drawdown(benchmark_prices)

    # 3. Calculate Sharpe ratio (assuming risk-free rate = 0 for simplicity)
    portfolio_sharpe = mean_return / std_dev_return
    benchmark_sharpe = benchmark_mean / benchmark_std

    # 4. Calculate beta (volatility vs market)
    beta = covariance(portfolio_returns, benchmark_returns) / variance(benchmark_returns)

    # 5. Determine verdict
    if portfolio_sharpe > benchmark_sharpe and portfolio_return > benchmark_return:
        verdict = "✅ Outperforming on both absolute and risk-adjusted basis"
    elif portfolio_return > benchmark_return:
        verdict = "⚠️ Higher returns but worse risk-adjusted performance"
    else:
        verdict = "❌ Underperforming the benchmark"

    return {
        "portfolio_return": portfolio_return,
        "benchmark_return": benchmark_return,
        "alpha": alpha,
        "portfolio_drawdown": portfolio_dd,
        "benchmark_drawdown": benchmark_dd,
        "portfolio_sharpe": portfolio_sharpe,
        "benchmark_sharpe": benchmark_sharpe,
        "beta": beta,
        "verdict": verdict
    }
```

**Benchmark Price Fetching**:
```python
def get_benchmark_prices(symbol: str, days: int) -> List[Tuple[datetime, float]]:
    """Fetch historical benchmark prices."""
    # Use existing market_data.py infrastructure
    # Query Public.com API or fallback to yfinance
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    prices = market_data_manager.get_historical_quotes(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date
    )

    return [(quote.date, quote.close) for quote in prices]
```

### Telegram Bot Integration

Add new command handler:
```python
async def benchmark_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Compare portfolio vs benchmark."""
    args = context.args

    # Parse arguments
    benchmark = "SPY"  # default
    days = 30  # default

    for arg in args:
        if arg.upper() in ["SPY", "QQQ"]:
            benchmark = arg.upper()
        elif arg.isdigit():
            days = min(int(arg), 365)

    # Run comparison
    result = calculate_benchmark_comparison_sync(
        bot_instance.storage,
        benchmark=benchmark,
        days=days
    )

    # Format output
    message = format_benchmark_comparison(result)
    await update.message.reply_text(message)
```

## Constraints

- Max comparison period: 365 days (limited by data availability)
- Requires at least 7 days of portfolio history
- Benchmark data must be from same time period as portfolio
- If benchmark data unavailable, show error with graceful fallback

## Dependencies

- Existing `portfolio_snapshots` table (populated by REQ-015 daily briefing)
- Market data API (Public.com or yfinance fallback)
- Storage module
- Math utilities (numpy for covariance/variance)

## Acceptance Criteria

- [ ] `/benchmark` compares last 30 days vs SPY
- [ ] `/benchmark 90` compares last 90 days vs SPY
- [ ] `/benchmark QQQ` compares vs QQQ instead of SPY
- [ ] Output shows returns, drawdown, Sharpe ratio, beta, verdict
- [ ] Handles missing data gracefully (requires 7+ days of history)
- [ ] Calculations are mathematically correct (unit tested)
- [ ] Works even if portfolio is in dry-run mode (uses simulated equity)

## Future Enhancements

- Chart overlay (portfolio vs benchmark on same graph)
- More benchmarks (IWM, DIA, custom comparison symbol)
- Sector-specific benchmarks (XLF for financials, XLE for energy)
- Rolling Sharpe ratio over time
- Sortino ratio (downside deviation only)

---
*Source: REQ-017 Performance and Reporting*
