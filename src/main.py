"""Main entry point for high-convexity portfolio trading bot."""
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from loguru import logger

from src.config import config
from src.client import TradingClient
from src.market_data import MarketDataManager
from src.portfolio import PortfolioManager
from src.execution import ExecutionManager
from src.strategy import HighConvexityStrategy
from src.storage import StorageManager
from src.utils.logger import setup_logging
from src.utils.account_manager import AccountManager


class TradingBot:
    """Main trading bot orchestrator."""
    
    def __init__(self, account_number: Optional[str] = None):
        """Initialize the trading bot.
        
        Args:
            account_number: Account number to use (will prompt if not provided)
        """
        setup_logging()
        
        logger.info("=" * 70)
        logger.info("High-Convexity Portfolio Trading Bot")
        logger.info("=" * 70)
        
        # Get or select account number (env > config > saved file > interactive only if TTY)
        if account_number is None:
            account_number = (
                (config.account_number and config.account_number.strip())
                or os.environ.get("PUBLIC_ACCOUNT_NUMBER", "").strip()
                or os.environ.get("ACCOUNT_NUMBER", "").strip()
                or AccountManager.get_saved_account()
            )
            if account_number == "":
                account_number = None
        
        if account_number is None:
            if not sys.stdin.isatty():
                raise ValueError(
                    "No account number available in headless environment. "
                    "Set PUBLIC_ACCOUNT_NUMBER in your environment (e.g. Render Secret) or run once interactively to save to data/bot_config.json."
                )
            logger.info("No saved account found. Please select an account.")
            account_number = AccountManager.select_account_interactive(config.api_secret_key)
            if account_number is None:
                raise ValueError("Account selection cancelled or failed")
        
        # Initialize components
        self.client = TradingClient(account_number=account_number)
        self.data_manager = MarketDataManager(self.client)
        self.portfolio_manager = PortfolioManager(self.client, self.data_manager)
        self.storage = StorageManager()
        self.execution_manager = ExecutionManager(
            self.client, self.portfolio_manager, storage=self.storage
        )
        self.strategy = HighConvexityStrategy(
            self.portfolio_manager,
            self.data_manager,
            self.execution_manager
        )
        
        self.running = False
        self._last_rebalance_date: Optional[datetime] = None  # date (in config TZ) we last ran
        logger.info("Trading bot initialized")
    
    def check_kill_switch(self) -> bool:
        """Check if kill switch should be activated.

        Returns:
            True if kill switch is active, False otherwise
        """
        equity = self.portfolio_manager.get_equity()

        # Save equity history
        self.storage.save_equity_history(equity)

        # Get high from last N days
        high_equity = self.storage.get_equity_high_last_n_days(config.kill_switch_lookback_days)

        # If no history yet (first month), use current equity as baseline
        if high_equity is None or high_equity <= 0:
            logger.debug(f"No equity history yet, using current equity ${equity:.2f} as baseline")
            return False

        drawdown_pct = (equity - high_equity) / high_equity

        if drawdown_pct <= -config.kill_switch_drawdown_pct:
            logger.warning(
                f"Kill switch activated: drawdown={drawdown_pct*100:.2f}% "
                f"(equity=${equity:.2f}, high=${high_equity:.2f})"
            )
            return True

        return False

    def check_and_trigger_cooldown(self, order_details: dict, result: dict) -> bool:
        """REQ-012: Check if a fill triggers cool-down due to large loss.

        Args:
            order_details: Original order details with entry_price
            result: Execution result with fill_price, quantity, symbol

        Returns:
            True if cool-down was triggered, False otherwise
        """
        if not config.cooldown_enabled:
            return False

        try:
            action = order_details.get("action", "").upper()
            # Only check on SELL/exit orders (realized loss)
            if action != "SELL":
                return False

            entry_price = order_details.get("entry_price")
            if not entry_price:
                return False

            fill_price = result.get("price", 0)
            quantity = result.get("quantity", 0)
            symbol = result.get("symbol", "")

            # Calculate P&L
            pnl_per_share = fill_price - entry_price
            pnl_total = pnl_per_share * quantity
            pnl_pct = (pnl_per_share / entry_price) if entry_price > 0 else 0

            # Check thresholds
            loss_pct_threshold = -abs(config.cooldown_loss_threshold_pct)
            loss_usd_threshold = -abs(config.cooldown_loss_threshold_usd)

            if pnl_pct <= loss_pct_threshold or pnl_total <= loss_usd_threshold:
                # Trigger cool-down
                from datetime import timedelta
                cooldown_until = datetime.now() + timedelta(minutes=config.cooldown_duration_minutes)
                self.storage.set_cooldown_until(cooldown_until)
                logger.warning(
                    f"Cool-down triggered: {symbol} loss {pnl_pct*100:.1f}% (${pnl_total:.2f}). "
                    f"Blocking trades until {cooldown_until.isoformat()}"
                )
                return True

        except Exception as e:
            logger.exception("Cool-down check failed")

        return False
    
    def run_daily_logic(
        self,
        poll_timeout_seconds: Optional[float] = None,
        quiet: bool = False,
    ) -> Dict[str, Any]:
        """Run daily trading logic.

        Args:
            poll_timeout_seconds: Timeout when waiting for order fill (None = config default).
            quiet: If True, skip banner and portfolio breakdown (e.g. when called from trading loop).

        Returns:
            Dict with orders_planned, orders_skipped, orders_sent (for loop summary).
        """
        run_result: Dict[str, Any] = {"orders_planned": 0, "orders_skipped": 0, "orders_sent": 0}
        try:
            if not quiet:
                logger.info("=" * 70)
                logger.info("Running daily trading logic")
                logger.info("=" * 70)

            # Check kill switch
            if self.check_kill_switch():
                logger.warning("Kill switch active - skipping new positions")
                return run_result
            
            # Refresh portfolio
            self.portfolio_manager.refresh_portfolio()

            if not quiet:
                self.portfolio_manager.display_portfolio_breakdown()

            # Save snapshots
            equity = self.portfolio_manager.get_equity()
            self.storage.save_config_snapshot(equity)

            allocations = self.portfolio_manager.get_current_allocations()
            self.storage.save_portfolio_snapshot({
                "equity": equity,
                "buying_power": self.portfolio_manager.get_buying_power(),
                "cash": self.portfolio_manager.get_cash(),
                "allocations": allocations,
            })

            # Check proactive alerts (REQ-014)
            if config.proactive_alerts_enabled:
                from src.alerts import AlertManager
                alert_manager = AlertManager(self.storage, self.portfolio_manager)
                alerts = alert_manager.check_all_alerts()

                if alerts:
                    # Log warnings
                    for alert in alerts:
                        logger.warning(f"⚠️  {alert['message']}")

                    # Store for Telegram delivery
                    self.storage.save_pending_alerts(alerts)

            # Run strategy logic
            orders = self.strategy.run_daily_logic()
            run_result["orders_planned"] = len(orders)

            if not orders:
                logger.info("No orders to execute")
                return run_result

            # REQ-012: Check cooldown before executing orders
            if config.cooldown_enabled and self.storage.is_in_cooldown():
                cooldown_until = self.storage.get_cooldown_until()
                time_left = (cooldown_until - datetime.now()).total_seconds() / 60 if cooldown_until else 0
                logger.warning(
                    f"Cool-down active. Trading blocked for {time_left:.0f} more minutes. "
                    f"Skipping {len(orders)} orders."
                )
                return run_result

            # Skip proposing orders for symbols that already have a pending order
            filtered_orders = []
            skipped_symbols = []
            for order_details in orders:
                if self.execution_manager.has_pending_order_for_order(order_details):
                    sym = order_details.get("symbol")
                    if sym:
                        skipped_symbols.append(sym)
                    continue
                filtered_orders.append(order_details)
            run_result["orders_skipped"] = len(skipped_symbols)
            orders = filtered_orders
            if skipped_symbols:
                logger.info(
                    f"Skipping {len(skipped_symbols)} order(s) this cycle (already pending: {', '.join(skipped_symbols)})"
                )
            if not orders:
                logger.info("No orders to execute (all skipped: pending orders or none proposed)")
                return run_result

            logger.info(f"Executing {len(orders)} orders")
            orders_sent = 0

            # Execute orders (poll_timeout_seconds: None = full config timeout; short value when run from trading loop)
            for order_details in orders:
                if self.strategy.trades_today >= config.max_trades_per_day:
                    logger.warning(f"Max trades per day reached: {config.max_trades_per_day}")
                    break

                # Check confirm trade threshold
                quantity = order_details.get("quantity", 0)
                price = order_details.get("price", 0)
                order_value = abs(quantity * price)
                symbol = order_details.get("symbol", "")
                action = order_details.get("action", "")

                # Log large trades for visibility
                if order_value > config.confirm_trade_threshold_usd:
                    logger.warning(
                        f"Large trade: {action} {quantity} {symbol} @ ${price:.2f} "
                        f"(value: ${order_value:,.2f}, threshold: ${config.confirm_trade_threshold_usd:,.2f})"
                    )
                elif abs(quantity) > config.confirm_trade_threshold_contracts:
                    logger.warning(
                        f"Large trade: {action} {quantity} {symbol} "
                        f"(contracts: {abs(quantity)}, threshold: {config.confirm_trade_threshold_contracts})"
                    )

                result = self.execution_manager.execute_order(
                    order_details,
                    poll_timeout_seconds=poll_timeout_seconds,
                )
                if isinstance(result, dict) and result.get("ok") is False:
                    logger.warning(f"Order blocked: {result.get('error', 'unknown')}")
                    continue
                if result:
                    orders_sent += 1
                    run_result["orders_sent"] = orders_sent
                    # Save order to database
                    self.storage.save_order({
                        **order_details,
                        **result,
                    })
                    
                    # Only update as filled when status is actually FILLED (not OPEN/NEW)
                    order_status = (result.get("status") or "").upper()
                    if order_status == "FILLED":
                        self.storage.update_order_status(
                            result["order_id"],
                            "FILLED",
                            datetime.now(timezone.utc).isoformat()
                        )
                        
                        # Save fill
                        self.storage.save_fill({
                            "order_id": result["order_id"],
                            "symbol": result["symbol"],
                            "quantity": result["quantity"],
                            "fill_price": result["price"],
                        })

                        # REQ-011: Compute realized P&L for SELL orders
                        action = order_details.get("action", "").upper()
                        if action == "SELL" and "entry_price" in order_details:
                            entry_price = order_details["entry_price"]
                            fill_price = result["price"]
                            quantity = result["quantity"]
                            realized_pnl = (fill_price - entry_price) * quantity
                            outcome = "win" if realized_pnl > 0 else "loss"

                            # Update the saved order with realized P&L and outcome
                            self.storage.save_order({
                                **order_details,
                                **result,
                                "realized_pnl": realized_pnl,
                                "outcome": outcome,
                            })

                            logger.info(
                                f"Realized P&L: ${realized_pnl:,.2f} ({outcome}) "
                                f"on {result.get('symbol')}"
                            )

                        # REQ-012: Check if this fill triggers cool-down
                        cooldown_triggered = self.check_and_trigger_cooldown(order_details, result)
                        if cooldown_triggered:
                            logger.warning(
                                f"Cool-down triggered after fill. Stopping execution of remaining orders."
                            )
                            # Stop executing remaining orders in this batch
                            break

                        # Update strategy trade counter
                        self.strategy.trades_today += 1
                        logger.info(f"Order filled: {result.get('symbol')} x{result.get('quantity')}")
                    else:
                        if order_status in ("CANCELLED", "REJECTED", "EXPIRED"):
                            logger.info(
                                f"Order did not fill (status={order_status})."
                            )
                        else:
                            logger.info(
                                f"Order submitted (status={order_status}); "
                                "still open and may fill later."
                            )
                    logger.info(f"Order result: {result}")
                else:
                    logger.error(f"Order execution failed: {order_details}")
            
            logger.info("Daily logic completed")
            return run_result

        except Exception as e:
            logger.error(f"Error in daily logic: {e}", exc_info=True)
            return run_result
    
    def _should_run_rebalance_now(self) -> bool:
        """Return True if current time in configured timezone is at or past rebalance time and we haven't run today."""
        tz = ZoneInfo(config.rebalance_timezone)
        now_tz = datetime.now(tz)
        today = now_tz.date()
        rebalance_today = now_tz.replace(
            hour=config.rebalance_time_hour,
            minute=config.rebalance_time_minute,
            second=0,
            microsecond=0,
        )
        if now_tz < rebalance_today:
            return False
        if self._last_rebalance_date is None or self._last_rebalance_date.date() < today:
            return True
        return False

    def start(self):
        """Start the trading bot."""
        self.running = True
        tz = ZoneInfo(config.rebalance_timezone)
        rebalance_time = f"{config.rebalance_time_hour:02d}:{config.rebalance_time_minute:02d}"
        logger.info(
            f"Scheduled daily rebalancing at {rebalance_time} {config.rebalance_timezone}"
        )

        # Run immediately if already past rebalance time today (in configured TZ)
        if self._should_run_rebalance_now():
            self._last_rebalance_date = datetime.now(tz)
            logger.info("Running initial logic (past rebalance time in configured timezone)")
            self.run_daily_logic()

        logger.info("Bot is running. Press Ctrl+C to stop.")

        while self.running:
            if self._should_run_rebalance_now():
                self._last_rebalance_date = datetime.now(tz)
                self.run_daily_logic()
            time.sleep(60)  # Check every minute
    
    def stop(self):
        """Stop the trading bot."""
        logger.info("Stopping trading bot...")
        self.running = False
        self.client.close()
        logger.info("Trading bot stopped")


def main():
    """Main function."""
    bot = TradingBot(account_number=None)  # Will prompt if not saved
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        bot.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        bot.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Error running bot: {e}", exc_info=True)
        raise
    finally:
        bot.stop()


if __name__ == "__main__":
    main()
