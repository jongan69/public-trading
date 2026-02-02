"""SQLite database storage for trading bot."""
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, date, timedelta
from loguru import logger
import json

from src.config import config


class StorageManager:
    """Manages SQLite database for positions, orders, and configuration."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize the storage manager.
        
        Args:
            db_path: Path to database file (defaults to config)
        """
        self.db_path = db_path or config.db_path
        self._init_database()
        logger.info(f"Storage manager initialized: {self.db_path}")
    
    def _init_database(self):
        """Initialize database schema. Ensures parent directory exists."""
        db_path = Path(self.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Positions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                osi_symbol TEXT,
                underlying TEXT,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                instrument_type TEXT NOT NULL,
                expiration TEXT,
                strike REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol)
            )
        """)
        
        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                limit_price REAL NOT NULL,
                status TEXT NOT NULL,
                preflight_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                filled_at TIMESTAMP,
                canceled_at TIMESTAMP
            )
        """)
        
        # Fills table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                fill_price REAL NOT NULL,
                fill_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            )
        """)
        
        # Contracts table (chosen option contracts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                osi_symbol TEXT NOT NULL UNIQUE,
                underlying TEXT NOT NULL,
                expiration TEXT NOT NULL,
                strike REAL NOT NULL,
                selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        
        # Configuration snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date DATE NOT NULL,
                config_json TEXT NOT NULL,
                equity REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Portfolio snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date DATE NOT NULL,
                equity REAL NOT NULL,
                buying_power REAL NOT NULL,
                cash REAL NOT NULL,
                allocations_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Equity history (for kill switch)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                equity REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date)
            )
        """)

        # Bot state (REQ-008: pause, cool-down, confirmations)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        self._migrate_orders_rationale()
        self._migrate_orders_learning_loop()
        logger.debug("Database schema initialized")

    def _migrate_orders_rationale(self):
        """Add rationale column to orders if missing (transparency/explainability)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in cursor.fetchall()]
        if "rationale" not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN rationale TEXT")
            conn.commit()
            logger.debug("Added rationale column to orders table")
        conn.close()

    def _migrate_orders_learning_loop(self):
        """Add theme and outcome columns to orders (REQ-009: learning loop)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in cursor.fetchall()]

        changes = []
        if "theme" not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN theme TEXT")
            changes.append("theme")
        if "outcome" not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN outcome TEXT")
            changes.append("outcome")
        if "entry_price" not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN entry_price REAL")
            changes.append("entry_price")
        if "realized_pnl" not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN realized_pnl REAL")
            changes.append("realized_pnl")

        if changes:
            conn.commit()
            logger.debug(f"Added learning loop columns to orders table: {', '.join(changes)}")
        conn.close()

    def save_position(self, position: Dict):
        """Save or update a position.
        
        Args:
            position: Position dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO positions 
            (symbol, osi_symbol, underlying, quantity, entry_price, instrument_type, expiration, strike, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            position["symbol"],
            position.get("osi_symbol"),
            position.get("underlying"),
            position["quantity"],
            position["entry_price"],
            position["instrument_type"],
            position.get("expiration"),
            position.get("strike"),
            datetime.now().isoformat(),
        ))
        
        conn.commit()
        conn.close()
    
    def get_positions(self) -> List[Dict]:
        """Get all positions.
        
        Returns:
            List of position dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM positions")
        rows = cursor.fetchall()
        
        columns = [desc[0] for desc in cursor.description]
        positions = [dict(zip(columns, row)) for row in rows]
        
        conn.close()
        return positions
    
    def delete_position(self, symbol: str):
        """Delete a position.
        
        Args:
            symbol: Symbol to delete
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        
        conn.commit()
        conn.close()
    
    def save_order(self, order: Dict):
        """Save an order (including rationale, theme, outcome for learning loop)."""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        preflight_json = json.dumps(order.get("preflight")) if order.get("preflight") else None
        rationale = order.get("rationale") or ""
        theme = order.get("theme")
        outcome = order.get("outcome")
        entry_price = order.get("entry_price")
        realized_pnl = order.get("realized_pnl")

        cursor.execute("""
            INSERT OR REPLACE INTO orders
            (order_id, symbol, side, quantity, limit_price, status, preflight_data, rationale, theme, outcome, entry_price, realized_pnl, created_at, filled_at, canceled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order["order_id"],
            order["symbol"],
            order.get("action") or order.get("side"),
            order["quantity"],
            order["price"] or order.get("limit_price"),
            order.get("status", "PENDING"),
            preflight_json,
            rationale,
            theme,
            outcome,
            entry_price,
            realized_pnl,
            order.get("created_at", datetime.now().isoformat()),
            order.get("filled_at"),
            order.get("canceled_at"),
        ))

        conn.commit()
        conn.close()
    
    def update_order_status(self, order_id: str, status: str, filled_at: Optional[str] = None):
        """Update order status.
        
        Args:
            order_id: Order ID
            status: New status
            filled_at: Fill timestamp if filled
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if status == "FILLED" and filled_at:
            cursor.execute("""
                UPDATE orders 
                SET status = ?, filled_at = ?
                WHERE order_id = ?
            """, (status, filled_at, order_id))
        else:
            cursor.execute("""
                UPDATE orders 
                SET status = ?
                WHERE order_id = ?
            """, (status, order_id))
        
        conn.commit()
        conn.close()
    
    def save_fill(self, fill: Dict):
        """Save a fill.
        
        Args:
            fill: Fill dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO fills (order_id, symbol, quantity, fill_price, fill_time)
            VALUES (?, ?, ?, ?, ?)
        """, (
            fill["order_id"],
            fill["symbol"],
            fill["quantity"],
            fill["fill_price"],
            fill.get("fill_time", datetime.now().isoformat()),
        ))
        
        conn.commit()
        conn.close()
    
    def save_contract(self, contract: Dict):
        """Save a chosen option contract.
        
        Args:
            contract: Contract dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        metadata_json = json.dumps(contract.get("metadata", {}))
        
        cursor.execute("""
            INSERT OR REPLACE INTO contracts 
            (osi_symbol, underlying, expiration, strike, selected_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            contract["osi_symbol"],
            contract["underlying"],
            contract["expiration"],
            contract["strike"],
            datetime.now().isoformat(),
            metadata_json,
        ))
        
        conn.commit()
        conn.close()
    
    def save_config_snapshot(self, equity: float):
        """Save configuration snapshot.
        
        Args:
            equity: Current equity value
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        config_dict = {
            "theme_underlyings": config.theme_underlyings,
            "moonshot_symbol": config.moonshot_symbol,
            "theme_a_target": config.theme_a_target,
            "theme_b_target": config.theme_b_target,
            "theme_c_target": config.theme_c_target,
            "moonshot_target": config.moonshot_target,
            "cash_minimum": config.cash_minimum,
        }
        
        config_json = json.dumps(config_dict)
        
        cursor.execute("""
            INSERT INTO config_snapshots (snapshot_date, config_json, equity, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            date.today().isoformat(),
            config_json,
            equity,
            datetime.now().isoformat(),
        ))
        
        conn.commit()
        conn.close()
    
    def save_portfolio_snapshot(self, portfolio_data: Dict):
        """Save portfolio snapshot.
        
        Args:
            portfolio_data: Portfolio data dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        allocations_json = json.dumps(portfolio_data.get("allocations", {}))
        
        cursor.execute("""
            INSERT INTO portfolio_snapshots 
            (snapshot_date, equity, buying_power, cash, allocations_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            date.today().isoformat(),
            portfolio_data["equity"],
            portfolio_data["buying_power"],
            portfolio_data["cash"],
            allocations_json,
            datetime.now().isoformat(),
        ))
        
        conn.commit()
        conn.close()
    
    def save_equity_history(self, equity: float):
        """Save equity history entry.
        
        Args:
            equity: Current equity value
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO equity_history (date, equity, created_at)
            VALUES (?, ?, ?)
        """, (
            date.today().isoformat(),
            equity,
            datetime.now().isoformat(),
        ))
        
        conn.commit()
        conn.close()
    
    def get_equity_high_last_n_days(self, days: int) -> Optional[float]:
        """Get highest equity in last N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Highest equity value or None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = (date.today() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            SELECT MAX(equity) FROM equity_history
            WHERE date >= ?
        """, (cutoff_date,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result and result[0] else None
    
    def get_recent_orders(self, limit: int = 100) -> List[Dict]:
        """Get recent orders.

        Args:
            limit: Maximum number of orders to return

        Returns:
            List of order dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM orders
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        orders = [dict(zip(columns, row)) for row in rows]

        conn.close()
        return orders

    # REQ-008: Bot state management for pause, cool-down, and confirmations

    def set_bot_state(self, key: str, value: str):
        """Set bot state value.

        Args:
            key: State key (e.g. 'trading_paused', 'cooldown_until')
            value: State value as string
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO bot_state (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, value, datetime.now().isoformat()))

        conn.commit()
        conn.close()

    def get_bot_state(self, key: str) -> Optional[str]:
        """Get bot state value.

        Args:
            key: State key

        Returns:
            State value or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT value FROM bot_state WHERE key = ?", (key,))
        result = cursor.fetchone()

        conn.close()
        return result[0] if result else None

    def delete_bot_state(self, key: str):
        """Delete bot state value.

        Args:
            key: State key to delete
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM bot_state WHERE key = ?", (key,))

        conn.commit()
        conn.close()

    def is_trading_paused(self) -> bool:
        """Check if trading is paused via bot state.

        Returns:
            True if trading is paused, False otherwise
        """
        paused = self.get_bot_state("trading_paused")
        return paused == "true" if paused else False

    def set_trading_paused(self, paused: bool):
        """Set trading paused state.

        Args:
            paused: True to pause trading, False to resume
        """
        self.set_bot_state("trading_paused", "true" if paused else "false")

    def get_cooldown_until(self) -> Optional[datetime]:
        """Get cool-down expiry time.

        Returns:
            Datetime when cool-down expires, or None if not in cool-down
        """
        cooldown_str = self.get_bot_state("cooldown_until")
        if not cooldown_str:
            return None
        try:
            return datetime.fromisoformat(cooldown_str)
        except (ValueError, TypeError):
            return None

    def set_cooldown_until(self, until: Optional[datetime]):
        """Set cool-down expiry time.

        Args:
            until: Datetime when cool-down should expire, or None to clear cool-down
        """
        if until:
            self.set_bot_state("cooldown_until", until.isoformat())
        else:
            self.delete_bot_state("cooldown_until")

    def is_in_cooldown(self) -> bool:
        """Check if bot is in cool-down period.

        Returns:
            True if in cool-down, False otherwise
        """
        cooldown_until = self.get_cooldown_until()
        if not cooldown_until:
            return False
        return datetime.now() < cooldown_until
