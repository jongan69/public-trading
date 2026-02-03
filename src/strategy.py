"""High-convexity portfolio strategy logic."""
from typing import Dict, List, Optional, Tuple
from datetime import date
from loguru import logger

from public_api_sdk import InstrumentType

from src.config import config
from src.portfolio import PortfolioManager, Position
from src.market_data import MarketDataManager
from src.execution import ExecutionManager


class HighConvexityStrategy:
    """High-convexity portfolio strategy implementation."""
    
    def __init__(
        self,
        portfolio_manager: PortfolioManager,
        data_manager: MarketDataManager,
        execution_manager: ExecutionManager
    ):
        """Initialize the strategy.
        
        Args:
            portfolio_manager: Portfolio manager instance
            data_manager: Market data manager instance
            execution_manager: Execution manager instance
        """
        self.portfolio = portfolio_manager
        self.data = data_manager
        self.execution = execution_manager
        self.trades_today = 0
        self.last_rebalance_date = None
        logger.info("High-convexity strategy initialized")
    
    def get_theme_for_underlying(self, underlying: str) -> Optional[str]:
        """Get theme name for an underlying symbol (REQ-011: for analytics).

        Args:
            underlying: Underlying symbol

        Returns:
            Theme name or None if not a theme position
        """
        if not underlying:
            return None

        underlying_upper = underlying.upper()

        # Check if it's the moonshot symbol
        if config.moonshot_symbol and underlying_upper == config.moonshot_symbol.upper():
            return "moonshot"

        # Check theme underlyings
        if len(config.theme_underlyings) > 0 and config.theme_underlyings[0].upper() == underlying_upper:
            return "theme_a"
        if len(config.theme_underlyings) > 1 and config.theme_underlyings[1].upper() == underlying_upper:
            return "theme_b"
        if len(config.theme_underlyings) > 2 and config.theme_underlyings[2].upper() == underlying_upper:
            return "theme_c"

        return None

    def check_entry_signal(self, underlying_symbol: str, underlying_price: float) -> bool:
        """Check if entry signal is valid.

        Args:
            underlying_symbol: Underlying symbol
            underlying_price: Current underlying price

        Returns:
            True if entry is allowed
        """
        if config.manual_mode_only:
            return True
        
        if config.use_sma_filter:
            # Try to get SMA data
            # Note: This requires historical data which may not be available
            # For now, use simplified rule
            try:
                # Placeholder: would need historical data API
                # For now, allow entry
                return True
            except:
                # Fallback to simplified rule
                pass
        
        # Simplified rule: allow on up-day if previous close exists
        # For now, allow entry (can be enhanced with historical data)
        return True
    
    def should_take_profit(self, position: Position, current_price: float) -> Tuple[bool, Optional[int]]:
        """Check if position should take profit.
        
        Args:
            position: Position to check
            current_price: Current price
            
        Returns:
            Tuple of (should_take_profit, quantity_to_close)
        """
        pnl_pct = position.get_pnl_pct(current_price)
        
        if pnl_pct >= config.take_profit_200_pct * 100:
            # Close all at +200%
            return (True, position.quantity)
        elif pnl_pct >= config.take_profit_100_pct * 100:
            # Close 50% at +100%
            close_qty = max(1, int(position.quantity * config.take_profit_100_close_pct))
            return (True, close_qty)
        
        return (False, None)
    
    def should_stop_loss(self, position: Position, current_price: float) -> bool:
        """Check if position should be stopped out.
        
        Args:
            position: Position to check
            current_price: Current price
            
        Returns:
            True if should stop loss
        """
        pnl_pct = position.get_pnl_pct(current_price)
        
        # Check drawdown
        if pnl_pct <= config.stop_loss_drawdown_pct * 100:
            # For options, also check if underlying is below strike
            if position.instrument_type == InstrumentType.OPTION and position.strike:
                underlying_price = self.data.get_quote(position.underlying or "")
                if underlying_price:
                    underlying_below_strike_pct = (underlying_price - position.strike) / position.strike
                    if underlying_below_strike_pct < config.stop_loss_underlying_pct:
                        return True
        
        # Check DTE for options
        if position.instrument_type == InstrumentType.OPTION:
            dte = position.get_dte()
            if dte is not None:
                if dte < config.close_if_dte_lt:
                    # Close if OTM and DTE < 30
                    if not position.is_itm(self.data.get_quote(position.underlying or "") or 0):
                        return True
        
        return False
    
    def should_roll(self, position: Position, current_price: float) -> Tuple[bool, Optional[Dict]]:
        """Check if position should be rolled.
        
        Args:
            position: Position to check
            current_price: Current price
            
        Returns:
            Tuple of (should_roll, new_contract_info)
        """
        if position.instrument_type != InstrumentType.OPTION:
            return (False, None)
        
        dte = position.get_dte()
        if dte is None or dte >= config.roll_trigger_dte:
            return (False, None)
        
        # Check if position is part of theme allocation
        themes = self.portfolio.get_positions_by_theme()
        is_theme_position = any(
            pos.symbol == position.symbol
            for theme_positions in themes.values()
            for pos in theme_positions
        )
        
        if not is_theme_position:
            return (False, None)
        
        # Calculate roll cost
        current_value = position.get_market_value(current_price)
        
        # Select new contract
        underlying = position.underlying or ""
        underlying_price = self.data.get_quote(underlying) or 0
        
        if underlying_price == 0:
            return (False, None)
        
        new_contract = self.data.select_option_contract(
            underlying,
            underlying_price,
            InstrumentType.EQUITY
        )
        
        if not new_contract:
            return (False, None)
        
        # Estimate roll cost (close current + open new)
        # This is simplified - actual cost depends on fills
        new_contract_price = new_contract["mid"]
        roll_debit = new_contract_price - current_price
        
        # Check roll cost limits: reject if EITHER limit is exceeded
        max_roll_debit_pct = current_value * config.max_roll_debit_pct
        max_roll_debit_absolute = config.max_roll_debit_absolute
        
        if roll_debit > max_roll_debit_pct or roll_debit > max_roll_debit_absolute:
            logger.info(f"Roll cost too high for {position.symbol}: ${roll_debit:.2f}")
            return (False, None)
        
        return (True, new_contract)
    
    def check_moonshot_trim(self) -> Optional[Dict]:
        """Check if moonshot position should be trimmed.
        
        Returns:
            Trim order details or None
        """
        equity = self.portfolio.get_equity()
        allocations = self.portfolio.get_current_allocations()
        moonshot_pct = allocations["moonshot"]
        
        # Trim if moonshot exceeds configured hard cap (moonshot_max)
        if moonshot_pct > config.moonshot_max:
            themes = self.portfolio.get_positions_by_theme()
            moonshot_positions = themes["moonshot"]
            
            if moonshot_positions:
                # Calculate trim quantity to bring moonshot to configured cap
                total_value = sum(
                    pos.get_market_value(self.portfolio.get_position_price(pos))
                    for pos in moonshot_positions
                )
                
                max_value = equity * config.moonshot_max
                trim_value = total_value - max_value
                
                # Trim proportionally across positions
                for position in moonshot_positions:
                    # Use bid for options, last/mid for equity
                    sell_price = self.portfolio.get_position_sell_price(position)
                    if sell_price is None or sell_price <= 0:
                        logger.warning(f"No price for moonshot trim {position.symbol}, skipping")
                        continue
                    trim_pct = trim_value / total_value if total_value > 0 else 0
                    # Shares to sell to bring moonshot to moonshot_max
                    trim_qty = min(int(position.quantity * trim_pct), position.quantity)
                    if trim_qty <= 0:
                        continue
                    rationale = f"Trim moonshot: current {moonshot_pct*100:.1f}%, cap {config.moonshot_max*100:.0f}%"
                    return {
                        "symbol": position.symbol,
                        "quantity": trim_qty,
                        "action": "SELL",
                        "price": float(sell_price),
                        "rationale": rationale,
                        "theme": "moonshot",  # REQ-011: tag with theme for analytics
                        "entry_price": position.entry_price,  # REQ-011: for realized P&L
                    }
        
        return None
    
    def rebalance(self) -> List[Dict]:
        """Execute rebalancing logic.
        
        Returns:
            List of orders to place
        """
        if self.trades_today >= config.max_trades_per_day:
            logger.warning(f"Max trades per day reached: {config.max_trades_per_day}")
            return []
        
        orders = []
        equity = self.portfolio.get_equity()
        current_allocations = self.portfolio.get_current_allocations()
        target_allocations = self.portfolio.get_target_allocations()
        rebalance_needs = self.portfolio.calculate_rebalance_needs()
        
        # Process each theme
        theme_map = {
            "theme_a": config.theme_underlyings[0],
            "theme_b": config.theme_underlyings[1],
            "theme_c": config.theme_underlyings[2] if len(config.theme_underlyings) > 2 else None,
        }
        
        for theme_name, underlying in theme_map.items():
            if underlying is None:
                continue
            
            need = rebalance_needs[theme_name]
            
            if need > 100:  # Need to add position
                # Check entry signal
                underlying_price = self.data.get_quote(underlying)
                if not underlying_price:
                    continue
                
                if not self.check_entry_signal(underlying, underlying_price):
                    logger.info(f"Entry signal not valid for {underlying}")
                    continue
                
                # Select option contract
                contract = self.data.select_option_contract(
                    underlying,
                    underlying_price,
                    InstrumentType.EQUITY
                )
                
                if not contract:
                    logger.warning(f"No suitable contract found for {underlying}")
                    continue
                
                # Calculate quantity
                contract_price = contract["mid"]
                quantity = int(need / contract_price)
                
                if quantity > 0:
                    rationale = f"Rebalance: {theme_name} below target (add {underlying})"
                    orders.append({
                        "action": "BUY",
                        "symbol": contract["osi_symbol"],
                        "quantity": quantity,
                        "price": contract_price,
                        "underlying": underlying,
                        "contract_info": contract,
                        "rationale": rationale,
                        "theme": theme_name,  # REQ-011: tag with theme for analytics
                    })
            
            elif need < -100:  # Need to reduce position
                themes = self.portfolio.get_positions_by_theme()
                theme_positions = themes[theme_name]
                
                for position in theme_positions:
                    current_price = self.portfolio.get_position_price(position)
                    position_value = position.get_market_value(current_price)
                    
                    if position_value > abs(need):
                        close_qty = int(abs(need) / current_price)
                        rationale = f"Rebalance: {theme_name} above target (reduce)"
                        orders.append({
                            "action": "SELL",
                            "symbol": position.symbol,
                            "quantity": close_qty,
                            "price": current_price,
                            "rationale": rationale,
                            "theme": theme_name,  # REQ-011: tag with theme for analytics
                            "entry_price": position.entry_price,  # REQ-011: for realized P&L
                        })
                        break
        
        # Moonshot trim is added in run_daily_logic at the start so it executes before any BUY (governance).
        
        return orders
    
    def process_positions(self) -> List[Dict]:
        """Process all positions for exits, rolls, etc.
        
        Returns:
            List of orders to place
        """
        orders = []
        
        for position in list(self.portfolio.positions.values()):
            current_price = self.portfolio.get_position_price(position)
            # For option SELL orders use bid (what buyers offer); for equity use last/mid
            sell_price = self.portfolio.get_position_sell_price(position)
            
            # Check take profit
            should_tp, tp_qty = self.should_take_profit(position, current_price)
            if should_tp and tp_qty and sell_price and sell_price > 0:
                pnl_pct = position.get_pnl_pct(current_price)
                if tp_qty >= position.quantity:
                    rationale = f"Take profit: +{pnl_pct:.0f}% (close all)"
                else:
                    rationale = f"Take profit: +{pnl_pct:.0f}% (close {tp_qty})"
                # REQ-011: derive theme for analytics
                theme = self.get_theme_for_underlying(position.underlying or position.symbol)
                orders.append({
                    "action": "SELL",
                    "symbol": position.symbol,
                    "quantity": tp_qty,
                    "price": sell_price,
                    "reason": "TAKE_PROFIT",
                    "rationale": rationale,
                    "theme": theme,  # REQ-011: tag with theme for analytics
                    "entry_price": position.entry_price,  # REQ-011: for realized P&L
                })
                continue
            elif should_tp and tp_qty:
                logger.warning(f"Skipping take profit for {position.symbol}: no valid sell price (bid/last)")
            
            # Check stop loss
            if self.should_stop_loss(position, current_price):
                if sell_price and sell_price > 0:
                    pnl_pct = position.get_pnl_pct(current_price)
                    dte = position.get_dte() if position.instrument_type == InstrumentType.OPTION else None
                    rationale = f"Stop loss: pnl {pnl_pct:.0f}%"
                    if dte is not None:
                        rationale += f", DTE={dte}"
                    # REQ-011: derive theme for analytics
                    theme = self.get_theme_for_underlying(position.underlying or position.symbol)
                    orders.append({
                        "action": "SELL",
                        "symbol": position.symbol,
                        "quantity": position.quantity,
                        "price": sell_price,
                        "reason": "STOP_LOSS",
                        "rationale": rationale,
                        "theme": theme,  # REQ-011: tag with theme for analytics
                        "entry_price": position.entry_price,  # REQ-011: for realized P&L
                    })
                    continue
                logger.warning(f"Skipping stop loss for {position.symbol}: no valid sell price (bid/last)")
            
            # Check roll
            should_roll, new_contract = self.should_roll(position, current_price)
            if should_roll and new_contract and sell_price and sell_price > 0:
                dte = position.get_dte() or 0
                underlying = position.underlying or "option"
                rationale_close = f"Roll: {underlying} DTE={dte} < {config.roll_trigger_dte} (close)"
                rationale_open = f"Roll: {underlying} (open new)"
                # REQ-011: derive theme for analytics
                theme = self.get_theme_for_underlying(position.underlying or position.symbol)
                # Close current (use bid for options)
                orders.append({
                    "action": "SELL",
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "price": sell_price,
                    "reason": "ROLL_CLOSE",
                    "rationale": rationale_close,
                    "theme": theme,  # REQ-011: tag with theme for analytics
                    "entry_price": position.entry_price,  # REQ-011: for realized P&L
                })
                # Open new
                orders.append({
                    "action": "BUY",
                    "symbol": new_contract["osi_symbol"],
                    "quantity": position.quantity,
                    "price": new_contract["mid"],
                    "underlying": position.underlying,
                    "contract_info": new_contract,
                    "reason": "ROLL_OPEN",
                    "rationale": rationale_open,
                    "theme": theme,  # REQ-011: tag with theme for analytics
                })
            elif should_roll and new_contract:
                logger.warning(f"Skipping roll for {position.symbol}: no valid sell price (bid/last)")
        
        return orders
    
    def run_daily_logic(self) -> List[Dict]:
        """Run daily strategy logic.
        
        Returns:
            List of orders to place
        """
        today = date.today()
        
        # Reset trades counter if new day
        if self.last_rebalance_date != today:
            self.trades_today = 0
            self.last_rebalance_date = today
        
        all_orders = []
        
        # Moonshot trim first so it executes before any BUY (avoids governance block: "Trim before adding")
        trim_order = self.check_moonshot_trim()
        if trim_order:
            all_orders.append(trim_order)
        
        # Process existing positions (exits, rolls)
        position_orders = self.process_positions()
        all_orders.extend(position_orders)
        
        # Rebalance if needed (theme BUYs/SELLs)
        rebalance_orders = self.rebalance()
        all_orders.extend(rebalance_orders)
        
        return all_orders
