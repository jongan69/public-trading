# High-Convexity Portfolio Trading Bot

A Python trading bot built on the Public.com Python SDK that manages a small account (~$1,200) using a "high-convexity portfolio" ruleset.

## Strategy Overview

The bot maintains a high-convexity portfolio with:

- **2-3 Option Themes** (long calls only): Each targeting 30-40% allocation
  - Theme A (UMC): 35% target
  - Theme B (TE): 35% target  
  - Theme C (AMPX): 15% target (optional)
- **1 Moonshot Position** (e.g., GME.WS warrants): 20% target with 30% hard cap
- **Cash Buffer**: Minimum 20% at all times

## Architecture

```
src/
├── config.py          # Configuration management
├── client.py          # PublicApiClient wrapper
├── market_data.py     # Quotes, chains, Greeks, expirations
├── portfolio.py       # Allocation math and position tracking
├── strategy.py        # Selection, rebalance, roll, trim logic
├── execution.py       # Preflight, order placement, polling
├── storage.py         # SQLite database
├── main.py            # Scheduler and run loop
├── telegram_bot.py    # Telegram + AI chat (portfolio, trades, strategy)
└── utils/
    └── logger.py      # Logging configuration
```

## Features

### Option Contract Selection
- Fetches expirations with 60-120 DTE (fallback 45-150)
- Selects CALLs only
- Chooses strike closest to spot * 1.00 to 1.10 (ATM to 10% OTM)
- Liquidity filters:
  - Skips if bid/ask missing
  - Skips if bid-ask spread > 12% of mid
  - Requires OI >= 50 and volume >= 10 (configurable)

### Position Management
- **Take Profit**: 
  - +100%: Close 50% of position
  - +200%: Close all
- **Stop Loss**:
  - Close if drawdown <= -40% AND underlying below strike by >5%
  - Close if DTE < 30 and option is OTM
- **Rolling**:
  - Roll when DTE < 60 if part of theme allocation
  - Roll to nearest monthly expiration ~+90 days
  - Only roll if cost <= 35% of current value or $100 absolute

### Moonshot Trim
- Auto-trim if position > 30% of equity (reduce to 25%)
- Never auto-add to moonshot; only trim

### Guardrails
- **No margin**: Cash-only trading
- **No shorting**: Long positions only
- **No naked options selling**: Long calls only
- **Kill Switch**: Stops opening new positions if equity drawdown > 25% from 30-day high
- **Dry-run mode**: Test without placing real orders

## Installation

1. **Create virtual environment**:

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

3. **Configure environment**:

Copy `.env.example` to `.env` and update:

```bash
cp .env.example .env
```

Required settings:
- `PUBLIC_SECRET_KEY`: Your Public.com API secret key

**Note**: Account number will be selected interactively on first run and saved locally in `data/bot_config.json` for future use.

## Usage

### Running the Bot (scheduled rebalance)

```bash
python -m src.main
```

Or:

```bash
cd src
python main.py
```

### Telegram + AI Bot

Talk to the bot in natural language over Telegram for portfolio, trades, strategy preview, and config.

