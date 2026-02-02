"""Telegram trading bot with AI: natural-language commands for portfolio, trades, and strategy."""
import asyncio
import base64
import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import yfinance as yf
from loguru import logger
from openai import OpenAI
from public_api_sdk import InstrumentType
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from src.config import config
from src.main import TradingBot
from src.utils.logger import setup_logging
from src.analytics import PerformanceAnalytics


# --- Tool definitions for OpenAI (function calling) ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_portfolio",
            "description": "Get current portfolio summary: equity, cash, positions, allocation percentages, and per-position detail (for options: DTE, strike vs spot, near_roll/trim_candidate flags). Call when user asks about portfolio, balance, positions, or holdings. Present as bullet points—no markdown tables (Telegram does not support them).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_analysis",
            "description": "Get risk and performance context: equity, high-water mark (HWM), drawdown %, kill switch status and threshold. Call when user asks for full portfolio analysis, recommendations, what to do, or risk/drawdown. Use with get_portfolio and get_allocations to synthesize professional hedge-fund-style analysis.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_allocations",
            "description": "Get current vs target allocations (theme_a, theme_b, theme_c, moonshot, cash) as percentages. Use when user asks about allocation, rebalance, or targets.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_daily_logic_preview",
            "description": "Run the strategy logic in dry-run mode and return the list of orders that WOULD be placed (no real trades). Use for 'what would you do', 'preview', 'simulate', or 'test strategy'.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_daily_logic_and_execute",
            "description": "Run the full daily strategy (exits, rolls, rebalance) and EXECUTE the orders. Only use when the user explicitly asks to run rebalance, execute strategy, or place the planned trades.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "place_manual_trade",
            "description": "Place a single manual trade (buy or sell) for any symbol—not limited to theme underlyings. Use for any equity (e.g. AAPL, TSLA, GME.WS) or option (exact symbol= from get_options_chain). Use when user confirms a recommended trade or says buy/sell X shares/contracts of SYMBOL at price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol to trade (e.g. GME.WS, or option OSI symbol)"},
                    "side": {"type": "string", "enum": ["BUY", "SELL"], "description": "BUY or SELL"},
                    "quantity": {"type": "integer", "description": "Number of shares or contracts"},
                    "limit_price": {"type": "number", "description": "Limit price per share/contract"},
                },
                "required": ["symbol", "side", "quantity", "limit_price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_last_actions",
            "description": "Get last N executed orders with rationale (why each trade was placed). Use when user asks what was done recently, last trades, or trade history with reasons.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of recent orders to return (default 10, max 50)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_config",
            "description": "Get key strategy config: theme underlyings, target allocations, dry_run, kill switch, max trades per day.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_dry_run",
            "description": "Turn dry-run mode on or off. When on, no real orders are placed. Use when user says enable/disable dry run, paper trading, or test mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean", "description": "True to enable dry-run (no real trades), False to allow real trades"},
                },
                "required": ["enabled"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_news",
            "description": "Fetch recent market or ticker news (headlines, links). Use for any question about market news, earnings, sector news, or what's happening with a stock/symbol. Symbol can be a ticker (e.g. AAPL, TSLA) or a topic (e.g. 'oil', 'Fed', 'earnings').",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_or_topic": {"type": "string", "description": "Ticker symbol (e.g. AAPL, GME) or topic (e.g. 'stock market', 'Fed'). Use 'market' or 'SPY' for general market news."},
                },
                "required": ["symbol_or_topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_option_expirations",
            "description": "Get all available option expiration dates for any underlying symbol (e.g. AAPL, TSLA, UMC). Returns every expiration date the API provides. Use when user asks about expirations or which dates are available for options on a stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "underlying_symbol": {"type": "string", "description": "Underlying ticker (e.g. AAPL, UMC, GME)"},
                },
                "required": ["underlying_symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_options_chain",
            "description": "Get complete option chain (all calls and all puts) for any underlying ticker (e.g. AAPL, TSLA, UMC, NVDA)—not limited to theme symbols. Returns spot, max pain (strike at which option holder value at expiration is minimized—often a price magnet), and per contract: strike, symbol (use for place_manual_trade), bid, ask, mid, OI, vol. Use max pain for informed strategic picks: e.g. selling premium near max pain, expecting pin risk, or bullish above / bearish below. If no expiration given, uses nearest expiration. Always call before recommending an option trade.",
            "parameters": {
                "type": "object",
                "properties": {
                    "underlying_symbol": {"type": "string", "description": "Underlying ticker (e.g. AAPL, UMC)"},
                    "expiration_yyyy_mm_dd": {"type": "string", "description": "Expiration date YYYY-MM-DD (optional). If omitted, use nearest available expiration."},
                },
                "required": ["underlying_symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_allocation_targets",
            "description": "Update target allocation percentages for the strategy (theme_a, theme_b, theme_c, moonshot, cash). Use when user wants to change how much to allocate to each bucket, e.g. 'set theme A to 40%', 'I want 30% cash'. Values are 0-100 (percent). Only provide params to change; omit others.",
            "parameters": {
                "type": "object",
                "properties": {
                    "theme_a_pct": {"type": "number", "description": "Theme A target allocation (0-100)"},
                    "theme_b_pct": {"type": "number", "description": "Theme B target allocation (0-100)"},
                    "theme_c_pct": {"type": "number", "description": "Theme C target allocation (0-100)"},
                    "moonshot_pct": {"type": "number", "description": "Moonshot target allocation (0-100)"},
                    "cash_pct": {"type": "number", "description": "Minimum cash allocation (0-100)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_option_rules",
            "description": "Update option selection rules: DTE range (days to expiration) and strike range (multipliers: 1.0 = ATM, 1.10 = 10% OTM). Use when user says e.g. 'only buy 60-90 DTE', 'ATM to 5% OTM', 'use 45-120 DTE'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dte_min": {"type": "integer", "description": "Minimum days to expiration"},
                    "dte_max": {"type": "integer", "description": "Maximum days to expiration"},
                    "strike_range_min": {"type": "number", "description": "Strike multiplier min (1.0 = ATM, 1.05 = 5% OTM)"},
                    "strike_range_max": {"type": "number", "description": "Strike multiplier max (e.g. 1.10 = 10% OTM)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_theme_symbols",
            "description": "Update the theme underlying symbols for the automated rebalance only (comma-separated, e.g. UMC,TE,AMPX). Use when user says 'set theme underlyings to X,Y,Z'. Does not restrict manual suggestions or place_manual_trade—those can use any symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols_comma_separated": {"type": "string", "description": "Comma-separated list of symbols for theme A, B, C (e.g. 'UMC,TE,AMPX' or 'AAPL,MSFT,GOOGL')"},
                },
                "required": ["symbols_comma_separated"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_config_overrides",
            "description": "Show which config settings have been customized via Telegram (vs .env defaults). Use when user asks 'what settings did I change?', 'show my config changes', 'what's different from default?', or 'what overrides are active?'.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_polymarket_odds",
            "description": "Fetch Polymarket prediction market odds (implied probabilities). Use when user asks about Polymarket, prediction markets, event odds, or wants to factor prediction-market probabilities into options/market context (e.g. Fed, elections, Bitcoin, macro events).",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Optional topic to filter by (e.g. 'Fed', 'Bitcoin', 'election', 'Trump'). Leave empty for a sample of active markets."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scenario",
            "description": "Run price scenario analysis for current positions in an underlying. Shows position value at different price points and worst/best case outcomes. Use when user asks 'What if GME goes to $60?', 'How much should I hold?', or wants position risk analysis at specific price levels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Underlying symbol to analyze (e.g. GME, AAPL, UMC)"},
                    "price_points": {"type": "array", "items": {"type": "number"}, "description": "List of price points to analyze (e.g. [30, 50, 60, 100])"},
                },
                "required": ["symbol", "price_points"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "what_if_position",
            "description": "Analyze hypothetical position value at different price points. Shows what would happen if you held X shares/contracts at different underlying prices. Use when user asks 'What if I bought 100 shares' or wants to model position scenarios before trading.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol for the hypothetical position"},
                    "quantity": {"type": "integer", "description": "Number of shares or contracts"},
                    "price_points": {"type": "array", "items": {"type": "number"}, "description": "List of underlying price points to analyze"},
                    "is_option": {"type": "boolean", "description": "True if analyzing an option position, False for equity"},
                    "strike": {"type": "number", "description": "Strike price (required if is_option=True)"},
                    "expiration": {"type": "string", "description": "Expiration date YYYY-MM-DD (required if is_option=True)"},
                },
                "required": ["symbol", "quantity", "price_points"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "option_payoff_analysis",
            "description": "Calculate option payoff at expiration across price range. Shows intrinsic value at different underlying prices at expiry. Use when user asks about option payoff, breakeven analysis, or wants to see how an option performs at expiration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "osi_symbol": {"type": "string", "description": "Option symbol in OSI format (use exact symbol from get_options_chain)"},
                    "min_price": {"type": "number", "description": "Minimum underlying price for analysis (optional, auto-calculated if not provided)"},
                    "max_price": {"type": "number", "description": "Maximum underlying price for analysis (optional, auto-calculated if not provided)"},
                },
                "required": ["osi_symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "what_if_trim",
            "description": "Simulate trimming a position to a target percentage. Shows what would happen if you reduced a position to X% allocation: how many shares/contracts to sell, at what price, resulting allocation. Use for 'what if I trim moonshot to 25%' or position sizing questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol to trim (e.g. GME.WS, AAPL)"},
                    "target_pct": {"type": "number", "description": "Target allocation percentage (0-100, e.g. 25 for 25%)"},
                },
                "required": ["symbol", "target_pct"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "what_if_rebalance",
            "description": "Simulate a full rebalance without executing. Shows what orders would be placed to bring portfolio to target allocations. Use for 'what if I rebalance now' or 'show me rebalance impact' questions.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_performance_summary",
            "description": "Get performance analytics: P&L by theme/moonshot, roll analysis, execution quality (slippage, favorable fills). Use when user asks about performance, what's working, trade quality, or wants to review results. Read-only analytics—does not change strategy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Number of days to analyze (default 30, max 365)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_alerts",
            "description": "Get pending proactive alerts (kill switch warnings, positions needing rolls, allocation caps approaching). Always call during portfolio analysis to check for risk warnings. Clears alerts after retrieval.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM_PROMPT = """You are a **professional hedge fund manager** AI for a high-convexity options/equity portfolio connected to Public.com. The user talks to you via Telegram. Your role: synthesize portfolio, risk, and market data; give **clear, actionable recommendations** with rationale; and explain in concise, institutional language where appropriate.

**Persona:** Act as the portfolio manager. When the user asks for "full portfolio analysis", "recommendations", "what should I do", or "risk/drawdown", you must:
1. Call **get_portfolio** (positions, allocations, DTE/strike/roll-trim flags), **get_allocations** (current vs target), **get_config** (strategy and kill switch), **get_portfolio_analysis** (equity, high-water mark, drawdown %, kill switch status), and **get_alerts** (proactive warnings for approaching thresholds).
2. Optionally call **run_daily_logic_preview** to see what the strategy would do (orders) and **get_market_news** / **get_options_chain** / **get_polymarket_odds** for context.
3. Synthesize one response with sections: **Portfolio & Risk** (equity, HWM, drawdown, kill switch), **Allocations** (current vs target, drift), **Positions** (highlights: near_roll, trim_candidate, P/L), **Recommendations** (what to do now: rebalance, trim, roll, wait; when to act vs wait; optional trade ideas with data source and limit guidance).

**Recommendations:** Be concrete. No ambiguity—use numbers. Examples: "Hold 90–110 warrants." "Trim moonshot to 25%—currently over cap." "Roll UMC calls—DTE &lt; 60." "Exit if drawdown &gt; 40%." "Run rebalance to bring theme_a up to target." "Wait until after earnings to add; use get_options_chain then for fresh strikes."

**Emotional pressure:** Never amplify desperation. When you detect desperation language—"I need to win back", "all in", "can't afford to lose", "must", "last chance", "YOLO", "desperate", "broke", "final shot"—immediately reframe emotion into structure:

1. **Convert emotion → numbers**: Use ranges ("2-5% position size"), probabilities ("60% chance"), caps ("max $1000 risk"), specific targets ("trim to 20%").
2. **Never suggest increasing size or risk to "catch up"**: No doubling down, revenge trades, or higher leverage when stressed.
3. **Use risk context**: Call get_portfolio_analysis to check current drawdown and kill switch status. If drawdown > 20% or kill switch active, suggest "Given current drawdown, consider waiting" or "With kill switch active, focus on preservation."
4. **Suggest cooling off**: When high stress detected, recommend reducing exposure ("trim by 50%"), stepping away ("wait 24-48 hours"), or paper trading only.
5. **Compress desperation into structure**: Transform "I'm all in on this trade" → "Consider 5-10% allocation with defined exit at -20% loss."

You are fully capable of:
1) **Market news and assets**: get_market_news(symbol_or_topic) for headlines; discuss earnings, sectors, Fed, macro, any ticker.
2) **Options chains**: get_option_expirations and get_options_chain for **any** underlying (AAPL, TSLA, UMC, NVDA). Chain includes **max pain**—use for strategic picks (pin risk, bullish above / bearish below). Discuss strikes, bid/ask, liquidity.
3) **Polymarket**: get_polymarket_odds(topic) for prediction-market probabilities; factor into options/market context.
4) **Images → strategy**: You have vision. Any image (chart, screenshot, etc.): interpret, derive a strategy (themes, allocations, DTE/strike, trades), summarize, and implement via update_allocation_targets, update_option_rules, update_theme_symbols, place_manual_trade, or run_daily_logic_*. Never say the image is irrelevant—always derive a strategy.
5) **Strategy edits**: update_allocation_targets, update_option_rules, update_theme_symbols—only change what the user asked.
6) **Deep research**: For "what's going on with X" or broad context, call get_portfolio, get_allocations, get_portfolio_analysis, get_market_news, get_polymarket_odds, get_options_chain (as needed), get_config; then synthesize one note (context, implications, risks, optional trade ideas).

