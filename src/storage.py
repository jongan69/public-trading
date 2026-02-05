"""SQLite database storage for trading bot."""
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
from loguru import logger
import json

from src.config import config


def _get_snapshot_config_dict() -> Dict[str, Any]:
    """Build dict of all non-sensitive config for snapshots (learning/analytics)."""
    from src.utils.config_override_manager import TELEGRAM_EDITABLE_KEYS
    return {k: getattr(config, k, None) for k in TELEGRAM_EDITABLE_KEYS if hasattr(config, k)}


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
        
        # Portfolio snapshots (config_json added for learning: correlate config with outcomes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date DATE NOT NULL,
                equity REAL NOT NULL,
                buying_power REAL NOT NULL,
                cash REAL NOT NULL,
                allocations_json TEXT,
                config_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Ensure config_json exists on existing DBs (no-op if already present)
        try:
            cursor.execute("ALTER TABLE portfolio_snapshots ADD COLUMN config_json TEXT")
        except sqlite3.OperationalError as e:
            # Column likely already exists, which is fine
            logger.debug(f"Migration: {e}")
        
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

        # Research reports (deep research capabilities)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                research_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reasoning_chain TEXT,
                fundamental_score REAL,
                technical_score REAL,
                sentiment_score REAL,
                overall_score REAL,
                recommendation TEXT,
                confidence REAL,
                key_findings TEXT,
                risks TEXT,
                catalysts TEXT,
                report_json TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_research_symbol_timestamp ON research_reports(symbol, timestamp DESC)")

        # Theme change proposals (autonomous theme management)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS theme_change_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                theme_name TEXT NOT NULL,
                current_symbols TEXT,
                proposed_symbols TEXT,
                reasoning_chain TEXT,
                recommendation_score REAL,
                expected_improvement TEXT,
                risks TEXT,
                status TEXT,
                proposed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                decided_at TIMESTAMP,
                executed_at TIMESTAMP,
                outcome TEXT
            )
        """)

        # Chain-of-thought logs (structured reasoning)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chain_of_thought_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                step_number INTEGER NOT NULL,
                step_name TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                data_json TEXT,
                confidence REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cot_session ON chain_of_thought_logs(session_id, step_number)")

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
        """Save full non-sensitive config snapshot for learning (correlate config with outcomes).

        Args:
            equity: Current equity value
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        config_dict = _get_snapshot_config_dict()
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
        """Save portfolio snapshot with current config for learning (correlate config with outcomes).

        Args:
            portfolio_data: Dict with equity, buying_power, cash, allocations (optional)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        allocations_json = json.dumps(portfolio_data.get("allocations", {}))
        config_dict = portfolio_data.get("config") or _get_snapshot_config_dict()
        config_json = json.dumps(config_dict)
        cursor.execute("""
            INSERT INTO portfolio_snapshots 
            (snapshot_date, equity, buying_power, cash, allocations_json, config_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            date.today().isoformat(),
            portfolio_data["equity"],
            portfolio_data["buying_power"],
            portfolio_data["cash"],
            allocations_json,
            config_json,
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

    def get_balance_trends(self, days: int = 30, max_points: int = 500) -> List[Dict]:
        """Get portfolio balance snapshots over time for trend observation (includes config for learning).

        Args:
            days: Number of days to look back.
            max_points: Maximum number of snapshots to return (most recent first).

        Returns:
            List of dicts with created_at, equity, buying_power, cash, allocations, config (when present).
            Ordered by created_at descending (newest first). config correlates snapshot with strategy for learning.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        # Support DBs with or without config_json column
        cursor.execute("PRAGMA table_info(portfolio_snapshots)")
        has_config = any(col[1] == "config_json" for col in cursor.fetchall())
        if has_config:
            cursor.execute("""
                SELECT created_at, snapshot_date, equity, buying_power, cash, allocations_json, config_json
                FROM portfolio_snapshots WHERE snapshot_date >= ? ORDER BY created_at DESC LIMIT ?
            """, (cutoff, max_points))
            columns = ["created_at", "snapshot_date", "equity", "buying_power", "cash", "allocations_json", "config_json"]
        else:
            cursor.execute("""
                SELECT created_at, snapshot_date, equity, buying_power, cash, allocations_json
                FROM portfolio_snapshots WHERE snapshot_date >= ? ORDER BY created_at DESC LIMIT ?
            """, (cutoff, max_points))
            columns = ["created_at", "snapshot_date", "equity", "buying_power", "cash", "allocations_json"]
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            d = dict(zip(columns, row))
            if d.get("allocations_json"):
                try:
                    d["allocations"] = json.loads(d["allocations_json"])
                except (TypeError, json.JSONDecodeError):
                    d["allocations"] = {}
            if d.get("config_json"):
                try:
                    d["config"] = json.loads(d["config_json"])
                except (TypeError, json.JSONDecodeError):
                    d["config"] = {}
            result.append(d)
        return result
    
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

    # =====================================
    # Proactive Alerts (REQ-014)
    # =====================================

    def get_pending_alerts(self) -> List[Dict[str, Any]]:
        """Get pending alerts from bot_state.

        Returns:
            List of alert dictionaries
        """
        alerts_json = self.get_bot_state("pending_alerts")
        if not alerts_json:
            return []
        try:
            import json
            return json.loads(alerts_json)
        except Exception:
            return []

    def save_pending_alerts(self, alerts: List[Dict[str, Any]]):
        """Save pending alerts to bot_state.

        Args:
            alerts: List of alert dictionaries to save
        """
        import json
        self.set_bot_state("pending_alerts", json.dumps(alerts))

    def clear_pending_alerts(self):
        """Clear pending alerts from bot_state."""
        self.delete_bot_state("pending_alerts")

    def mark_alert_triggered(self, alert_key: str):
        """Mark an alert as triggered with current timestamp.

        Args:
            alert_key: Alert type identifier (e.g., 'kill_switch_warning', 'roll_warning_AAPL')
        """
        key = f"alert_last_triggered_{alert_key}"
        self.set_bot_state(key, datetime.now().isoformat())

    def get_alert_last_triggered(self, alert_key: str) -> Optional[datetime]:
        """Get timestamp of last trigger for an alert type.

        Args:
            alert_key: Alert type identifier

        Returns:
            Datetime of last trigger, or None if never triggered
        """
        key = f"alert_last_triggered_{alert_key}"
        value = self.get_bot_state(key)
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    # =====================================
    # Daily Briefing (REQ-015)
    # =====================================

    def get_briefing_subscribers(self) -> List[int]:
        """Get list of chat IDs subscribed to daily briefing.

        Returns:
            List of chat IDs
        """
        subs_json = self.get_bot_state("daily_briefing_subscribers")
        if not subs_json:
            return []
        try:
            return json.loads(subs_json)
        except Exception:
            return []

    def add_briefing_subscriber(self, chat_id: int):
        """Add chat ID to daily briefing subscribers.

        Args:
            chat_id: Telegram chat ID to add
        """
        subs = self.get_briefing_subscribers()
        if chat_id not in subs:
            subs.append(chat_id)
            self.set_bot_state("daily_briefing_subscribers", json.dumps(subs))

    def remove_briefing_subscriber(self, chat_id: int):
        """Remove chat ID from daily briefing subscribers.

        Args:
            chat_id: Telegram chat ID to remove
        """
        subs = self.get_briefing_subscribers()
        if chat_id in subs:
            subs.remove(chat_id)
            self.set_bot_state("daily_briefing_subscribers", json.dumps(subs))

    def is_briefing_subscriber(self, chat_id: int) -> bool:
        """Check if chat ID is subscribed to daily briefing.

        Args:
            chat_id: Telegram chat ID to check

        Returns:
            True if subscribed, False otherwise
        """
        return chat_id in self.get_briefing_subscribers()

    # =====================================
    # Deep Research & Theme Management
    # =====================================

    def save_research_report(self, report: Dict[str, Any]) -> int:
        """Save research report to database.

        Args:
            report: Research report dictionary with keys:
                symbol, research_type, reasoning_chain, fundamental_score,
                technical_score, sentiment_score, overall_score,
                recommendation, confidence, key_findings, risks, catalysts

        Returns:
            Report ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO research_reports (
                symbol, research_type, reasoning_chain, fundamental_score,
                technical_score, sentiment_score, overall_score, recommendation,
                confidence, key_findings, risks, catalysts, report_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report.get("symbol"),
            report.get("research_type", "deep_symbol"),
            json.dumps(report.get("reasoning_chain", [])),
            report.get("fundamental_score"),
            report.get("technical_score"),
            report.get("sentiment_score"),
            report.get("overall_score"),
            report.get("recommendation"),
            report.get("confidence"),
            json.dumps(report.get("key_findings", [])),
            json.dumps(report.get("risks", [])),
            json.dumps(report.get("catalysts", [])),
            json.dumps(report)
        ))

        report_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Saved research report: {report.get('symbol')} (ID: {report_id})")
        return report_id

    def get_research_report(self, report_id: int) -> Optional[Dict]:
        """Get research report by ID.

        Args:
            report_id: Report ID

        Returns:
            Report dictionary or None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM research_reports WHERE id = ?
        """, (report_id,))

        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        conn.close()

        if row:
            report = dict(zip(columns, row))
            # Parse JSON fields
            for field in ["reasoning_chain", "key_findings", "risks", "catalysts"]:
                if report.get(field):
                    try:
                        report[field] = json.loads(report[field])
                    except Exception:
                        pass
            return report
        return None

    def get_recent_research_reports(self, symbol: Optional[str] = None,
                                   limit: int = 10) -> List[Dict]:
        """Get recent research reports.

        Args:
            symbol: Optional symbol to filter by
            limit: Maximum number of reports to return

        Returns:
            List of report dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if symbol:
            cursor.execute("""
                SELECT * FROM research_reports
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (symbol, limit))
        else:
            cursor.execute("""
                SELECT * FROM research_reports
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))

        columns = [desc[0] for desc in cursor.description]
        reports = []
        for row in cursor.fetchall():
            report = dict(zip(columns, row))
            # Parse JSON fields
            for field in ["reasoning_chain", "key_findings", "risks", "catalysts"]:
                if report.get(field):
                    try:
                        report[field] = json.loads(report[field])
                    except Exception:
                        pass
            reports.append(report)

        conn.close()
        return reports

    def save_theme_change_proposal(self, proposal: Dict[str, Any]) -> int:
        """Save theme change proposal.

        Args:
            proposal: Proposal dictionary with keys:
                theme_name, current_symbols, proposed_symbols, reasoning_chain,
                recommendation_score, expected_improvement, risks, confidence

        Returns:
            Proposal ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO theme_change_proposals (
                theme_name, current_symbols, proposed_symbols, reasoning_chain,
                recommendation_score, expected_improvement, risks, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            proposal.get("theme_name"),
            json.dumps(proposal.get("current_symbols", [])),
            json.dumps(proposal.get("proposed_symbols", [])),
            json.dumps(proposal.get("reasoning_chain", [])),
            proposal.get("recommendation_score"),
            proposal.get("expected_improvement"),
            json.dumps(proposal.get("risks", [])),
            proposal.get("status", "proposed")
        ))

        proposal_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Saved theme change proposal: {proposal.get('theme_name')} (ID: {proposal_id})")
        return proposal_id

    def get_theme_change_proposal(self, proposal_id: int) -> Optional[Dict]:
        """Get theme change proposal by ID.

        Args:
            proposal_id: Proposal ID

        Returns:
            Proposal dictionary or None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM theme_change_proposals WHERE id = ?
        """, (proposal_id,))

        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        conn.close()

        if row:
            proposal = dict(zip(columns, row))
            # Parse JSON fields
            for field in ["current_symbols", "proposed_symbols", "reasoning_chain", "risks"]:
                if proposal.get(field):
                    try:
                        proposal[field] = json.loads(proposal[field])
                    except Exception:
                        pass
            return proposal
        return None

    def get_recent_theme_proposals(self, theme_name: Optional[str] = None,
                                  limit: int = 10) -> List[Dict]:
        """Get recent theme change proposals.

        Args:
            theme_name: Optional theme to filter by
            limit: Maximum number of proposals to return

        Returns:
            List of proposal dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if theme_name:
            cursor.execute("""
                SELECT * FROM theme_change_proposals
                WHERE theme_name = ?
                ORDER BY proposed_at DESC
                LIMIT ?
            """, (theme_name, limit))
        else:
            cursor.execute("""
                SELECT * FROM theme_change_proposals
                ORDER BY proposed_at DESC
                LIMIT ?
            """, (limit,))

        columns = [desc[0] for desc in cursor.description]
        proposals = []
        for row in cursor.fetchall():
            proposal = dict(zip(columns, row))
            # Parse JSON fields
            for field in ["current_symbols", "proposed_symbols", "reasoning_chain", "risks"]:
                if proposal.get(field):
                    try:
                        proposal[field] = json.loads(proposal[field])
                    except Exception:
                        pass
            proposals.append(proposal)

        conn.close()
        return proposals

    def update_theme_change_proposal(self, proposal_id: int,
                                    status: str,
                                    executed_at: Optional[datetime] = None) -> None:
        """Update theme change proposal status.

        Args:
            proposal_id: Proposal ID
            status: New status (proposed, approved, rejected, executed)
            executed_at: Optional execution timestamp
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if executed_at:
            cursor.execute("""
                UPDATE theme_change_proposals
                SET status = ?, executed_at = ?, decided_at = ?
                WHERE id = ?
            """, (status, executed_at.isoformat(), datetime.now().isoformat(), proposal_id))
        else:
            cursor.execute("""
                UPDATE theme_change_proposals
                SET status = ?, decided_at = ?
                WHERE id = ?
            """, (status, datetime.now().isoformat(), proposal_id))

        conn.commit()
        conn.close()
        logger.info(f"Updated theme change proposal {proposal_id}: status={status}")

    def log_chain_of_thought(self, session_id: str, step_number: int,
                           step_name: str, reasoning: str,
                           data: Optional[Dict] = None,
                           confidence: Optional[float] = None) -> None:
        """Log a chain-of-thought reasoning step.

        Args:
            session_id: Session ID (groups related steps)
            step_number: Step number in sequence
            step_name: Name of this step
            reasoning: Human-readable reasoning text
            data: Optional supporting data dictionary
            confidence: Optional confidence score (0-1)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO chain_of_thought_logs (
                session_id, step_number, step_name, reasoning, data_json, confidence
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            step_number,
            step_name,
            reasoning,
            json.dumps(data) if data else None,
            confidence
        ))

        conn.commit()
        conn.close()

    def get_chain_of_thought(self, session_id: str) -> List[Dict]:
        """Get all chain-of-thought steps for a session.

        Args:
            session_id: Session ID

        Returns:
            List of step dictionaries ordered by step_number
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM chain_of_thought_logs
            WHERE session_id = ?
            ORDER BY step_number ASC
        """, (session_id,))

        columns = [desc[0] for desc in cursor.description]
        steps = []
        for row in cursor.fetchall():
            step = dict(zip(columns, row))
            # Parse data_json
            if step.get("data_json"):
                try:
                    step["data"] = json.loads(step["data_json"])
                except Exception:
                    pass
            steps.append(step)

        conn.close()
        return steps
