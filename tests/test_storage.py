"""Tests for StorageManager."""
import pytest
import sqlite3
import json
import os
from pathlib import Path
from datetime import date, datetime
from src.storage import StorageManager


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_bot.db"
    storage = StorageManager(db_path=str(db_path))
    yield storage
    # Cleanup
    if db_path.exists():
        db_path.unlink()


def test_save_and_get_position(temp_db):
    """Test saving and retrieving positions."""
    position = {
        "symbol": "AAPL250117C00150000",
        "osi_symbol": "AAPL250117C00150000",
        "underlying": "AAPL",
        "quantity": 1,
        "entry_price": 50.0,
        "instrument_type": "OPTION",
        "expiration": "2025-01-17",
        "strike": 150.0
    }
    
    temp_db.save_position(position)
    
    positions = temp_db.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "AAPL250117C00150000"
    assert positions[0]["quantity"] == 1


def test_delete_position(temp_db):
    """Test deleting a position."""
    position = {
        "symbol": "AAPL250117C00150000",
        "quantity": 1,
        "entry_price": 50.0,
        "instrument_type": "OPTION"
    }
    
    temp_db.save_position(position)
    assert len(temp_db.get_positions()) == 1
    
    temp_db.delete_position("AAPL250117C00150000")
    assert len(temp_db.get_positions()) == 0


def test_save_and_update_order(temp_db):
    """Test saving and updating orders."""
    order = {
        "order_id": "ORDER123",
        "symbol": "AAPL",
        "action": "BUY",
        "quantity": 10,
        "price": 150.0,
        "status": "PENDING"
    }
    
    temp_db.save_order(order)
    
    temp_db.update_order_status("ORDER123", "FILLED", datetime.now().isoformat())
    
    orders = temp_db.get_recent_orders()
    assert len(orders) == 1
    assert orders[0]["status"] == "FILLED"


def test_save_fill(temp_db):
    """Test saving fills."""
    fill = {
        "order_id": "ORDER123",
        "symbol": "AAPL",
        "quantity": 10,
        "fill_price": 150.0
    }
    
    temp_db.save_fill(fill)
    
    # Verify fill was saved (would need to query fills table directly)
    conn = sqlite3.connect(temp_db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM fills WHERE order_id = ?", ("ORDER123",))
    fills = cursor.fetchall()
    conn.close()
    
    assert len(fills) == 1


def test_save_contract(temp_db):
    """Test saving option contracts."""
    contract = {
        "osi_symbol": "AAPL250117C00150000",
        "underlying": "AAPL",
        "expiration": "2025-01-17",
        "strike": 150.0
    }
    
    temp_db.save_contract(contract)
    
    # Verify contract was saved
    conn = sqlite3.connect(temp_db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contracts WHERE osi_symbol = ?", ("AAPL250117C00150000",))
    contracts = cursor.fetchall()
    conn.close()
    
    assert len(contracts) == 1


def test_save_config_snapshot(temp_db):
    """Test saving configuration snapshots."""
    temp_db.save_config_snapshot(1200.0)
    
    # Verify snapshot was saved
    conn = sqlite3.connect(temp_db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM config_snapshots")
    snapshots = cursor.fetchall()
    conn.close()
    
    assert len(snapshots) == 1
    assert snapshots[0][3] == 1200.0  # equity column


def test_save_portfolio_snapshot(temp_db):
    """Test saving portfolio snapshots."""
    portfolio_data = {
        "equity": 1200.0,
        "buying_power": 600.0,
        "cash": 300.0,
        "allocations": {
            "theme_a": 0.35,
            "theme_b": 0.35
        }
    }
    
    temp_db.save_portfolio_snapshot(portfolio_data)
    
    # Verify snapshot was saved
    conn = sqlite3.connect(temp_db.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM portfolio_snapshots")
    snapshots = cursor.fetchall()
    conn.close()
    
    assert len(snapshots) == 1
    assert snapshots[0][2] == 1200.0  # equity column


def test_save_and_get_equity_history(temp_db):
    """Test saving and retrieving equity history."""
    temp_db.save_equity_history(1200.0)
    temp_db.save_equity_history(1300.0)
    
    high = temp_db.get_equity_high_last_n_days(30)
    assert high == 1300.0


def test_get_recent_orders(temp_db):
    """Test getting recent orders."""
    for i in range(5):
        order = {
            "order_id": f"ORDER{i}",
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
            "price": 150.0,
            "status": "FILLED"
        }
        temp_db.save_order(order)
    
    orders = temp_db.get_recent_orders(limit=3)
    assert len(orders) == 3
    # Should be most recent first
    assert orders[0]["order_id"] == "ORDER4"
