"""Tests for allocation math."""
import pytest
from unittest.mock import Mock, MagicMock
from src.portfolio import PortfolioManager, Position
from src.market_data import MarketDataManager
from src.client import TradingClient
from public_api_sdk import InstrumentType


@pytest.fixture
def mock_client():
    """Create a mock trading client."""
    client = Mock(spec=TradingClient)
    client.client = Mock()
    client.account_number = "TEST_ACCOUNT"
    portfolio_mock = Mock()
    portfolio_mock.equity = 1200.0
    portfolio_mock.buying_power = 600.0
    portfolio_mock.cash = 300.0
    client.client.get_portfolio.return_value = portfolio_mock
    return client


@pytest.fixture
def mock_data_manager():
    """Create a mock data manager."""
    manager = Mock(spec=MarketDataManager)
    manager.get_quote.return_value = 100.0
    return manager


@pytest.fixture
def portfolio_manager(mock_client, mock_data_manager):
    """Create a portfolio manager instance."""
    return PortfolioManager(mock_client, mock_data_manager)


def test_get_equity(portfolio_manager, mock_client):
    """Test getting equity."""
    equity = portfolio_manager.get_equity()
    assert equity == 1200.0


def test_get_current_allocations_empty(portfolio_manager):
    """Test allocations with no positions."""
    allocations = portfolio_manager.get_current_allocations()
    
    assert allocations["theme_a"] == 0.0
    assert allocations["theme_b"] == 0.0
    assert allocations["theme_c"] == 0.0
    assert allocations["moonshot"] == 0.0
    assert allocations["cash"] == 0.25  # 300 / 1200


def test_get_current_allocations_with_positions(portfolio_manager, mock_data_manager):
    """Test allocations with positions."""
    # Add a theme A position
    position = Position(
        symbol="UMC250117C00100000",
        quantity=1,
        entry_price=50.0,
        instrument_type=InstrumentType.OPTION,
        osi_symbol="UMC250117C00100000",
        underlying="UMC",
        expiration="2025-01-17",
        strike=100.0
    )
    
    portfolio_manager.add_position(position)
    
    # Mock current price
    mock_data_manager.get_quote.return_value = 60.0
    
    allocations = portfolio_manager.get_current_allocations()
    
    # Position value: 1 * 60 = 60
    # Equity: 1200
    # Allocation: 60 / 1200 = 0.05
    assert allocations["theme_a"] == pytest.approx(0.05, abs=0.01)


def test_calculate_rebalance_needs(portfolio_manager, mock_data_manager):
    """Test rebalancing needs calculation."""
    from src.config import config
    
    # Add a small position
    position = Position(
        symbol="UMC250117C00100000",
        quantity=1,
        entry_price=50.0,
        instrument_type=InstrumentType.OPTION,
        osi_symbol="UMC250117C00100000",
        underlying="UMC",
        expiration="2025-01-17",
        strike=100.0
    )
    
    portfolio_manager.add_position(position)
    mock_data_manager.get_quote.return_value = 60.0
    
    needs = portfolio_manager.calculate_rebalance_needs()
    
    # Target for theme_a: 1200 * 0.35 = 420
    # Current: 60
    # Need: 420 - 60 = 360
    assert needs["theme_a"] == pytest.approx(360.0, abs=10.0)


def test_get_target_allocations():
    """Test target allocations."""
    from src.portfolio import PortfolioManager
    from src.client import TradingClient
    from src.market_data import MarketDataManager
    
    client = Mock(spec=TradingClient)
    data = Mock(spec=MarketDataManager)
    portfolio = PortfolioManager(client, data)
    
    targets = portfolio.get_target_allocations()

    assert targets["theme_a"] == 0.35
    assert targets["theme_b"] == 0.35
    assert targets["moonshot"] == 0.20
    assert targets["cash"] >= 0.20


