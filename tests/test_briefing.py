"""Tests for daily briefing subscriber management (REQ-015)."""
import pytest
from src.storage import StorageManager


@pytest.fixture
def storage(tmp_path):
    """Create temporary storage for testing."""
    db_path = tmp_path / "test_briefing.db"
    return StorageManager(db_path=str(db_path))


def test_get_briefing_subscribers_empty(storage):
    """Test getting subscribers when none exist."""
    subscribers = storage.get_briefing_subscribers()
    assert subscribers == []


def test_add_briefing_subscriber(storage):
    """Test adding a subscriber."""
    storage.add_briefing_subscriber(12345)

    subscribers = storage.get_briefing_subscribers()
    assert 12345 in subscribers
    assert len(subscribers) == 1


def test_is_briefing_subscriber(storage):
    """Test checking if a chat is subscribed."""
    # Initially not subscribed
    assert not storage.is_briefing_subscriber(12345)

    # Add subscriber
    storage.add_briefing_subscriber(12345)
    assert storage.is_briefing_subscriber(12345)


def test_remove_briefing_subscriber(storage):
    """Test removing a subscriber."""
    # Add subscriber
    storage.add_briefing_subscriber(12345)
    assert storage.is_briefing_subscriber(12345)

    # Remove subscriber
    storage.remove_briefing_subscriber(12345)
    assert not storage.is_briefing_subscriber(12345)
    assert storage.get_briefing_subscribers() == []


def test_add_duplicate_subscriber(storage):
    """Test that adding the same subscriber twice doesn't create duplicates."""
    storage.add_briefing_subscriber(12345)
    storage.add_briefing_subscriber(12345)

    subscribers = storage.get_briefing_subscribers()
    assert len(subscribers) == 1
    assert 12345 in subscribers


def test_multiple_subscribers(storage):
    """Test managing multiple subscribers."""
    # Add multiple subscribers
    storage.add_briefing_subscriber(12345)
    storage.add_briefing_subscriber(67890)
    storage.add_briefing_subscriber(11111)

    subscribers = storage.get_briefing_subscribers()
    assert len(subscribers) == 3
    assert 12345 in subscribers
    assert 67890 in subscribers
    assert 11111 in subscribers

    # Remove one subscriber
    storage.remove_briefing_subscriber(67890)

    subscribers = storage.get_briefing_subscribers()
    assert len(subscribers) == 2
    assert 12345 in subscribers
    assert 11111 in subscribers
    assert 67890 not in subscribers


def test_remove_nonexistent_subscriber(storage):
    """Test that removing a non-existent subscriber doesn't error."""
    # Should not raise an error
    storage.remove_briefing_subscriber(99999)
    assert storage.get_briefing_subscribers() == []


def test_subscriber_persistence(storage):
    """Test that subscribers persist across multiple calls."""
    # Add subscribers
    storage.add_briefing_subscriber(12345)
    storage.add_briefing_subscriber(67890)

    # Retrieve multiple times
    subs1 = storage.get_briefing_subscribers()
    subs2 = storage.get_briefing_subscribers()
    subs3 = storage.get_briefing_subscribers()

    assert subs1 == subs2 == subs3
    assert len(subs1) == 2
    assert 12345 in subs1
    assert 67890 in subs1
