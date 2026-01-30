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
├── config.py          # Configuration management (env vars)
├── client.py          # PublicApiClient wrapper
├── market_data.py     # Quotes, chains, Greeks, expirations
├── portfolio.py       # Allocation math and position tracking
├── strategy.py        # Selection, rebalance, roll, trim logic
├── execution.py       # Preflight, order placement, polling
├── storage.py         # SQLite database
├── main.py            # Scheduler and run loop
├── telegram_bot.py    # Telegram + AI chat (portfolio, trades, strategy)
└── utils/
    ├── logger.py      # Logging configuration
    └── account_manager.py  # Account selection and data/bot_config.json
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

Run all commands from the **project root** (the directory containing `.env` and `src/`).

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

**Note**: Account number is selected interactively on first run and saved in `data/bot_config.json` for future runs.

## Usage

### Running the Bot (scheduled rebalance)

From project root:

```bash
python -m src.main
```

Or:

```bash
python run.py
```

### Telegram + AI Bot

Talk to the bot in natural language over Telegram for portfolio, trades, strategy preview, and config.

1. Create a bot with [@BotFather](https://t.me/BotFather) and get `TELEGRAM_BOT_TOKEN`.
2. Add to `.env`:
   - `TELEGRAM_BOT_TOKEN=...`
   - `OPENAI_API_KEY=...` (for AI understanding)
   - `ALLOWED_TELEGRAM_USER_IDS=123456789` (optional; comma-separated user IDs allowed to execute trades; leave empty to allow all for read-only)
3. From project root, run:

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

You can import and use components programmatically. Run from project root so `.env` and `data/` resolve correctly. `TradingClient` requires an `account_number`; use `AccountManager.get_saved_account()` or prompt interactively.

```python
from src.utils.account_manager import AccountManager
from src.config import config
from src.client import TradingClient
from src.market_data import MarketDataManager
from src.portfolio import PortfolioManager
from src.execution import ExecutionManager
from src.strategy import HighConvexityStrategy

# Account: use saved or select interactively
account = AccountManager.get_saved_account()
if not account:
    account = AccountManager.select_account_interactive(config.api_secret_key)
if not account:
    raise SystemExit("No account selected")

# Initialize components
client = TradingClient(account_number=account)
data_manager = MarketDataManager(client)
portfolio_manager = PortfolioManager(client, data_manager)
execution_manager = ExecutionManager(client, portfolio_manager)
strategy = HighConvexityStrategy(portfolio_manager, data_manager, execution_manager)

# Run daily logic (returns list of order dicts: action, symbol, quantity, price)
orders = strategy.run_daily_logic()

# Execute orders (each returns result dict or None)
for order_details in orders:
    result = execution_manager.execute_order(order_details)
    print(result)
```

For full behavior (kill switch, storage, scheduling), use `TradingBot` from `src.main` or run `python run.py`.

## Configuration

All configuration is managed through environment variables in `.env`. Values below match `src/config.py` and `.env.example`.

### Strategy Universe
- `THEME_UNDERLYINGS`: Comma-separated list (default: "UMC,TE,AMPX")
- `MOONSHOT_SYMBOL`: Moonshot symbol (default: "GME.WS")

### Target Allocations
- `THEME_A_TARGET`, `THEME_B_TARGET`, `THEME_C_TARGET`: Theme targets (defaults: 0.35, 0.35, 0.15)
- `MOONSHOT_TARGET`: Moonshot target (default: 0.20)
- `MOONSHOT_MAX`: Moonshot hard cap (default: 0.30)
- `CASH_MINIMUM`: Minimum cash buffer (default: 0.20)

### Option Selection
- `OPTION_DTE_MIN`, `OPTION_DTE_MAX`: DTE range (defaults: 60, 120)
- `OPTION_DTE_FALLBACK_MIN`, `OPTION_DTE_FALLBACK_MAX`: Fallback DTE if no expirations in range (defaults: 45, 150)
- `STRIKE_RANGE_MIN`, `STRIKE_RANGE_MAX`: Strike multiplier vs spot (defaults: 1.00, 1.10)
- `MAX_BID_ASK_SPREAD_PCT`: Max bid-ask spread (default: 0.12)
- `MIN_OPEN_INTEREST`, `MIN_VOLUME`: Liquidity filters (defaults: 50, 10)

### Roll Rules
- `ROLL_TRIGGER_DTE`: Roll when DTE below this (default: 60)
- `ROLL_TARGET_DTE`: Roll to expiration ~this DTE (default: 90)
- `MAX_ROLL_DEBIT_PCT`: Max roll cost as % of current value (default: 0.35)
- `MAX_ROLL_DEBIT_ABSOLUTE`: Max roll cost in dollars (default: 100.0)

### Profit/Loss Rules
- `TAKE_PROFIT_100_PCT`, `TAKE_PROFIT_200_PCT`: Thresholds (defaults: 1.00, 2.00)
- `TAKE_PROFIT_100_CLOSE_PCT`: Fraction to close at +100% (default: 0.50)
- `STOP_LOSS_DRAWDOWN_PCT`: Stop loss drawdown (default: -0.40)
- `STOP_LOSS_UNDERLYING_PCT`: Close if underlying below strike by this much (default: -0.05)
- `CLOSE_IF_DTE_LT`: Close any position if DTE below (default: 30)
- `CLOSE_IF_OTM_DTE_LT`: Close OTM options if DTE below (default: 30)

### Execution
- `MAX_TRADES_PER_DAY`: Max trades per day (default: 5)
- `ORDER_PRICE_OFFSET_PCT`: Limit price offset from mid (default: 0.0)
- `ORDER_POLL_TIMEOUT_SECONDS`: Order status poll timeout (default: 300)
- `ORDER_POLL_INTERVAL_SECONDS`: Poll interval (default: 5)
- `DRY_RUN`: Skip placing real orders (default: false)

### Signals
- `USE_SMA_FILTER`: Use SMA filter for entry (default: true)
- `SMA_PERIOD`: SMA period (default: 20)
- `MANUAL_MODE_ONLY`: Only open positions via manual/Telegram (default: false)

### Trading Hours
- `TRADE_EXTENDED_HOURS`: Allow extended-hours trading (default: false)

### Rebalancing
- `REBALANCE_TIME_HOUR`, `REBALANCE_TIME_MINUTE`: Daily run time (defaults: 9, 30)
- `REBALANCE_TIMEZONE`: Timezone (default: "America/New_York")

### Guardrails
- `KILL_SWITCH_DRAWDOWN_PCT`: Stop new positions if drawdown exceeds (default: 0.25)
- `KILL_SWITCH_LOOKBACK_DAYS`: Lookback for equity high (default: 30)
- `KILL_SWITCH_COOLDOWN_DAYS`: Cooldown days (default: 5)

### Database & Logging
- `DB_PATH`: SQLite path (default: "data/trading_bot.db")
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `LOG_FILE`: Log file path (default: "logs/high_convexity_bot.log")

### Telegram + AI
- `TELEGRAM_BOT_TOKEN`: Bot token from BotFather (required for Telegram bot)
- `OPENAI_API_KEY`: OpenAI API key for AI chat (required for Telegram bot)
- `ALLOWED_TELEGRAM_USER_IDS`: Comma-separated user IDs allowed to execute trades / change config (empty = read-only for all)

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

From project root, run tests:

```bash
python3 -m pytest
```

Or:

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