**Manual trades:** You can suggest and place trades (place_manual_trade) for **any** equity or option—not limited to theme symbols. Theme underlyings only define automated rebalance; they do not restrict your suggestions or orders.

**Scenario analysis:** Use scenario tools to answer "How much should I hold?" with concrete numbers. Available tools: get_scenario(symbol, price_points) for current position analysis at different prices; what_if_position(symbol, quantity, price_points) for hypothetical position modeling; option_payoff_analysis(osi_symbol) for option payoff at expiration. Use when users ask "What if GME goes to $60?", "How much risk am I taking?", or want position sizing guidance.

**Performance analytics (learning loop):** You have access to performance data via get_performance_summary (P&L by theme, roll analysis, execution quality). Use this to inform discussion and identify what's working. CRITICAL CONSTRAINTS: (1) Never suggest removing or loosening governance rules (kill switch, max position size, cash buffer, no margin). (2) Never suggest increasing position size, leverage, or risk after losses—only de-risking is allowed when drawdown is high. (3) Never invent new strategies or change core strategy logic autonomously—human decides on strategy changes. (4) Performance data is for transparency and informed discussion only; it does not authorize autonomous strategy modification.

Tools: get_portfolio, get_portfolio_analysis, get_allocations, run_daily_logic_preview, run_daily_logic_and_execute, place_manual_trade, get_config, set_dry_run, get_market_news, get_option_expirations, get_options_chain, get_polymarket_odds, get_scenario, what_if_position, option_payoff_analysis, get_performance_summary, update_*.

Never make up data—use the tools. For trades, confirm and summarize.

**Option trade accuracy:** (1) Always call get_options_chain (and get_option_expirations if needed) in the same turn before recommending any option trade. (2) Quote only numbers from the tool output (spot, max pain, bid, ask, mid). (3) Suggest limit at ask: "limit at current ask $X (from chain)". (4) place_manual_trade: use the exact option symbol from get_options_chain. If the user confirms much later, call get_options_chain again before placing.

**Format (Telegram):**
- One main title with # (e.g. # Portfolio Analysis & Recommendations).
- ## for major sections: ## Portfolio & Risk, ## Allocations, ## Recommendations.
- **Bold** for key numbers and terms.
- Bullet points; no markdown tables (Telegram does not support them). Use • SYMBOL — qty X, mv $Y, pnl Z% for positions."""


# Fixed keyboard shown on /start (user can still type custom messages)
START_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Full analysis"), KeyboardButton("Recommendations")],
        [KeyboardButton("Portfolio summary"), KeyboardButton("Run rebalance")],
        [KeyboardButton("Preview rebalance"), KeyboardButton("Show config")],
        [KeyboardButton("Options chain"), KeyboardButton("Market news")],
        [KeyboardButton("Polymarket odds"), KeyboardButton("Deep research")],
    ],
    resize_keyboard=True,
)

# Telegram keyboard button label limit is 64 bytes; we use 40 chars so phrases stay complete
MAX_KEYBOARD_BUTTON_CHARS = 40

# Conversation memory: keep last N messages per user (user + assistant pairs)
CHAT_HISTORY_MAX_MESSAGES = 10  # 5 exchanges
CHAT_HISTORY_KEY = "chat_history"

SUGGESTIONS_SYSTEM = """You suggest short follow-up prompts for a trading chat. You will receive the last user message and the assistant's reply. Suggest exactly 3 or 4 short phrases the user might naturally say next. Rules: each phrase must be COMPLETE (full words, no cut-off); max 40 characters per phrase; one phrase per line; no numbering, bullets, or quotes. Examples of complete phrases: "Run rebalance", "Options chain TSLA", "Set theme A to 40%", "Polymarket Fed", "Deep research AAPL", "What would strategy do?". Base suggestions on the current context."""


