"""SQLite database storage for trading bot."""
import sqlite3
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
        """Initialize database schema."""
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
        
        conn.commit()
        conn.close()
        logger.debug("Database schema initialized")
    
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
        """Save an order.
        
        Args:
            order: Order dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        preflight_json = json.dumps(order.get("preflight")) if order.get("preflight") else None
        
        cursor.execute("""
            INSERT OR REPLACE INTO orders 
            (order_id, symbol, side, quantity, limit_price, status, preflight_data, created_at, filled_at, canceled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order["order_id"],
            order["symbol"],
            order.get("action") or order.get("side"),
            order["quantity"],
            order["price"] or order.get("limit_price"),
            order.get("status", "PENDING"),
            preflight_json,
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
