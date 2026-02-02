---
id: REQ-016
title: Export trades (CSV) and performance report
status: pending
created_at: 2026-02-02T00:00:00Z
user_request: UR-002
---

# Export Trades (CSV) and Performance Report

## What

Users cannot export trade history or a performance summary for records or taxes. Add CSV export of orders/fills and an optional performance report (e.g. PDF or text file) for a given date range.

## Detailed Requirements

- **Trades CSV:** A tool or script that exports orders (and optionally fills) to CSV for a configurable date range. Columns: order_id, symbol, side, quantity, limit_price, status, fill_price (if filled), created_at, filled_at, rationale, theme (if present). Output to a file (e.g. `data/exports/trades_YYYY-MM-DD_to_YYYY-MM-DD.csv`) or return path. Expose via Telegram (e.g. “Export my trades” → bot generates and sends file or link) or CLI (e.g. `python -m src.export_trades --days 30`).
- **Performance report:** A report (text or PDF) summarizing performance over N days: total P&L, win rate, P&L by theme (if data available), roll analysis, execution quality summary. Reuse analytics.get_performance_summary logic; format for file output. Optional: PDF using a simple template (e.g. reportlab or fpdf) or markdown that user can convert. Expose via Telegram (“Send performance report”) or CLI.
- **Safety:** Export path should be under project data dir; do not expose secrets. File names include date range to avoid overwrite.

## Constraints

- CSV format should be standard (headers, one row per order or per fill). Performance report is read-only (no strategy changes).

## Dependencies

- storage (get_recent_orders, get fills), analytics (get_performance_summary, get_pnl_by_theme, etc.), telegram_bot (optional tool to trigger export and send file), config (export path).

---
*Source: Bot Missing Features Audit plan – missing feature 2.6*
