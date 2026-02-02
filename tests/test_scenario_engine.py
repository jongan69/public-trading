"""Tests for scenario simulation engine."""
import pytest
from datetime import date, datetime
from unittest.mock import Mock, MagicMock

from src.scenario import ScenarioEngine
from src.portfolio import Position
from public_api_sdk import InstrumentType


class TestScenarioEngine:
    """Test the scenario simulation engine functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock market data manager
        self.mock_market_data = Mock()
        self.mock_market_data.get_quote.return_value = 100.0
        self.mock_market_data.get_option_greeks.return_value = {
            "AAPL  241220C00150000": {
                "theta": -0.05,
                "delta": 0.6,
                "gamma": 0.02,
                "vega": 0.15
            }
        }
        self.mock_market_data.get_quote_bid_ask.return_value = {
            "bid": 4.5,
            "ask": 5.0,
            "mid": 4.75,
            "last": 4.8
        }

        # Mock portfolio manager
        self.mock_portfolio = Mock()
        self.mock_portfolio.get_positions.return_value = [
            Position(
                symbol="AAPL",
                quantity=100,
                entry_price=95.0,
                instrument_type=InstrumentType.EQUITY
            ),
            Position(
                symbol="AAPL  241220C00150000",
                quantity=5,
                entry_price=4.0,
                instrument_type=InstrumentType.OPTION,
                osi_symbol="AAPL  241220C00150000",
                underlying="AAPL",
                strike=150.0,
                expiration="2024-12-20"
            )
        ]
        self.mock_portfolio.get_portfolio_analysis.return_value = {
            "equity": 50000.0,
            "buying_power": 25000.0,
            "cash": 15000.0
        }

        # Create scenario engine
        self.scenario_engine = ScenarioEngine(self.mock_market_data, self.mock_portfolio)

    def test_price_ladder_analysis_basic(self):
        """Test basic price ladder analysis functionality."""
        price_points = [80, 100, 120, 140]
        result = self.scenario_engine.price_ladder_analysis("AAPL", price_points)

        assert "symbol" in result
        assert result["symbol"] == "AAPL"
        assert "price_scenarios" in result
        assert len(result["price_scenarios"]) == 4
        assert "worst_case" in result
        assert "best_case" in result

        # Check that all price points are covered
        for price in price_points:
            assert price in result["price_scenarios"]

    def test_price_ladder_analysis_with_options(self):
        """Test price ladder analysis includes option positions correctly."""
        price_points = [140, 150, 160]  # Around strike price
        result = self.scenario_engine.price_ladder_analysis("AAPL", price_points)

        # At $140 (below strike), option should be worthless
        # At $160 (above strike), option should have intrinsic value
        scenarios = result["price_scenarios"]

        # Check that option value changes appropriately
        assert scenarios[140] < scenarios[160]  # Higher price should give higher total value

    def test_hypothetical_position_analysis(self):
        """Test analysis with hypothetical positions."""
        price_points = [90, 100, 110]
        hypothetical_positions = [
            {
                "symbol": "AAPL",
                "quantity": 50,
                "entry_price": 100.0,
                "is_option": False,
                "underlying": "AAPL"
            }
        ]

        result = self.scenario_engine.price_ladder_analysis(
            "AAPL",
            price_points,
            include_positions=False,
            hypothetical_positions=hypothetical_positions
        )

        assert "price_scenarios" in result
        scenarios = result["price_scenarios"]

        # For 50 equity shares at different prices
        assert scenarios[90] == 50 * 90   # 50 shares * $90
        assert scenarios[100] == 50 * 100 # 50 shares * $100
        assert scenarios[110] == 50 * 110 # 50 shares * $110

    def test_option_payoff_at_expiry(self):
        """Test option payoff calculation at expiration."""
        # Test call option
        result = self.scenario_engine.option_payoff_at_expiry(
            "AAPL  241220C00150000",
            price_range=(140, 160)
        )

        assert "osi_symbol" in result
        assert "underlying" in result
        assert result["underlying"] == "AAPL"
        assert result["strike"] == 150.0
        assert result["option_type"] == "C"
        assert "payoffs" in result

        payoffs = result["payoffs"]
        # Check intrinsic values for call option
        for price, payoff in payoffs.items():
            expected_payoff = max(0, price - 150.0)
            assert abs(payoff - expected_payoff) < 0.01

    def test_option_payoff_put_option(self):
        """Test option payoff calculation for put options."""
        # Test with a put option OSI symbol
        result = self.scenario_engine.option_payoff_at_expiry(
            "AAPL  241220P00150000",
            price_range=(140, 160)
        )

        assert result["option_type"] == "P"
        payoffs = result["payoffs"]

        # Check intrinsic values for put option
        for price, payoff in payoffs.items():
            expected_payoff = max(0, 150.0 - price)
            assert abs(payoff - expected_payoff) < 0.01

    def test_time_decay_analysis(self):
        """Test time decay analysis functionality."""
        result = self.scenario_engine.time_decay_analysis("AAPL  241220C00150000")

        assert "osi_symbol" in result
        assert "theta" in result
        assert "current_price" in result
        assert "time_decay_values" in result

        # Check that time decay reduces option value over time
        time_values = result["time_decay_values"]
        assert time_values[0] > time_values[30]  # Value should decrease over time with theta

    def test_capital_impact_analysis(self):
        """Test capital impact analysis."""
        scenarios = [
            {"price": 80, "probability": 0.3},
            {"price": 100, "probability": 0.4},
            {"price": 120, "probability": 0.3}
        ]

        result = self.scenario_engine.capital_impact_analysis("AAPL", scenarios, 50000.0)

        assert "current_capital" in result
        assert result["current_capital"] == 50000.0
        assert "expected_capital_change" in result
        assert "scenarios" in result
        assert len(result["scenarios"]) == 3

        # Check that each scenario has required fields
        for scenario in result["scenarios"]:
            assert "price" in scenario
            assert "probability" in scenario
            assert "capital_change" in scenario
            assert "new_capital" in scenario

    def test_osi_symbol_parsing(self):
        """Test OSI symbol parsing functionality."""
        # Test call option
        call_details = self.scenario_engine._parse_osi_symbol("AAPL  241220C00150000")
        assert call_details["underlying"] == "AAPL"
        assert call_details["type"] == "C"
        assert call_details["strike"] == 150.0

        # Test put option
        put_details = self.scenario_engine._parse_osi_symbol("AAPL  241220P00095000")
        assert put_details["underlying"] == "AAPL"
        assert put_details["type"] == "P"
        assert put_details["strike"] == 95.0

    def test_option_type_detection(self):
        """Test option type detection (call vs put)."""
        # Test with OSI symbols
        assert self.scenario_engine._is_call_option("AAPL  241220C00150000") == True
        assert self.scenario_engine._is_call_option("AAPL  241220P00150000") == False

    def test_position_value_calculation_equity(self):
        """Test position value calculation for equity."""
        position = Position(
            symbol="AAPL",
            quantity=100,
            entry_price=95.0,
            instrument_type=InstrumentType.EQUITY
        )

        value = self.scenario_engine._calculate_position_value(position, 110.0)
        assert value == 100 * 110.0  # 100 shares * $110

    def test_position_value_calculation_option(self):
        """Test position value calculation for options."""
        # Call option position
        call_position = Position(
            symbol="AAPL  241220C00150000",
            quantity=5,
            entry_price=4.0,
            instrument_type=InstrumentType.OPTION,
            strike=150.0,
            osi_symbol="AAPL  241220C00150000"
        )

        # At $160, call should have $10 intrinsic value per share
        value = self.scenario_engine._calculate_position_value(call_position, 160.0)
        assert value == 5 * 10.0 * 100  # 5 contracts * $10 intrinsic * 100 shares per contract

        # At $140, call should be worthless
        value = self.scenario_engine._calculate_position_value(call_position, 140.0)
        assert value == 0.0

    def test_format_scenario_summary(self):
        """Test scenario results formatting."""
        mock_result = {
            "symbol": "AAPL",
            "current_value": 15000.0,
            "worst_case": {
                "price": 80.0,
                "value": 12000.0,
                "change": -3000.0,
                "change_pct": -20.0
            },
            "best_case": {
                "price": 120.0,
                "value": 18000.0,
                "change": 3000.0,
                "change_pct": 20.0
            },
            "price_scenarios": {
                80: 12000.0,
                100: 15000.0,
                120: 18000.0
            }
        }

        summary = self.scenario_engine.format_scenario_summary(mock_result)

        assert "AAPL" in summary
        assert "$15,000.00" in summary
        assert "Worst case" in summary
        assert "Best case" in summary
        assert "$80.00" in summary
        assert "$120.00" in summary

    def test_error_handling_no_positions(self):
        """Test handling when no positions exist for a symbol."""
        self.mock_portfolio.get_positions.return_value = []

        result = self.scenario_engine.price_ladder_analysis("TSLA", [100, 200])

        # Should still return valid structure even with no positions
        assert "symbol" in result
        assert result["symbol"] == "TSLA"

    def test_error_handling_invalid_osi(self):
        """Test handling of invalid OSI symbols."""
        result = self.scenario_engine.option_payoff_at_expiry("INVALID_SYMBOL")

        assert "error" in result
        assert "Could not parse OSI symbol" in result["error"]

    def test_price_ladder_worst_best_case(self):
        """Test that worst and best case scenarios are correctly identified."""
        price_points = [50, 100, 150, 200]
        result = self.scenario_engine.price_ladder_analysis("AAPL", price_points)

        worst_case = result["worst_case"]
        best_case = result["best_case"]

        # Best case should have higher value than worst case
        assert best_case["value"] > worst_case["value"]

        # Worst and best case prices should be from our price points
        assert worst_case["price"] in price_points
        assert best_case["price"] in price_points