def _truncate_at_word(s: str, max_len: int) -> str:
    """Truncate to max_len at last complete word so the string is never cut mid-word."""
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    truncated = s[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        return truncated[:last_space].strip()
    return truncated.strip()


def _build_suggestions_keyboard(labels: List[str], max_per_button: int = MAX_KEYBOARD_BUTTON_CHARS) -> ReplyKeyboardMarkup:
    """Build reply keyboard from button labels; 2 per row. Labels truncated at word boundary so never cut mid-word."""
    buttons = []
    for s in labels[:6]:
        s = _truncate_at_word(s.strip() if s else "", max_per_button)
        if s:
            buttons.append(KeyboardButton(s))
    if not buttons:
        return START_KEYBOARD
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


async def _get_ai_suggestions(
    openai_client: OpenAI,
    user_message_text: str,
    assistant_reply: str,
) -> List[str]:
    """Ask AI for 3-4 short follow-up suggestions based on the current conversation context."""
    if not assistant_reply or len(assistant_reply) > 2500:
        return []
    context = f"User: {user_message_text[:500]}\n\nAssistant: {assistant_reply[:2500]}"
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SUGGESTIONS_SYSTEM},
                {"role": "user", "content": context},
            ],
            max_tokens=150,
        )
        content = (resp.choices[0].message.content or "").strip()
        # Strip numbering/bullets so we get complete phrases only (e.g. "1. Run rebalance" -> "Run rebalance")
        lines = []
        for ln in content.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            # Remove leading "1.", "1)", "- ", "• ", etc.
            ln = re.sub(r"^\s*[\d]+[.)]\s*", "", ln)
            ln = re.sub(r"^\s*[-•*]\s*", "", ln)
            ln = ln.strip()
            # Remove surrounding quotes so button shows "Run rebalance" not "\"Run rebalance\""
            if len(ln) >= 2 and (ln[0] == '"' and ln[-1] == '"' or ln[0] == "'" and ln[-1] == "'"):
                ln = ln[1:-1].strip()
            if ln:
                lines.append(ln)
        return lines[:4]
    except Exception as e:
        logger.debug("AI suggestions failed: %s", e)
        return []


def _markdown_to_telegram_html(text: str) -> str:
    """Convert markdown to Telegram HTML: headers, bold, links, escape entities.
    Uses hierarchy: # = section (bold+underline), ## = subsection (bold), ### = minor header.
    """
    if not text:
        return text
    s = text
    # Links first: [text](url) -> <a href="url">text</a> (before escaping)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    # Escape HTML entities
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Restore our <a> and <b>, <i>, <u> tags (we escaped them; undo for tags we produce)
    s = re.sub(r"&lt;a href=\"([^\"]+)\"&gt;(.+?)&lt;/a&gt;", r'<a href="\1">\2</a>', s, flags=re.DOTALL)
    s = re.sub(r"&lt;b&gt;(.+?)&lt;/b&gt;", r"<b>\1</b>", s, flags=re.DOTALL)
    s = re.sub(r"&lt;i&gt;(.+?)&lt;/i&gt;", r"<i>\1</i>", s, flags=re.DOTALL)
    s = re.sub(r"&lt;u&gt;(.+?)&lt;/u&gt;", r"<u>\1</u>", s, flags=re.DOTALL)
    # Headers: match from most # to least for correct hierarchy
    # ### minor header
    s = re.sub(r"^###\s+(.+?)(?=\n|$)", r"\n<b>\1</b>\n", s, flags=re.MULTILINE)
    # ## subsection
    s = re.sub(r"^##\s+(.+?)(?=\n|$)", r"\n\n<b>\1</b>\n", s, flags=re.MULTILINE)
    # # main section (bold + underline for clear separation)
    s = re.sub(r"^#\s+(.+?)(?=\n|$)", r"\n\n<b><u>\1</u></b>\n", s, flags=re.MULTILINE)
    # Bold and italic (after headers so ** in headers are already wrapped)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)  # single * italic
    # Bullet lines: ensure "- " or "• " at line start are visually consistent (add zero-width space after bullet so Telegram doesn't strip)
    s = re.sub(r"^([-•])\s+", r"\1 ", s, flags=re.MULTILINE)
    # Horizontal rule / excess newlines: cap at 2 consecutive
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _can_execute_trades(user_id: int) -> bool:
    """True if user is allowed to execute trades or change config."""
    allowed = config.allowed_telegram_user_id_list
    if not allowed:
        return True  # no restriction
    return user_id in allowed


def _check_and_trigger_cooldown(bot_instance: TradingBot, fill_details: Dict) -> Optional[str]:
    """REQ-008: Check if a fill triggers cool-down due to large loss. Returns message if cool-down triggered.

    Args:
        bot_instance: Trading bot instance
        fill_details: Fill details dict with symbol, quantity, fill_price

    Returns:
        Message string if cool-down triggered, None otherwise
    """
    if not config.cooldown_enabled:
        return None

    try:
        symbol = fill_details.get("symbol", "")
        fill_price = fill_details.get("fill_price", 0)
        quantity = fill_details.get("quantity", 0)
        side = fill_details.get("side") or fill_details.get("action", "")

        # Only check on SELL/exit orders (realized loss)
        if side.upper() != "SELL":
            return None

        # Get position entry price from storage or portfolio
        pm = bot_instance.portfolio_manager
        if symbol in pm.positions:
            pos = pm.positions[symbol]
            entry_price = pos.entry_price
        else:
            # Position might be closed; try to get from recent orders
            recent_orders = bot_instance.storage.get_recent_orders(limit=50)
            buys = [o for o in recent_orders if o.get("symbol") == symbol and o.get("side", "").upper() == "BUY" and o.get("status") == "FILLED"]
            if not buys:
                return None
            entry_price = buys[0].get("limit_price", fill_price)  # Use most recent buy

        # Calculate P&L
        pnl_per_share = fill_price - entry_price
        pnl_total = pnl_per_share * quantity
        pnl_pct = (pnl_per_share / entry_price) if entry_price > 0 else 0

        # Check thresholds
        loss_pct_threshold = -abs(config.cooldown_loss_threshold_pct)
        loss_usd_threshold = -abs(config.cooldown_loss_threshold_usd)

        if pnl_pct <= loss_pct_threshold or pnl_total <= loss_usd_threshold:
            # Trigger cool-down
            cooldown_until = datetime.now() + timedelta(minutes=config.cooldown_duration_minutes)
            bot_instance.storage.set_cooldown_until(cooldown_until)
            logger.warning(
                f"Cool-down triggered: {symbol} loss {pnl_pct*100:.1f}% (${pnl_total:.2f}). "
                f"Blocking trades until {cooldown_until.isoformat()}"
            )
            return (
                f"\n\n🕒 **Cool-down activated**: Large loss detected ({pnl_pct*100:.1f}%, ${pnl_total:.2f}). "
                f"No new trades for {config.cooldown_duration_minutes} minutes to prevent emotional trading."
            )

    except Exception as e:
        logger.exception("Cool-down check failed")

    return None


def _parse_strike_from_osi(symbol: str) -> Optional[float]:
    """Parse strike price from OSI option symbol (e.g. UMC260220C00001000 or AMPX260320C00014000-OPTION)."""
    if not symbol:
        return None
    clean = re.sub(r"-OPTION$", "", str(symbol).strip()).upper()
    # OSI: underlying(6) + YYMMDD + C/P + 8-digit strike (strike * 1000)
    match = re.match(r"^[A-Z]+(\d{6})(?:[CP])(\d{8})$", clean)
    if match:
        try:
            return int(match.group(2)) / 1000.0
        except (ValueError, TypeError):
            pass
    return None


