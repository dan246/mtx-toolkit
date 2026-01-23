"""
Tests for BlacklistManager service.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import IPBlacklist, MediaMTXNode
from app.services.blacklist_manager import BlacklistManager


@pytest.fixture
def sample_blacklist_entry(db_session, sample_node):
    """Create a sample blacklist entry."""
    entry = IPBlacklist(
        ip_address="192.168.1.100",
        reason="Test block",
        blocked_by="test",
        is_permanent=False,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        is_active=True,
    )
    db_session.add(entry)
    db_session.commit()
    return entry


@pytest.fixture
def sample_permanent_entry(db_session):
    """Create a sample permanent blacklist entry."""
    entry = IPBlacklist(
        ip_address="192.168.1.200",
        reason="Permanent block",
        blocked_by="admin",
        is_permanent=True,
        expires_at=None,
        is_active=True,
    )
    db_session.add(entry)
    db_session.commit()
    return entry


@pytest.fixture
def sample_expired_entry(db_session):
    """Create an expired blacklist entry."""
    entry = IPBlacklist(
        ip_address="192.168.1.150",
        reason="Expired block",
        blocked_by="test",
        is_permanent=False,
        expires_at=datetime.utcnow() - timedelta(hours=1),
        is_active=True,
    )
    db_session.add(entry)
    db_session.commit()
    return entry


class TestBlacklistManager:
    """Tests for BlacklistManager service."""

    def test_block_ip_new(self, app_context, db_session):
        """Test blocking a new IP address."""
        manager = BlacklistManager()
        result = manager.block_ip(
            ip_address="10.0.0.1",
            reason="Test block",
            blocked_by="test_user",
            duration="1h",
        )

        assert result["success"] is True
        assert "blocked successfully" in result["message"]
        assert result["entry"]["ip_address"] == "10.0.0.1"
        assert result["entry"]["is_permanent"] is False

    def test_block_ip_permanent(self, app_context, db_session):
        """Test blocking an IP permanently."""
        manager = BlacklistManager()
        result = manager.block_ip(
            ip_address="10.0.0.2",
            reason="Permanent block",
            blocked_by="admin",
            duration="permanent",
        )

        assert result["success"] is True
        assert result["entry"]["is_permanent"] is True
        assert result["entry"]["expires_at"] is None

    def test_block_ip_with_path_pattern(self, app_context, db_session):
        """Test blocking an IP with path pattern."""
        manager = BlacklistManager()
        result = manager.block_ip(
            ip_address="10.0.0.3",
            reason="Path-specific block",
            blocked_by="test",
            duration="1h",
            path_pattern="cam1/*",
        )

        assert result["success"] is True
        assert result["entry"]["path_pattern"] == "cam1/*"

    def test_block_ip_with_node_id(self, app_context, db_session, sample_node):
        """Test blocking an IP for specific node."""
        manager = BlacklistManager()
        result = manager.block_ip(
            ip_address="10.0.0.4",
            reason="Node-specific block",
            blocked_by="test",
            duration="1h",
            node_id=sample_node.id,
        )

        assert result["success"] is True
        assert result["entry"]["node_id"] == sample_node.id

    def test_block_ip_update_existing(
        self, app_context, db_session, sample_blacklist_entry
    ):
        """Test updating an existing block."""
        manager = BlacklistManager()
        result = manager.block_ip(
            ip_address=sample_blacklist_entry.ip_address,
            reason="Updated reason",
            blocked_by="new_user",
            duration="6h",
        )

        assert result["success"] is True
        assert "updated" in result["message"]
        assert result["entry"]["reason"] == "Updated reason"

    def test_block_ip_various_durations(self, app_context, db_session):
        """Test various block durations."""
        manager = BlacklistManager()
        durations = ["5m", "15m", "30m", "1h", "6h", "24h", "7d", "30d"]

        for i, duration in enumerate(durations):
            result = manager.block_ip(
                ip_address=f"10.0.1.{i}",
                duration=duration,
            )
            assert result["success"] is True
            assert result["entry"]["is_permanent"] is False

    def test_block_ip_invalid_duration(self, app_context, db_session):
        """Test blocking with invalid duration defaults to 1h."""
        manager = BlacklistManager()
        result = manager.block_ip(
            ip_address="10.0.0.99",
            duration="invalid",
        )

        assert result["success"] is True
        # Should default to 1h

    def test_unblock_ip_by_id(self, app_context, db_session, sample_blacklist_entry):
        """Test unblocking by entry ID."""
        manager = BlacklistManager()
        result = manager.unblock_ip(sample_blacklist_entry.id)

        assert result["success"] is True
        assert "unblocked successfully" in result["message"]

        # Verify entry is now inactive
        entry = IPBlacklist.query.get(sample_blacklist_entry.id)
        assert entry.is_active is False

    def test_unblock_ip_not_found(self, app_context, db_session):
        """Test unblocking non-existent entry."""
        manager = BlacklistManager()
        result = manager.unblock_ip(99999)

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_unblock_ip_by_address(
        self, app_context, db_session, sample_blacklist_entry
    ):
        """Test unblocking by IP address."""
        manager = BlacklistManager()
        result = manager.unblock_ip_by_address(sample_blacklist_entry.ip_address)

        assert result["success"] is True
        assert result["count"] == 1

    def test_unblock_ip_by_address_multiple(self, app_context, db_session):
        """Test unblocking multiple entries for same IP."""
        # Create multiple entries for same IP
        for i in range(3):
            entry = IPBlacklist(
                ip_address="192.168.5.5",
                reason=f"Block {i}",
                is_active=True,
                path_pattern=f"path{i}" if i > 0 else None,
            )
            db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()
        result = manager.unblock_ip_by_address("192.168.5.5")

        assert result["success"] is True
        assert result["count"] == 3

    def test_unblock_ip_by_address_with_filters(
        self, app_context, db_session, sample_node
    ):
        """Test unblocking with path_pattern and node_id filters."""
        entry = IPBlacklist(
            ip_address="192.168.6.6",
            reason="Filtered block",
            is_active=True,
            path_pattern="cam1",
            node_id=sample_node.id,
        )
        db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()
        result = manager.unblock_ip_by_address(
            "192.168.6.6", path_pattern="cam1", node_id=sample_node.id
        )

        assert result["success"] is True
        assert result["count"] == 1

    def test_is_ip_blocked_not_blocked(self, app_context, db_session):
        """Test checking an IP that is not blocked."""
        manager = BlacklistManager()
        result = manager.is_ip_blocked("10.10.10.10")

        assert result["blocked"] is False

    def test_is_ip_blocked_active(
        self, app_context, db_session, sample_blacklist_entry
    ):
        """Test checking an IP that is blocked."""
        manager = BlacklistManager()
        result = manager.is_ip_blocked(sample_blacklist_entry.ip_address)

        assert result["blocked"] is True
        assert result["entry"]["ip_address"] == sample_blacklist_entry.ip_address

    def test_is_ip_blocked_expired(self, app_context, db_session, sample_expired_entry):
        """Test checking an expired block."""
        manager = BlacklistManager()
        result = manager.is_ip_blocked(sample_expired_entry.ip_address)

        # Expired entries should be cleaned up
        assert result["blocked"] is False

    def test_is_ip_blocked_with_path(self, app_context, db_session):
        """Test checking IP block with path pattern."""
        entry = IPBlacklist(
            ip_address="192.168.7.7",
            reason="Path block",
            is_active=True,
            path_pattern="cam*",
        )
        db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()

        # Should match path starting with "cam"
        result = manager.is_ip_blocked("192.168.7.7", path="cam1")
        assert result["blocked"] is True

        # Should not match other paths
        result = manager.is_ip_blocked("192.168.7.7", path="other")
        assert result["blocked"] is False

    def test_is_ip_blocked_with_node_id(self, app_context, db_session, sample_node):
        """Test checking IP block with node_id."""
        entry = IPBlacklist(
            ip_address="192.168.8.8",
            reason="Node block",
            is_active=True,
            node_id=sample_node.id,
        )
        db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()

        # Should match correct node
        result = manager.is_ip_blocked("192.168.8.8", node_id=sample_node.id)
        assert result["blocked"] is True

        # Should not match other nodes
        result = manager.is_ip_blocked("192.168.8.8", node_id=9999)
        assert result["blocked"] is False

    def test_list_blocked_ips(self, app_context, db_session, sample_blacklist_entry):
        """Test listing blocked IPs."""
        manager = BlacklistManager()
        result = manager.list_blocked_ips()

        assert len(result["entries"]) >= 1
        assert result["total"] >= 1
        assert result["page"] == 1

    def test_list_blocked_ips_pagination(self, app_context, db_session):
        """Test listing blocked IPs with pagination."""
        # Create multiple entries
        for i in range(15):
            entry = IPBlacklist(
                ip_address=f"192.168.10.{i}",
                reason=f"Block {i}",
                is_active=True,
            )
            db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()
        result = manager.list_blocked_ips(page=1, per_page=10)

        assert len(result["entries"]) == 10
        assert result["total"] == 15
        assert result["pages"] == 2

        result_page2 = manager.list_blocked_ips(page=2, per_page=10)
        assert len(result_page2["entries"]) == 5

    def test_list_blocked_ips_empty(self, app_context, db_session):
        """Test listing when no IPs are blocked."""
        manager = BlacklistManager()
        result = manager.list_blocked_ips()

        assert result["entries"] == []
        assert result["total"] == 0
        assert result["pages"] == 1

    def test_get_block_stats(
        self, app_context, db_session, sample_blacklist_entry, sample_permanent_entry
    ):
        """Test getting block statistics."""
        manager = BlacklistManager()
        result = manager.get_block_stats()

        assert result["total_blocked"] >= 2
        assert result["permanent"] >= 1
        assert result["temporary"] >= 1

    def test_get_block_stats_empty(self, app_context, db_session):
        """Test getting stats when no IPs are blocked."""
        manager = BlacklistManager()
        result = manager.get_block_stats()

        assert result["total_blocked"] == 0
        assert result["permanent"] == 0
        assert result["temporary"] == 0

    def test_cleanup_expired(self, app_context, db_session, sample_expired_entry):
        """Test cleanup of expired entries."""
        manager = BlacklistManager()
        count = manager._cleanup_expired()

        assert count >= 1

        # Verify entry is now inactive
        entry = IPBlacklist.query.get(sample_expired_entry.id)
        assert entry.is_active is False

    def test_cleanup_expired_none_expired(
        self, app_context, db_session, sample_blacklist_entry
    ):
        """Test cleanup when no entries are expired."""
        manager = BlacklistManager()
        count = manager._cleanup_expired()

        assert count == 0

    def test_entry_to_dict(self, app_context, db_session, sample_blacklist_entry):
        """Test entry to dict conversion."""
        manager = BlacklistManager()
        result = manager._entry_to_dict(sample_blacklist_entry)

        assert result["id"] == sample_blacklist_entry.id
        assert result["ip_address"] == sample_blacklist_entry.ip_address
        assert result["reason"] == sample_blacklist_entry.reason
        assert result["is_permanent"] is False
        assert result["remaining_seconds"] is not None
        assert result["remaining_seconds"] > 0

    def test_entry_to_dict_permanent(
        self, app_context, db_session, sample_permanent_entry
    ):
        """Test entry to dict for permanent entry."""
        manager = BlacklistManager()
        result = manager._entry_to_dict(sample_permanent_entry)

        assert result["is_permanent"] is True
        assert result["expires_at"] is None
        assert result["remaining_seconds"] is None

    def test_entry_to_dict_with_node(self, app_context, db_session, sample_node):
        """Test entry to dict with associated node."""
        entry = IPBlacklist(
            ip_address="192.168.9.9",
            reason="Node block",
            is_active=True,
            node_id=sample_node.id,
        )
        db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()
        result = manager._entry_to_dict(entry)

        assert result["node_id"] == sample_node.id
        assert result["node_name"] == sample_node.name

    def test_entry_applies_global(self, app_context, db_session):
        """Test _entry_applies for global entry (no path/node restrictions)."""
        entry = IPBlacklist(
            ip_address="192.168.11.11",
            is_active=True,
        )
        db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()

        # Global entry should apply to any path/node
        assert manager._entry_applies(entry, "any_path", 123) is True
        assert manager._entry_applies(entry, None, None) is True

    def test_entry_applies_node_specific(self, app_context, db_session, sample_node):
        """Test _entry_applies for node-specific entry."""
        entry = IPBlacklist(
            ip_address="192.168.12.12",
            is_active=True,
            node_id=sample_node.id,
        )
        db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()

        # Should only apply to correct node
        assert manager._entry_applies(entry, None, sample_node.id) is True
        assert manager._entry_applies(entry, None, 9999) is False
        assert manager._entry_applies(entry, None, None) is False

    def test_entry_applies_path_pattern_wildcard(self, app_context, db_session):
        """Test _entry_applies for wildcard path pattern."""
        entry = IPBlacklist(
            ip_address="192.168.13.13",
            is_active=True,
            path_pattern="cam*",
        )
        db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()

        # Wildcard should match paths starting with "cam"
        assert manager._entry_applies(entry, "cam1", None) is True
        assert manager._entry_applies(entry, "camera", None) is True
        assert manager._entry_applies(entry, "other", None) is False

    def test_entry_applies_path_pattern_exact(self, app_context, db_session):
        """Test _entry_applies for exact path pattern."""
        entry = IPBlacklist(
            ip_address="192.168.14.14",
            is_active=True,
            path_pattern="exact_path",
        )
        db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()

        # Exact pattern should only match exact path
        assert manager._entry_applies(entry, "exact_path", None) is True
        assert manager._entry_applies(entry, "exact_path_extra", None) is False
        assert manager._entry_applies(entry, "other", None) is False

    def test_find_existing_block_found(
        self, app_context, db_session, sample_blacklist_entry
    ):
        """Test finding existing block."""
        manager = BlacklistManager()
        result = manager._find_existing_block(
            sample_blacklist_entry.ip_address, None, None
        )

        assert result is not None
        assert result.id == sample_blacklist_entry.id

    def test_find_existing_block_not_found(self, app_context, db_session):
        """Test finding non-existent block."""
        manager = BlacklistManager()
        result = manager._find_existing_block("10.20.30.40", None, None)

        assert result is None

    def test_find_existing_block_with_path(self, app_context, db_session):
        """Test finding block with specific path pattern."""
        entry = IPBlacklist(
            ip_address="192.168.15.15",
            is_active=True,
            path_pattern="specific_path",
        )
        db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()

        # Should find entry with matching path
        result = manager._find_existing_block("192.168.15.15", "specific_path", None)
        assert result is not None

        # Should not find entry with different path
        result = manager._find_existing_block("192.168.15.15", "other_path", None)
        assert result is None

    def test_find_existing_block_with_node(self, app_context, db_session, sample_node):
        """Test finding block with specific node."""
        entry = IPBlacklist(
            ip_address="192.168.16.16",
            is_active=True,
            node_id=sample_node.id,
        )
        db_session.add(entry)
        db_session.commit()

        manager = BlacklistManager()

        # Should find entry with matching node
        result = manager._find_existing_block("192.168.16.16", None, sample_node.id)
        assert result is not None

        # Should not find entry with different node
        result = manager._find_existing_block("192.168.16.16", None, 9999)
        assert result is None

    def test_update_block(self, app_context, db_session, sample_blacklist_entry):
        """Test updating an existing block."""
        manager = BlacklistManager()
        result = manager._update_block(
            sample_blacklist_entry,
            reason="New reason",
            blocked_by="new_admin",
            duration="24h",
        )

        assert result["success"] is True
        assert result["entry"]["reason"] == "New reason"
        assert result["entry"]["blocked_by"] == "new_admin"

    def test_update_block_to_permanent(
        self, app_context, db_session, sample_blacklist_entry
    ):
        """Test updating block to permanent."""
        manager = BlacklistManager()
        result = manager._update_block(
            sample_blacklist_entry,
            reason=None,
            blocked_by=None,
            duration="permanent",
        )

        assert result["success"] is True
        assert result["entry"]["is_permanent"] is True
        assert result["entry"]["expires_at"] is None
