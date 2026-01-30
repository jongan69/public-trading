"""Tests for ExecutionManager."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal
from src.execution import ExecutionManager
from src.client import TradingClient
from src.portfolio import PortfolioManager
from public_api_sdk import OrderSide, OrderType, InstrumentType


@pytest.fixture
def mock_client():
    """Create a mock trading client."""
    client = Mock(spec=TradingClient)
    client.client = Mock()
    return client


@pytest.fixture
def mock_portfolio():
    """Create a mock portfolio manager."""
    portfolio = Mock(spec=PortfolioManager)
    portfolio.get_equity.return_value = 1200.0
    portfolio.get_cash.return_value = 300.0
    return portfolio


@pytest.fixture
def execution_manager(mock_client, mock_portfolio):
    """Create an execution manager instance."""
    return ExecutionManager(mock_client, mock_portfolio)


def test_calculate_preflight(execution_manager, mock_client):
    """Test preflight calculation."""
    class MockPreflight:
        def __init__(self):
            self.estimated_commission = Decimal("1.00")
            self.order_value = Decimal("1500.00")
            self.estimated_cost = Decimal("1501.00")
            self.buying_power_requirement = Decimal("1501.00")
    
    mock_client.client.perform_preflight_calculation.return_value = MockPreflight()
    
    preflight = execution_manager.calculate_preflight(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        limit_price=Decimal("150.00")
    )
    
    assert preflight is not None
    assert preflight["estimated_commission"] == 1.0
    assert preflight["order_value"] == 1500.0


def test_check_cash_buffer_sufficient(execution_manager, mock_portfolio):
    """Test cash buffer check with sufficient cash."""
    mock_portfolio.get_equity.return_value = 1200.0
    mock_portfolio.get_cash.return_value = 300.0
    
    # Order value: 100, cash: 300, target cash: 240 (20% of 1200)
    # Remaining: 300 - 100 = 200, which is < 240, so should fail
    # Actually wait, let me recalculate: 300 - 100 = 200, target is 240, so fails
    # But if order is 50: 300 - 50 = 250, target is 240, so passes
    
    result = execution_manager.check_cash_buffer(50.0)
    assert result == True


def test_check_cash_buffer_insufficient(execution_manager, mock_portfolio):
    """Test cash buffer check with insufficient cash."""
    mock_portfolio.get_equity.return_value = 1200.0
    mock_portfolio.get_cash.return_value = 300.0
    
    # Order value: 100, cash: 300, target cash: 240 (20% of 1200)
    # Remaining: 300 - 100 = 200 < 240, so should fail
    result = execution_manager.check_cash_buffer(100.0)
    assert result == False


def test_place_order_dry_run(execution_manager):
    """Test order placement in dry run mode."""
    from src.config import config
    original_dry_run = config.dry_run
    
    try:
        config.dry_run = True
        
        order_id = execution_manager.place_order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            limit_price=Decimal("150.00")
        )
        
        assert order_id is not None
        assert order_id.startswith("DRY_RUN_")
        # In dry run, order_history is still updated
        assert len(execution_manager.order_history) >= 1
    finally:
        config.dry_run = original_dry_run


def test_place_order_real(execution_manager, mock_client):
    """Test order placement in real mode."""
    from src.config import config
    original_dry_run = config.dry_run
    
    try:
        config.dry_run = False
        
        class MockOrderResponse:
            def __init__(self):
                self.order_id = "ORDER123"
        
        mock_client.client.place_order.return_value = MockOrderResponse()
        
        order_id = execution_manager.place_order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            limit_price=Decimal("150.00")
        )
        
        assert order_id == "ORDER123"
        assert len(execution_manager.order_history) == 1
    finally:
        config.dry_run = original_dry_run


def test_poll_order_status_dry_run(execution_manager):
    """Test order polling in dry run mode."""
    from src.config import config
    original_dry_run = config.dry_run
    
    try:
        config.dry_run = True
        
        result = execution_manager.poll_order_status("DRY_RUN_TEST")
        
        assert result is not None
        assert result["status"] == "FILLED"
        assert result["dry_run"] == True
    finally:
        config.dry_run = original_dry_run


def test_execute_order_complete_flow(execution_manager, mock_client, mock_portfolio):
    """Test complete order execution flow."""
    from src.config import config
    original_dry_run = config.dry_run
    
    try:
        config.dry_run = True
        
        # Mock preflight
        class MockPreflight:
            def __init__(self):
                self.estimated_commission = Decimal("1.00")
                self.order_value = Decimal("150.00")
                self.estimated_cost = Decimal("151.00")
                self.buying_power_requirement = Decimal("151.00")
        
        mock_client.client.perform_preflight_calculation.return_value = MockPreflight()
        mock_portfolio.get_cash.return_value = 500.0  # Sufficient cash
        
        order_details = {
            "action": "BUY",
            "symbol": "AAPL",
            "quantity": 1,
            "price": 150.0
        }
        
        result = execution_manager.execute_order(order_details)
        
        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["action"] == "BUY"
    finally:
        config.dry_run = original_dry_run


def test_cancel_order_dry_run(execution_manager):
    """Test order cancellation in dry run mode."""
    from src.config import config
    original_dry_run = config.dry_run
    
    try:
        config.dry_run = True
        
        result = execution_manager.cancel_order("ORDER123")
        assert result == True
    finally:
        config.dry_run = original_dry_run
