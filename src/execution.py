"""Order execution and management."""
import re
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime, timezone, date
import uuid
import time
from loguru import logger

from src.utils.trading_hours import is_after_same_day_option_cutoff_et

from public_api_sdk import (
    OrderRequest,
    OrderInstrument,
    InstrumentType,
    OrderSide,
    OrderType,
    TimeInForce,
    OrderExpirationRequest,
    EquityMarketSession,
    OpenCloseIndicator,
    PreflightRequest,
)

from src.config import config
from src.client import TradingClient
from src.portfolio import PortfolioManager
from src.utils.governance import check_governance


def _parse_expiration_date_from_osi(symbol: str) -> Optional[date]:
    """Parse expiration date from OSI option symbol (e.g. AAPL260130C00200000 -> 2026-01-30)."""
    clean = re.sub(r"-OPTION$", "", str(symbol).strip()).upper()
    match = re.match(r"^[A-Z]+(\d{6})(?:[CP])\d{8}$", clean)
    if not match:
        return None
    try:
        yymmdd = match.group(1)
        yy = int(yymmdd[:2])
        mm = int(yymmdd[2:4])
        dd = int(yymmdd[4:6])
        # For OSI format, YY is always in current century (2000-2099)
        year = 2000 + yy
        return date(year, mm, dd)
    except (ValueError, TypeError):
        return None


def _normalize_option_symbol(symbol: str) -> str:
    """Strip -OPTION suffix from option symbols for API calls.
    
    Args:
        symbol: Option symbol (may include -OPTION suffix)
        
    Returns:
        Clean OSI symbol without suffix
    """
    return re.sub(r"-OPTION$", "", str(symbol)).strip()


def _normalize_order_status(status) -> str:
    """Normalize order status to string (API may return enum).
    
    Args:
        status: Order status from API (enum or str)
        
    Returns:
        Uppercase string, e.g. 'FILLED', 'NEW', 'OPEN'
    """
    if status is None:
        return "UNKNOWN"
    if hasattr(status, "value"):
        return str(status.value).upper()
    return str(status).upper()