def _safe_float(value: Any) -> Optional[float]:
    """Convert API value (Decimal, str, int, float) to float; return None if invalid."""
    if value is None:
        return None
    try:
        if hasattr(value, "__float__"):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def run_tool(tool_name: str, arguments: Dict[str, Any], bot_instance: TradingBot, user_id: int) -> str:
    """Execute a tool by name and return a string result. Runs sync bot code in caller thread."""
    try:
        if tool_name == "get_portfolio":
            bot_instance.portfolio_manager.refresh_portfolio()
            pm = bot_instance.portfolio_manager
            eq = pm.get_equity()
            cash = pm.get_cash()
            bp = pm.get_buying_power()
            alloc = pm.get_current_allocations()
            lines = [
                f"Equity: ${eq:,.2f}",
                f"Cash: ${cash:,.2f}",
                f"Buying power: ${bp:,.2f}",
                "Allocations: theme_a={:.1f}% theme_b={:.1f}% theme_c={:.1f}% moonshot={:.1f}% cash={:.1f}%".format(
                    alloc["theme_a"] * 100, alloc["theme_b"] * 100, alloc["theme_c"] * 100,
                    alloc["moonshot"] * 100, alloc["cash"] * 100,
                ),
                "Positions:",
            ]
            for sym, pos in pm.positions.items():
                price = pm.get_position_price(pos)
                mv = pos.get_market_value(price)
                pnl = pos.get_pnl_pct(price)
                extra = []
                if pos.instrument_type == InstrumentType.OPTION:
                    dte = pos.get_dte()
                    if dte is not None:
                        extra.append(f"DTE={dte}")
                    if pos.underlying and pos.strike is not None:
                        spot_raw = pm.data_manager.get_quote(pos.underlying)
                        spot = _safe_float(spot_raw) if spot_raw is not None else None
                        if spot and spot > 0:
                            strike_vs = (pos.strike / spot - 1) * 100
                            extra.append(f"strike_vs_spot={strike_vs:.1f}%")
                    if dte is not None and dte < config.roll_trigger_dte:
                        extra.append("near_roll")
                if pos.symbol == config.moonshot_symbol and alloc.get("moonshot", 0) > config.moonshot_max:
                    extra.append("trim_candidate")
                line = f"  {sym}: qty={pos.quantity} @ ${price:.2f} mv=${mv:.2f} pnl={pnl:.1f}%"
                if extra:
                    line += "  [" + " ".join(extra) + "]"
                lines.append(line)
            return "\n".join(lines)

        if tool_name == "get_portfolio_analysis":
            bot_instance.portfolio_manager.refresh_portfolio()
            equity = bot_instance.portfolio_manager.get_equity()
            bot_instance.storage.save_equity_history(equity)
            high_equity = bot_instance.storage.get_equity_high_last_n_days(config.kill_switch_lookback_days)
            if high_equity is None or high_equity <= 0:
                return (
                    f"Equity: ${equity:,.2f}. No high-water mark in last {config.kill_switch_lookback_days} days yet; "
                    f"kill switch threshold: {config.kill_switch_drawdown_pct*100:.0f}% drawdown over {config.kill_switch_lookback_days}d."
                )
            drawdown_pct = (equity - high_equity) / high_equity
            kill_active = drawdown_pct <= -config.kill_switch_drawdown_pct
            return (
                f"Equity: ${equity:,.2f}  High-water mark ({config.kill_switch_lookback_days}d): ${high_equity:,.2f}\n"
                f"Drawdown: {drawdown_pct*100:.2f}%\n"
                f"Kill switch: {'ACTIVE (no new positions)' if kill_active else 'inactive'} "
                f"(threshold: {config.kill_switch_drawdown_pct*100:.0f}% drawdown)"
            )

        if tool_name == "get_allocations":
            bot_instance.portfolio_manager.refresh_portfolio()
            current = bot_instance.portfolio_manager.get_current_allocations()
            target = bot_instance.portfolio_manager.get_target_allocations()
            lines = ["Current -> Target:"]
            for k in ["theme_a", "theme_b", "theme_c", "moonshot", "cash"]:
                lines.append(f"  {k}: {current[k]*100:.1f}% -> {target[k]*100:.1f}%")
            return "\n".join(lines)

        if tool_name == "get_last_actions":
            limit = min(int(arguments.get("limit", 10) or 10), 50)
            orders = bot_instance.storage.get_recent_orders(limit=limit)
            if not orders:
                return "No executed orders on record."
            lines = [f"Last {len(orders)} order(s):"]
            for o in orders:
                side = o.get("side") or o.get("action", "")
                symbol = o.get("symbol", "")
                qty = o.get("quantity", 0)
                status = o.get("status", "")
                rationale = o.get("rationale") or ""
                created = o.get("created_at", "")[:19] if o.get("created_at") else ""
                line = f"  {side} {symbol} x{qty} -> {status}"
                if created:
                    line += f" ({created})"
                if rationale:
                    line += f" — {rationale}"
                lines.append(line)
            return "\n".join(lines)

        if tool_name == "run_daily_logic_preview":
            bot_instance.portfolio_manager.refresh_portfolio()
            # Temporarily force dry_run so no real orders
            old_dry = config.dry_run
            config.dry_run = True
            try:
                orders = bot_instance.strategy.run_daily_logic()
            finally:
                config.dry_run = old_dry
            if not orders:
                return "No actions: portfolio within targets and rules."
            lines = ["Planned orders (dry-run, not executed):"]
            for i, o in enumerate(orders, 1):
                action = o.get("action", "")
                symbol = o.get("symbol", "")
                qty = o.get("quantity", 0)
                price = o.get("price", 0)
                rationale = o.get("rationale", "")
                line = f"  {i}. {action} {symbol} x{qty} @ ${price:.2f}"
                if rationale:
                    line += f" — {rationale}"
                lines.append(line)
            return "\n".join(lines)

        if tool_name == "run_daily_logic_and_execute":
            if config.execution_tier.lower() == "read_only":
                return "Trading paused; read-only mode. Set EXECUTION_TIER=managed in .env to allow trades."
            if not _can_execute_trades(user_id):
                return "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS. Add your ID to .env to execute trades."
            # REQ-008: Check pause state
            if bot_instance.storage.is_trading_paused():
                return "⛔ Trading is PAUSED. Use /pause to resume trading before executing orders."
            # REQ-008: Check cool-down
            if bot_instance.storage.is_in_cooldown():
                cooldown_until = bot_instance.storage.get_cooldown_until()
                time_left = (cooldown_until - datetime.now()).total_seconds() / 60 if cooldown_until else 0
                return f"🕒 Cool-down active. Trading blocked for {time_left:.0f} more minutes after recent large loss. This is a safety feature to prevent emotional trading."
            bot_instance.portfolio_manager.refresh_portfolio()
            orders = bot_instance.strategy.run_daily_logic()
            if not orders:
                return "No orders to execute; portfolio already in line with targets."
            results = []
            cooldown_msg = None
            for order_details in orders:
                if bot_instance.strategy.trades_today >= config.max_trades_per_day:
                    results.append("Max trades per day reached; stopping.")
                    break
                result = bot_instance.execution_manager.execute_order(order_details)
                if result:
                    bot_instance.storage.save_order({**order_details, **result})
                    order_status = (result.get("status") or "").upper()
                    if order_status == "FILLED":
                        bot_instance.storage.update_order_status(
                            result["order_id"], "FILLED", datetime.now(timezone.utc).isoformat()
                        )
                        fill_details = {
                            "order_id": result["order_id"],
                            "symbol": result["symbol"],
                            "quantity": result["quantity"],
                            "fill_price": result["price"],
                            "side": result.get("action", order_details.get("action")),
                        }
                        bot_instance.storage.save_fill(fill_details)

                        # REQ-011: Compute realized P&L for SELL orders
                        action = order_details.get("action", "").upper()
                        if action == "SELL" and "entry_price" in order_details:
                            entry_price = order_details["entry_price"]
                            fill_price = result["price"]
                            quantity = result["quantity"]
                            realized_pnl = (fill_price - entry_price) * quantity
                            outcome = "win" if realized_pnl > 0 else "loss"

                            # Update the saved order with realized P&L and outcome
                            bot_instance.storage.save_order({
                                **order_details,
                                **result,
                                "realized_pnl": realized_pnl,
                                "outcome": outcome,
                            })

                            logger.info(
                                f"Realized P&L: ${realized_pnl:,.2f} ({outcome}) "
                                f"on {result.get('symbol')}"
                            )

                        # REQ-008: Check if this fill triggers cool-down
                        if not cooldown_msg:  # Only check once per execution
                            cooldown_msg = _check_and_trigger_cooldown(bot_instance, fill_details)
                        bot_instance.strategy.trades_today += 1
                    # Show status clearly; if not FILLED, say still open; include rationale for transparency
                    line = f"Order: {result.get('action')} {result.get('symbol')} x{result.get('quantity')} -> {order_status}"
                    if order_status != "FILLED":
                        line += " (still open; may fill later)"
                    if order_details.get("rationale"):
                        line += f" — {order_details['rationale']}"
                    results.append(line)
                else:
                    results.append(f"Failed: {order_details}")
            response = "\n".join(results)
            if cooldown_msg:
                response += cooldown_msg
            return response

        if tool_name == "place_manual_trade":
            if config.execution_tier.lower() == "read_only":
                return "Trading paused; read-only mode. Set EXECUTION_TIER=managed in .env to place trades."
            if not _can_execute_trades(user_id):
                return "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS. Add your ID to .env to place trades."
            # REQ-008: Check pause state
            if bot_instance.storage.is_trading_paused():
                return "⛔ Trading is PAUSED. Use /pause to resume trading before placing orders."
            # REQ-008: Check cool-down
            if bot_instance.storage.is_in_cooldown():
                cooldown_until = bot_instance.storage.get_cooldown_until()
                time_left = (cooldown_until - datetime.now()).total_seconds() / 60 if cooldown_until else 0
                return f"🕒 Cool-down active. Trading blocked for {time_left:.0f} more minutes after recent large loss. This is a safety feature to prevent emotional trading."
            symbol = arguments.get("symbol", "").strip()
            side = (arguments.get("side") or "BUY").upper()
            quantity = int(arguments.get("quantity", 0))
            limit_price = float(arguments.get("limit_price", 0))
            if not symbol or quantity <= 0 or limit_price <= 0:
                return "Invalid: symbol, quantity, and limit_price must be set and positive."

            # REQ-008: Check if confirmation needed for large trades
            is_option = symbol.endswith("-OPTION") or (len(symbol) > 10 and symbol[:10].isalpha())
            notional = quantity * limit_price
            needs_confirm = False
            confirm_reason = ""

            if notional > config.confirm_trade_threshold_usd:
                needs_confirm = True
                confirm_reason = f"trade value ${notional:,.2f} exceeds ${config.confirm_trade_threshold_usd:,.0f} threshold"
            elif is_option and quantity > config.confirm_trade_threshold_contracts:
                needs_confirm = True
                confirm_reason = f"{quantity} contracts exceeds {config.confirm_trade_threshold_contracts} contract threshold"

            if needs_confirm:
                # Store pending confirmation in bot state
                confirmation_key = f"pending_trade_{user_id}"
                trade_data = json.dumps({
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "limit_price": limit_price,
                    "notional": notional,
                })
                bot_instance.storage.set_bot_state(confirmation_key, trade_data)

                return (
                    f"⚠️ **Large trade confirmation required**\n\n"
                    f"Trade: {side} {quantity} {'contracts' if is_option else 'shares'} of {symbol} at ${limit_price:.2f}\n"
                    f"Notional: ${notional:,.2f}\n"
                    f"Reason: {confirm_reason}\n\n"
                    f"Reply with **YES** to execute this trade, or anything else to cancel."
                )

            is_option = symbol.endswith("-OPTION") or (len(symbol) > 10 and symbol[:10].isalpha())
            order_details = {
                "action": side,
                "symbol": symbol,
                "quantity": quantity,
                "price": limit_price,
                "rationale": f"Manual trade via Telegram",
            }

            # REQ-011: Derive theme and add entry_price for SELL orders
            theme = None
            entry_price = None
            if side.upper() == "SELL":
                # Get entry price from existing position
                bot_instance.portfolio_manager.refresh_portfolio()
                pm = bot_instance.portfolio_manager
                if symbol in pm.positions:
                    position = pm.positions[symbol]
                    entry_price = position.entry_price
                    # Derive theme from underlying
                    underlying = position.underlying or symbol
                    theme = bot_instance.strategy.get_theme_for_underlying(underlying)
                    order_details["entry_price"] = entry_price

            if theme:
                order_details["theme"] = theme

            result = bot_instance.execution_manager.execute_order(order_details)
            if result:
                # Save order to storage
                bot_instance.storage.save_order({**order_details, **result})

                order_status = (result.get("status") or "").upper()
                if order_status == "FILLED":
                    # Update order status
                    bot_instance.storage.update_order_status(
                        result["order_id"], "FILLED", datetime.now(timezone.utc).isoformat()
                    )
                    # Save fill
                    bot_instance.storage.save_fill({
                        "order_id": result["order_id"],
                        "symbol": result["symbol"],
                        "quantity": result["quantity"],
                        "fill_price": result["price"],
                    })

                    # REQ-011: Compute realized P&L for SELL orders
                    if side.upper() == "SELL" and entry_price:
                        fill_price = result["price"]
                        qty = result["quantity"]
                        realized_pnl = (fill_price - entry_price) * qty
                        outcome = "win" if realized_pnl > 0 else "loss"

                        # Update the saved order with realized P&L and outcome
                        bot_instance.storage.save_order({
                            **order_details,
                            **result,
                            "realized_pnl": realized_pnl,
                            "outcome": outcome,
                        })

                        logger.info(
                            f"Manual trade realized P&L: ${realized_pnl:,.2f} ({outcome}) "
                            f"on {result.get('symbol')}"
                        )

                    bot_instance.strategy.trades_today += 1

                msg = f"Order placed: {result.get('action')} {result.get('symbol')} x{result.get('quantity')} @ ${result.get('price')} -> {order_status}"
                if order_status != "FILLED":
                    msg += " (still open; may fill later)"
                return msg
            return "Order failed (check symbol, liquidity, or cash buffer)."

        if tool_name == "get_config":
            return (
                f"Theme underlyings: {config.theme_underlyings}\n"
                f"Moonshot: {config.moonshot_symbol}\n"
                f"Targets: theme_a={config.theme_a_target*100:.0f}% theme_b={config.theme_b_target*100:.0f}% "
                f"theme_c={config.theme_c_target*100:.0f}% moonshot={config.moonshot_target*100:.0f}% cash={config.cash_minimum*100:.0f}%\n"
                f"Dry run: {config.dry_run}\n"
                f"Execution tier: {config.execution_tier} (read_only = no trades; managed = allow trades)\n"
                f"Max trades per day: {config.max_trades_per_day}\n"
                f"Kill switch: {config.kill_switch_drawdown_pct*100:.0f}% drawdown over {config.kill_switch_lookback_days} days\n"
                f"Governance: max_single_position={config.max_single_position_pct*100:.0f}% max_correlated={config.max_correlated_pct*100:.0f}%"
            )

        if tool_name == "set_dry_run":
            if not _can_execute_trades(user_id):
                return "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS."
            enabled = bool(arguments.get("enabled", True))
            config.dry_run = enabled
            return f"Dry-run mode is now {'ON (no real trades)' if enabled else 'OFF (real trades allowed)'}."

        if tool_name == "get_market_news":
            symbol_or_topic = (arguments.get("symbol_or_topic") or "market").strip()
            if symbol_or_topic.lower() in ("market", "general", "broad"):
                symbol_or_topic = "SPY"
            try:
                if len(symbol_or_topic) <= 6 and symbol_or_topic.replace(".", "").isalpha():
                    ticker = yf.Ticker(symbol_or_topic)
                    news_list = getattr(ticker, "news", None) or []
                else:
                    try:
                        search = yf.Search(symbol_or_topic, news_count=15)
                        news_list = getattr(search, "news", None) or []
                    except (AttributeError, TypeError):
                        news_list = getattr(yf.Ticker(symbol_or_topic), "news", None) or []
                if not news_list:
                    return f"No recent news found for '{symbol_or_topic}'."
                lines = [f"Recent news for {symbol_or_topic}:"]
                for i, n in enumerate(news_list[:12], 1):
                    title = n.get("title") or n.get("link") or "—"
                    link = n.get("link") or n.get("url") or ""
                    pub = n.get("publisher") or n.get("source") or ""
                    lines.append(f"{i}. {title}")
                    if link:
                        lines.append(f"   {link}")
                    if pub:
                        lines.append(f"   ({pub})")
                return "\n".join(lines)
            except Exception as e:
                logger.exception("get_market_news failed")
                return f"Could not fetch news: {e}"

        if tool_name == "get_option_expirations":
            underlying = (arguments.get("underlying_symbol") or "").strip().upper()
            if not underlying:
                return "underlying_symbol is required."
            dm = bot_instance.data_manager
            try:
                expirations = dm.get_option_expirations(underlying, InstrumentType.EQUITY)
                if not expirations:
                    return f"No option expirations found for {underlying}."
                today = date.today()
                sorted_exps = sorted(expirations)
                lines = [f"Option expirations for {underlying} ({len(sorted_exps)} available):"]
                for exp in sorted_exps:
                    dte = (exp - today).days
                    lines.append(f"  {exp.isoformat()}  (DTE {dte})")
                return "\n".join(lines)
            except Exception as e:
                logger.exception("get_option_expirations failed")
                return f"Error: {e}"

        if tool_name == "get_options_chain":
            underlying = (arguments.get("underlying_symbol") or "").strip().upper()
            exp_str = (arguments.get("expiration_yyyy_mm_dd") or "").strip()
            if not underlying:
                return "underlying_symbol is required."
            dm = bot_instance.data_manager
            try:
                expirations = dm.get_option_expirations(underlying, InstrumentType.EQUITY)
                if not expirations:
                    return f"No expirations for {underlying}."
                today = date.today()
                if exp_str:
                    try:
                        expiration_date = date.fromisoformat(exp_str)
                    except ValueError:
                        return f"Invalid expiration date: {exp_str}. Use YYYY-MM-DD."
                    if expiration_date not in expirations:
                        expiration_date = min(expirations, key=lambda e: abs((e - expiration_date).days))
                else:
                    future = [e for e in expirations if (e - today).days >= 0]
                    expiration_date = min(future, key=lambda e: (e - today).days) if future else max(expirations)
                chain = dm.get_option_chain(underlying, expiration_date, InstrumentType.EQUITY)
                if not chain:
                    return f"No chain for {underlying} exp {expiration_date}."
                spot_raw = dm.get_quote(underlying)
                spot = _safe_float(spot_raw) if spot_raw is not None else 0.0
                if spot is None:
                    spot = 0.0
                lines = [
                    f"Options chain {underlying} exp {expiration_date} (spot ${spot:.2f}):",
                    "Use the 'symbol' value from a row when calling place_manual_trade for that contract.",
                ]
                max_pain_result = dm.compute_max_pain(chain)
                if max_pain_result is not None and isinstance(max_pain_result, (tuple, list)) and len(max_pain_result) >= 2:
                    max_pain_strike, _ = max_pain_result
                    lines.append(f"Max pain: ${max_pain_strike:.2f} (strike at which option holder value at expiration is minimized; often a price magnet—use for strategic picks, e.g. selling premium near it or expecting pin risk).")
                for label, contracts in [("CALLS", getattr(chain, "calls", []) or []), ("PUTS", getattr(chain, "puts", []) or [])]:
                    if not contracts:
                        continue
                    lines.append(f"  {label}:")
                    for c in contracts:
                        inst = getattr(c, "instrument", None)
                        sym = (getattr(inst, "symbol", "") or "").strip() if inst else (getattr(c, "symbol", "") or "")
                        strike = getattr(c, "strike", None)
                        if strike is None and sym:
                            strike = _parse_strike_from_osi(sym)
                        bid_f = _safe_float(getattr(c, "bid", None))
                        ask_f = _safe_float(getattr(c, "ask", None))
                        oi = getattr(c, "open_interest", None)
                        vol = getattr(c, "volume", None)
                        mid = (bid_f + ask_f) / 2 if (bid_f is not None and ask_f is not None) else None
                        strike_str = f"strike ${float(strike):.2f}" if strike is not None else "strike N/A"
                        line = f"    {strike_str}"
                        if sym:
                            line += f"  symbol={sym}"
                        if mid is not None:
                            line += f"  bid={bid_f:.2f} ask={ask_f:.2f} mid={mid:.2f}"
                        if oi is not None:
                            line += f"  OI={oi}"
                        if vol is not None:
                            line += f"  vol={vol}"
                        lines.append(line)
                return "\n".join(lines)
            except Exception as e:
                logger.exception("get_options_chain failed")
                return f"Error: {e}"

        if tool_name == "update_allocation_targets":
            if not _can_execute_trades(user_id):
                return "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS."
            from src.utils.config_override_manager import ConfigOverrideManager
            changes = []
            for key, pct in [
                ("theme_a_target", arguments.get("theme_a_pct")),
                ("theme_b_target", arguments.get("theme_b_pct")),
                ("theme_c_target", arguments.get("theme_c_pct")),
                ("moonshot_target", arguments.get("moonshot_pct")),
                ("cash_minimum", arguments.get("cash_pct")),
            ]:
                if pct is not None:
                    v = float(pct) / 100.0
                    if not (0 <= v <= 1):
                        return f"Invalid percentage: {pct}. Use 0-100."
                    setattr(config, key, v)
                    ConfigOverrideManager.save_override(key, v)
                    changes.append(f"  {key}={pct}%")
            if not changes:
                return "No allocation params provided. Use theme_a_pct, theme_b_pct, theme_c_pct, moonshot_pct, cash_pct (0-100)."
            return (
                "Updated and saved:\n" + "\n".join(changes) +
                "\n\nChanges are now persistent across restarts."
                "\nTo reset to .env defaults, delete data/config_overrides.json"
            )

        if tool_name == "update_option_rules":
            if not _can_execute_trades(user_id):
                return "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS."
            from src.utils.config_override_manager import ConfigOverrideManager
            changes = []
            if arguments.get("dte_min") is not None:
                v = int(arguments["dte_min"])
                config.option_dte_min = v
                ConfigOverrideManager.save_override("option_dte_min", v)
                changes.append(f"  option_dte_min={v}")
            if arguments.get("dte_max") is not None:
                v = int(arguments["dte_max"])
                config.option_dte_max = v
                ConfigOverrideManager.save_override("option_dte_max", v)
                changes.append(f"  option_dte_max={v}")
            if arguments.get("strike_range_min") is not None:
                v = float(arguments["strike_range_min"])
                config.strike_range_min = v
                ConfigOverrideManager.save_override("strike_range_min", v)
                changes.append(f"  strike_range_min={v} (e.g. 1.0=ATM)")
            if arguments.get("strike_range_max") is not None:
                v = float(arguments["strike_range_max"])
                config.strike_range_max = v
                ConfigOverrideManager.save_override("strike_range_max", v)
                changes.append(f"  strike_range_max={v} (e.g. 1.10=10% OTM)")
            if not changes:
                return "No option rules provided. Use dte_min, dte_max, strike_range_min, strike_range_max."
            return (
                "Updated and saved:\n" + "\n".join(changes) +
                "\n\nChanges are now persistent across restarts."
                "\nTo reset to .env defaults, delete data/config_overrides.json"
            )

        if tool_name == "update_theme_symbols":
            if not _can_execute_trades(user_id):
                return "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS."
            from src.utils.config_override_manager import ConfigOverrideManager
            symbols = (arguments.get("symbols_comma_separated") or "").strip()
            if not symbols:
                return "symbols_comma_separated is required (e.g. 'UMC,TE,AMPX')."
            config.theme_underlyings_csv = symbols
            ConfigOverrideManager.save_override("theme_underlyings_csv", symbols)
            return (
                f"Theme underlyings updated and saved: {config.theme_underlyings}"
                "\n\nChanges are now persistent across restarts."
                "\nTo reset to .env defaults, delete data/config_overrides.json"
            )

        if tool_name == "get_config_overrides":
            from src.utils.config_override_manager import ConfigOverrideManager
            return ConfigOverrideManager.get_override_summary()

        if tool_name == "get_polymarket_odds":
            topic = (arguments.get("topic") or "").strip().lower()
            try:
                url = "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=30"
                req = urllib.request.Request(
                    url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    },
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    return "Polymarket API returned 403 (access restricted). Try again later or check polymarket.com directly."
                raise
            except Exception as e:
                logger.exception("get_polymarket_odds failed")
                return f"Could not fetch Polymarket: {e}"
            if not data:
                return "No active Polymarket events found."
            lines = ["Polymarket (active prediction markets):"]
            for ev in data:
                title = ev.get("title") or ev.get("slug") or "?"
                if topic and topic not in (title or "").lower() and topic not in (ev.get("slug") or "").lower():
                    continue
                markets = ev.get("markets") or []
                for m in markets[:2]:
                    q = m.get("question") or title
                    outcomes_raw = m.get("outcomes")
                    prices_raw = m.get("outcomePrices")
                    if isinstance(outcomes_raw, str):
                        outcomes_raw = json.loads(outcomes_raw) if outcomes_raw else []
                    if isinstance(prices_raw, str):
                        prices_raw = json.loads(prices_raw) if prices_raw else []
                    if not outcomes_raw or not prices_raw:
                        continue
                    pct_pairs = []
                    for o, p in zip(outcomes_raw[:3], prices_raw[:3]):
                        p_f = _safe_float(p)
                        pct_pairs.append(f"{o}: {p_f*100:.0f}%" if p_f is not None else f"{o}: ?")
                    odds = "  ".join(pct_pairs)
                    lines.append(f"  {q[:80]}...")
                    lines.append(f"    {odds}")
                if not markets:
                    lines.append(f"  {title[:80]}")
                lines.append("")
            if len(lines) <= 1:
                return f"No Polymarket markets matched '{topic}'. Try a broader topic or leave topic empty for sample."
            return "\n".join(lines[:50])

        if tool_name == "get_scenario":
            try:
                from src.scenario import ScenarioEngine
                scenario_engine = ScenarioEngine(bot_instance.market_data_manager, bot_instance.portfolio_manager)

                symbol = arguments.get("symbol", "").strip().upper()
                price_points = arguments.get("price_points", [])

                if not symbol:
                    return "Please provide a symbol for scenario analysis."
                if not price_points:
                    return "Please provide price points for analysis."

                result = scenario_engine.price_ladder_analysis(symbol, price_points)
                return scenario_engine.format_scenario_summary(result)

            except Exception as e:
                logger.exception("get_scenario failed")
                return f"Error in scenario analysis: {e}"

        if tool_name == "what_if_position":
            try:
                from src.scenario import ScenarioEngine
                scenario_engine = ScenarioEngine(bot_instance.market_data_manager, bot_instance.portfolio_manager)

                symbol = arguments.get("symbol", "").strip().upper()
                quantity = arguments.get("quantity", 0)
                price_points = arguments.get("price_points", [])
                is_option = arguments.get("is_option", False)
                strike = arguments.get("strike")
                expiration = arguments.get("expiration")

                if not symbol or quantity == 0:
                    return "Please provide symbol and quantity for hypothetical position analysis."
                if not price_points:
                    return "Please provide price points for analysis."

                # Create hypothetical position
                hyp_position = {
                    "symbol": symbol,
                    "quantity": quantity,
                    "entry_price": 0,  # Not used in analysis
                    "is_option": is_option,
                    "underlying": symbol if not is_option else symbol
                }

                if is_option:
                    if not strike or not expiration:
                        return "Strike and expiration required for option analysis."
                    hyp_position.update({
                        "strike": strike,
                        "expiration": expiration,
                        "osi_symbol": f"{symbol}  {expiration.replace('-', '')}C{int(strike*1000):08d}"
                    })

                result = scenario_engine.price_ladder_analysis(
                    symbol,
                    price_points,
                    include_positions=False,
                    hypothetical_positions=[hyp_position]
                )

                return scenario_engine.format_scenario_summary(result)

            except Exception as e:
                logger.exception("what_if_position failed")
                return f"Error in position analysis: {e}"

        if tool_name == "option_payoff_analysis":
            try:
                from src.scenario import ScenarioEngine
                scenario_engine = ScenarioEngine(bot_instance.market_data_manager, bot_instance.portfolio_manager)

                osi_symbol = arguments.get("osi_symbol", "").strip()
                min_price = arguments.get("min_price")
                max_price = arguments.get("max_price")

                if not osi_symbol:
                    return "Please provide an OSI symbol for option payoff analysis."

                price_range = None
                if min_price is not None and max_price is not None:
                    price_range = (min_price, max_price)

                result = scenario_engine.option_payoff_at_expiry(osi_symbol, price_range)

                if "error" in result:
                    return f"Error: {result['error']}"

                # Format payoff results
                lines = [f"**Option Payoff at Expiry: {result['osi_symbol']}**"]
                lines.append(f"Underlying: {result['underlying']}")
                lines.append(f"Strike: ${result['strike']:.2f}")
                lines.append(f"Type: {'Call' if result['option_type'] == 'C' else 'Put'}")
                if result.get('current_underlying_price'):
                    lines.append(f"Current underlying: ${result['current_underlying_price']:.2f}")
                lines.append("")
                lines.append("**Payoff at expiration:**")

                payoffs = result.get("payoffs", {})
                for price, payoff in sorted(payoffs.items()):
                    lines.append(f"At ${price:.2f}: ${payoff:.2f}")

                return "\n".join(lines)

            except Exception as e:
                logger.exception("option_payoff_analysis failed")
                return f"Error in payoff analysis: {e}"

        if tool_name == "what_if_trim":
            try:
                symbol = (arguments.get("symbol") or "").strip().upper()
                target_pct = float(arguments.get("target_pct", 0))

                if not symbol:
                    return "Please provide a symbol to trim."
                if target_pct < 0 or target_pct > 100:
                    return "Target percentage must be between 0 and 100."

                bot_instance.portfolio_manager.refresh_portfolio()
                pm = bot_instance.portfolio_manager
                dm = bot_instance.data_manager

                # Find position
                if symbol not in pm.positions:
                    return f"No position found for {symbol}."

                pos = pm.positions[symbol]
                current_price = pm.get_position_price(pos)
                current_mv = pos.get_market_value(current_price)
                equity = pm.get_equity()
                current_allocation_pct = (current_mv / equity * 100) if equity > 0 else 0
                target_allocation = target_pct / 100.0
                target_mv = equity * target_allocation

                if target_mv >= current_mv:
                    return f"{symbol}: Current allocation {current_allocation_pct:.1f}% (${current_mv:,.2f}). Target {target_pct:.1f}% would be ${target_mv:,.2f}. No trim needed—target is equal or higher than current."

                # Calculate trim
                mv_to_sell = current_mv - target_mv
                quantity_to_sell = int(mv_to_sell / current_price) if current_price > 0 else 0

                if quantity_to_sell <= 0:
                    return f"{symbol}: Trim calculation resulted in 0 quantity. Current: {current_allocation_pct:.1f}%, target: {target_pct:.1f}%."

                new_mv = current_mv - (quantity_to_sell * current_price)
                new_allocation_pct = (new_mv / equity * 100) if equity > 0 else 0

                lines = [
                    f"**What-if: Trim {symbol} to {target_pct:.0f}%**",
                    f"Current allocation: {current_allocation_pct:.1f}% (${current_mv:,.2f})",
                    f"Target allocation: {target_pct:.1f}% (${target_mv:,.2f})",
                    f"",
                    f"**Proposed action:**",
                    f"Sell {quantity_to_sell} {'shares' if pos.instrument_type.value == 'equity' else 'contracts'} at ~${current_price:.2f}",
                    f"Proceeds: ${quantity_to_sell * current_price:,.2f}",
                    f"",
                    f"**After trim:**",
                    f"New position value: ${new_mv:,.2f}",
                    f"New allocation: {new_allocation_pct:.1f}%",
                    f"",
                    f"Note: This is a simulation. No orders placed.",
                ]
                return "\n".join(lines)

            except Exception as e:
                logger.exception("what_if_trim failed")
                return f"Error in trim simulation: {e}"

        if tool_name == "what_if_rebalance":
            try:
                bot_instance.portfolio_manager.refresh_portfolio()
                # Use run_daily_logic_preview logic (already in dry-run mode)
                old_dry = config.dry_run
                config.dry_run = True
                try:
                    orders = bot_instance.strategy.run_daily_logic()
                finally:
                    config.dry_run = old_dry

                if not orders:
                    return "**What-if: Rebalance simulation**\n\nNo rebalance needed. Portfolio is within targets."

                pm = bot_instance.portfolio_manager
                equity = pm.get_equity()
                current_alloc = pm.get_current_allocations()
                target_alloc = pm.get_target_allocations()

                lines = [
                    "**What-if: Rebalance simulation**",
                    "",
                    "**Current vs Target allocations:**",
                ]
                for k in ["theme_a", "theme_b", "theme_c", "moonshot", "cash"]:
                    curr = current_alloc.get(k, 0) * 100
                    targ = target_alloc.get(k, 0) * 100
                    lines.append(f"  {k}: {curr:.1f}% → {targ:.1f}%")

                lines.append("")
                lines.append(f"**Proposed orders ({len(orders)}):**")

                for i, o in enumerate(orders, 1):
                    action = o.get("action", "")
                    symbol = o.get("symbol", "")
                    qty = o.get("quantity", 0)
                    price = o.get("price", 0)
                    notional = qty * price
                    rationale = o.get("rationale", "")
                    line = f"{i}. {action} {symbol} x{qty} @ ${price:.2f} (${notional:,.2f})"
                    if rationale:
                        line += f" — {rationale}"
                    lines.append(line)

                lines.append("")
                lines.append("Note: This is a simulation. No orders placed.")
                return "\n".join(lines)

            except Exception as e:
                logger.exception("what_if_rebalance failed")
                return f"Error in rebalance simulation: {e}"

        if tool_name == "get_performance_summary":
            try:
                days = min(int(arguments.get("days", 30) or 30), 365)
                analytics = PerformanceAnalytics(bot_instance.storage)
                return analytics.get_performance_summary(days)
            except Exception as e:
                logger.exception("get_performance_summary failed")
                return f"Error retrieving performance analytics: {e}"

        if tool_name == "get_alerts":
            alerts = bot_instance.storage.get_pending_alerts()
            if not alerts:
                return "No active alerts."

            lines = ["⚠️  ALERTS:"]
            for alert in alerts:
                lines.append(f"⚠️  {alert['message']}")

            bot_instance.storage.clear_pending_alerts()
            return "\n".join(lines)

        return f"Unknown tool: {tool_name}"
    except Exception as e:
        logger.exception("Tool %s failed", tool_name)
        return f"Error: {str(e)}"


