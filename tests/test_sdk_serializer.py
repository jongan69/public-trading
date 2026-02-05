"""Tests for SDK serializer (extract_quote_data, extract_greeks_data, extract_portfolio_position_data, etc.)."""
import pytest
from decimal import Decimal
from datetime import date, datetime
from unittest.mock import Mock

from src.utils.sdk_serializer import (
    serialize_sdk_object,
    extract_quote_data,
    extract_greeks_data,
    extract_option_contract_data,
    extract_option_chain_data,
    extract_portfolio_position_data,
    extract_portfolio_data,
)


def test_serialize_sdk_object_primitive():
    """Primitives pass through unchanged."""
    assert serialize_sdk_object(1) == 1
    assert serialize_sdk_object(1.5) == 1.5
    assert serialize_sdk_object("a") == "a"
    assert serialize_sdk_object(True) is True
    assert serialize_sdk_object(None) is None


def test_serialize_sdk_object_decimal():
    """Decimal becomes float."""
    assert serialize_sdk_object(Decimal("10.5")) == 10.5


def test_serialize_sdk_object_date():
    """Date becomes ISO string."""
    d = date(2025, 1, 17)
    assert serialize_sdk_object(d) == "2025-01-17"


def test_serialize_sdk_object_datetime():
    """Datetime becomes ISO string."""
    dt = datetime(2025, 1, 17, 12, 0, 0)
    out = serialize_sdk_object(dt)
    assert "2025-01-17" in out and "12:00" in out


def test_serialize_sdk_object_list():
    """List is recursively serialized."""
    assert serialize_sdk_object([1, Decimal("2.5"), "x"]) == [1, 2.5, "x"]


def test_serialize_sdk_object_dict():
    """Dict is recursively serialized."""
    assert serialize_sdk_object({"a": Decimal("1.5"), "b": 2}) == {"a": 1.5, "b": 2}


def test_serialize_sdk_object_nested_object():
    """Object with attributes is serialized to dict."""
    class Obj:
        x = 1
        y = "two"
    assert serialize_sdk_object(Obj()) == {"x": 1, "y": "two"}


def test_extract_quote_data_production_shape():
    """extract_quote_data returns symbol, last, bid, ask, mid."""
    class Instrument:
        pass
    inst = Instrument()
    inst.symbol = "AAPL"
    inst.type = "EQUITY"

    class Quote:
        pass
    q = Quote()
    q.instrument = inst
    q.last = Decimal("150.0")
    q.bid = Decimal("149.9")
    q.ask = Decimal("150.1")

    result = extract_quote_data(q)
    assert result["symbol"] == "AAPL"
    assert result["last"] == 150.0
    assert result["bid"] == 149.9
    assert result["ask"] == 150.1
    assert result["mid"] == 150.0


def test_extract_greeks_data_production_shape():
    """extract_greeks_data returns delta, gamma, theta, vega."""
    class MockGreeks:
        delta = 0.5
        gamma = 0.1
        theta = -0.05
        vega = 0.2

    result = extract_greeks_data(MockGreeks())
    assert result["delta"] == 0.5
    assert result["gamma"] == 0.1
    assert result["theta"] == -0.05
    assert result["vega"] == 0.2


def test_extract_option_contract_data_production_shape():
    """extract_option_contract_data returns symbol, strike, bid, ask, mid."""
    class MockContract:
        symbol = "AAPL250117C00150000"
        strike = 150.0
        bid = Decimal("5.50")
        ask = Decimal("5.80")

    result = extract_option_contract_data(MockContract())
    assert result["symbol"] == "AAPL250117C00150000"
    assert result["strike"] == 150.0
    assert result["bid"] == 5.5
    assert result["ask"] == 5.8
    assert result["mid"] == 5.65


def test_extract_option_chain_data_production_shape():
    """extract_option_chain_data returns underlying, spot_price, calls, puts."""
    class MockCall:
        symbol = "AAPL250117C00150000"
        strike = 150.0
        bid = 5.5
        ask = 5.8
    class MockPut:
        symbol = "AAPL250117P00150000"
        strike = 150.0
        bid = 4.0
        ask = 4.2
    class MockChain:
        underlying = "AAPL"
        expiration = "2025-01-17"
        spot_price = 150.0
        calls = [MockCall()]
        puts = [MockPut()]

    result = extract_option_chain_data(MockChain())
    assert result.get("underlying") == "AAPL" or result.get("spot_price") == 150.0
    assert len(result["calls"]) == 1
    assert len(result["puts"]) == 1
    assert result["calls"][0]["symbol"] == "AAPL250117C00150000"
    assert result["puts"][0]["symbol"] == "AAPL250117P00150000"


def test_extract_portfolio_position_data_production_shape():
    """extract_portfolio_position_data returns symbol, quantity, unit_cost."""
    class MockInstrument:
        symbol = "AAPL"
        type = "EQUITY"
    class MockCostBasis:
        unit_cost = 145.0
        total_cost = 1450.0
    class MockPosition:
        instrument = MockInstrument()
        quantity = 10
        cost_basis = MockCostBasis()

    result = extract_portfolio_position_data(MockPosition())
    assert result["symbol"] == "AAPL"
    assert result["quantity"] == 10
    assert result["unit_cost"] == 145.0
    assert result["total_cost"] == 1450.0


def test_extract_portfolio_data_production_shape():
    """extract_portfolio_data returns equity, buying_power, cash, positions."""
    class Instrument:
        pass
    inst = Instrument()
    inst.symbol = "AAPL"
    inst.type = "EQUITY"

    class Position:
        pass
    pos = Position()
    pos.instrument = inst
    pos.quantity = 10
    pos.cost_basis = None

    class BuyingPower:
        pass
    bp = BuyingPower()
    bp.buying_power = Decimal("600.0")

    class Portfolio:
        pass
    p = Portfolio()
    p.equity = 1200.0
    p.buying_power = bp
    p.cash = 300.0
    p.positions = [pos]

    result = extract_portfolio_data(p)
    assert result["equity"] == 1200.0
    assert result["position_count"] == 1
    assert len(result["positions"]) == 1
    assert result["positions"][0]["symbol"] == "AAPL"
