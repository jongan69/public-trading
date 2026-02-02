"""Export manager for trades CSV and performance reports (REQ-016)."""
import csv
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from src.storage import StorageManager


class ExportManager:
    """Manages export of trade history and performance reports."""

    def __init__(self, storage: "StorageManager"):
        """Initialize ExportManager.

        Args:
            storage: StorageManager instance for accessing trade data
        """
        self.storage = storage
        self.export_dir = Path(storage.db_path).parent / "exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ExportManager initialized with export directory: {self.export_dir}")

    def generate_trades_csv(self, days: int = 30) -> str:
        """Export orders and fills to CSV file.

        Args:
            days: Number of days of history to export (default 30)

        Returns:
            Path to generated CSV file
        """
        logger.info(f"Generating trades CSV for last {days} days")

        # Get orders from storage
        orders = self.storage.get_recent_orders(limit=10000)

        # Filter by date
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        filtered_orders = [
            o for o in orders
            if o.get("created_at", "") >= cutoff
        ]

        logger.info(f"Found {len(filtered_orders)} orders within date range")

        # Get fills for each order
        conn = sqlite3.connect(self.storage.db_path)
        cursor = conn.cursor()

        # Build rows for CSV
        rows = []
        for order in filtered_orders:
            order_id = order.get("order_id")

            # Query fills for this order
            cursor.execute(
                "SELECT fill_price, fill_time FROM fills WHERE order_id = ?",
                (order_id,)
            )
            fills = cursor.fetchall()

            # Create row (one per order, aggregate fills)
            avg_fill_price = None
            if fills:
                avg_fill_price = sum(f[0] for f in fills) / len(fills)

            fill_time = fills[0][1] if fills else order.get("filled_at")

            rows.append({
                "order_id": order_id,
                "symbol": order.get("symbol", ""),
                "side": order.get("side", ""),
                "quantity": order.get("quantity", ""),
                "limit_price": order.get("limit_price", ""),
                "status": order.get("status", ""),
                "fill_price": avg_fill_price if avg_fill_price is not None else "",
                "created_at": order.get("created_at", ""),
                "filled_at": fill_time if fill_time else "",
                "rationale": order.get("rationale", ""),
                "theme": order.get("theme", ""),
            })

        conn.close()

        # Write CSV
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")
        filename = f"trades_{date_from}_to_{date_to}.csv"
        filepath = self.export_dir / filename

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "order_id", "symbol", "side", "quantity", "limit_price",
                "status", "fill_price", "created_at", "filled_at",
                "rationale", "theme"
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        logger.info(f"Exported {len(rows)} trades to {filepath}")
        return str(filepath)

    def generate_performance_report(self, days: int = 30) -> str:
        """Generate performance report text file.

        Args:
            days: Number of days of history to include (default 30)

        Returns:
            Path to generated report file
        """
        logger.info(f"Generating performance report for last {days} days")

        from src.analytics import PerformanceAnalytics

        analytics = PerformanceAnalytics(self.storage)

        # Get metrics from existing analytics
        pnl_by_theme = analytics.get_pnl_by_theme(days)
        roll_analysis = analytics.get_roll_analysis(days)
        execution_quality = analytics.get_execution_quality(days)

        # Build report sections
        lines = []
        lines.append("=" * 60)
        lines.append(f"PERFORMANCE REPORT ({days} days)")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        lines.append("")

        # Section 1: P&L by Theme
        lines.append("P&L BY THEME")
        lines.append("-" * 60)

        if pnl_by_theme:
            total_pnl = 0
            total_trades = 0
            for theme, metrics in sorted(pnl_by_theme.items()):
                trades = metrics.get("trades", 0)
                pnl = metrics.get("realized_pnl", 0)
                avg_pnl = metrics.get("avg_pnl", 0)
                win_rate = metrics.get("win_rate", 0)

                lines.append(f"{theme}:")
                lines.append(f"  Trades: {trades}")
                lines.append(f"  Total P&L: ${pnl:,.2f}")
                lines.append(f"  Avg P&L: ${avg_pnl:,.2f}")
                lines.append(f"  Win Rate: {win_rate:.1f}%")
                lines.append("")

                total_pnl += pnl
                total_trades += trades

            lines.append(f"TOTAL P&L: ${total_pnl:,.2f}")
            lines.append(f"TOTAL TRADES: {total_trades}")
        else:
            lines.append("No trades in period")

        lines.append("")

        # Section 2: Roll Analysis
        lines.append("ROLL ANALYSIS")
        lines.append("-" * 60)
        lines.append(f"Total Rolls: {roll_analysis.get('rolls', 0)}")
        lines.append(f"Hold to Expiry: {roll_analysis.get('hold_to_expiry', 0)}")
        lines.append(f"Unique Symbols Rolled: {roll_analysis.get('unique_rolled_symbols', 0)}")
        lines.append(f"Roll Rate: {roll_analysis.get('roll_rate', 0):.1f}%")
        lines.append("")

        # Section 3: Execution Quality
        lines.append("EXECUTION QUALITY")
        lines.append("-" * 60)
        lines.append(f"Total Fills: {execution_quality.get('total_fills', 0)}")
        lines.append(f"Favorable Fills: {execution_quality.get('favorable_fills', 0)}")
        lines.append(f"At Limit Fills: {execution_quality.get('at_limit_fills', 0)}")
        lines.append(f"Unfavorable Fills: {execution_quality.get('unfavorable_fills', 0)}")
        lines.append(f"Avg Slippage: ${execution_quality.get('avg_slippage', 0):.4f}")
        lines.append(f"Favorable Fill Rate: {execution_quality.get('favorable_rate', 0):.1f}%")
        lines.append("")

        lines.append("=" * 60)

        # Write to file
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")
        filename = f"performance_{date_from}_to_{date_to}.txt"
        filepath = self.export_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"Generated performance report: {filepath}")
        return str(filepath)