1. Create a bot with [@BotFather](https://t.me/BotFather) and get `TELEGRAM_BOT_TOKEN`.
2. Add to `.env`:
   - `TELEGRAM_BOT_TOKEN=...`
   - `OPENAI_API_KEY=...` (for AI understanding)
   - `ALLOWED_TELEGRAM_USER_IDS=123456789` (optional; comma-separated user IDs allowed to execute trades; leave empty to allow all for read-only)
3. Run:

```bash
python run_telegram.py
```

Or:

```bash
python -m src.telegram_bot
```

Then message your bot on Telegram. You can have full conversation about market news, options chains, and building custom strategies:

- **Portfolio & strategy**: *"Portfolio summary"*, *"What would the strategy do?"*, *"Run rebalance"*, *"Show config"*
- **Market news**: *"What's the news on AAPL?"*, *"Any Fed news?"*, *"Earnings this week"*
- **Options chains**: *"Options chain for UMC"*, *"Expirations for GME"*, *"Calls and puts for TSLA"*
- **Polymarket odds**: *"Polymarket odds on Fed"*, *"Prediction markets Bitcoin"*, *"Election odds"* — discuss and factor into options/market context
- **Images**: Send a screenshot of a chart, strategy doc, or table — the bot describes it and can help implement or discuss vs portfolio/options
- **Build strategy via chat**: *"Set theme A to 40%"*, *"Use 60–90 DTE only"*, *"Set themes to AAPL, MSFT, GOOGL"*, *"I want 25% cash"*
- **Trades**: *"Buy 10 GME.WS at 25"*, *"Turn on dry run"*

### Dry Run Mode

Test without placing real orders:

```bash
# Set in .env
DRY_RUN=true

python -m src.main
```

### Manual Execution

You can also import and use components programmatically:

```python
from src.client import TradingClient
from src.market_data import MarketDataManager
from src.portfolio import PortfolioManager
from src.execution import ExecutionManager
from src.strategy import HighConvexityStrategy

# Initialize components
client = TradingClient()
data_manager = MarketDataManager(client)
portfolio_manager = PortfolioManager(client, data_manager)
execution_manager = ExecutionManager(client, portfolio_manager)
strategy = HighConvexityStrategy(portfolio_manager, data_manager, execution_manager)

# Run daily logic
orders = strategy.run_daily_logic()

# Execute orders
for order in orders:
    result = execution_manager.execute_order(order)
    print(result)
```

## Configuration

All configuration is managed through environment variables in `.env`:

### Strategy Universe
- `THEME_UNDERLYINGS`: Comma-separated list (default: "UMC,TE,AMPX")
- `MOONSHOT_SYMBOL`: Moonshot symbol (default: "GME.WS")

### Target Allocations
- `THEME_A_TARGET`: Theme A target allocation (default: 0.35)
- `THEME_B_TARGET`: Theme B target allocation (default: 0.35)
- `THEME_C_TARGET`: Theme C target allocation (default: 0.15)
- `MOONSHOT_TARGET`: Moonshot target allocation (default: 0.20)
- `MOONSHOT_MAX`: Moonshot hard cap (default: 0.30)
- `CASH_MINIMUM`: Minimum cash buffer (default: 0.20)

### Option Selection
- `OPTION_DTE_MIN`: Minimum days to expiration (default: 60)
- `OPTION_DTE_MAX`: Maximum days to expiration (default: 120)
- `STRIKE_RANGE_MIN`: Minimum strike multiplier (default: 1.00)
- `STRIKE_RANGE_MAX`: Maximum strike multiplier (default: 1.10)
- `MAX_BID_ASK_SPREAD_PCT`: Maximum bid-ask spread (default: 0.12)
- `MIN_OPEN_INTEREST`: Minimum open interest (default: 50)
- `MIN_VOLUME`: Minimum volume (default: 10)

### Profit/Loss Rules
- `TAKE_PROFIT_100_PCT`: Take profit threshold at +100% (default: 1.00)
- `TAKE_PROFIT_200_PCT`: Take profit threshold at +200% (default: 2.00)
- `STOP_LOSS_DRAWDOWN_PCT`: Stop loss drawdown threshold (default: -0.40)
- `CLOSE_IF_DTE_LT`: Close if DTE less than (default: 30)

### Execution
- `MAX_TRADES_PER_DAY`: Maximum trades per day (default: 5)
- `ORDER_POLL_TIMEOUT_SECONDS`: Order polling timeout (default: 300)
- `DRY_RUN`: Enable dry-run mode (default: false)

### Rebalancing
- `REBALANCE_TIME_HOUR`: Rebalance hour (default: 9)
- `REBALANCE_TIME_MINUTE`: Rebalance minute (default: 30)
- `REBALANCE_TIMEZONE`: Timezone (default: "America/New_York")

### Guardrails
- `KILL_SWITCH_DRAWDOWN_PCT`: Kill switch threshold (default: 0.25)
- `KILL_SWITCH_LOOKBACK_DAYS`: Lookback period (default: 30)

### Telegram + AI
- `TELEGRAM_BOT_TOKEN`: Bot token from BotFather (required for Telegram bot)
- `OPENAI_API_KEY`: OpenAI API key for AI chat (required for Telegram bot)
- `ALLOWED_TELEGRAM_USER_IDS`: Comma-separated Telegram user IDs allowed to execute trades / change config (empty = allow all for read-only)

## Database

The bot uses SQLite to store:

- **Positions**: Current positions snapshot
- **Orders**: Order history with status
- **Fills**: Fill details
- **Contracts**: Chosen option contracts
- **Config Snapshots**: Configuration used each run
- **Portfolio Snapshots**: Daily portfolio state
- **Equity History**: Equity over time (for kill switch)

Database location: `data/trading_bot.db` (configurable via `DB_PATH`)

## Testing

Run tests:

```bash
pytest
```

Test specific modules:

```bash
pytest tests/test_allocation.py
pytest tests/test_roll_decision.py
pytest tests/test_option_selection.py
```

## Logging

Logs are written to:
- **Console**: Colored output with timestamps
- **File**: `logs/high_convexity_bot.log` (rotated at 10MB, retained 7 days)

Log level controlled via `LOG_LEVEL` environment variable (DEBUG, INFO, WARNING, ERROR).

## Important Notes

### Order Execution
- Orders are **asynchronous** - always poll `get_order()` to confirm fills
- The bot automatically polls order status until filled/canceled/rejected
- Preflight calculations are performed before every order
- Cash buffer is checked before buy orders

### Risk Management
- **No margin**: All trades are cash-only
- **No shorting**: Long positions only
- **No naked selling**: Long calls only (no writing options)
- **Kill switch**: Automatically stops opening new positions if drawdown exceeds threshold

### Market Hours
- Rebalancing occurs once per day at configured time (default: 9:30 AM ET)
- Uses CORE session by default (can enable extended hours via `TRADE_EXTENDED_HOURS`)

### Dry Run Mode
Always test in dry-run mode first:

```bash
DRY_RUN=true python -m src.main
```

This will log all orders without actually placing them.

## Troubleshooting

### Common Issues

1. **"No suitable contract found"**
   - Check liquidity filters (OI, volume, bid-ask spread)
   - Verify expiration dates are available
   - Check strike range settings

2. **"Order would violate cash buffer"**
   - Increase cash allocation or reduce position sizes
   - Check current cash balance

3. **"Kill switch activated"**
   - Equity has dropped >25% from 30-day high
   - Bot will stop opening new positions
   - Existing positions will still be managed

4. **"Max trades per day reached"**
   - Increase `MAX_TRADES_PER_DAY` or wait for next day

## License

MIT
# public-trading
