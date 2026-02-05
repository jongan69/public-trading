"""Portfolio allocation and position tracking."""
import re
from typing import Dict, List, Optional
from loguru import logger
from datetime import date

from public_api_sdk import InstrumentType

from src.client import TradingClient
from src.market_data import MarketDataManager
from src.config import config
from src.utils.sdk_serializer import extract_portfolio_position_data, extract_portfolio_data


class Position:
    """Represents a single position."""
    
    def __init__(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        instrument_type: InstrumentType = InstrumentType.EQUITY,
        osi_symbol: Optional[str] = None,
        expiration: Optional[str] = None,
        strike: Optional[float] = None,
        underlying: Optional[str] = None
    ):
        """Initialize a position.
        
        Args:
            symbol: Symbol (OSI for options, regular symbol for equity)
            quantity: Number of shares/contracts
            entry_price: Entry price per share/contract
            instrument_type: Type of instrument
            osi_symbol: OSI symbol for options
            expiration: Expiration date for options
            strike: Strike price for options
            underlying: Underlying symbol for options
        """
        self.symbol = symbol
        self.quantity = quantity
        self.entry_price = entry_price
        self.instrument_type = instrument_type
        self.osi_symbol = osi_symbol
        self.expiration = expiration
        self.strike = strike
        self.underlying = underlying
    
    def get_market_value(self, current_price: float) -> float:
        """Calculate current market value.
        
        Args:
            current_price: Current price per share/contract
            
        Returns:
            Market value
        """
        return self.quantity * current_price
    
    def get_pnl(self, current_price: float) -> float:
        """Calculate profit/loss.
        
        Args:
            current_price: Current price per share/contract
            
        Returns:
            P/L amount
        """
        return (current_price - self.entry_price) * self.quantity
    
    def get_pnl_pct(self, current_price: float) -> float:
        """Calculate profit/loss percentage.
        
        Args:
            current_price: Current price per share/contract
            
        Returns:
            P/L percentage
        """
        if self.entry_price == 0:
            return 0.0
        return ((current_price - self.entry_price) / self.entry_price) * 100
    
    def get_dte(self) -> Optional[int]:
        """Get days to expiration for options.
        
        Returns:
            Days to expiration or None if not an option
        """
        if not self.expiration:
            return None
        
        try:
            exp_date = date.fromisoformat(self.expiration)
            return (exp_date - date.today()).days
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse expiration date '{self.expiration}': {e}")
            return None
    
    def is_itm(self, underlying_price: float) -> bool:
        """Check if option is in the money.
        
        Args:
            underlying_price: Current underlying price
            
        Returns:
            True if ITM, False otherwise (or if not an option)
        """
        if not self.strike or self.instrument_type != InstrumentType.OPTION:
            return False
        
        # For calls: ITM if underlying > strike
        return underlying_price > self.strike


