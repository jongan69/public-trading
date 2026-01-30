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


# --- Tool definitions for OpenAI (function calling) ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_portfolio",
            "description": "Get current portfolio summary: equity, cash, positions, and allocation percentages. Call when user asks about portfolio, balance, positions, or holdings. Present the reply as bullet points or one line per position—do not use markdown tables (Telegram does not support them).",
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
            "description": "Get available option expiration dates for any underlying symbol (e.g. AAPL, TSLA, UMC). Use when user asks about expirations or which dates are available for options on a stock.",
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
            "description": "Get option chain (calls and puts) for any underlying ticker (e.g. AAPL, TSLA, UMC, NVDA)—not limited to theme symbols. Returns spot, and per contract: strike, symbol (use for place_manual_trade), bid, ask, mid, OI, vol. Use when user asks about options for any symbol. If no expiration given, uses nearest expiration. Always call before recommending an option trade.",
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
]

SYSTEM_PROMPT = """You are an AI assistant for a high-convexity options/equity trading bot connected to Public.com. The user talks to you via Telegram and can send text and/or images.

You are fully capable of:
1) **Conversation about market news and assets**: Use get_market_news(symbol_or_topic) for current headlines. Discuss earnings, sectors, Fed, macro, or any ticker.
2) **Options chains**: Use get_option_expirations and get_options_chain for **any** underlying ticker (not just theme symbols)—e.g. AAPL, TSLA, UMC, NVDA. Discuss strikes, bid/ask, liquidity, and build options strategies for whatever symbol the user asks about.
3) **Polymarket prediction odds**: Use get_polymarket_odds(topic) to fetch prediction-market probabilities (e.g. Fed rate, elections, Bitcoin). Factor these into options or market context when relevant—e.g. "Polymarket says 70% chance X; that could support/hurt this option thesis."
4) **Images — turn ANY image into a trading strategy**: You have vision. The user can send any image (chart, photo, meme, art, screenshot, random picture). Your job: (a) interpret it creatively and derive a trading strategy from it—themes, risk profile, allocation split, option rules, or concrete trades—regardless of whether the image is "about" finance; (b) summarize the strategy in plain language; (c) implement it when it makes sense using update_allocation_targets, update_option_rules, update_theme_symbols, place_manual_trade, or run_daily_logic_*. Map what you see (metaphors, structure, numbers, mood) to allocations (%), DTE/strike rules, theme symbols, or orders. E.g. a skateboard image → momentum + obstacles → "momentum themes 40%, defensive 30%, cash 30%" and apply. Never say the image is irrelevant—always derive a strategy from it.
5) **Building custom strategies through conversation**: Use update_allocation_targets, update_option_rules, and update_theme_symbols. Only provide params the user asked to change.
6) **Deep research**: When the user asks for research, deep analysis, "what's going on with X", or comprehensive market context, use ALL relevant data. Call multiple tools in one response: get_portfolio and get_allocations for their book; get_market_news(symbol_or_topic) for headlines; get_polymarket_odds(topic) for prediction-market context; get_option_expirations and get_options_chain for options context; get_config for strategy settings. Then synthesize: tie news + Polymarket odds + options + portfolio into one coherent research note (context, implications, risks, optional trade/strategy ideas). Do not stop after one tool—gather from several sources and then answer.

**Suggestions and manual trades are not limited to theme underlyings.** You can suggest and place trades (via place_manual_trade) for **any** equity or option symbol the user asks about—e.g. AAPL, TSLA, NVDA, SPY, or any option chain. Theme underlyings (from get_config) only define which symbols the **automated rebalance** (run_daily_logic) uses; they do not restrict manual suggestions or orders. You can make multiple tool calls before replying.

You also have: get_portfolio, get_allocations, run_daily_logic_preview, run_daily_logic_and_execute, place_manual_trade, get_config, set_dry_run.

Be conversational and helpful. For trades, confirm and summarize. Never make up portfolio, chain, or Polymarket data—use the tools.

**Option trade accuracy:** (1) Always call get_options_chain (and get_option_expirations if needed) in the same turn before recommending any option trade. Never use prices, strikes, or symbols from memory or a previous message. (2) In your recommendation, quote only numbers that appear in the tool output (spot, bid, ask, mid). State explicitly that the data is from the options chain just fetched (e.g. \"Data from options chain fetched for this recommendation\"). (3) When suggesting a limit price, use the ask from the chain and say \"limit at current ask $X (from chain)\" or similar. (4) When the user confirms and you call place_manual_trade: use the exact option symbol from the get_options_chain output (the symbol= value for that strike/expiration). Never fabricate or guess option symbols. If the user confirms long after the recommendation, call get_options_chain again to get fresh bid/ask and the exact symbol before placing.

When the user asks for research or deep analysis: call get_market_news, get_polymarket_odds, get_options_chain (and get_portfolio/get_allocations if relevant), then synthesize one answer. When a message includes an image: (1) analyze it, (2) turn it into a trading strategy regardless of context—derive themes, allocations, rules, or trades from whatever you see, (3) implement via tools and summarize. Any image can become a strategy; you are allowed to make trades and set strategy from any image.

Format replies for Telegram so they render well:
- Use one main title at the top with # (e.g. # Fed Context and Market Overview).
- Use ## for each major section: ## Fed News, ## Market Headlines, ## Polymarket Odds, ## Implications for Trading Strategies.
- Use ### only for subsections inside a section if needed.
- Use **bold** for key numbers, percentages, and terms (e.g. **26% Yes / 74% No**).
- Use [link text](url) for links; keep anchor text short (e.g. [Read more](url)).
- Use short bullet points (- or •) and numbered lists (1. 2. 3.) for clarity.
- Keep paragraphs to 1–2 sentences; one idea per line in lists. Avoid long walls of text.
- Do not use markdown tables (| col1 | col2 |)—Telegram does not support them and they show as raw text. For portfolio positions, allocations, or any tabular data use bullet points with one item per line, e.g. • SYMBOL — qty X, mv $Y, pnl Z%."""


