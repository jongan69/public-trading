"""Tests that the Telegram bot correctly consumes API data (portfolio, options chain, Polymarket)."""
import json
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

import pytest

from src.telegram_bot import (
    _parse_strike_from_osi,
    _safe_float,
    run_tool,
)


# --- Helpers ---


def test_parse_strike_from_osi():
    """Parse strike from OSI option symbols (8-digit strike = strike * 1000)."""
    # 00001000 -> 1.0, 00010000 -> 10.0, 00014000 -> 14.0, 00150000 -> 150.0
    assert _parse_strike_from_osi("UMC260220C00001000") == 1.0
    assert _parse_strike_from_osi("UMC260220C00010000") == 10.0
    assert _parse_strike_from_osi("AMPX260320C00014000-OPTION") == 14.0
    assert _parse_strike_from_osi("AAPL250117P00150000") == 150.0
    assert _parse_strike_from_osi("") is None
    assert _parse_strike_from_osi("INVALID") is None


def test_safe_float():
    """Convert API values (Decimal, str, int, float) to float safely."""
    assert _safe_float(Decimal("10.5")) == 10.5
    assert _safe_float("10.5") == 10.5
    assert _safe_float(10) == 10.0
    assert _safe_float(10.5) == 10.5
    assert _safe_float(None) is None
    assert _safe_float("") is None
    assert _safe_float("bad") is None


# --- get_options_chain: Quote-like objects (instrument.symbol, bid, ask) ---


@pytest.fixture
def mock_bot_for_options():
    """Minimal TradingBot mock with data_manager returning option chain (Quote-like)."""
    bot = Mock()
    dm = Mock()
    bot.data_manager = dm

    class MockQuote:
        def __init__(self, symbol, bid, ask, open_interest=None, volume=None):
            self.instrument = Mock()
            self.instrument.symbol = symbol
            self.bid = Decimal(str(bid)) if bid is not None else None
            self.ask = Decimal(str(ask)) if ask is not None else None
            self.open_interest = open_interest
            self.volume = volume

    chain = Mock()
    # OSI: 00010000 = strike 10, 00012000 = strike 12
    chain.calls = [
        MockQuote("UMC260220C00010000", 8.50, 10.30, 100, 50),
        MockQuote("UMC260220C00012000", 7.00, 9.00, None, None),
    ]
    chain.puts = [
        MockQuote("UMC260220P00010000", 10.00, 11.90),
    ]

    dm.get_option_expirations.return_value = []
    dm.get_option_chain.return_value = chain
    dm.get_quote.return_value = 10.13
    dm.compute_max_pain.return_value = None  # optional; bot handles None

    # Make get_option_expirations return a list of dates so chain is used
    from datetime import date, timedelta
    today = date.today()
    dm.get_option_expirations.return_value = [today + timedelta(days=30)]

    return bot, dm


def test_run_tool_get_options_chain_consumes_quote_data(mock_bot_for_options):
    """Options chain output must contain symbol= and bid/ask from Quote (Decimal-safe)."""
    bot, dm = mock_bot_for_options
    result = run_tool(
        "get_options_chain",
        {"underlying_symbol": "UMC", "expiration_yyyy_mm_dd": ""},
        bot,
        user_id=0,
    )
    assert "symbol=UMC260220C00010000" in result
    assert "bid=8.50" in result and "ask=10.30" in result
    assert "mid=9.40" in result
    assert "strike $10.00" in result
    assert "spot $10.13" in result
    assert "Use the 'symbol' value" in result


def test_run_tool_get_options_chain_handles_string_bid_ask():
    """Options chain should handle bid/ask as strings (API sometimes returns string)."""
    bot = Mock()
    dm = Mock()
    bot.data_manager = dm

    class MockQuoteStr:
        instrument = Mock()
        instrument.symbol = "UMC260220C00001000"
        bid = "8.50"
        ask = "10.30"
        open_interest = None
        volume = None

    chain = Mock()
    chain.calls = [MockQuoteStr()]
    chain.puts = []
    from datetime import date, timedelta
    dm.get_option_expirations.return_value = [date.today() + timedelta(days=30)]
    dm.get_option_chain.return_value = chain
    dm.get_quote.return_value = "10.13"
    dm.compute_max_pain.return_value = None

    result = run_tool(
        "get_options_chain",
        {"underlying_symbol": "UMC"},
        bot,
        user_id=0,
    )
    assert "bid=8.50" in result and "ask=10.30" in result
    assert "spot $10.13" in result


# --- get_polymarket_odds: outcomePrices / outcomes (string or list) ---


@patch("src.telegram_bot.urllib.request.urlopen")
def test_run_tool_get_polymarket_odds_consumes_json(mock_urlopen):
    """Polymarket tool must parse outcomePrices/outcomes (string or list) and format odds correctly."""
    raw = [
        {
            "title": "Fed rate",
            "slug": "fed-rate",
            "markets": [
                {
                    "question": "Will Fed cut in March?",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.65", "0.35"]',
                },
                {
                    "question": "Another market",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": [0.70, 0.30],
                },
            ],
        },
    ]
    resp = Mock()
    resp.read.return_value = json.dumps(raw).encode()
    resp.__enter__ = Mock(return_value=resp)
    resp.__exit__ = Mock(return_value=None)
    mock_urlopen.return_value = resp

    bot = Mock()
    result = run_tool("get_polymarket_odds", {"topic": "fed"}, bot, user_id=0)

    assert "Yes: 65%" in result or "65%" in result
    assert "70%" in result or "Yes: 70%" in result
    assert "Polymarket" in result or "Fed" in result.lower()


# --- get_portfolio: equity/cash/alloc from portfolio manager ---


def test_run_tool_get_portfolio_uses_manager_numbers():
    """Portfolio tool must pass through equity, cash, buying power and allocations from manager."""
    bot = Mock()
    pm = Mock()
    bot.portfolio_manager = pm
    pm.refresh_portfolio = Mock()
    pm.get_equity.return_value = 1062.79
    pm.get_cash.return_value = 392.52
    pm.get_buying_power.return_value = 392.52
    pm.get_current_allocations.return_value = {
        "theme_a": 0.01,
        "theme_b": 0.0,
        "theme_c": 0.013,
        "moonshot": 0.347,
        "cash": 0.369,
    }
    pm.positions = {}

    result = run_tool("get_portfolio", {}, bot, user_id=0)

    assert "1,062.79" in result or "1062.79" in result
    assert "392.52" in result
    assert "1.0%" in result or "1.0" in result
    assert "34.7%" in result or "34.7" in result
    pm.get_equity.assert_called_once()
    pm.get_cash.assert_called_once()
    pm.get_buying_power.assert_called_once()
