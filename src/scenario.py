"""Scenario simulation engine for option and position analysis."""
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, date
from loguru import logger
import math

from public_api_sdk import InstrumentType, OptionChainResponse

from src.market_data import MarketDataManager
from src.portfolio import PortfolioManager, Position
from src.config import config


class ScenarioEngine:
    """Engine for running price scenarios and option analysis."""

    def __init__(self, market_data: MarketDataManager, portfolio: PortfolioManager):
        """Initialize the scenario engine.

        Args:
            market_data: Market data manager instance
            portfolio: Portfolio manager instance
        """
        self.market_data = market_data
        self.portfolio = portfolio
        logger.info("Scenario engine initialized")

    def price_ladder_analysis(
        self,
        symbol: str,
        price_points: List[float],
        include_positions: bool = True,
        hypothetical_positions: Optional[List[Dict]] = None
    ) -> Dict[str, Union[float, Dict[float, float]]]:
        """Analyze position value at different underlying price points.

        Args:
            symbol: Underlying symbol to analyze
            price_points: List of price points to evaluate
            include_positions: Include current positions in analysis
            hypothetical_positions: Additional hypothetical positions to include

        Returns:
            Dictionary with analysis results including value at each price point
        """
        try:
            results = {
                "symbol": symbol,
                "analysis_date": datetime.now().isoformat(),
                "price_scenarios": {},
                "worst_case": {"price": None, "value": None, "change": None},
                "best_case": {"price": None, "value": None, "change": None},
                "current_value": 0.0
            }

            # Get current positions for this underlying
            positions = []
            if include_positions:
                current_positions = self.portfolio.get_positions()
                for pos in current_positions:
                    if (pos.instrument_type == InstrumentType.EQUITY and pos.symbol == symbol) or \
                       (pos.instrument_type == InstrumentType.OPTION and pos.underlying == symbol):
                        positions.append(pos)

            # Add hypothetical positions
            if hypothetical_positions:
                for hyp_pos in hypothetical_positions:
                    pos = Position(
                        symbol=hyp_pos.get("symbol", ""),
                        quantity=hyp_pos.get("quantity", 0),
                        entry_price=hyp_pos.get("entry_price", 0.0),
                        instrument_type=InstrumentType.OPTION if hyp_pos.get("is_option", False) else InstrumentType.EQUITY,
                        osi_symbol=hyp_pos.get("osi_symbol"),
                        expiration=hyp_pos.get("expiration"),
                        strike=hyp_pos.get("strike"),
                        underlying=hyp_pos.get("underlying", symbol)
                    )
                    positions.append(pos)

            if not positions:
                logger.warning(f"No positions found for {symbol}")
                return results

            # Get current underlying price for reference
            current_price = self.market_data.get_quote(symbol)
            if current_price:
                current_value = sum(self._calculate_position_value(pos, current_price) for pos in positions)
                results["current_value"] = current_value

            # Calculate value at each price point
            worst_value = float('inf')
            best_value = float('-inf')
            worst_price = None
            best_price = None

            for price_point in sorted(price_points):
                total_value = 0.0

                for position in positions:
                    pos_value = self._calculate_position_value(position, price_point)
                    total_value += pos_value

                results["price_scenarios"][price_point] = total_value

                # Track worst and best case scenarios
                if total_value < worst_value:
                    worst_value = total_value
                    worst_price = price_point
                if total_value > best_value:
                    best_value = total_value
                    best_price = price_point

            # Calculate changes from current value
            if current_value != 0:
                results["worst_case"] = {
                    "price": worst_price,
                    "value": worst_value,
                    "change": worst_value - current_value,
                    "change_pct": ((worst_value - current_value) / abs(current_value)) * 100
                }
                results["best_case"] = {
                    "price": best_price,
                    "value": best_value,
                    "change": best_value - current_value,
                    "change_pct": ((best_value - current_value) / abs(current_value)) * 100
                }

            logger.debug(f"Price ladder analysis completed for {symbol}")
            return results

        except Exception as e:
            logger.error(f"Error in price ladder analysis for {symbol}: {e}")
            return {"error": str(e)}

    def option_payoff_at_expiry(
        self,
        osi_symbol: str,
        price_range: Optional[Tuple[float, float]] = None,
        num_points: int = 20
    ) -> Dict[str, Union[str, Dict[float, float]]]:
        """Calculate option payoff at expiration across price range.

        Args:
            osi_symbol: Option symbol in OSI format
            price_range: (min_price, max_price) or None for auto-range
            num_points: Number of price points to calculate

        Returns:
            Dictionary with payoff analysis
        """
        try:
            # Parse option details from OSI symbol
            option_details = self._parse_osi_symbol(osi_symbol)
            if not option_details:
                return {"error": "Could not parse OSI symbol"}

            underlying = option_details["underlying"]
            strike = option_details["strike"]
            option_type = option_details["type"]  # "C" for call, "P" for put

            # Get current underlying price for auto-range
            current_price = self.market_data.get_quote(underlying)
            if not current_price and not price_range:
                return {"error": "Could not get current price for auto-range"}

            # Set price range
            if price_range is None:
                # Auto-range: ±50% around current price
                min_price = current_price * 0.5
                max_price = current_price * 1.5
            else:
                min_price, max_price = price_range

            # Generate price points
            price_points = []
            for i in range(num_points):
                price = min_price + (max_price - min_price) * i / (num_points - 1)
                price_points.append(price)

            # Calculate intrinsic values at expiry
            payoffs = {}
            for price in price_points:
                if option_type == "C":  # Call option
                    intrinsic = max(0, price - strike)
                else:  # Put option
                    intrinsic = max(0, strike - price)

                payoffs[price] = intrinsic

            return {
                "osi_symbol": osi_symbol,
                "underlying": underlying,
                "strike": strike,
                "option_type": option_type,
                "current_underlying_price": current_price,
                "payoffs": payoffs,
                "breakeven": strike  # For long positions; actual breakeven includes premium
            }

        except Exception as e:
            logger.error(f"Error calculating option payoff for {osi_symbol}: {e}")
            return {"error": str(e)}

    def time_decay_analysis(
        self,
        osi_symbol: str,
        days_forward: List[int] = None
    ) -> Dict[str, Union[str, float, Dict[int, float]]]:
        """Analyze time decay impact on option value.

        Args:
            osi_symbol: Option symbol in OSI format
            days_forward: List of days into the future to analyze

        Returns:
            Dictionary with time decay analysis
        """
        if days_forward is None:
            days_forward = [0, 7, 14, 30, 45, 60]

        try:
            # Get current option Greeks including theta
            greeks = self.market_data.get_option_greeks([osi_symbol])
            if not greeks or osi_symbol not in greeks:
                return {"error": "Could not get option Greeks"}

            theta = greeks[osi_symbol].get("theta", 0)

            # Get current option price
            current_quote = self.market_data.get_quote_bid_ask(
                osi_symbol, InstrumentType.OPTION
            )
            if not current_quote:
                return {"error": "Could not get current option price"}

            current_price = current_quote.get("mid", 0)

            # Simple theta-based decay approximation
            # Note: This is simplified and doesn't account for changing gamma, volatility, etc.
            time_values = {}
            for days in days_forward:
                # Approximate value change due to time decay
                # Theta is typically negative for long positions
                estimated_value = max(0, current_price + (theta * days))
                time_values[days] = estimated_value

            return {
                "osi_symbol": osi_symbol,
                "current_price": current_price,
                "theta": theta,
                "time_decay_values": time_values,
                "daily_decay": theta,
                "note": "Simplified theta-based approximation; actual decay varies with price movement and volatility"
            }

        except Exception as e:
            logger.error(f"Error in time decay analysis for {osi_symbol}: {e}")
            return {"error": str(e)}

    def capital_impact_analysis(
        self,
        symbol: str,
        scenarios: List[Dict],
        current_capital: Optional[float] = None
    ) -> Dict[str, Union[float, List[Dict]]]:
        """Analyze capital impact across multiple scenarios.

        Args:
            symbol: Underlying symbol
            scenarios: List of scenario dicts with 'price' and optional 'probability'
            current_capital: Current capital amount (defaults to portfolio equity)

        Returns:
            Dictionary with capital impact analysis
        """
        try:
            if current_capital is None:
                portfolio_data = self.portfolio.get_portfolio_analysis()
                current_capital = portfolio_data.get("equity", 0)

            # Get price points from scenarios
            price_points = [s["price"] for s in scenarios]

            # Run price ladder analysis
            ladder_results = self.price_ladder_analysis(symbol, price_points)
            if "error" in ladder_results:
                return ladder_results

            # Calculate capital impacts
            scenario_results = []
            expected_value = 0.0
            total_probability = 0.0

            for scenario in scenarios:
                price = scenario["price"]
                probability = scenario.get("probability", 1.0 / len(scenarios))  # Equal weight default

                position_value = ladder_results["price_scenarios"].get(price, 0)
                capital_change = position_value - ladder_results["current_value"]
                new_capital = current_capital + capital_change
                capital_change_pct = (capital_change / current_capital) * 100 if current_capital > 0 else 0

                scenario_result = {
                    "price": price,
                    "probability": probability,
                    "position_value": position_value,
                    "capital_change": capital_change,
                    "new_capital": new_capital,
                    "capital_change_pct": capital_change_pct
                }
                scenario_results.append(scenario_result)

                # Calculate expected value
                expected_value += capital_change * probability
                total_probability += probability

            # Normalize expected value if probabilities don't sum to 1
            if total_probability > 0 and total_probability != 1.0:
                expected_value = expected_value / total_probability

            return {
                "symbol": symbol,
                "current_capital": current_capital,
                "expected_capital_change": expected_value,
                "expected_capital_change_pct": (expected_value / current_capital) * 100 if current_capital > 0 else 0,
                "scenarios": scenario_results,
                "worst_case_capital": min(s["new_capital"] for s in scenario_results),
                "best_case_capital": max(s["new_capital"] for s in scenario_results)
            }

        except Exception as e:
            logger.error(f"Error in capital impact analysis for {symbol}: {e}")
            return {"error": str(e)}

    def _calculate_position_value(self, position: Position, underlying_price: float) -> float:
        """Calculate position value at given underlying price.

        Args:
            position: Position object
            underlying_price: Price of underlying asset

        Returns:
            Position value at the given underlying price
        """
        try:
            if position.instrument_type == InstrumentType.EQUITY:
                # Simple: shares * price
                return position.quantity * underlying_price

            elif position.instrument_type == InstrumentType.OPTION:
                # For options, calculate intrinsic value (simplified)
                if not position.strike:
                    logger.warning(f"No strike price for option {position.symbol}")
                    return 0.0

                # Determine if call or put from OSI symbol
                is_call = self._is_call_option(position.osi_symbol or position.symbol)

                if is_call:
                    intrinsic = max(0, underlying_price - position.strike)
                else:
                    intrinsic = max(0, position.strike - underlying_price)

                # Return intrinsic value * quantity (contracts * 100 shares per contract)
                return intrinsic * position.quantity * 100

            else:
                logger.warning(f"Unknown instrument type for {position.symbol}")
                return 0.0

        except Exception as e:
            logger.error(f"Error calculating position value for {position.symbol}: {e}")
            return 0.0

    def _parse_osi_symbol(self, osi_symbol: str) -> Optional[Dict]:
        """Parse OSI option symbol to extract details.

        Args:
            osi_symbol: Option symbol in OSI format

        Returns:
            Dictionary with parsed details or None
        """
        try:
            # OSI format: SYMBOL + YYMMDD + C/P + Strike price
            # Example: "AAPL  241220C00150000" for Apple Dec 20 2024 $150 Call

            # Remove any trailing "-OPTION" suffix
            symbol = osi_symbol.replace("-OPTION", "").strip()

            # Find the date part (6 digits)
            date_match = None
            option_type = None
            strike_str = None

            # Look for pattern: 6 digits followed by C or P
            import re
            match = re.search(r'(\d{6})([CP])(\d+)', symbol)
            if match:
                date_str = match.group(1)
                option_type = match.group(2)
                strike_str = match.group(3)
                underlying = symbol[:match.start(1)].strip()
            else:
                logger.warning(f"Could not parse OSI symbol: {osi_symbol}")
                return None

            # Parse strike price (usually 8 digits with implied decimal)
            try:
                strike = float(strike_str) / 1000  # OSI uses 3 decimal places
            except ValueError:
                logger.warning(f"Could not parse strike from {strike_str}")
                return None

            return {
                "underlying": underlying,
                "strike": strike,
                "type": option_type,
                "date_str": date_str,
                "original_symbol": osi_symbol
            }

        except Exception as e:
            logger.error(f"Error parsing OSI symbol {osi_symbol}: {e}")
            return None

    def _is_call_option(self, symbol: str) -> bool:
        """Determine if option is a call based on symbol.

        Args:
            symbol: Option symbol

        Returns:
            True if call, False if put
        """
        try:
            # Look for C or P in the symbol
            if 'C' in symbol.upper() and 'P' not in symbol.upper():
                return True
            elif 'P' in symbol.upper() and 'C' not in symbol.upper():
                return False
            else:
                # Try to parse OSI format
                details = self._parse_osi_symbol(symbol)
                if details:
                    return details["type"] == "C"

                # Default assumption (could be made configurable)
                logger.warning(f"Could not determine option type for {symbol}, assuming call")
                return True

        except Exception as e:
            logger.warning(f"Error determining option type for {symbol}: {e}")
            return True  # Default to call

    def format_scenario_summary(self, analysis_result: Dict) -> str:
        """Format scenario analysis results into human-readable text.

        Args:
            analysis_result: Results from price_ladder_analysis or similar

        Returns:
            Formatted text summary
        """
        try:
            if "error" in analysis_result:
                return f"Error in analysis: {analysis_result['error']}"

            symbol = analysis_result.get("symbol", "Unknown")
            current_value = analysis_result.get("current_value", 0)
            worst_case = analysis_result.get("worst_case", {})
            best_case = analysis_result.get("best_case", {})

            summary = f"**Scenario Analysis for {symbol}**\n"
            summary += f"Current position value: ${current_value:,.2f}\n\n"

            if worst_case.get("price") is not None:
                summary += f"**Worst case:** At ${worst_case['price']:,.2f}: "
                summary += f"${worst_case['value']:,.2f} "
                summary += f"({worst_case['change']:+,.2f}, {worst_case.get('change_pct', 0):+.1f}%)\n"

            if best_case.get("price") is not None:
                summary += f"**Best case:** At ${best_case['price']:,.2f}: "
                summary += f"${best_case['value']:,.2f} "
                summary += f"({best_case['change']:+,.2f}, {best_case.get('change_pct', 0):+.1f}%)\n"

            # Add detailed price scenarios
            scenarios = analysis_result.get("price_scenarios", {})
            if scenarios:
                summary += f"\n**Price Scenarios:**\n"
                for price, value in sorted(scenarios.items()):
                    change = value - current_value if current_value else 0
                    change_pct = (change / abs(current_value)) * 100 if current_value != 0 else 0
                    summary += f"At ${price:,.2f}: ${value:,.2f} ({change:+,.2f}, {change_pct:+.1f}%)\n"

            return summary

        except Exception as e:
            logger.error(f"Error formatting scenario summary: {e}")
            return f"Error formatting results: {e}"