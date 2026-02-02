# High-Convexity Portfolio Trading Bot

A Python trading bot built on the Public.com Python SDK that manages a small account (~$1,200) using a "high-convexity portfolio" ruleset.

**Vision:** An autonomous hedge-fund manager AI that combines portfolio risk governance, scenario simulation, and execution authority to manage capital under asymmetric, high-convexity strategies while enforcing survival constraints. Not a chatbot—an **operating system for capital**. Optimized for: (1) survival under uncertainty, (2) asymmetric upside capture, (3) capital scalability, (4) human override and transparency. The AI can be aggressive but is never allowed to risk ruin.

**Layers (current mapping):** Human interface → Telegram + AI chat (portfolio, recommendations, overrides). Decision & governance → kill switch, allocation caps, no margin/naked options (config + strategy). Strategy & simulation → convex themes, moonshot trim, roll logic (strategy.py). Data & market intelligence → quotes, options chains, Greeks, news, Polymarket (market_data, telegram tools). Execution & broker control → preflight, limit orders, poll status, dry-run (execution.py). Permission model: read-only by default; managed execution (rebalance, roll, trim) via config; human can pause, override, or restrict via Telegram/env.

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
- **Emergency Stop** (`/pause`): Immediately pause all trading via Telegram command (toggle on/off)
- **Trade Confirmations**: Large trades require two-step "YES" confirmation to execute
- **Cool-down**: Optional automatic trading pause after large realized losses
- **What-if Simulations**: Preview position changes before executing
- **Performance Analytics**: Track P&L by theme, roll success, execution quality—read-only, no autonomous strategy changes
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
- **What-if simulations**: *"What if I trim moonshot to 25%?"*, *"What if I rebalance now?"* — simulate position changes without executing
- **Emergency controls**: `/pause` — immediately stop all trading (toggle on/off)
- **Performance analytics**: *"Show performance summary"*, *"How are the themes performing?"* — P&L by theme, roll analysis, execution quality

### Task queue (do-work)

The repo uses the **do-work** skill for Claude Code task management: capture requests fast, process later.

- **Capture**: `do work add ...` — creates request files; place or move pending REQs in `do-work/pending/`.
- **Process**: `do work run` — triages and works through the queue (simple → implement; medium → explore then build; complex → plan, explore, build).
- **Verify**: `do work verify` — checks captured REQs against original input.
- **Cleanup**: `do work cleanup` — consolidates archive (runs automatically at end of work loop).

Structure: `do-work/pending/` (pending REQs), `do-work/user-requests/` (verbatim input per request), `do-work/working/` (in progress), `do-work/archive/` (completed). Skill is installed at `.agents/skills/do-work`.

**Pending (in queue):** All pending REQs live in `do-work/pending/`: REQ-010 (universal accessibility feature map), REQ-013 (config persistence), REQ-014 (proactive alerts), REQ-015 (daily briefing), REQ-016 (export trades/performance), REQ-017 (product backlog). When you run `do work run`, process from here; when a REQ is completed, move it to `archive/<user-request>/`.

**Completed (archived):** All completed REQs for a user request live under `do-work/archive/<user-request>/` (e.g. `archive/UR-001/`, `archive/UR-002/`). UR-002 completed: REQ-002 through REQ-009, REQ-011, REQ-012 (governance, execution tier, decision compression, transparency, emotional pressure, scenario engine, human control, learning loop, learning-loop persistence, cooldown headless). UR-001 completed: REQ-001 (market data hedge fund chat).

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
- `USE_MAX_PAIN_FOR_SELECTION`: When true, automated option selection prefers the strike closest to max pain within the allowed range (default: true). Options chain data in the Telegram bot includes max pain for informed strategic picks.

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
- `MAX_SINGLE_POSITION_PCT`: Max any single position as % of equity (default: 0.30)
- `MAX_CORRELATED_PCT`: Max combined theme A+B+C allocation (default: 0.60)

### Execution authority
- `EXECUTION_TIER`: `managed` (allow trades) or `read_only` (pause all trading; AI can still read portfolio and recommend). Default: `managed`. Set to `read_only` for emergency pause.

### Human Control & Failure-Mode Mitigations
- `CONFIRM_TRADE_THRESHOLD_USD`: Require confirmation for trades above this notional value (default: 500.0)
- `CONFIRM_TRADE_THRESHOLD_CONTRACTS`: Require confirmation for option trades above this many contracts (default: 10)
- `COOLDOWN_ENABLED`: Enable cool-down after large realized losses (default: false)
- `COOLDOWN_LOSS_THRESHOLD_PCT`: Loss percentage that triggers cool-down (default: 0.10 = 10%)
- `COOLDOWN_LOSS_THRESHOLD_USD`: Loss dollar amount that triggers cool-down (default: 500.0)
- `COOLDOWN_DURATION_MINUTES`: How long to block trading after large loss (default: 60)

**Emergency stop**: Use `/pause` in Telegram to immediately pause all trading (toggle on/off). Trading can also be paused via `EXECUTION_TIER=read_only` in `.env`.

**Trade confirmations**: Large trades (>$500 or >10 contracts by default) require two-step confirmation: bot asks "Reply YES to execute". This prevents accidental large orders.

**Cool-down after loss**: When enabled, if a realized loss exceeds thresholds (10% or $500 by default), bot blocks new trades for 60 minutes. This prevents emotional trading after losses.

**What-if simulations**: Use `what_if_trim` and `what_if_rebalance` tools to preview position changes without executing. Ask the AI: "What if I trim moonshot to 25%?" or "What if I rebalance now?"