class PortfolioManager:
    """Manages portfolio allocation and position tracking."""
    
    def __init__(self, client: TradingClient, data_manager: MarketDataManager):
        """Initialize the portfolio manager.
        
        Args:
            client: Trading client instance
            data_manager: Market data manager instance
        """
        self.client = client
        self.data_manager = data_manager
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        logger.info("Portfolio manager initialized")
    
    def refresh_portfolio(self):
        """Refresh portfolio data from API."""
        try:
            portfolio = self.client.client.get_portfolio(self.client.account_number)
            
            # Get equity and buying power with proper handling
            equity = self.get_equity()
            buying_power = self.get_buying_power()
            
            # Clear existing positions before loading fresh ones
            self.positions.clear()
            
            # Load positions from portfolio response using comprehensive extraction
            # PortfolioPosition structure: instrument.symbol, quantity, cost_basis.unit_cost, etc.
            if hasattr(portfolio, 'positions') and portfolio.positions:
                for pos in portfolio.positions:
                    try:
                        # Use comprehensive serializer to extract ALL fields
                        pos_data = extract_portfolio_position_data(pos)
                        
                        symbol = pos_data.get("symbol")
                        if not symbol:
                            continue
                        
                        quantity = pos_data.get("quantity") or 0
                        if quantity == 0:
                            continue
                        
                        instrument_type_str = pos_data.get("instrument_type")
                        if isinstance(instrument_type_str, str):
                            # Convert string to InstrumentType enum
                            instrument_type = InstrumentType.EQUITY
                            if "OPTION" in instrument_type_str.upper():
                                instrument_type = InstrumentType.OPTION
                            elif "CRYPTO" in instrument_type_str.upper():
                                instrument_type = InstrumentType.CRYPTO
                        else:
                            instrument_type = InstrumentType.EQUITY
                        
                        # Extract entry price (prefer unit_cost, fallback to average_cost or calculated)
                        entry_price = pos_data.get("unit_cost") or pos_data.get("average_cost") or 0.0
                        if entry_price == 0.0 and pos_data.get("total_cost") and quantity > 0:
                            entry_price = pos_data.get("total_cost") / quantity
                        
                        # For options, parse OSI symbol to extract underlying, strike, expiration
                        osi_symbol = symbol if instrument_type == InstrumentType.OPTION else None
                        underlying = None
                        strike = None
                        expiration = None
                        
                        if instrument_type == InstrumentType.OPTION and osi_symbol:
                            # Parse OSI format: SYMBOL + YYMMDD + C/P + STRIKE*1000 (8 digits)
                            # API may return symbol with suffix e.g. "AMPX260320C00014000-OPTION"
                            osi_clean = re.sub(r"-OPTION$", "", str(osi_symbol)).strip()
                            try:
                                match = re.match(r'^([A-Z]+)(\d{6})([CP])(\d{8})$', osi_clean)
                                if match:
                                    underlying = match.group(1)
                                    date_str = match.group(2)
                                    option_type = match.group(3)
                                    strike_str = match.group(4)
                                    yy = int(date_str[:2])
                                    mm = int(date_str[2:4])
                                    dd = int(date_str[4:6])
                                    # For OSI format, YY is always in current century (2000-2099)
                                    year = 2000 + yy
                                    expiration = f"{year:04d}-{mm:02d}-{dd:02d}"
                                    strike = float(strike_str) / 1000.0
                                else:
                                    # Fallback: underlying = leading letters before first digit
                                    letter_match = re.match(r"^([A-Z]+)", osi_clean)
                                    if letter_match:
                                        underlying = letter_match.group(1)
                            except Exception as e:
                                logger.debug(f"Could not parse OSI symbol {osi_symbol}: {e}")
                        
                        position = Position(
                            symbol=symbol,
                            quantity=quantity,
                            entry_price=entry_price,
                            instrument_type=instrument_type,
                            osi_symbol=osi_symbol,
                            expiration=expiration,
                            strike=strike,
                            underlying=underlying
                        )
                        self.positions[symbol] = position
                        logger.debug(f"Loaded position: {symbol} x{quantity} @ ${entry_price:.2f}")
                    except Exception as e:
                        logger.warning(f"Error loading position: {e}", exc_info=True)
                        continue
            
            logger.info(f"Portfolio refreshed: equity=${equity:.2f}, buying_power=${buying_power:.2f}")
            
        except Exception as e:
            logger.error(f"Error refreshing portfolio: {e}")
            raise
    
    def get_portfolio_comprehensive(self) -> Dict:
        """Get comprehensive portfolio data with ALL fields for AI consumption.
        
        Returns:
            Dictionary with all portfolio fields including comprehensive position data
        """
        try:
            portfolio = self.client.client.get_portfolio(self.client.account_number)
            portfolio_data = extract_portfolio_data(portfolio)
            
            # Add calculated fields
            portfolio_data["equity"] = self.get_equity()
            portfolio_data["buying_power"] = self.get_buying_power()
            portfolio_data["cash"] = self.get_cash()
            
            return portfolio_data
        except Exception as e:
            logger.error(f"Error getting comprehensive portfolio: {e}")
            return {}
    
    def get_equity(self) -> float:
        """Get current portfolio equity.
        
        Returns:
            Equity value (sum of all asset-type values from API, or cash when API equity is 0).
        """
        try:
            portfolio = self.client.client.get_portfolio(self.client.account_number)
            equity = portfolio.equity
            
            # Handle different response formats
            if isinstance(equity, list):
                # API returns List[PortfolioEquity] with .value (Decimal) per asset type
                total = 0.0
                for x in equity:
                    if isinstance(x, (int, float)):
                        total += float(x)
                    elif hasattr(x, "value"):
                        total += float(x.value)
                    elif hasattr(x, "__float__"):
                        total += float(x)
                equity = total if total > 0 else 0.0
            elif hasattr(equity, "__float__"):
                equity = float(equity)
            elif hasattr(equity, "value"):
                equity = float(equity.value)
            elif isinstance(equity, str):
                equity = float(equity)
            else:
                try:
                    equity = float(equity)
                except (TypeError, ValueError):
                    logger.warning(f"Unexpected equity type: {type(equity)}, value: {equity}")
                    equity = 0.0

            # Fallback: API may return 0 equity for cash-only; use cash as effective equity
            if equity == 0:
                cash = self.get_cash()
                if cash > 0:
                    equity = cash
            return float(equity)
        except Exception as e:
            logger.error(f"Error getting equity: {e}")
            return 0.0
    
    def get_buying_power(self) -> float:
        """Get current buying power.
        
        Returns:
            Buying power value
        """
        try:
            portfolio = self.client.client.get_portfolio(self.client.account_number)
            buying_power = portfolio.buying_power
            
            # Handle different response formats
            if isinstance(buying_power, list):
                if len(buying_power) == 0:
                    buying_power = 0.0
                elif len(buying_power) == 1:
                    buying_power = buying_power[0] if isinstance(buying_power[0], (int, float)) else 0.0
                else:
                    # Multiple values - sum them
                    buying_power = sum(float(x) for x in buying_power if isinstance(x, (int, float)))
            elif hasattr(buying_power, 'buying_power'):
                # BuyingPower object with buying_power attribute
                bp_value = buying_power.buying_power
                buying_power = float(bp_value) if hasattr(bp_value, '__float__') else float(bp_value)
            elif hasattr(buying_power, 'cash_only_buying_power'):
                # BuyingPower object - use cash_only_buying_power as fallback
                bp_value = buying_power.cash_only_buying_power
                buying_power = float(bp_value) if hasattr(bp_value, '__float__') else float(bp_value)
            elif hasattr(buying_power, '__float__'):
                # Object with __float__ method (like Decimal)
                buying_power = float(buying_power)
            elif hasattr(buying_power, 'value'):
                # Object with value attribute
                buying_power = float(buying_power.value)
            elif isinstance(buying_power, str):
                buying_power = float(buying_power)
            else:
                try:
                    buying_power = float(buying_power)
                except (TypeError, ValueError):
                    logger.warning(f"Unexpected buying_power type: {type(buying_power)}, value: {buying_power}")
                    buying_power = 0.0
            
            return float(buying_power)
        except Exception as e:
            logger.error(f"Error getting buying_power: {e}")
            return 0.0
    
    def get_cash(self) -> float:
        """Get cash balance.
        
        Returns:
            Cash balance
        """
        try:
            portfolio = self.client.client.get_portfolio(self.client.account_number)
            
            # Try to get cash directly
            if hasattr(portfolio, 'cash'):
                cash = portfolio.cash
                # Handle different response formats
                if isinstance(cash, list):
                    if len(cash) == 0:
                        cash = 0.0
                    elif len(cash) == 1:
                        cash = cash[0] if isinstance(cash[0], (int, float)) else 0.0
                    else:
                        # Multiple values - sum them
                        cash = sum(float(x) for x in cash if isinstance(x, (int, float)))
                elif hasattr(cash, '__float__'):
                    # Object with __float__ method (like Decimal)
                    cash = float(cash)
                elif hasattr(cash, 'value'):
                    # Object with value attribute
                    cash = float(cash.value)
                elif isinstance(cash, str):
                    cash = float(cash)
                else:
                    try:
                        cash = float(cash)
                    except (TypeError, ValueError):
                        logger.warning(f"Unexpected cash type: {type(cash)}, value: {cash}")
                        cash = 0.0
                return float(cash)
            else:
                # Fallback to cash_only_buying_power from buying_power object if available
                if hasattr(portfolio, 'buying_power') and hasattr(portfolio.buying_power, 'cash_only_buying_power'):
                    bp_value = portfolio.buying_power.cash_only_buying_power
                    return float(bp_value) if hasattr(bp_value, '__float__') else float(bp_value)
                # Otherwise fallback to buying power
                return self.get_buying_power()
        except Exception as e:
            logger.error(f"Error getting cash: {e}")
            return 0.0
    
    def get_positions_by_theme(self) -> Dict[str, List[Position]]:
        """Get positions grouped by theme.
        
        Returns:
            Dictionary mapping theme name to list of positions
        """
        themes = {
            "theme_a": [],  # UMC
            "theme_b": [],  # TE
            "theme_c": [],  # AMPX
            "moonshot": [],
        }
        
        theme_symbols = config.theme_underlyings
        for position in self.positions.values():
            # Moonshot: match by symbol (e.g. GME.WS)
            if position.symbol == config.moonshot_symbol:
                themes["moonshot"].append(position)
                continue
            # Theme A/B/C: options by underlying, or equity by symbol
            underlying = position.underlying
            if position.instrument_type == InstrumentType.OPTION and not underlying and position.symbol:
                # Derive underlying from OSI (e.g. "UMC250117C00100000" or "AMPX...-OPTION")
                base = re.sub(r"-OPTION$", "", str(position.symbol)).strip()
                letter_match = re.match(r"^([A-Z]+)", base)
                if letter_match:
                    underlying = letter_match.group(1)
            symbol_for_theme = underlying or position.symbol
            if symbol_for_theme == theme_symbols[0]:
                themes["theme_a"].append(position)
            elif len(theme_symbols) > 1 and symbol_for_theme == theme_symbols[1]:
                themes["theme_b"].append(position)
            elif len(theme_symbols) > 2 and symbol_for_theme == theme_symbols[2]:
                themes["theme_c"].append(position)
        
        return themes
    
    def get_current_allocations(self) -> Dict[str, float]:
        """Calculate current allocations as percentages of equity.
        
        Returns:
            Dictionary with allocation percentages
        """
        equity = self.get_equity()
        if equity == 0:
            return {
                "theme_a": 0.0,
                "theme_b": 0.0,
                "theme_c": 0.0,
                "moonshot": 0.0,
                "cash": 0.0,
            }
        
        themes = self.get_positions_by_theme()
        
        # Calculate market values
        theme_a_value = sum(
            pos.get_market_value(self.get_position_price(pos))
            for pos in themes["theme_a"]
        )
        theme_b_value = sum(
            pos.get_market_value(self.get_position_price(pos))
            for pos in themes["theme_b"]
        )
        theme_c_value = sum(
            pos.get_market_value(self.get_position_price(pos))
            for pos in themes["theme_c"]
        )
        moonshot_value = sum(
            pos.get_market_value(self.get_position_price(pos))
            for pos in themes["moonshot"]
        )
        
        cash = self.get_cash()
        
        return {
            "theme_a": theme_a_value / equity,
            "theme_b": theme_b_value / equity,
            "theme_c": theme_c_value / equity,
            "moonshot": moonshot_value / equity,
            "cash": cash / equity,
        }

    def _classify_asset_type(self, instrument_type: InstrumentType) -> str:
        """Map InstrumentType to asset class bucket.

        Args:
            instrument_type: Public.com API instrument type

        Returns:
            Asset class: "equity", "crypto", "bonds", "alt"
        """
        if instrument_type == InstrumentType.CRYPTO:
            return "crypto"
        elif instrument_type in (InstrumentType.BOND, InstrumentType.TREASURY):
            return "bonds"
        elif instrument_type == InstrumentType.ALT:
            return "alt"
        else:  # EQUITY, OPTION, INDEX, MULTI_LEG_INSTRUMENT
            return "equity"

    def get_allocations_by_type(self) -> Dict[str, Dict[str, float]]:
        """Calculate portfolio allocation by asset type.

        Returns allocation split across equity, crypto, bonds, alt, and cash.
        Similar to get_current_allocations() but groups by asset class instead of theme.

        Returns:
            Dict with percentages and dollar values per asset type:
            {
                "equity": {"pct": 0.70, "value": 100000.0},
                "crypto": {"pct": 0.15, "value": 21500.0},
                "bonds": {"pct": 0.0, "value": 0.0},
                "alt": {"pct": 0.0, "value": 0.0},
                "cash": {"pct": 0.15, "value": 21500.0}
            }
        """
        equity = self.get_equity()

        # Handle zero equity
        if equity == 0:
            return {
                "equity": {"pct": 0.0, "value": 0.0},
                "crypto": {"pct": 0.0, "value": 0.0},
                "bonds": {"pct": 0.0, "value": 0.0},
                "alt": {"pct": 0.0, "value": 0.0},
                "cash": {"pct": 0.0, "value": 0.0},
            }

        # Initialize type value accumulators
        type_values = {
            "equity": 0.0,
            "crypto": 0.0,
            "bonds": 0.0,
            "alt": 0.0,
        }

        # Sum market values per asset type
        for position in self.positions.values():
            asset_type = self._classify_asset_type(position.instrument_type)
            market_value = position.get_market_value(self.get_position_price(position))
            type_values[asset_type] += market_value

        # Add cash
        cash = self.get_cash()

        # Build result with both percentages and dollar values
        result = {}
        for asset_type, value in type_values.items():
            result[asset_type] = {
                "pct": value / equity,
                "value": value
            }

        result["cash"] = {
            "pct": cash / equity,
            "value": cash
        }

        return result

    def get_target_allocations(self) -> Dict[str, float]:
        """Get target allocations.
        
        Returns:
            Dictionary with target allocation percentages
        """
        return {
            "theme_a": config.theme_a_target,
            "theme_b": config.theme_b_target,
            "theme_c": config.theme_c_target,
            "moonshot": config.moonshot_target,
            "cash": config.cash_minimum,
        }
    
    def calculate_rebalance_needs(self) -> Dict[str, float]:
        """Calculate rebalancing needs.
        
        Returns:
            Dictionary with target dollar amounts for each theme
        """
        equity = self.get_equity()
        targets = self.get_target_allocations()
        current = self.get_current_allocations()
        
        needs = {}
        for theme in ["theme_a", "theme_b", "theme_c", "moonshot"]:
            target_value = equity * targets[theme]
            current_value = equity * current[theme]
            needs[theme] = target_value - current_value
        
        return needs
    
    def get_position_price(self, position: Position) -> float:
        """Get current price for a position. Always returns a float (never None).
        
        Args:
            position: Position to get price for
            
        Returns:
            Current price, or entry price, or 0.0 if unavailable
        """
        if position.instrument_type == InstrumentType.OPTION and position.osi_symbol:
            quote = self.data_manager.get_quote(position.osi_symbol, InstrumentType.OPTION)
            if quote is not None:
                return float(quote)
        quote = self.data_manager.get_quote(position.symbol)
        if quote is not None:
            return float(quote)
        try:
            return float(position.entry_price) if position.entry_price is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def get_position_sell_price(self, position: Position) -> float:
        """Get price to use for a SELL order (bid for options, last/mid for equity).
        
        For options, uses the bid so the limit sell is at the price buyers are offering.
        Never returns 0: falls back to mid, last, then get_position_price (entry).
        
        Args:
            position: Position to sell
            
        Returns:
            Limit price to use for the sell order
        """
        if position.instrument_type == InstrumentType.OPTION:
            symbol = position.osi_symbol or position.symbol
            bid_ask = self.data_manager.get_quote_bid_ask(symbol, InstrumentType.OPTION)
            if bid_ask:
                for key in ("bid", "mid", "last"):
                    val = bid_ask.get(key)
                    if val is not None and float(val) > 0:
                        return float(val)
        fallback = self.get_position_price(position)
        return fallback if fallback and fallback > 0 else (float(position.entry_price) if position.entry_price else 0.0)

    def display_portfolio_breakdown(self):
        """Display comprehensive portfolio holdings breakdown."""
        equity = self.get_equity()
        buying_power = self.get_buying_power()
        cash = self.get_cash()
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("PORTFOLIO BREAKDOWN")
        logger.info("=" * 70)
        logger.info(f"Total Equity:     ${equity:>12,.2f}")
        logger.info(f"Buying Power:     ${buying_power:>12,.2f}")
        logger.info(f"Cash:             ${cash:>12,.2f}")
        logger.info("")
        
        # Get allocations
        current_allocations = self.get_current_allocations()
        target_allocations = self.get_target_allocations()
        themes = self.get_positions_by_theme()
        
        # Display allocation summary
        logger.info("ALLOCATION SUMMARY")
        logger.info("-" * 70)
        theme_names = {
            "theme_a": f"Theme A ({config.theme_underlyings[0]})",
            "theme_b": f"Theme B ({config.theme_underlyings[1]})",
            "theme_c": f"Theme C ({config.theme_underlyings[2] if len(config.theme_underlyings) > 2 else 'N/A'})",
            "moonshot": f"Moonshot ({config.moonshot_symbol})",
            "cash": "Cash",
        }
        
        for theme_key, theme_label in theme_names.items():
            current_pct = current_allocations.get(theme_key, 0.0) * 100
            target_pct = target_allocations.get(theme_key, 0.0) * 100
            current_value = equity * current_allocations.get(theme_key, 0.0)
            
            status = "✓" if abs(current_pct - target_pct) < 5 else "⚠"
            logger.info(
                f"{status} {theme_label:25s} "
                f"Current: {current_pct:>6.1f}% (${current_value:>8,.2f}) | "
                f"Target: {target_pct:>6.1f}%"
            )
        
        logger.info("")
        
        # Display positions by theme
        total_positions_value = 0.0
        total_pnl = 0.0
        has_any_positions = any(len(positions) > 0 for key, positions in themes.items() if key != "cash")
        
        if not has_any_positions:
            logger.info("No positions currently held.")
            logger.info("")
        
        for theme_key, theme_label in theme_names.items():
            if theme_key == "cash":
                continue
                
            positions = themes.get(theme_key, [])
            if not positions:
                continue
            
            logger.info(f"{theme_label.upper()}")
            logger.info("-" * 70)
            
            theme_value = 0.0
            theme_pnl = 0.0
            
            for position in positions:
                current_price = self.get_position_price(position)
                if current_price <= 0:
                    current_price = position.entry_price or 0.0
                market_value = position.get_market_value(current_price)
                pnl = position.get_pnl(current_price)
                pnl_pct = position.get_pnl_pct(current_price) if (position.entry_price or 0) != 0 else 0.0
                
                theme_value += market_value
                theme_pnl += pnl
                total_positions_value += market_value
                total_pnl += pnl
                
                # Format position display
                if position.instrument_type == InstrumentType.OPTION:
                    dte = position.get_dte()
                    dte_str = f"DTE: {dte}" if dte is not None else "DTE: N/A"
                    strike_str = f"Strike: ${position.strike:.2f}" if position.strike else "Strike: N/A"
                    underlying = position.underlying or "N/A"
                    underlying_price = self.data_manager.get_quote(underlying) if underlying != "N/A" else 0
                    itm_str = "ITM" if position.is_itm(underlying_price) else "OTM"
                    
                    # Clean symbol display: show underlying + expiration + strike if available
                    if underlying != "N/A" and position.expiration and position.strike:
                        exp_short = position.expiration.replace("-", "")[-6:] if position.expiration else ""
                        display_symbol = f"{underlying} {exp_short} ${position.strike:.0f}C"
                    else:
                        # Fallback to cleaned OSI symbol
                        display_symbol = re.sub(r"-OPTION$", "", position.symbol).strip()
                    
                    logger.info(
                        f"  {display_symbol:20s} | "
                        f"Qty: {position.quantity:>4d} | "
                        f"Entry: ${position.entry_price:>7.2f} | "
                        f"Current: ${current_price:>7.2f} | "
                        f"Value: ${market_value:>8,.2f}"
                    )
                    logger.info(
                        f"    P/L: ${pnl:>8,.2f} ({pnl_pct:>+6.1f}%) | "
                        f"{dte_str} | {strike_str} | {itm_str} | "
                        f"Underlying: {underlying} @ ${underlying_price:.2f}"
                    )
                else:
                    logger.info(
                        f"  {position.symbol:20s} | "
                        f"Qty: {position.quantity:>4d} | "
                        f"Entry: ${position.entry_price:>7.2f} | "
                        f"Current: ${current_price:>7.2f} | "
                        f"Value: ${market_value:>8,.2f}"
                    )
                    logger.info(
                        f"    P/L: ${pnl:>8,.2f} ({pnl_pct:>+6.1f}%)"
                    )
            
            # Count options vs equity in this theme
            option_count = sum(1 for p in positions if p.instrument_type == InstrumentType.OPTION)
            equity_count = sum(1 for p in positions if p.instrument_type == InstrumentType.EQUITY)
            position_summary = []
            if option_count > 0:
                position_summary.append(f"{option_count} option{'s' if option_count != 1 else ''}")
            if equity_count > 0:
                position_summary.append(f"{equity_count} equity position{'s' if equity_count != 1 else ''}")
            summary_str = f" ({', '.join(position_summary)})" if position_summary else ""
            
            logger.info(f"  Theme Total: ${theme_value:>10,.2f} | P/L: ${theme_pnl:>10,.2f}{summary_str}")
            logger.info("")
        
        # Summary (equity from API may include other assets beyond positions + cash)
        logger.info("PORTFOLIO SUMMARY")
        logger.info("-" * 70)
        logger.info(f"Total Positions Value: ${total_positions_value:>10,.2f}")
        logger.info(f"Total P/L:             ${total_pnl:>10,.2f} ({total_pnl/equity*100 if equity > 0 else 0:.2f}%)")
        logger.info(f"Cash:                  ${cash:>10,.2f}")
        positions_plus_cash = total_positions_value + cash
        if equity > 0 and abs(equity - positions_plus_cash) > 0.01:
            other = equity - positions_plus_cash
            logger.info(f"Other (savings/etc):   ${other:>10,.2f} ({(other/equity)*100:.1f}%)")
        logger.info(f"Total Equity:          ${equity:>10,.2f}")
        logger.info("=" * 70)
        logger.info("")
    
    def add_position(self, position: Position):
        """Add a position to the portfolio.
        
        Args:
            position: Position to add
        """
        if position.symbol in self.positions:
            # Update existing position
            existing = self.positions[position.symbol]
            # Combine positions (average entry price)
            total_cost = (existing.quantity * existing.entry_price) + (position.quantity * position.entry_price)
            total_quantity = existing.quantity + position.quantity
            existing.entry_price = total_cost / total_quantity if total_quantity > 0 else existing.entry_price
            existing.quantity = total_quantity
        else:
            self.positions[position.symbol] = position
        
        logger.info(f"Position added: {position.symbol} x{position.quantity} @ ${position.entry_price:.2f}")
    
    def remove_position(self, symbol: str, quantity: Optional[int] = None):
        """Remove a position or reduce quantity.
        
        Args:
            symbol: Symbol to remove/reduce
            quantity: Quantity to remove (None to remove all)
        """
        if symbol not in self.positions:
            logger.warning(f"Position not found: {symbol}")
            return
        
        position = self.positions[symbol]
        
        if quantity is None or quantity >= position.quantity:
            del self.positions[symbol]
            logger.info(f"Position removed: {symbol}")
        else:
            position.quantity -= quantity
            logger.info(f"Position reduced: {symbol} by {quantity}")
