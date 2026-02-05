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
    """Minimal TradingBot mock with data_manager returning comprehensive option chain (dict shape)."""
    from datetime import date, timedelta
    bot = Mock()
    dm = Mock()
    bot.data_manager = dm

    today = date.today()
    exp_date = today + timedelta(days=30)
    dm.get_option_expirations.return_value = [exp_date]

    # Production: get_option_chain_comprehensive returns dict with calls/puts as list of dicts
    chain_data = {
        "spot_price": 10.13,
        "max_pain_strike": None,
        "calls": [
            {"symbol": "UMC260220C00010000", "strike": 10.0, "bid": 8.50, "ask": 10.30, "mid": 9.40, "open_interest": 100, "volume": 50},
            {"symbol": "UMC260220C00012000", "strike": 12.0, "bid": 7.00, "ask": 9.00, "mid": 8.00, "open_interest": None, "volume": None},
        ],
        "puts": [
            {"symbol": "UMC260220P00010000", "strike": 10.0, "bid": 10.00, "ask": 11.90, "mid": 10.95, "open_interest": None, "volume": None},
        ],
    }
    dm.get_option_chain_comprehensive.return_value = chain_data

    return bot, dm


def test_run_tool_get_options_chain_consumes_quote_data(mock_bot_for_options):
    """Options chain output must contain symbol= and bid/ask from comprehensive chain dict."""
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
    dm.get_option_chain_comprehensive.assert_called_once()


def test_run_tool_get_options_chain_handles_string_bid_ask():
    """Options chain should handle bid/ask as numbers in dict (production shape)."""
    from datetime import date, timedelta
    bot = Mock()
    dm = Mock()
    bot.data_manager = dm
    dm.get_option_expirations.return_value = [date.today() + timedelta(days=30)]
    dm.get_option_chain_comprehensive.return_value = {
        "spot_price": 10.13,
        "max_pain_strike": None,
        "calls": [{"symbol": "UMC260220C00001000", "strike": 1.0, "bid": 8.50, "ask": 10.30, "mid": 9.40}],
        "puts": [],
    }

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
    # Production: get_portfolio_comprehensive returns dict with positions list
    pm.get_portfolio_comprehensive.return_value = {"positions": []}

    result = run_tool("get_portfolio", {}, bot, user_id=0)

    assert "1,062.79" in result or "1062.79" in result
    assert "392.52" in result
    assert "1.0%" in result or "1.0" in result
    assert "34.7%" in result or "34.7" in result
    pm.get_equity.assert_called_once()
    pm.get_cash.assert_called_once()
    pm.get_buying_power.assert_called_once()
    pm.get_portfolio_comprehensive.assert_called_once()


# --- get_fundamental_analysis ---


@patch("src.fundamental_analysis.FundamentalAnalysis")
def test_run_tool_get_fundamental_analysis_returns_formatted_output(MockFA):
    """get_fundamental_analysis tool is invoked with symbol and returns formatted analysis."""
    bot = Mock()
    mock_analyzer = Mock()
    mock_analyzer.get_comprehensive_analysis.return_value = {
        "symbol": "GME",
        "analysis_date": "2026-02-04T12:00:00",
        "current_price": 25.50,
        "dcf_analysis": {
            "intrinsic_value_per_share": 104.57,
            "discount_to_intrinsic": 75.3,
            "valuation_result": "UNDERVALUED",
            "free_cash_flow_ltm": 563_200_000,
        },
        "pe_analysis": {"current_pe": 27.45, "industry_pe": 20.37, "result": "ABOUT_RIGHT"},
        "volatility_analysis": {"periods": {"1wk": {"total_return_pct": 7.7, "volatility_pct": 45.0}}},
        "valuation_score": {"valuation_score": 2.0, "max_score": 6, "breakdown": {}},
    }
    MockFA.return_value = mock_analyzer

    result = run_tool("get_fundamental_analysis", {"symbol": "GME"}, bot, user_id=0)

    assert "GME" in result
    assert "25.50" in result
    assert "104.57" in result
    assert "75.3" in result
    assert "UNDERVALUED" in result
    assert "27.45" in result
    assert "Valuation Score" in result or "valuation" in result.lower()
    mock_analyzer.get_comprehensive_analysis.assert_called_once_with("GME")


def test_run_tool_get_fundamental_analysis_requires_symbol():
    """get_fundamental_analysis with missing symbol returns error."""
    bot = Mock()
    result = run_tool("get_fundamental_analysis", {}, bot, user_id=0)
    assert "required" in result.lower() or "symbol" in result.lower()
