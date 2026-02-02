"""Market data retrieval and management."""
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date
from loguru import logger

from public_api_sdk import (
    OrderInstrument,
    InstrumentType,
    OptionExpirationsRequest,
    OptionChainRequest,
    OptionChainResponse,
    OptionExpirationsResponse,
)

from src.client import TradingClient
from src.config import config
from src.utils.trading_hours import is_after_same_day_option_cutoff_et


class MarketDataManager:
    """Manages market data retrieval including quotes, option chains, and Greeks."""
    
    def __init__(self, client: TradingClient):
        """Initialize the market data manager.
        
        Args:
            client: Trading client instance
        """
        self.client = client
        self._quote_cache: Dict[str, float] = {}
        logger.info("Market data manager initialized")
    
    def get_quotes(self, symbols: List[str], instrument_type: InstrumentType = InstrumentType.EQUITY) -> Dict[str, float]:
        """Get current quotes for multiple symbols.
        
        Args:
            symbols: List of symbols to get quotes for
            instrument_type: Type of instrument (default: EQUITY)
            
        Returns:
            Dictionary mapping symbol to last price
        """
        try:
            instruments = [
                OrderInstrument(symbol=symbol, type=instrument_type)
                for symbol in symbols
            ]
            
            quotes = self.client.client.get_quotes(instruments)
            
            result = {}
            for quote in quotes:
                symbol = quote.instrument.symbol
                # last can be None for illiquid options, crypto, or no recent trade
                price = quote.last
                if price is None:
                    # Fallback to bid/ask mid when last is missing
                    bid = getattr(quote, "bid", None)
                    ask = getattr(quote, "ask", None)
                    if bid is not None and ask is not None:
                        try:
                            price = (float(bid) + float(ask)) / 2
                        except (TypeError, ValueError):
                            price = None
                    else:
                        price = None
                else:
                    try:
                        price = float(price)
                    except (TypeError, ValueError):
                        price = None
                if price is not None:
                    result[symbol] = price
                    self._quote_cache[symbol] = price
                else:
                    result[symbol] = None
                    logger.debug(f"No price for {symbol} (last/bid/ask missing)")
            
            logger.debug(f"Retrieved quotes for {len([v for v in result.values() if v is not None])} symbols")
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving quotes: {e}")
            raise
    
    def get_quote(self, symbol: str, instrument_type: InstrumentType = InstrumentType.EQUITY) -> Optional[float]:
        """Get current quote for a single symbol.
        
        Args:
            symbol: Symbol to get quote for
            instrument_type: Type of instrument (default: EQUITY)
            
        Returns:
            Last price or None if error
        """
        try:
            quotes = self.get_quotes([symbol], instrument_type)
            return quotes.get(symbol)
        except Exception as e:
            logger.error(f"Error retrieving quote for {symbol}: {e}")
            return None

    def get_quote_bid_ask(
        self, symbol: str, instrument_type: InstrumentType = InstrumentType.EQUITY
    ) -> Optional[Dict[str, float]]:
        """Get bid, ask, and mid for a symbol (for option sell/buy limit pricing).
        
        Args:
            symbol: Symbol to get quote for
            instrument_type: Type of instrument (default: EQUITY)
            
        Returns:
            Dict with keys bid, ask, mid (and last if available), or None if unavailable
        """
        try:
            api_symbol = re.sub(r"-OPTION$", "", str(symbol)).strip() if instrument_type == InstrumentType.OPTION else symbol
            instruments = [OrderInstrument(symbol=api_symbol, type=instrument_type)]
            quotes = self.client.client.get_quotes(instruments)
            if not quotes:
                return None
            quote = quotes[0]
            bid = float(quote.bid) if quote.bid is not None else None
            ask = float(quote.ask) if quote.ask is not None else None
            last = float(quote.last) if quote.last is not None else None
            if bid is None and ask is None:
                return {"bid": last, "ask": last, "mid": last, "last": last} if last is not None else None
            bid = bid if bid is not None else (ask if ask is not None else last)
            ask = ask if ask is not None else (bid if bid is not None else last)
            mid = (bid + ask) / 2.0 if (bid is not None and ask is not None) else (bid or ask)
            return {"bid": bid, "ask": ask, "mid": mid, "last": last}
        except Exception as e:
            logger.debug(f"Error getting bid/ask for {symbol}: {e}")
            return None
    
    def get_option_expirations(
        self, 
        underlying_symbol: str,
        underlying_type: InstrumentType = InstrumentType.EQUITY
    ) -> List[date]:
        """Get available option expiration dates for an underlying.
        
        Args:
            underlying_symbol: Underlying symbol
            underlying_type: Type of underlying instrument
            
        Returns:
            List of expiration dates
        """
        try:
            request = OptionExpirationsRequest(
                instrument=OrderInstrument(
                    symbol=underlying_symbol,
                    type=underlying_type
                )
            )
            
            response: OptionExpirationsResponse = self.client.client.get_option_expirations(request)
            expirations = [datetime.fromisoformat(exp).date() for exp in response.expirations]
            
            logger.debug(f"Retrieved {len(expirations)} expirations for {underlying_symbol}")
            return expirations
            
        except Exception as e:
            logger.error(f"Error retrieving expirations for {underlying_symbol}: {e}")
            return []
    
    def get_option_chain(
        self,
        underlying_symbol: str,
        expiration_date: date,
        underlying_type: InstrumentType = InstrumentType.EQUITY
    ) -> Optional[OptionChainResponse]:
        """Get option chain for a specific expiration.
        
        Args:
            underlying_symbol: Underlying symbol
            expiration_date: Expiration date
            underlying_type: Type of underlying instrument
            
        Returns:
            Option chain response or None if error
        """
        try:
            expiration_str = expiration_date.isoformat()
            
            request = OptionChainRequest(
                instrument=OrderInstrument(
                    symbol=underlying_symbol,
                    type=underlying_type
                ),
                expiration_date=expiration_str
            )
            
            chain = self.client.client.get_option_chain(request)
            logger.debug(
                f"Retrieved option chain for {underlying_symbol} "
                f"expiring {expiration_str}: {len(chain.calls)} calls"
            )
            return chain
            
        except Exception as e:
            logger.error(
                f"Error retrieving option chain for {underlying_symbol} "
                f"expiring {expiration_date}: {e}"
            )
            return None

    @staticmethod
    def compute_max_pain(chain: OptionChainResponse) -> Optional[Tuple[float, float]]:
        """Compute max pain strike from option chain (open interest–weighted).
        
        Max pain is the strike at which total option holder value at expiration is minimized
        (i.e. maximum pain for holders / maximum gain for writers). Uses OI * 100 per contract.
        
        Returns:
            (max_pain_strike, total_value_at_max_pain) or None if no OI data.
        """
        calls = getattr(chain, "calls", []) or []
        puts = getattr(chain, "puts", []) or []
        strikes_set = set()
        # (strike, oi) for calls and puts
        call_data: List[Tuple[float, int]] = []
        put_data: List[Tuple[float, int]] = []
        for c in calls:
            strike = getattr(c, "strike", None)
            if strike is None:
                continue
            k = float(strike)
            strikes_set.add(k)
            oi = getattr(c, "open_interest", None)
            oi = int(oi) if oi is not None else 0
            call_data.append((k, oi))
        for p in puts:
            strike = getattr(p, "strike", None)
            if strike is None:
                continue
            k = float(strike)
            strikes_set.add(k)
            oi = getattr(p, "open_interest", None)
            oi = int(oi) if oi is not None else 0
            put_data.append((k, oi))
        if not strikes_set:
            return None
        # If no OI anywhere, all totals are 0 -> arbitrary; skip.
        if not call_data and not put_data:
            return None
        if all(oi == 0 for _, oi in call_data) and all(oi == 0 for _, oi in put_data):
            return None
        best_strike = None
        best_total = float("inf")
        for S in sorted(strikes_set):
            call_value = sum(max(0.0, S - K) * 100 * oi for K, oi in call_data)
            put_value = sum(max(0.0, K - S) * 100 * oi for K, oi in put_data)
            total = call_value + put_value
            if total < best_total:
                best_total = total
                best_strike = S
        if best_strike is None:
            return None
        return (best_strike, best_total)
    
    def get_option_greeks(self, osi_symbols: List[str]) -> Dict[str, Dict]:
        """Get Greeks for multiple option contracts.
        
        Args:
            osi_symbols: List of OSI format option symbols
            
        Returns:
            Dictionary mapping OSI symbol to Greeks dict
        """
        try:
            if len(osi_symbols) == 1:
                greek_response = self.client.client.get_option_greek(osi_symbols[0])
                return {osi_symbols[0]: {
                    "delta": float(greek_response.greeks.delta),
                    "gamma": float(greek_response.greeks.gamma),
                    "theta": float(greek_response.greeks.theta),
                    "vega": float(greek_response.greeks.vega),
                }}
            else:
                greeks_response = self.client.client.get_option_greeks(osi_symbols)
                result = {}
                for i, greek_data in enumerate(greeks_response.greeks):
                    # Use symbol from response if present, else same order as osi_symbols
                    symbol = getattr(greek_data, "osi_symbol", None) or getattr(
                        greek_data, "symbol", None
                    )
                    if symbol is None and i < len(osi_symbols):
                        symbol = osi_symbols[i]
                    if symbol is None:
                        continue
                    result[symbol] = {
                        "delta": float(greek_data.greeks.delta),
                        "gamma": float(greek_data.greeks.gamma),
                        "theta": float(greek_data.greeks.theta),
                        "vega": float(greek_data.greeks.vega),
                    }
                return result
                
        except Exception as e:
            logger.error(f"Error retrieving Greeks: {e}")
            return {}
    
    def select_option_contract(
        self,
        underlying_symbol: str,
        underlying_price: float,
        underlying_type: InstrumentType = InstrumentType.EQUITY
    ) -> Optional[Dict]:
        """Select an option contract based on selection rules.
        
        Args:
            underlying_symbol: Underlying symbol
            underlying_price: Current underlying price
            underlying_type: Type of underlying instrument
            
        Returns:
            Dictionary with contract details including OSI symbol, or None if no valid contract
        """
        try:
            # Get expirations
            expirations = self.get_option_expirations(underlying_symbol, underlying_type)
            if not expirations:
                logger.warning(f"No expirations found for {underlying_symbol}")
                return None
            
            # Filter expirations by DTE
            today = date.today()
            target_expirations = [
                exp for exp in expirations
                if config.option_dte_min <= (exp - today).days <= config.option_dte_max
            ]
            
            # Fallback to wider range if needed
            if not target_expirations:
                target_expirations = [
                    exp for exp in expirations
                    if config.option_dte_fallback_min <= (exp - today).days <= config.option_dte_fallback_max
                ]
            
            if not target_expirations:
                logger.warning(f"No suitable expirations found for {underlying_symbol}")
                return None
            
            # Public does not allow opening same-day expiring option positions after 3:30 PM ET
            if is_after_same_day_option_cutoff_et():
                target_expirations = [e for e in target_expirations if e > today]
                if not target_expirations:
                    logger.warning(
                        "No expirations left after excluding same-day (Public cutoff 3:30 PM ET)."
                    )
                    return None
            
            # Try expirations in order
            for expiration in sorted(target_expirations):
                chain = self.get_option_chain(underlying_symbol, expiration, underlying_type)
                if not chain:
                    continue
                
                # Filter CALLs only
                calls = chain.calls if hasattr(chain, 'calls') else []
                
                # Find strike closest to target range (spot * 1.00 to 1.10)
                target_min = underlying_price * config.strike_range_min
                target_max = underlying_price * config.strike_range_max
                
                max_pain_strike = None
                if config.use_max_pain_for_selection:
                    max_pain_result = self.compute_max_pain(chain)
                    if max_pain_result is not None:
                        max_pain_strike, _ = max_pain_result
                
                best_contract = None
                best_strike_diff = float('inf')
                
                for call in calls:
                    if getattr(call, "strike", None) is None:
                        continue
                    strike = float(call.strike)
                    
                    # Check if strike is in range
                    if strike < target_min or strike > target_max:
                        continue
                    
                    # Liquidity filters
                    bid = float(call.bid) if call.bid else None
                    ask = float(call.ask) if call.ask else None
                    
                    if bid is None or ask is None:
                        continue
                    
                    mid = (bid + ask) / 2
                    spread_pct = (ask - bid) / mid if mid > 0 else float('inf')
                    
                    if spread_pct > config.max_bid_ask_spread_pct:
                        continue
                    
                    # Check OI and volume if available
                    oi = int(call.open_interest) if hasattr(call, 'open_interest') and call.open_interest else None
                    volume = int(call.volume) if hasattr(call, 'volume') and call.volume else None
                    
                    if oi is not None and oi < config.min_open_interest:
                        continue
                    if volume is not None and volume < config.min_volume:
                        continue
                    
                    # Strategic pick: prefer strike closest to max pain when enabled, else closest to ATM
                    if max_pain_strike is not None:
                        strike_diff = abs(strike - max_pain_strike)
                    else:
                        strike_diff = abs(strike - underlying_price)
                    if strike_diff < best_strike_diff:
                        best_strike_diff = strike_diff
                        best_contract = call
                
                if best_contract:
                    osi_symbol = best_contract.symbol if hasattr(best_contract, "symbol") else None
                    bid = getattr(best_contract, "bid", None)
                    ask = getattr(best_contract, "ask", None)
                    strike_val = getattr(best_contract, "strike", None)
                    if osi_symbol and bid is not None and ask is not None and strike_val is not None:
                        return {
                            "osi_symbol": osi_symbol,
                            "underlying": underlying_symbol,
                            "expiration": expiration.isoformat(),
                            "strike": float(strike_val),
                            "bid": float(bid),
                            "ask": float(ask),
                            "mid": (float(bid) + float(ask)) / 2,
                            "open_interest": int(best_contract.open_interest) if getattr(best_contract, "open_interest", None) else None,
                            "volume": int(best_contract.volume) if getattr(best_contract, "volume", None) else None,
                        }
            
            logger.warning(f"No suitable option contract found for {underlying_symbol}")
            return None
            
        except Exception as e:
            logger.error(f"Error selecting option contract for {underlying_symbol}: {e}")
            return None
    
    def clear_cache(self):
        """Clear the quote cache."""
        self._quote_cache.clear()
        logger.debug("Quote cache cleared")