# Fixed keyboard shown on /start (user can still type custom messages)
START_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Portfolio summary"), KeyboardButton("What would the strategy do?")],
        [KeyboardButton("Options chain for UMC"), KeyboardButton("Polymarket odds")],
        [KeyboardButton("News on AAPL"), KeyboardButton("Show config")],
        [KeyboardButton("Deep research: Fed + markets")],
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
            eq = bot_instance.portfolio_manager.get_equity()
            cash = bot_instance.portfolio_manager.get_cash()
            bp = bot_instance.portfolio_manager.get_buying_power()
            alloc = bot_instance.portfolio_manager.get_current_allocations()
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
            for sym, pos in bot_instance.portfolio_manager.positions.items():
                price = bot_instance.portfolio_manager.get_position_price(pos)
                mv = pos.get_market_value(price)
                pnl = pos.get_pnl_pct(price)
                lines.append(f"  {sym}: qty={pos.quantity} @ ${price:.2f} mv=${mv:.2f} pnl={pnl:.1f}%")
            return "\n".join(lines)

        if tool_name == "get_allocations":
            bot_instance.portfolio_manager.refresh_portfolio()
            current = bot_instance.portfolio_manager.get_current_allocations()
            target = bot_instance.portfolio_manager.get_target_allocations()
            lines = ["Current -> Target:"]
            for k in ["theme_a", "theme_b", "theme_c", "moonshot", "cash"]:
                lines.append(f"  {k}: {current[k]*100:.1f}% -> {target[k]*100:.1f}%")
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
                return "Strategy would place no orders (portfolio already in line with targets)."
            return "Planned orders (dry-run, not executed):\n" + json.dumps(
                [{k: v for k, v in o.items() if k != "contract_info"} for o in orders],
                indent=2,
            )

        if tool_name == "run_daily_logic_and_execute":
            if not _can_execute_trades(user_id):
                return "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS. Add your ID to .env to execute trades."
            bot_instance.portfolio_manager.refresh_portfolio()
            orders = bot_instance.strategy.run_daily_logic()
            if not orders:
                return "No orders to execute; portfolio already in line with targets."
            results = []
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
                        bot_instance.storage.save_fill({
                            "order_id": result["order_id"],
                            "symbol": result["symbol"],
                            "quantity": result["quantity"],
                            "fill_price": result["price"],
                        })
                        bot_instance.strategy.trades_today += 1
                    # Show status clearly; if not FILLED, say still open
                    line = f"Order: {result.get('action')} {result.get('symbol')} x{result.get('quantity')} -> {order_status}"
                    if order_status != "FILLED":
                        line += " (still open; may fill later)"
                    results.append(line)
                else:
                    results.append(f"Failed: {order_details}")
            return "\n".join(results)

        if tool_name == "place_manual_trade":
            if not _can_execute_trades(user_id):
                return "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS. Add your ID to .env to place trades."
            symbol = arguments.get("symbol", "").strip()
            side = (arguments.get("side") or "BUY").upper()
            quantity = int(arguments.get("quantity", 0))
            limit_price = float(arguments.get("limit_price", 0))
            if not symbol or quantity <= 0 or limit_price <= 0:
                return "Invalid: symbol, quantity, and limit_price must be set and positive."
            is_option = symbol.endswith("-OPTION") or (len(symbol) > 10 and symbol[:10].isalpha())
            order_details = {
                "action": side,
                "symbol": symbol,
                "quantity": quantity,
                "price": limit_price,
            }
            result = bot_instance.execution_manager.execute_order(order_details)
            if result:
                order_status = (result.get("status") or "").upper()
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
                f"Max trades per day: {config.max_trades_per_day}\n"
                f"Kill switch: {config.kill_switch_drawdown_pct*100:.0f}% drawdown over {config.kill_switch_lookback_days} days"
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
                lines = [f"Option expirations for {underlying} (next 12):"]
                for exp in sorted(expirations)[:12]:
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
                for label, contracts in [("CALLS", getattr(chain, "calls", []) or []), ("PUTS", getattr(chain, "puts", []) or [])]:
                    if not contracts:
                        continue
                    lines.append(f"  {label}:")
                    for c in contracts[:25]:
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
                    changes.append(f"  {key}={pct}%")
            if not changes:
                return "No allocation params provided. Use theme_a_pct, theme_b_pct, theme_c_pct, moonshot_pct, cash_pct (0-100)."
            return "Updated (this session):\n" + "\n".join(changes) + "\nTo make permanent, set in .env: THEME_A_TARGET=0.40 etc."

        if tool_name == "update_option_rules":
            if not _can_execute_trades(user_id):
                return "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS."
            changes = []
            if arguments.get("dte_min") is not None:
                v = int(arguments["dte_min"])
                config.option_dte_min = v
                changes.append(f"  option_dte_min={v}")
            if arguments.get("dte_max") is not None:
                v = int(arguments["dte_max"])
                config.option_dte_max = v
                changes.append(f"  option_dte_max={v}")
            if arguments.get("strike_range_min") is not None:
                v = float(arguments["strike_range_min"])
                config.strike_range_min = v
                changes.append(f"  strike_range_min={v} (e.g. 1.0=ATM)")
            if arguments.get("strike_range_max") is not None:
                v = float(arguments["strike_range_max"])
                config.strike_range_max = v
                changes.append(f"  strike_range_max={v} (e.g. 1.10=10% OTM)")
            if not changes:
                return "No option rules provided. Use dte_min, dte_max, strike_range_min, strike_range_max."
            return "Updated (this session):\n" + "\n".join(changes) + "\nTo make permanent, set OPTION_DTE_MIN etc. in .env."

        if tool_name == "update_theme_symbols":
            if not _can_execute_trades(user_id):
                return "Not allowed: your user ID is not in ALLOWED_TELEGRAM_USER_IDS."
            symbols = (arguments.get("symbols_comma_separated") or "").strip()
            if not symbols:
                return "symbols_comma_separated is required (e.g. 'UMC,TE,AMPX')."
            config.theme_underlyings_csv = symbols
            return f"Theme underlyings updated to: {config.theme_underlyings}. To make permanent, set THEME_UNDERLYINGS={symbols} in .env."

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
        "Hey—I’m your trading assistant. Text or images, I’ve got you.\n\n"
        "Tap a button below or type anything. Ask for <b>deep research</b> on a topic (e.g. \"deep research on AAPL\" or \"what's going on with Fed\") and I'll pull news, Polymarket, options, and your portfolio into one synthesis.",
        parse_mode="HTML",
        reply_markup=START_KEYBOARD,
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
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Telegram bot running. Send /start for help.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
