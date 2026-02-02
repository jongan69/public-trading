"""Performance analytics for learning loop (REQ-009)."""
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional
from collections import defaultdict
from loguru import logger

from src.storage import StorageManager


class PerformanceAnalytics:
    """Read-only analytics for strategy performance tracking."""

    def __init__(self, storage: StorageManager):
        """Initialize analytics with storage manager.

        Args:
            storage: StorageManager instance
        """
        self.storage = storage

    def get_pnl_by_theme(self, days: int = 30) -> Dict[str, Dict[str, float]]:
        """Get P&L breakdown by theme over last N days.

        Args:
            days: Number of days to look back

        Returns:
            Dict mapping theme to metrics (trades, realized_pnl, avg_pnl)
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        orders = self.storage.get_recent_orders(limit=1000)

        # Filter to filled orders in timeframe with theme and realized P&L
        theme_data = defaultdict(lambda: {"trades": 0, "realized_pnl": 0.0, "wins": 0, "losses": 0})

        for order in orders:
            if order.get("status") != "FILLED":
                continue
            created_at = order.get("created_at", "")
            if created_at < cutoff:
                continue

            theme = order.get("theme") or "untagged"
            realized_pnl = order.get("realized_pnl")

            if realized_pnl is not None:
                theme_data[theme]["trades"] += 1
                theme_data[theme]["realized_pnl"] += float(realized_pnl)
                if realized_pnl > 0:
                    theme_data[theme]["wins"] += 1
                elif realized_pnl < 0:
                    theme_data[theme]["losses"] += 1

        # Calculate averages
        for theme, data in theme_data.items():
            if data["trades"] > 0:
                data["avg_pnl"] = data["realized_pnl"] / data["trades"]
                data["win_rate"] = data["wins"] / data["trades"] if data["trades"] > 0 else 0
            else:
                data["avg_pnl"] = 0.0
                data["win_rate"] = 0.0

        return dict(theme_data)

    def get_roll_analysis(self, days: int = 90) -> Dict[str, any]:
        """Analyze roll execution: rolled vs held to expiry.

        Args:
            days: Number of days to look back

        Returns:
            Dict with roll metrics
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        orders = self.storage.get_recent_orders(limit=1000)

        rolls = 0
        hold_to_expiry = 0
        roll_symbols = set()

        for order in orders:
            if order.get("status") != "FILLED":
                continue
            created_at = order.get("created_at", "")
            if created_at < cutoff:
                continue

            rationale = (order.get("rationale") or "").lower()
            outcome = (order.get("outcome") or "").lower()

            if "roll" in rationale or "roll" in outcome:
                rolls += 1
                roll_symbols.add(order.get("symbol", ""))
            elif "expir" in rationale or "dte" in rationale:
                hold_to_expiry += 1

        return {
            "rolls": rolls,
            "hold_to_expiry": hold_to_expiry,
            "unique_rolled_symbols": len(roll_symbols),
            "roll_rate": rolls / (rolls + hold_to_expiry) if (rolls + hold_to_expiry) > 0 else 0,
        }

    def get_execution_quality(self, days: int = 30) -> Dict[str, any]:
        """Analyze execution quality: limit vs fill price, slippage.

        Args:
            days: Number of days to look back

        Returns:
            Dict with execution metrics
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        orders = self.storage.get_recent_orders(limit=1000)

        slippage_data = []
        favorable = 0
        unfavorable = 0
        at_limit = 0

        for order in orders:
            if order.get("status") != "FILLED":
                continue
            created_at = order.get("created_at", "")
            if created_at < cutoff:
                continue

            limit_price = order.get("limit_price")
            side = order.get("side", "").upper()

            # Get fill price from fills table
            fills = self._get_fills_for_order(order.get("order_id"))
            if not fills:
                continue

            fill_price = fills[0].get("fill_price")
            if limit_price and fill_price:
                # Calculate slippage (positive = better than limit, negative = worse)
                if side == "BUY":
                    slippage = limit_price - fill_price  # Pay less = good
                else:  # SELL
                    slippage = fill_price - limit_price  # Get more = good

                slippage_data.append(slippage)

                if slippage > 0:
                    favorable += 1
                elif slippage < 0:
                    unfavorable += 1
                else:
                    at_limit += 1

        return {
            "total_fills": len(slippage_data),
            "favorable_fills": favorable,
            "unfavorable_fills": unfavorable,
            "at_limit_fills": at_limit,
            "avg_slippage": sum(slippage_data) / len(slippage_data) if slippage_data else 0,
            "favorable_rate": favorable / len(slippage_data) if slippage_data else 0,
        }

    def _get_fills_for_order(self, order_id: str) -> List[Dict]:
        """Get fills for a specific order ID.

        Args:
            order_id: Order ID to lookup

        Returns:
            List of fill dictionaries
        """
        import sqlite3
        conn = sqlite3.connect(self.storage.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM fills
            WHERE order_id = ?
            ORDER BY fill_time DESC
        """, (order_id,))

        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        fills = [dict(zip(columns, row)) for row in rows]

        conn.close()
        return fills

    def get_performance_summary(self, days: int = 30) -> str:
        """Get comprehensive performance summary for last N days.

        Args:
            days: Number of days to look back

        Returns:
            Formatted string summary
        """
        pnl_by_theme = self.get_pnl_by_theme(days)
        roll_analysis = self.get_roll_analysis(days)
        exec_quality = self.get_execution_quality(days)

        lines = [
            f"**Performance Summary (Last {days} days)**",
            "",
            "**P&L by Theme:**",
        ]

        total_pnl = 0.0
        total_trades = 0

        if pnl_by_theme:
            for theme, data in sorted(pnl_by_theme.items(), key=lambda x: x[1]["realized_pnl"], reverse=True):
                pnl = data["realized_pnl"]
                trades = data["trades"]
                avg = data["avg_pnl"]
                win_rate = data["win_rate"]
                total_pnl += pnl
                total_trades += trades

                lines.append(
                    f"  • {theme}: {trades} trades, "
                    f"P&L ${pnl:,.2f} (avg ${avg:.2f}), "
                    f"win rate {win_rate*100:.1f}%"
                )
        else:
            lines.append("  No trades with P&L data in period.")

        lines.extend([
            "",
            f"**Total: {total_trades} trades, P&L ${total_pnl:,.2f}**",
            "",
            "**Roll Analysis:**",
            f"  • Rolls executed: {roll_analysis['rolls']}",
            f"  • Held to expiry: {roll_analysis['hold_to_expiry']}",
            f"  • Unique symbols rolled: {roll_analysis['unique_rolled_symbols']}",
            f"  • Roll rate: {roll_analysis['roll_rate']*100:.1f}%",
            "",
            "**Execution Quality:**",
            f"  • Total fills: {exec_quality['total_fills']}",
            f"  • Favorable (better than limit): {exec_quality['favorable_fills']} ({exec_quality['favorable_rate']*100:.1f}%)",
            f"  • At limit: {exec_quality['at_limit_fills']}",
            f"  • Unfavorable (worse than limit): {exec_quality['unfavorable_fills']}",
            f"  • Avg slippage: ${exec_quality['avg_slippage']:.4f}",
            "",
            "Note: This is read-only analytics. Strategy changes require human decision.",
        ])

        return "\n".join(lines)