**Performance analytics (learning loop)**: The bot tracks trade performance for transparency:
- P&L by theme/moonshot over configurable time period
- Roll analysis (rolled vs held to expiry)
- Execution quality (slippage, favorable vs unfavorable fills)

Access via `get_performance_summary` tool in Telegram. This is read-only analytics—the AI cannot autonomously change strategy, remove governance rules, or increase risk based on this data. Human interprets results and decides on any strategy adjustments.

### Database & Logging
- `DB_PATH`: SQLite path (default: "data/trading_bot.db")
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `LOG_FILE`: Log file path (default: "logs/high_convexity_bot.log")

### Telegram + AI
- `TELEGRAM_BOT_TOKEN`: Bot token from BotFather (required for Telegram bot)
- `OPENAI_API_KEY`: OpenAI API key for AI chat (required for Telegram bot)
- `ALLOWED_TELEGRAM_USER_IDS`: Comma-separated user IDs allowed to execute trades / change config (empty = read-only for all)

### Config Persistence via Telegram

When you update config settings via Telegram (allocations, option rules, theme symbols), changes are automatically saved to `data/config_overrides.json` and persist across restarts.

**Precedence order** (highest to lowest):
1. **Telegram overrides** (`data/config_overrides.json`) - WINS
2. Environment variables (`.env`)
3. Hardcoded defaults (`src/config.py`)

**To view your changes**: Ask the bot "show my config changes" or "what settings did I change?"

**To reset Telegram changes**: Delete `data/config_overrides.json` and restart the bot.

**To force a specific value**: Set it in `.env` and delete `data/config_overrides.json`.

**Best practice**: Use `.env` for initial setup and infrastructure settings. Use Telegram for dynamic strategy adjustments during trading.

### Proactive Alerts (REQ-014)

The bot proactively monitors risk thresholds and warns you before they trigger, giving you time to act.

**Alert Types**:
1. **Kill Switch Warning**: Drawdown approaching -25% trigger (default warning at -20%)
2. **Roll Needed**: Option positions approaching 60 DTE roll trigger (default warning at 67 DTE)
3. **Cap Approaching**: Moonshot allocation approaching 30% cap (default warning at 28%)

**How Alerts Work**:
- Checked during daily run (logged to console)
- Stored in database for Telegram delivery
- Retrieved via "show alerts" or automatically during portfolio analysis
- Cleared after viewing to prevent duplicates

**Alert Configuration** (`.env` or Telegram):
- `PROACTIVE_ALERTS_ENABLED`: Enable/disable alerts (default: true)
- `KILL_SWITCH_WARNING_PCT`: Drawdown warning threshold (default: 0.20 = -20%)
- `ROLL_WARNING_DAYS_BEFORE`: Days before roll trigger to warn (default: 7)
- `CAP_WARNING_THRESHOLD_PCT`: Allocation warning threshold (default: 0.28 = 28%)
- `ALERT_COALESCING_HOURS`: Min hours between duplicate alerts (default: 24)

**Viewing Alerts**:
- Ask the bot: "show alerts", "any warnings?", or "check for alerts"
- Alerts automatically shown during "full portfolio analysis"
- Check daily run logs for `⚠️` warnings

**Disabling Alerts**: Set `PROACTIVE_ALERTS_ENABLED=false` in `.env` to disable all alerts.

**Alert Coalescing**: Each alert type is limited to once per 24 hours (configurable via `ALERT_COALESCING_HOURS`). This prevents spam while ensuring you see critical warnings daily.

### Daily Briefing (REQ-015)

Receive an optional morning briefing via Telegram before market open with portfolio health, today's planned actions, and market context.

**Briefing Content**:
- **Portfolio health**: Equity, change, drawdown %, kill switch status, cash %
- **Today's planned actions**: Preview of rebalance orders (from `run_daily_logic_preview`)
- **Market context**: News summary for SPY/market (optional, AI-summarized)

**Configuration** (`.env`):
- `DAILY_BRIEFING_ENABLED`: Enable/disable feature (default: false)
- `BRIEFING_TIME_HOUR`: Hour to send briefing (default: 9)
- `BRIEFING_TIME_MINUTE`: Minute to send briefing (default: 0)
- `BRIEFING_TIMEZONE`: Timezone for delivery (default: America/New_York)
- `BRIEFING_INCLUDE_MARKET_NEWS`: Include market news section (default: true)

**Telegram Commands**:
- `/briefing on` - Subscribe to daily briefings
- `/briefing off` - Unsubscribe from daily briefings
- `/briefing status` - Check subscription status and timing

**Example**: Set `DAILY_BRIEFING_ENABLED=true` in `.env`, restart the Telegram bot, send `/briefing on` to receive morning updates at 9:00 AM ET each day.

**How It Works**: The bot uses python-telegram-bot's built-in job queue to schedule daily messages. When enabled, subscribed users receive a proactive message at the configured time with fresh portfolio data and market context. The briefing runs in preview mode only—no trades are executed during briefing generation.

## Database

The bot uses SQLite to store:

- **Positions**: Current positions snapshot
- **Orders**: Order history with status, rationale, theme, outcome, and P&L (for analytics)
- **Fills**: Fill details
- **Contracts**: Chosen option contracts
- **Config Snapshots**: Configuration used each run
- **Portfolio Snapshots**: Daily portfolio state
- **Equity History**: Equity over time (for kill switch)
- **Bot State**: Trading pause status, cool-down state, pending confirmations

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
