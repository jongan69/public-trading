"""Main entry point for high-convexity portfolio trading bot."""
import signal
import sys
from datetime import datetime, timezone
from typing import Optional
from loguru import logger
import schedule
import time

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
        
        # Get or select account number
        if account_number is None:
            account_number = AccountManager.get_saved_account()
        
        if account_number is None:
            logger.info("No saved account found. Please select an account.")
            account_number = AccountManager.select_account_interactive(config.api_secret_key)
            if account_number is None:
                raise ValueError("Account selection cancelled or failed")
        
        # Initialize components
        self.client = TradingClient(account_number=account_number)
        self.data_manager = MarketDataManager(self.client)
        self.portfolio_manager = PortfolioManager(self.client, self.data_manager)
        self.execution_manager = ExecutionManager(self.client, self.portfolio_manager)
        self.storage = StorageManager()
        self.strategy = HighConvexityStrategy(
            self.portfolio_manager,
            self.data_manager,
            self.execution_manager
        )
        
        self.running = False
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
        
        if high_equity is None:
            return False
        
        drawdown_pct = (equity - high_equity) / high_equity
        
        if drawdown_pct <= -config.kill_switch_drawdown_pct:
            logger.warning(
                f"Kill switch activated: drawdown={drawdown_pct*100:.2f}% "
                f"(equity=${equity:.2f}, high=${high_equity:.2f})"
            )
            return True
        
        return False
    
    def run_daily_logic(self):
        """Run daily trading logic."""
        try:
            logger.info("=" * 70)
            logger.info("Running daily trading logic")
            logger.info("=" * 70)
            
            # Check kill switch
            if self.check_kill_switch():
                logger.warning("Kill switch active - skipping new positions")
                # Still process exits/rolls but don't open new positions
                # This would require modifying strategy logic
                return
            
            # Refresh portfolio
            self.portfolio_manager.refresh_portfolio()
            
            # Display portfolio breakdown
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
            
            # Run strategy logic
            orders = self.strategy.run_daily_logic()
            
            if not orders:
                logger.info("No orders to execute")
                return
            
            logger.info(f"Executing {len(orders)} orders")
            
            # Execute orders
            for order_details in orders:
                if self.strategy.trades_today >= config.max_trades_per_day:
                    logger.warning(f"Max trades per day reached: {config.max_trades_per_day}")
                    break
                
                result = self.execution_manager.execute_order(order_details)
                
                if result:
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
                        
                        # Update strategy trade counter
                        self.strategy.trades_today += 1
                        logger.info(f"Order filled: {result.get('symbol')} x{result.get('quantity')}")
                    else:
                        logger.info(
                            f"Order submitted (status={order_status}); "
                            "still open and may fill later."
                        )
                    logger.info(f"Order result: {result}")
                else:
                    logger.error(f"Order execution failed: {order_details}")
            
            logger.info("Daily logic completed")
            
        except Exception as e:
            logger.error(f"Error in daily logic: {e}", exc_info=True)
    
    def start(self):
        """Start the trading bot."""
        self.running = True
        
        # Schedule daily rebalancing
        rebalance_time = f"{config.rebalance_time_hour:02d}:{config.rebalance_time_minute:02d}"
        schedule.every().day.at(rebalance_time).do(self.run_daily_logic)
        
        logger.info(f"Scheduled daily rebalancing at {rebalance_time} {config.rebalance_timezone}")
        
        # Run initial logic if it's past rebalance time
        now = datetime.now()
        rebalance_datetime = now.replace(
            hour=config.rebalance_time_hour,
            minute=config.rebalance_time_minute,
            second=0,
            microsecond=0
        )
        
        if now >= rebalance_datetime:
            logger.info("Running initial logic (past rebalance time)")
            self.run_daily_logic()
        
        # Main loop
        logger.info("Bot is running. Press Ctrl+C to stop.")
        
        while self.running:
            schedule.run_pending()
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