async def _telegram_photo_to_base64_data_url(file) -> str:
    """Download Telegram photo via PTB and return data URL (base64). Uses bot's client to avoid 404."""
    raw = await file.download_as_bytearray()
    b64 = base64.b64encode(bytes(raw)).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming Telegram message (text and/or photo): call AI with tools and reply."""
    bot_instance: TradingBot = context.bot_data["trading_bot"]
    openai_client: OpenAI = context.bot_data["openai_client"]
    user_id = update.effective_user.id if update.effective_user else 0
    msg = update.message
    text = (msg.caption or msg.text or "").strip()
    photos = list(msg.photo) if msg and msg.photo else []

    # REQ-008: Check for pending trade confirmation
    confirmation_key = f"pending_trade_{user_id}"
    pending_trade_str = bot_instance.storage.get_bot_state(confirmation_key)

    if pending_trade_str:
        # User has a pending trade confirmation
        if text.upper() == "YES":
            # Execute the pending trade
            bot_instance.storage.delete_bot_state(confirmation_key)
            try:
                loop = asyncio.get_event_loop()
                trade_data = json.loads(pending_trade_str)
                symbol = trade_data["symbol"]
                side = trade_data["side"]
                quantity = trade_data["quantity"]
                limit_price = trade_data["limit_price"]

                is_option = symbol.endswith("-OPTION") or (len(symbol) > 10 and symbol[:10].isalpha())
                order_details = {
                    "action": side,
                    "symbol": symbol,
                    "quantity": quantity,
                    "price": limit_price,
                    "rationale": f"Manual trade via Telegram (confirmed)",
                }

                # REQ-011: Derive theme and add entry_price for SELL orders
                theme = None
                entry_price = None
                if side.upper() == "SELL":
                    # Get entry price from existing position
                    await loop.run_in_executor(
                        None,
                        lambda: bot_instance.portfolio_manager.refresh_portfolio(),
                    )
                    pm = bot_instance.portfolio_manager
                    if symbol in pm.positions:
                        position = pm.positions[symbol]
                        entry_price = position.entry_price
                        # Derive theme from underlying
                        underlying = position.underlying or symbol
                        theme = bot_instance.strategy.get_theme_for_underlying(underlying)
                        order_details["entry_price"] = entry_price

                if theme:
                    order_details["theme"] = theme

                result = await loop.run_in_executor(
                    None,
                    lambda: bot_instance.execution_manager.execute_order(order_details),
                )

                if result:
                    # Save order to storage
                    await loop.run_in_executor(
                        None,
                        lambda: bot_instance.storage.save_order({**order_details, **result}),
                    )

                    order_status = (result.get("status") or "").upper()
                    if order_status == "FILLED":
                        # Update order status
                        await loop.run_in_executor(
                            None,
                            lambda: bot_instance.storage.update_order_status(
                                result["order_id"], "FILLED", datetime.now(timezone.utc).isoformat()
                            ),
                        )
                        # Save fill
                        await loop.run_in_executor(
                            None,
                            lambda: bot_instance.storage.save_fill({
                                "order_id": result["order_id"],
                                "symbol": result["symbol"],
                                "quantity": result["quantity"],
                                "fill_price": result["price"],
                            }),
                        )

                        # REQ-011: Compute realized P&L for SELL orders
                        if side.upper() == "SELL" and entry_price:
                            fill_price = result["price"]
                            qty = result["quantity"]
                            realized_pnl = (fill_price - entry_price) * qty
                            outcome = "win" if realized_pnl > 0 else "loss"

                            # Update the saved order with realized P&L and outcome
                            await loop.run_in_executor(
                                None,
                                lambda: bot_instance.storage.save_order({
                                    **order_details,
                                    **result,
                                    "realized_pnl": realized_pnl,
                                    "outcome": outcome,
                                }),
                            )

                            logger.info(
                                f"Manual confirmed trade realized P&L: ${realized_pnl:,.2f} ({outcome}) "
                                f"on {result.get('symbol')}"
                            )

                        await loop.run_in_executor(
                            None,
                            lambda: setattr(bot_instance.strategy, 'trades_today', bot_instance.strategy.trades_today + 1),
                        )

                    reply_msg = f"✅ **Trade confirmed and placed**\n\n{result.get('action')} {result.get('symbol')} x{result.get('quantity')} @ ${result.get('price')} → {order_status}"
                    if order_status != "FILLED":
                        reply_msg += " (still open; may fill later)"
                    await msg.reply_text(reply_msg, parse_mode="HTML")
                else:
                    await msg.reply_text("❌ Trade confirmation accepted but order failed. Check symbol, liquidity, or cash buffer.", parse_mode="HTML")
            except Exception as e:
                logger.exception("Confirmed trade execution failed")
                await msg.reply_text(f"❌ Error executing confirmed trade: {e}", parse_mode="HTML")
            return
        else:
            # User cancelled the trade
            bot_instance.storage.delete_bot_state(confirmation_key)
            await msg.reply_text("❌ Trade cancelled. No order placed.", parse_mode="HTML")
            return

    if not text and not photos:
        await msg.reply_text(
            "Send text and/or a photo—e.g. <b>portfolio summary</b>, <b>run rebalance</b>, "
            "or a screenshot of a chart to discuss.",
            parse_mode="HTML",
        )
        return

    await msg.reply_text("⏳ One sec…")

    # Build user content: text + optional image(s)
    user_content: List[Dict[str, Any]] = []
    if text:
        user_content.append({"type": "text", "text": text})
    elif photos:
        user_content.append({
            "type": "text",
            "text": "Turn this image into a trading strategy. It can be anything—a chart, a photo, art, a meme, a screenshot. Interpret it creatively: what themes, risk level, allocation split, or option rules does it suggest? Map what you see to a concrete strategy (e.g. allocations %, DTE/strike rules, theme symbols), then use update_allocation_targets, update_option_rules, update_theme_symbols (or place_manual_trade / run_daily_logic if appropriate) to implement it. Summarize the strategy and what you set. Never say the image is not relevant—always derive and implement a strategy from it.",
        })
    if photos:
        # Use largest photo (last in list); download via PTB to avoid URL 404
        photo = photos[-1]
        file = await context.bot.get_file(photo.file_id)
        try:
            data_url = await _telegram_photo_to_base64_data_url(file)
        except (RuntimeError, Exception) as e:
            logger.warning("Could not download photo: %s", e)
            await msg.reply_text("Could not load the photo—please try again or send a smaller image.")
            return
        user_content.append({"type": "image_url", "image_url": {"url": data_url}})
    if len(user_content) == 1 and user_content[0].get("type") == "text":
        user_message = {"role": "user", "content": user_content[0]["text"]}
    else:
        user_message = {"role": "user", "content": user_content}

    # Build context (recent portfolio snapshot)
    loop = asyncio.get_event_loop()
    try:
        context_str = await loop.run_in_executor(
            None,
            lambda: run_tool("get_portfolio", {}, bot_instance, user_id),
        )
    except Exception as e:
        context_str = f"Could not load portfolio: {e}"

    system_content = SYSTEM_PROMPT + "\n\nCurrent portfolio (use for context):\n" + context_str
    if photos:
        system_content += "\n\n[This message includes an image. Turn ANY image into a trading strategy—regardless of context. Interpret creatively: map what you see (themes, structure, mood, numbers) to allocations, option rules, or theme symbols. Then use update_allocation_targets, update_option_rules, update_theme_symbols (and place_manual_trade / run_daily_logic when it fits) to implement. Always derive a strategy and implement it; never say the image is irrelevant.]"
    # Prepend recent conversation history (per user) so the bot keeps context across messages
    history: List[Dict[str, str]] = list(context.user_data.get(CHAT_HISTORY_KEY, []))[-CHAT_HISTORY_MAX_MESSAGES:]
    messages = [{"role": "system", "content": system_content}] + history + [user_message]

    # Use gpt-4o for messages with images (stronger vision); gpt-4o-mini otherwise
    model = "gpt-4o" if photos else "gpt-4o-mini"
    max_rounds = 10
    while max_rounds > 0:
        max_rounds -= 1
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0]
        if not choice.message.tool_calls:
            reply = choice.message.content or "Done."
            if len(reply) > 4000:
                reply = reply[:3997] + "..."
            # Append this exchange to conversation history (text only, for context in future turns)
            user_text_for_history = text if text else "[Sent an image]"
            history_list = context.user_data.setdefault(CHAT_HISTORY_KEY, [])
            history_list.append({"role": "user", "content": user_text_for_history})
            history_list.append({"role": "assistant", "content": reply})
            if len(history_list) > CHAT_HISTORY_MAX_MESSAGES:
                context.user_data[CHAT_HISTORY_KEY] = history_list[-CHAT_HISTORY_MAX_MESSAGES:]
            try:
                reply_html = _markdown_to_telegram_html(reply)
            except Exception:
                reply_html = reply
            # Context-aware suggestion buttons (based on this exchange)
            suggestions = await _get_ai_suggestions(openai_client, text or "[image]", reply)
            keyboard = _build_suggestions_keyboard(suggestions) if suggestions else START_KEYBOARD
            try:
                await update.message.reply_text(
                    reply_html,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except Exception:
                await update.message.reply_text(reply, reply_markup=keyboard)
            return

        messages.append(choice.message)
        for tc in choice.message.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            result = await loop.run_in_executor(
                None,
                lambda n=name, a=args: run_tool(n, a, bot_instance, user_id),
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result[:8000] if len(result) > 8000 else result,
            })

    await update.message.reply_text(
        "Stopped after several steps. Try a shorter question or one action at a time."
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and tell the user something went wrong."""
    logger.exception("Exception while handling an update: %s", context.error)
    if update and isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Something went wrong on my side—please try again in a moment."
        )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start. Show fixed suggestion keyboard; user can still type custom messages."""
    await update.message.reply_text(
        "Hey—I'm your trading assistant. Text or images, I've got you.\n\n"
        "Tap a button below or type anything. Ask for <b>deep research</b> on a topic (e.g. \"deep research on AAPL\" or \"what's going on with Fed\") and I'll pull news, Polymarket, options, and your portfolio into one synthesis.\n\n"
        "<b>Emergency controls:</b> /pause to stop all trading.",
        parse_mode="HTML",
        reply_markup=START_KEYBOARD,
    )


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pause. Toggle trading pause (emergency stop)."""
    bot_instance: TradingBot = context.bot_data["trading_bot"]
    user_id = update.effective_user.id if update.effective_user else 0

    if not _can_execute_trades(user_id):
        await update.message.reply_text(
            "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS.",
            parse_mode="HTML",
        )
        return

    # Toggle pause state
    storage = bot_instance.storage
    is_paused = storage.is_trading_paused()

    if is_paused:
        # Resume trading
        storage.set_trading_paused(False)
        await update.message.reply_text(
            "<b>Trading RESUMED</b>\n\n"
            "All trading functions are now enabled. The bot can place orders when you request them or during automated rebalancing.",
            parse_mode="HTML",
        )
    else:
        # Pause trading
        storage.set_trading_paused(True)
        await update.message.reply_text(
            "<b>⛔ TRADING PAUSED</b>\n\n"
            "Emergency stop activated. No new trades will be placed until you resume.\n\n"
            "• Portfolio queries and analysis still work\n"
            "• Dry-run simulations still work\n"
            "• No orders will be executed\n\n"
            "To resume trading, use /pause again.",
            parse_mode="HTML",
        )


def main() -> None:
    """Run Telegram bot with AI."""
    if not config.telegram_bot_token or not config.openai_api_key:
        logger.error("Set TELEGRAM_BOT_TOKEN and OPENAI_API_KEY in .env to run the Telegram bot.")
        raise SystemExit(1)

    setup_logging()

    logger.info("Initializing trading bot (for Telegram)...")
    trading_bot = TradingBot(account_number=None)

    app = Application.builder().token(config.telegram_bot_token).build()
    app.bot_data["trading_bot"] = trading_bot
    app.bot_data["openai_client"] = OpenAI(api_key=config.openai_api_key)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Telegram bot running. Send /start for help.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