def test_classify_asset_type(portfolio_manager):
    """Test asset type classification from instrument type."""
    # Test equity classification
    assert portfolio_manager._classify_asset_type(InstrumentType.EQUITY) == "equity"
    assert portfolio_manager._classify_asset_type(InstrumentType.OPTION) == "equity"
    assert portfolio_manager._classify_asset_type(InstrumentType.INDEX) == "equity"
    assert portfolio_manager._classify_asset_type(InstrumentType.MULTI_LEG_INSTRUMENT) == "equity"

    # Test crypto classification
    assert portfolio_manager._classify_asset_type(InstrumentType.CRYPTO) == "crypto"

    # Test bonds classification
    assert portfolio_manager._classify_asset_type(InstrumentType.BOND) == "bonds"
    assert portfolio_manager._classify_asset_type(InstrumentType.TREASURY) == "bonds"

    # Test alt classification
    assert portfolio_manager._classify_asset_type(InstrumentType.ALT) == "alt"


def test_get_allocations_by_type_empty(portfolio_manager):
    """Test allocation by type with empty portfolio."""
    by_type = portfolio_manager.get_allocations_by_type()

    # Mock portfolio has equity=1200, cash=300
    # With no positions: equity 0%, cash 25%
    assert by_type["equity"]["pct"] == 0.0
    assert by_type["equity"]["value"] == 0.0
    assert by_type["crypto"]["pct"] == 0.0
    assert by_type["bonds"]["pct"] == 0.0
    assert by_type["alt"]["pct"] == 0.0
    assert by_type["cash"]["pct"] == pytest.approx(0.25, abs=0.01)  # 300/1200
    assert by_type["cash"]["value"] == 300.0


def test_get_allocations_by_type_with_equity(portfolio_manager, mock_data_manager):
    """Test allocation by type with equity position."""
    # Add equity position
    position = Position(
        symbol="AAPL",
        quantity=10,
        entry_price=100.0,
        instrument_type=InstrumentType.EQUITY
    )
    portfolio_manager.add_position(position)

    # Mock quote: $150 per share
    mock_data_manager.get_quote.return_value = 150.0

    by_type = portfolio_manager.get_allocations_by_type()

    # Market value: 10 * 150 = $1500
    # Mock equity (denominator): $1200
    # Cash: $300
    # equity: 1500/1200 = 125%
    # cash: 300/1200 = 25%

    assert by_type["equity"]["pct"] == pytest.approx(1.25, abs=0.01)
    assert by_type["equity"]["value"] == pytest.approx(1500.0, abs=1.0)
    assert by_type["crypto"]["pct"] == 0.0
    assert by_type["cash"]["pct"] == pytest.approx(0.25, abs=0.01)
    assert by_type["cash"]["value"] == pytest.approx(300.0, abs=1.0)


def test_get_allocations_by_type_mixed_assets(portfolio_manager, mock_data_manager):
    """Test allocation by type with multiple asset types."""
    # Add equity
    pos_equity = Position(
        symbol="AAPL",
        quantity=10,
        entry_price=100.0,
        instrument_type=InstrumentType.EQUITY
    )
    portfolio_manager.add_position(pos_equity)

    # Add option (counts as equity)
    pos_option = Position(
        symbol="SPY250117C00500000",
        quantity=1,
        entry_price=500.0,
        instrument_type=InstrumentType.OPTION,
        osi_symbol="SPY250117C00500000",
        underlying="SPY",
        expiration="2025-01-17",
        strike=500.0
    )
    portfolio_manager.add_position(pos_option)

    # Mock quotes
    def mock_quote(symbol, instrument_type=None):
        if symbol == "AAPL":
            return 150.0
        elif symbol == "SPY250117C00500000":
            return 10.0  # $10 per contract = $1000
        return 100.0  # default

    mock_data_manager.get_quote.side_effect = mock_quote

    by_type = portfolio_manager.get_allocations_by_type()

    # Market value: AAPL 10*150 = 1500, SPY opt 1*10 = 10
    # Total equity in positions: 1510
    # Mock equity (denominator): 1200
    # Cash: 300
    # equity: 1510/1200 = 125.8%
    # cash: 300/1200 = 25%
    # (Percentages exceed 100% because position values exceed mock equity)

    assert by_type["equity"]["pct"] == pytest.approx(1.258, abs=0.01)
    assert by_type["equity"]["value"] == pytest.approx(1510.0, abs=1.0)
    assert by_type["cash"]["pct"] == pytest.approx(0.25, abs=0.01)
