"""
Tests for Blacklist API endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestBlacklistAPI:
    """Tests for Blacklist API endpoints."""

    def test_list_blocked_ips(self, client, app_context, db_session):
        """Test listing blocked IPs."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.list_blocked_ips.return_value = {
                "entries": [
                    {
                        "id": 1,
                        "ip_address": "192.168.1.100",
                        "reason": "Test",
                        "is_permanent": False,
                    }
                ],
                "total": 1,
                "page": 1,
                "pages": 1,
            }
            mock_manager_class.return_value = mock_manager

            response = client.get("/api/blacklist/")
            assert response.status_code == 200

            data = response.get_json()
            assert data["total"] == 1
            assert len(data["entries"]) == 1

    def test_list_blocked_ips_with_pagination(self, client, app_context):
        """Test listing blocked IPs with pagination."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.list_blocked_ips.return_value = {
                "entries": [],
                "total": 0,
                "page": 2,
                "pages": 1,
            }
            mock_manager_class.return_value = mock_manager

            response = client.get("/api/blacklist/?page=2&per_page=25")
            assert response.status_code == 200

            mock_manager.list_blocked_ips.assert_called_once_with(page=2, per_page=25)

    def test_get_stats(self, client, app_context):
        """Test getting blacklist stats."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_block_stats.return_value = {
                "total_blocked": 10,
                "permanent": 3,
                "temporary": 7,
            }
            mock_manager_class.return_value = mock_manager

            response = client.get("/api/blacklist/stats")
            assert response.status_code == 200

            data = response.get_json()
            assert data["total_blocked"] == 10
            assert data["permanent"] == 3
            assert data["temporary"] == 7

    def test_block_ip(self, client, app_context):
        """Test blocking an IP."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.block_ip.return_value = {
                "success": True,
                "message": "IP blocked successfully",
                "entry": {
                    "id": 1,
                    "ip_address": "10.0.0.1",
                    "reason": "Test block",
                },
            }
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/blacklist/block",
                json={
                    "ip_address": "10.0.0.1",
                    "reason": "Test block",
                    "duration": "1h",
                },
            )
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is True

    def test_block_ip_missing_address(self, client, app_context):
        """Test blocking without IP address."""
        response = client.post(
            "/api/blacklist/block",
            json={
                "reason": "Test block",
            },
        )
        assert response.status_code == 400

        data = response.get_json()
        assert data["success"] is False
        assert "ip_address is required" in data["error"]

    def test_block_ip_with_all_options(
        self, client, app_context, db_session, sample_node
    ):
        """Test blocking IP with all options."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.block_ip.return_value = {
                "success": True,
                "message": "IP blocked successfully",
                "entry": {"id": 1},
            }
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/blacklist/block",
                json={
                    "ip_address": "10.0.0.2",
                    "reason": "Full options test",
                    "blocked_by": "admin",
                    "duration": "24h",
                    "path_pattern": "cam/*",
                    "node_id": sample_node.id,
                },
            )
            assert response.status_code == 200

            mock_manager.block_ip.assert_called_once_with(
                ip_address="10.0.0.2",
                reason="Full options test",
                blocked_by="admin",
                duration="24h",
                path_pattern="cam/*",
                node_id=sample_node.id,
            )

    def test_unblock_by_id(self, client, app_context):
        """Test unblocking by entry ID."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.unblock_ip.return_value = {
                "success": True,
                "message": "IP unblocked successfully",
            }
            mock_manager_class.return_value = mock_manager

            response = client.post("/api/blacklist/unblock/1")
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is True

    def test_unblock_by_id_not_found(self, client, app_context):
        """Test unblocking non-existent entry."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.unblock_ip.return_value = {
                "success": False,
                "error": "Entry not found",
            }
            mock_manager_class.return_value = mock_manager

            response = client.post("/api/blacklist/unblock/99999")
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is False

    def test_unblock_by_ip(self, client, app_context):
        """Test unblocking by IP address."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.unblock_ip_by_address.return_value = {
                "success": True,
                "message": "Unblocked 1 entries",
                "count": 1,
            }
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/blacklist/unblock",
                json={
                    "ip_address": "192.168.1.100",
                },
            )
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is True
            assert data["count"] == 1

    def test_unblock_by_ip_missing_address(self, client, app_context):
        """Test unblocking without IP address."""
        response = client.post(
            "/api/blacklist/unblock",
            json={},
        )
        assert response.status_code == 400

        data = response.get_json()
        assert data["success"] is False
        assert "ip_address is required" in data["error"]

    def test_unblock_by_ip_with_filters(
        self, client, app_context, db_session, sample_node
    ):
        """Test unblocking with path and node filters."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.unblock_ip_by_address.return_value = {
                "success": True,
                "count": 1,
            }
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/blacklist/unblock",
                json={
                    "ip_address": "192.168.1.100",
                    "path_pattern": "cam1",
                    "node_id": sample_node.id,
                },
            )
            assert response.status_code == 200

            mock_manager.unblock_ip_by_address.assert_called_once_with(
                ip_address="192.168.1.100",
                path_pattern="cam1",
                node_id=sample_node.id,
            )

    def test_check_ip(self, client, app_context):
        """Test checking if IP is blocked."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.is_ip_blocked.return_value = {
                "blocked": True,
                "entry": {
                    "id": 1,
                    "ip_address": "192.168.1.100",
                    "reason": "Test",
                },
            }
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/blacklist/check",
                json={
                    "ip_address": "192.168.1.100",
                },
            )
            assert response.status_code == 200

            data = response.get_json()
            assert data["blocked"] is True

    def test_check_ip_not_blocked(self, client, app_context):
        """Test checking IP that is not blocked."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.is_ip_blocked.return_value = {
                "blocked": False,
            }
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/blacklist/check",
                json={
                    "ip_address": "10.10.10.10",
                },
            )
            assert response.status_code == 200

            data = response.get_json()
            assert data["blocked"] is False

    def test_check_ip_missing_address(self, client, app_context):
        """Test checking without IP address."""
        response = client.post(
            "/api/blacklist/check",
            json={},
        )
        assert response.status_code == 400

        data = response.get_json()
        assert data["success"] is False
        assert "ip_address is required" in data["error"]

    def test_check_ip_with_path_and_node(
        self, client, app_context, db_session, sample_node
    ):
        """Test checking IP with path and node context."""
        with patch(
            "app.services.blacklist_manager.BlacklistManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.is_ip_blocked.return_value = {"blocked": False}
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/blacklist/check",
                json={
                    "ip_address": "192.168.1.100",
                    "path": "cam1",
                    "node_id": sample_node.id,
                },
            )
            assert response.status_code == 200

            mock_manager.is_ip_blocked.assert_called_once_with(
                ip_address="192.168.1.100",
                path="cam1",
                node_id=sample_node.id,
            )