class ExecutionManager:
    """Manages order execution with preflight checks and polling."""

    def __init__(
        self,
        client: TradingClient,
        portfolio_manager: PortfolioManager,
        storage: Optional[object] = None,
    ):
        """Initialize the execution manager.

        Args:
            client: Trading client instance
            portfolio_manager: Portfolio manager instance
            storage: Optional StorageManager for governance (kill switch). If None, kill switch is skipped in governance.
        """
        self.client = client
        self.portfolio = portfolio_manager
        self.storage = storage
        self.order_history: List[Dict] = []
        logger.info("Execution manager initialized")
    
    def calculate_preflight(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        limit_price: Decimal,
        instrument_type: InstrumentType = InstrumentType.EQUITY
    ) -> Optional[Dict]:
        """Calculate preflight for an order.
        
        Args:
            symbol: Symbol to trade
            side: Buy or sell
            quantity: Number of shares/contracts
            limit_price: Limit price
            instrument_type: Type of instrument
            
        Returns:
            Preflight response dictionary or None if error
        """
        try:
            # Strip -OPTION suffix for API calls
            api_symbol = _normalize_option_symbol(symbol) if instrument_type == InstrumentType.OPTION else symbol
            if instrument_type == InstrumentType.OPTION:
                if symbol != api_symbol:
                    logger.info(f"Normalizing option symbol: {symbol} -> {api_symbol}")
                else:
                    logger.debug(f"Option symbol already normalized: {symbol}")
            
            # Build preflight request - options and equity have different fields
            if instrument_type == InstrumentType.OPTION:
                # Options: use open_close_indicator, no equity_market_session
                open_close = OpenCloseIndicator.CLOSE if side == OrderSide.SELL else OpenCloseIndicator.OPEN
                preflight_request = PreflightRequest(
                    instrument=OrderInstrument(symbol=api_symbol, type=instrument_type),
                    order_side=side,
                    order_type=OrderType.LIMIT,
                    expiration=OrderExpirationRequest(time_in_force=TimeInForce.DAY),
                    quantity=quantity,
                    limit_price=limit_price,
                    open_close_indicator=open_close
                )
            else:
                # Equity: use equity_market_session, no open_close_indicator
                equity_session = (
                    EquityMarketSession.EXTENDED 
                    if config.trade_during_extended_hours 
                    else EquityMarketSession.CORE
                )
                preflight_request = PreflightRequest(
                    instrument=OrderInstrument(symbol=api_symbol, type=instrument_type),
                    order_side=side,
                    order_type=OrderType.LIMIT,
                    expiration=OrderExpirationRequest(time_in_force=TimeInForce.DAY),
                    quantity=quantity,
                    limit_price=limit_price,
                    equity_market_session=equity_session
                )
            
            preflight_response = self.client.client.perform_preflight_calculation(preflight_request)
            
            def _to_float(v):
                if v is None:
                    return 0.0
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return 0.0
            
            result = {
                "estimated_commission": _to_float(preflight_response.estimated_commission),
                "order_value": _to_float(preflight_response.order_value),
                "estimated_cost": _to_float(preflight_response.estimated_cost),
                "buying_power_requirement": _to_float(preflight_response.buying_power_requirement),
            }
            
            logger.info(f"Preflight for {symbol}: {result}")
            return result
            
        except Exception as e:
            err_msg = str(e).lower()
            if "same-day" in err_msg and "3:30" in err_msg:
                logger.error(
                    "Preflight failed: Public does not allow opening same-day expiring option positions after 3:30 PM ET."
                )
            else:
                logger.error(f"Error calculating preflight: {e}")
            return None
    
    def check_cash_buffer(self, order_value: float) -> bool:
        """Check if order would violate cash buffer requirement.
        
        Args:
            order_value: Value of the order
            
        Returns:
            True if cash buffer would be maintained, False otherwise
        """
        equity = self.portfolio.get_equity()
        cash = self.portfolio.get_cash()
        target_cash = equity * config.cash_minimum
        
        remaining_cash = cash - order_value
        
        if remaining_cash < target_cash:
            logger.warning(
                f"Order would violate cash buffer: "
                f"remaining=${remaining_cash:.2f}, target=${target_cash:.2f}"
            )
            return False
        
        return True
    
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        limit_price: Decimal,
        instrument_type: InstrumentType = InstrumentType.EQUITY,
        order_id: Optional[str] = None
    ) -> Optional[str]:
        """Place an order.
        
        Args:
            symbol: Symbol to trade
            side: Buy or sell
            quantity: Number of shares/contracts
            limit_price: Limit price
            instrument_type: Type of instrument
            order_id: Optional order ID (generated if not provided)
            
        Returns:
            Order ID if successful, None otherwise
        """
        if config.dry_run:
            order_id = f"DRY_RUN_{uuid.uuid4()}"
            logger.info(f"[DRY RUN] Would place order: {side.value} {quantity} {symbol} @ ${limit_price}")
            # Still record in history for dry run
            order_record = {
                "order_id": order_id,
                "symbol": symbol,
                "side": side.value,
                "quantity": quantity,
                "limit_price": float(limit_price),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "PENDING",
            }
            self.order_history.append(order_record)
            return order_id
        
        try:
            order_id = order_id or str(uuid.uuid4())
            
            # Strip -OPTION suffix for API calls
            api_symbol = _normalize_option_symbol(symbol) if instrument_type == InstrumentType.OPTION else symbol
            
            # Build order request - options and equity have different fields
            if instrument_type == InstrumentType.OPTION:
                # Options: use open_close_indicator, no equity_market_session
                open_close = OpenCloseIndicator.CLOSE if side == OrderSide.SELL else OpenCloseIndicator.OPEN
                order_request = OrderRequest(
                    order_id=order_id,
                    instrument=OrderInstrument(symbol=api_symbol, type=instrument_type),
                    order_side=side,
                    order_type=OrderType.LIMIT,
                    expiration=OrderExpirationRequest(time_in_force=TimeInForce.DAY),
                    quantity=quantity,
                    limit_price=limit_price,
                    open_close_indicator=open_close
                )
            else:
                # Equity: use equity_market_session, no open_close_indicator
                equity_session = (
                    EquityMarketSession.EXTENDED 
                    if config.trade_during_extended_hours 
                    else EquityMarketSession.CORE
                )
                order_request = OrderRequest(
                    order_id=order_id,
                    instrument=OrderInstrument(symbol=api_symbol, type=instrument_type),
                    order_side=side,
                    order_type=OrderType.LIMIT,
                    expiration=OrderExpirationRequest(time_in_force=TimeInForce.DAY),
                    quantity=quantity,
                    limit_price=limit_price,
                    equity_market_session=equity_session
                )
            
            order_response = self.client.client.place_order(order_request)
            
            order_record = {
                "order_id": order_response.order_id,
                "symbol": symbol,
                "side": side.value,
                "quantity": quantity,
                "limit_price": float(limit_price),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "PENDING",
            }
            self.order_history.append(order_record)
            
            logger.info(f"Order placed: {order_response.order_id} for {symbol}")
            return order_response.order_id
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    def poll_order_status(
        self,
        order_id: str,
        timeout_seconds: Optional[int] = None,
        poll_interval_seconds: Optional[int] = None
    ) -> Optional[Dict]:
        """Poll order status until filled, canceled, or timeout.
        
        Args:
            order_id: Order ID to poll
            timeout_seconds: Timeout in seconds (defaults to config)
            poll_interval_seconds: Poll interval in seconds (defaults to config)
            
        Returns:
            Final order status dictionary or None if timeout/error
        """
        if config.dry_run and order_id.startswith("DRY_RUN_"):
            return {
                "order_id": order_id,
                "status": "FILLED",
                "dry_run": True,
            }
        
        timeout = timeout_seconds or config.order_poll_timeout_seconds
        interval = poll_interval_seconds or config.order_poll_interval_seconds
        
        start_time = time.time()
        
        # Terminal states (SDK uses CANCELLED with two L's)
        terminal_statuses = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}

        while time.time() - start_time < timeout:
            try:
                order_details = self.client.client.get_order(
                    order_id=order_id,
                    account_id=self.client.account_number,
                )
                raw_status = order_details.status
                status_str = _normalize_order_status(raw_status)
                
                # Update order history with normalized string
                for order in self.order_history:
                    if order["order_id"] == order_id:
                        order["status"] = status_str
                        break
                
                # Only treat as done when status is actually terminal
                if status_str in terminal_statuses:
                    logger.info(f"Order {order_id} reached terminal state: {status_str}")
                    return {
                        "order_id": order_id,
                        "status": status_str,
                    }
                
                time.sleep(interval)
                
            except Exception as e:
                err_str = str(e).lower()
                # 404 is expected right after placement (order not yet indexed)
                if "404" in err_str or "not found" in err_str:
                    logger.debug(f"Order {order_id} not yet visible, retrying: {e}")
                else:
                    logger.error(f"Error polling order {order_id}: {e}")
                time.sleep(interval)
        
        logger.warning(f"Order {order_id} polling timeout")
        return None
    
    def _has_pending_order_for_symbol(self, symbol: str, instrument_type: InstrumentType) -> bool:
        """Return True if there is already a pending (open) order for this symbol."""
        try:
            portfolio = self.client.client.get_portfolio(self.client.account_number)
            orders = getattr(portfolio, "orders", None)
            if orders is None:
                logger.warning("Portfolio has no 'orders' attribute; cannot check pending orders")
                return False
            if not orders:
                return False
            pending_statuses = {"NEW", "PARTIALLY_FILLED", "PENDING_REPLACE", "PENDING_CANCEL"}
            our_symbol = _normalize_option_symbol(symbol) if instrument_type == InstrumentType.OPTION else symbol
            for order in orders:
                if not hasattr(order, "instrument"):
                    continue
                order_symbol = getattr(order.instrument, "symbol", None)
                if not order_symbol:
                    continue
                # Normalize using this order's instrument type (API may return option with/without -OPTION)
                order_instrument_type = getattr(order.instrument, "type", None)
                is_option = order_instrument_type == InstrumentType.OPTION
                order_symbol_norm = _normalize_option_symbol(order_symbol) if is_option else order_symbol
                status = getattr(order, "status", None)
                status_str = status.value if hasattr(status, "value") else str(status)
                if order_symbol_norm == our_symbol and status_str in pending_statuses:
                    logger.debug(
                        f"Found pending order for {symbol} (status={status_str}); skipping duplicate"
                    )
                    return True
            return False
        except Exception as e:
            logger.warning(f"Could not check pending orders for {symbol}: {e}")
            return False

    def has_pending_order_for_order(self, order_details: Dict) -> bool:
        """Return True if there is already a pending order for this order's symbol (skip proposing for this cycle)."""
        symbol = (order_details or {}).get("symbol")
        if not symbol:
            return False
        is_option = (
            symbol.endswith("-OPTION") or
            (len(symbol) > 10 and re.match(r"^[A-Z]+\d{6}[CP]\d{8}", symbol.replace("-OPTION", "")))
        )
        instrument_type = InstrumentType.OPTION if is_option else InstrumentType.EQUITY
        return self._has_pending_order_for_symbol(symbol, instrument_type)
    
    def execute_order(
        self,
        order_details: Dict,
        poll_timeout_seconds: Optional[int] = None,
    ) -> Optional[Dict]:
        """Execute an order with preflight check and polling.

        Args:
            order_details: Dictionary with order details (action, symbol, quantity, price, etc.)
            poll_timeout_seconds: Max seconds to wait for fill. None = use config (e.g. 300).
                0 = do not poll (return immediately after place with one status check).
                Use a short value (e.g. 30) when called from the trading loop to avoid blocking.

        Returns:
            Success: dict with order_id, symbol, action, quantity, price, status, etc.
            Failure: dict with ok=False and error=<reason> so caller can surface to user/AI.
        """
        action = order_details.get("action")
        symbol = order_details.get("symbol")
        quantity = order_details.get("quantity")
        price = order_details.get("price")

        if not all([action, symbol, quantity, price]):
            err = "Invalid order details: missing action, symbol, quantity, or price"
            logger.error(f"{err}: {order_details}")
            return {"ok": False, "error": err}

        logger.info(
            f"Executing order: {action} {quantity} {symbol} @ {price}"
        )
        side = OrderSide.BUY if action == "BUY" else OrderSide.SELL
        limit_price = Decimal(str(price))

        # Determine instrument type: check for -OPTION suffix or OSI format (long alphanumeric)
        is_option = (
            symbol.endswith("-OPTION") or
            (len(symbol) > 10 and re.match(r"^[A-Z]+\d{6}[CP]\d{8}", symbol.replace("-OPTION", "")))
        )
        instrument_type = InstrumentType.OPTION if is_option else InstrumentType.EQUITY
        if is_option:
            logger.debug(f"Detected option symbol: {symbol} (type: {instrument_type})")
            # Public does not allow opening same-day expiring option positions after 3:30 PM ET
            exp_date = _parse_expiration_date_from_osi(symbol)
            if exp_date is not None and exp_date == date.today() and is_after_same_day_option_cutoff_et():
                err = "Public does not allow opening same-day expiring option positions after 3:30 PM ET."
                logger.warning(f"Order blocked: {err}")
                return {"ok": False, "error": err}

        # Governance: hard rules (kill switch, min cash, max position, max correlated)
        allowed, reason = check_governance(self.portfolio, self.storage, order_details)
        if not allowed:
            logger.warning(f"Governance block: {reason}")
            return {"ok": False, "error": reason}

        # Preflight check
        preflight = self.calculate_preflight(
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            instrument_type=instrument_type
        )

        if not preflight:
            err = f"Preflight check failed for {symbol} (symbol or quote may be invalid)."
            logger.error(f"Order blocked: {err}")
            return {"ok": False, "error": err}

        # Check cash buffer for buy orders
        if side == OrderSide.BUY:
            if not self.check_cash_buffer(preflight["order_value"]):
                err = f"Order would violate cash buffer: need ${preflight.get('order_value', 0):,.2f}; trim or add cash first."
                logger.warning(f"Order blocked: {err}")
                return {"ok": False, "error": err}

        # Skip if there's already a pending order for this symbol (avoids "quantity exceeds remaining" error)
        if self._has_pending_order_for_symbol(symbol, instrument_type):
            err = (
                f"Already have a pending order for {symbol}. "
                "Wait for it to fill or cancel before placing another."
            )
            logger.warning(f"Order blocked: {err}")
            return {"ok": False, "error": err}

        # Place order
        order_id = self.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            instrument_type=instrument_type
        )

        if not order_id:
            err = "Order placement failed (no order ID returned); check symbol and liquidity."
            logger.error(f"Order failed: {err}")
            return {"ok": False, "error": err}
        
        # Poll for fill; use provided timeout or config (order remains open in market if not filled)
        poll_timeout = (
            config.order_poll_timeout_seconds
            if poll_timeout_seconds is None
            else poll_timeout_seconds
        )
        if poll_timeout == 0:
            # No wait: one quick status check then return (avoids blocking loop)
            result = self.poll_order_status(order_id, timeout_seconds=3)
            if not result:
                result = {"order_id": order_id, "status": "OPEN"}
        else:
            result = self.poll_order_status(order_id, timeout_seconds=poll_timeout)
        
        if result:
            status = result["status"]  # already normalized string
        else:
            status = "OPEN"
            logger.info(
                f"Order {order_id} still open after {poll_timeout}s - continuing. "
                "Order remains in market and may fill later."
            )

        logger.info(f"Order placed: {order_id} {action} {quantity} {symbol} @ {price} -> {status}")
        return {
            "order_id": order_id,
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": price,
            "preflight": preflight,
            "status": status,
        }
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancellation request submitted, False otherwise
        """
        if config.dry_run:
            logger.info(f"[DRY RUN] Would cancel order: {order_id}")
            return True
        
        try:
            self.client.client.cancel_order(order_id=order_id)
            logger.info(f"Cancel request submitted for order: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Error canceling order {order_id}: {e}")
            return False
