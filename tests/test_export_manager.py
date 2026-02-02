"""Tests for ExportManager (REQ-016)."""
import pytest
import csv
from pathlib import Path
from datetime import datetime, timedelta
from src.export_manager import ExportManager
from src.storage import StorageManager


@pytest.fixture
def storage(tmp_path):
    """Create temporary storage with test data."""
    db_path = tmp_path / "test_export.db"
    storage = StorageManager(db_path=str(db_path))

    # Add test orders
    test_orders = [
        {
            "order_id": "TEST001",
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 100,
            "price": 150.00,
            "limit_price": 150.00,
            "status": "FILLED",
            "rationale": "Test order 1",
            "theme": "theme_a",
        },
        {
            "order_id": "TEST002",
            "symbol": "MSFT",
            "side": "SELL",
            "quantity": 50,
            "price": 300.00,
            "limit_price": 300.00,
            "status": "FILLED",
            "rationale": "Test order 2",
            "theme": "theme_b",
        },
    ]

    for order in test_orders:
        storage.save_order(order)

    return storage


@pytest.fixture
def export_manager(storage):
    """Create ExportManager instance."""
    return ExportManager(storage)


def test_export_directory_created(export_manager):
    """Test that export directory is created."""
    assert export_manager.export_dir.exists()
    assert export_manager.export_dir.name == "exports"


def test_generate_trades_csv(export_manager):
    """Test CSV export generates valid file."""
    file_path = export_manager.generate_trades_csv(days=30)

    # Check file exists
    assert Path(file_path).exists()

    # Check file is valid CSV
    with open(file_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        # Should have 2 test orders
        assert len(rows) == 2

        # Check columns
        assert "order_id" in rows[0]
        assert "symbol" in rows[0]
        assert "side" in rows[0]
        assert "quantity" in rows[0]
        assert "limit_price" in rows[0]
        assert "status" in rows[0]

        # Check data (order-independent)
        order_ids = {row["order_id"] for row in rows}
        assert "TEST001" in order_ids
        assert "TEST002" in order_ids

        # Find AAPL order
        aapl_row = next(r for r in rows if r["symbol"] == "AAPL")
        assert aapl_row["order_id"] == "TEST001"


def test_generate_performance_report(export_manager):
    """Test performance report generation."""
    file_path = export_manager.generate_performance_report(days=30)

    # Check file exists
    assert Path(file_path).exists()

    # Check file has content
    with open(file_path, "r") as f:
        content = f.read()

        # Should have report headers
        assert "PERFORMANCE REPORT" in content
        assert "P&L BY THEME" in content
        assert "ROLL ANALYSIS" in content
        assert "EXECUTION QUALITY" in content


def test_csv_filename_format(export_manager):
    """Test that CSV filename includes date range."""
    file_path = export_manager.generate_trades_csv(days=30)
    filename = Path(file_path).name

    # Should match pattern: trades_YYYY-MM-DD_to_YYYY-MM-DD.csv
    assert filename.startswith("trades_")
    assert filename.endswith(".csv")
    assert "_to_" in filename


def test_report_filename_format(export_manager):
    """Test that report filename includes date range."""
    file_path = export_manager.generate_performance_report(days=30)
    filename = Path(file_path).name

    # Should match pattern: performance_YYYY-MM-DD_to_YYYY-MM-DD.txt
    assert filename.startswith("performance_")
    assert filename.endswith(".txt")
    assert "_to_" in filename


def test_export_with_no_orders(tmp_path):
    """Test export when no orders exist."""
    db_path = tmp_path / "empty.db"
    storage = StorageManager(db_path=str(db_path))
    export_manager = ExportManager(storage)

    # Should not error, just generate empty CSV
    file_path = export_manager.generate_trades_csv(days=30)

    with open(file_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 0  # No data rows, only header


def test_multiple_subscribers(export_manager):
    """Test that CSV export handles multiple orders correctly."""
    # Add more test orders
    additional_orders = [
        {
            "order_id": "TEST003",
            "symbol": "TSLA",
            "side": "BUY",
            "quantity": 25,
            "price": 200.00,
            "limit_price": 200.00,
            "status": "FILLED",
            "rationale": "Test order 3",
            "theme": "moonshot",
        },
    ]

    for order in additional_orders:
        export_manager.storage.save_order(order)

    file_path = export_manager.generate_trades_csv(days=30)

    with open(file_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        # Should now have 3 orders
        assert len(rows) == 3
