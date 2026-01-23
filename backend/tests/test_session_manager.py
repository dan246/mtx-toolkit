"""
Tests for SessionManager service.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.session_manager import SessionManager


class TestSessionManager:
    """Tests for SessionManager service."""

    def test_init(self, app_context):
        """Test SessionManager initialization."""
        manager = SessionManager()
        assert manager.timeout == 10

    def test_get_all_sessions_no_nodes(self, app_context, db_session):
        """Test get_all_sessions when no nodes exist."""
        manager = SessionManager()
        result = manager.get_all_sessions()

        assert result["sessions"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["summary"]["total_viewers"] == 0

    def test_get_all_sessions_with_node(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test get_all_sessions with a node returning sessions."""

        # Only RTSP returns sessions, others return empty
        def mock_get_side_effect(url, **kwargs):
            mock_response = MagicMock()
            mock_response.status_code = 200
            if "rtspsessions" in url:
                mock_response.json.return_value = {
                    "items": [
                        {
                            "id": "session-1",
                            "created": "2024-01-15T10:00:00Z",
                            "remoteAddr": "192.168.1.100:54321",
                            "state": "read",
                            "path": "cam1",
                            "bytesReceived": 1024,
                            "bytesSent": 1048576,
                            "transport": "TCP",
                        }
                    ]
                }
            else:
                mock_response.json.return_value = {"items": []}
            return mock_response

        mock_httpx["get"].side_effect = mock_get_side_effect

        manager = SessionManager()
        result = manager.get_all_sessions()

        assert result["total"] == 1
        assert len(result["sessions"]) == 1
        assert result["sessions"][0]["client_ip"] == "192.168.1.100"
        assert result["sessions"][0]["client_port"] == 54321
        assert result["sessions"][0]["protocol"] == "rtsp"

    def test_get_all_sessions_filter_by_protocol(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test get_all_sessions with protocol filter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_httpx["get"].return_value = mock_response

        manager = SessionManager()
        result = manager.get_all_sessions(protocol="webrtc")

        # Should only call webrtc endpoint
        assert mock_httpx["get"].call_count == 1
        call_url = mock_httpx["get"].call_args[0][0]
        assert "webrtcsessions" in call_url

    def test_get_all_sessions_filter_by_node(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test get_all_sessions with node_id filter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_httpx["get"].return_value = mock_response

        manager = SessionManager()
        result = manager.get_all_sessions(node_id=sample_node.id)

        assert (
            result["errors"] is None
            or len(result["errors"]) == 0
            or all(
                e.get("error") == "HTTP 404" or "timeout" in e.get("error", "").lower()
                for e in (result["errors"] or [])
            )
        )

    def test_get_all_sessions_filter_by_path(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test get_all_sessions with path filter."""

        # Only RTSP returns sessions with path data
        def mock_get_side_effect(url, **kwargs):
            mock_response = MagicMock()
            mock_response.status_code = 200
            if "rtspsessions" in url:
                mock_response.json.return_value = {
                    "items": [
                        {
                            "id": "session-1",
                            "created": "2024-01-15T10:00:00Z",
                            "remoteAddr": "192.168.1.100:54321",
                            "state": "read",
                            "path": "cam1",
                            "bytesReceived": 0,
                            "bytesSent": 0,
                        },
                        {
                            "id": "session-2",
                            "created": "2024-01-15T10:00:00Z",
                            "remoteAddr": "192.168.1.101:54322",
                            "state": "read",
                            "path": "cam2",
                            "bytesReceived": 0,
                            "bytesSent": 0,
                        },
                    ]
                }
            else:
                mock_response.json.return_value = {"items": []}
            return mock_response

        mock_httpx["get"].side_effect = mock_get_side_effect

        manager = SessionManager()
        result = manager.get_all_sessions(path="cam1")

        assert result["total"] == 1
        assert result["sessions"][0]["path"] == "cam1"

    def test_get_all_sessions_viewers_only(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test get_all_sessions only returns viewers (state=read)."""

        # Only RTSP returns sessions with mixed states
        def mock_get_side_effect(url, **kwargs):
            mock_response = MagicMock()
            mock_response.status_code = 200
            if "rtspsessions" in url:
                mock_response.json.return_value = {
                    "items": [
                        {
                            "id": "session-1",
                            "created": "2024-01-15T10:00:00Z",
                            "remoteAddr": "192.168.1.100:54321",
                            "state": "read",
                            "path": "cam1",
                            "bytesReceived": 0,
                            "bytesSent": 0,
                        },
                        {
                            "id": "session-2",
                            "created": "2024-01-15T10:00:00Z",
                            "remoteAddr": "192.168.1.101:54322",
                            "state": "publish",
                            "path": "cam1",
                            "bytesReceived": 0,
                            "bytesSent": 0,
                        },
                    ]
                }
            else:
                mock_response.json.return_value = {"items": []}
            return mock_response

        mock_httpx["get"].side_effect = mock_get_side_effect

        manager = SessionManager()
        result = manager.get_all_sessions(viewers_only=True)

        assert result["total"] == 1
        assert result["sessions"][0]["state"] == "read"

    def test_get_all_sessions_pagination(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test get_all_sessions pagination."""

        # Only RTSP returns sessions for pagination test
        def mock_get_side_effect(url, **kwargs):
            mock_response = MagicMock()
            mock_response.status_code = 200
            if "rtspsessions" in url:
                mock_response.json.return_value = {
                    "items": [
                        {
                            "id": f"session-{i}",
                            "created": "2024-01-15T10:00:00Z",
                            "remoteAddr": f"192.168.1.{i}:54321",
                            "state": "read",
                            "path": "cam1",
                            "bytesReceived": 0,
                            "bytesSent": 0,
                        }
                        for i in range(5)
                    ]
                }
            else:
                mock_response.json.return_value = {"items": []}
            return mock_response

        mock_httpx["get"].side_effect = mock_get_side_effect

        manager = SessionManager()
        result = manager.get_all_sessions(page=1, per_page=2)

        assert result["total"] == 5
        assert len(result["sessions"]) == 2
        assert result["page"] == 1
        assert result["pages"] == 3

    def test_get_all_sessions_api_error(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test get_all_sessions handles API errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_httpx["get"].return_value = mock_response

        manager = SessionManager()
        result = manager.get_all_sessions()

        assert result["errors"] is not None
        assert any("HTTP 500" in e["error"] for e in result["errors"])

    def test_get_all_sessions_timeout(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test get_all_sessions handles timeout."""
        mock_httpx["get"].side_effect = httpx.TimeoutException("Timeout")

        manager = SessionManager()
        result = manager.get_all_sessions()

        assert result["errors"] is not None
        assert any("timeout" in e["error"].lower() for e in result["errors"])

    def test_get_all_sessions_connection_error(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test get_all_sessions handles connection errors."""
        mock_httpx["get"].side_effect = Exception("Connection refused")

        manager = SessionManager()
        result = manager.get_all_sessions()

        assert result["errors"] is not None
        assert any("Connection refused" in e["error"] for e in result["errors"])

    def test_get_node_sessions(self, app_context, db_session, sample_node, mock_httpx):
        """Test get_node_sessions."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_httpx["get"].return_value = mock_response

        manager = SessionManager()
        result = manager.get_node_sessions(sample_node.id)

        assert "sessions" in result
        assert "summary" in result

    def test_get_path_sessions(self, app_context, db_session, sample_node, mock_httpx):
        """Test get_path_sessions."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_httpx["get"].return_value = mock_response

        manager = SessionManager()
        result = manager.get_path_sessions(path="cam1")

        assert "sessions" in result
        assert "summary" in result

    def test_get_path_sessions_by_stream_id(
        self, app_context, db_session, sample_stream, mock_httpx
    ):
        """Test get_path_sessions with stream_id lookup."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_httpx["get"].return_value = mock_response

        manager = SessionManager()
        result = manager.get_path_sessions(path="", stream_id=sample_stream.id)

        assert "sessions" in result

    def test_get_sessions_summary(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test get_sessions_summary."""

        # Only RTSP returns sessions for summary test
        def mock_get_side_effect(url, **kwargs):
            mock_response = MagicMock()
            mock_response.status_code = 200
            if "rtspsessions" in url:
                mock_response.json.return_value = {
                    "items": [
                        {
                            "id": "session-1",
                            "created": "2024-01-15T10:00:00Z",
                            "remoteAddr": "192.168.1.100:54321",
                            "state": "read",
                            "path": "cam1",
                            "bytesReceived": 0,
                            "bytesSent": 0,
                        }
                    ]
                }
            else:
                mock_response.json.return_value = {"items": []}
            return mock_response

        mock_httpx["get"].side_effect = mock_get_side_effect

        manager = SessionManager()
        result = manager.get_sessions_summary()

        assert "summary" in result
        assert "total_viewers" in result
        assert result["total_viewers"] == 1

    def test_kick_session_success(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test successful session kick."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx["post"].return_value = mock_response

        manager = SessionManager()
        result = manager.kick_session(
            node_id=sample_node.id, session_id="session-123", protocol="rtsp"
        )

        assert result["success"] is True
        assert result["kicked"] is True
        assert "kicked successfully" in result["message"]

    def test_kick_session_failure(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test failed session kick."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_httpx["post"].return_value = mock_response

        manager = SessionManager()
        result = manager.kick_session(
            node_id=sample_node.id, session_id="session-123", protocol="rtsp"
        )

        assert result["success"] is False
        assert result["kicked"] is False

    def test_kick_session_node_not_found(self, app_context, db_session):
        """Test kick_session with invalid node_id."""
        manager = SessionManager()
        result = manager.kick_session(
            node_id=9999, session_id="session-123", protocol="rtsp"
        )

        assert result["success"] is False
        assert "Node not found" in result["error"]

    def test_kick_session_invalid_protocol(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test kick_session with invalid protocol."""
        manager = SessionManager()
        result = manager.kick_session(
            node_id=sample_node.id, session_id="session-123", protocol="invalid"
        )

        assert result["success"] is False
        assert "Invalid protocol" in result["error"]

    def test_kick_session_timeout(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test kick_session handles timeout."""
        mock_httpx["post"].side_effect = httpx.TimeoutException("Timeout")

        manager = SessionManager()
        result = manager.kick_session(
            node_id=sample_node.id, session_id="session-123", protocol="rtsp"
        )

        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    def test_kick_session_exception(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test kick_session handles exceptions."""
        mock_httpx["post"].side_effect = Exception("Connection error")

        manager = SessionManager()
        result = manager.kick_session(
            node_id=sample_node.id, session_id="session-123", protocol="rtsp"
        )

        assert result["success"] is False
        assert "Connection error" in result["error"]

    def test_normalize_session_ipv4(self, app_context):
        """Test _normalize_session with IPv4 address."""
        manager = SessionManager()

        class MockNode:
            id = 1
            name = "test-node"

        item = {
            "id": "session-1",
            "created": "2024-01-15T10:00:00Z",
            "remoteAddr": "192.168.1.100:54321",
            "state": "read",
            "path": "cam1",
            "bytesReceived": 1024,
            "bytesSent": 2048,
            "transport": "TCP",
        }

        result = manager._normalize_session(item, MockNode(), "rtsp")

        assert result["client_ip"] == "192.168.1.100"
        assert result["client_port"] == 54321
        assert result["protocol"] == "rtsp"

    def test_normalize_session_ipv6(self, app_context):
        """Test _normalize_session with IPv6 address."""
        manager = SessionManager()

        class MockNode:
            id = 1
            name = "test-node"

        item = {
            "id": "session-1",
            "created": "2024-01-15T10:00:00Z",
            "remoteAddr": "[::1]:54321",
            "state": "read",
            "path": "cam1",
            "bytesReceived": 0,
            "bytesSent": 0,
        }

        result = manager._normalize_session(item, MockNode(), "rtsp")

        assert result["client_ip"] == "::1"
        assert result["client_port"] == 54321

    def test_normalize_session_no_port(self, app_context):
        """Test _normalize_session with address without port."""
        manager = SessionManager()

        class MockNode:
            id = 1
            name = "test-node"

        item = {
            "id": "session-1",
            "created": "2024-01-15T10:00:00Z",
            "remoteAddr": "192.168.1.100",
            "state": "read",
            "path": "cam1",
            "bytesReceived": 0,
            "bytesSent": 0,
        }

        result = manager._normalize_session(item, MockNode(), "rtsp")

        assert result["client_ip"] == "192.168.1.100"
        assert result["client_port"] == 0

    def test_normalize_session_invalid_port(self, app_context):
        """Test _normalize_session with invalid port."""
        manager = SessionManager()

        class MockNode:
            id = 1
            name = "test-node"

        item = {
            "id": "session-1",
            "created": "2024-01-15T10:00:00Z",
            "remoteAddr": "192.168.1.100:invalid",
            "state": "read",
            "path": "cam1",
            "bytesReceived": 0,
            "bytesSent": 0,
        }

        result = manager._normalize_session(item, MockNode(), "rtsp")

        assert result["client_ip"] == "192.168.1.100"
        assert result["client_port"] == 0

    def test_normalize_session_exception(self, app_context):
        """Test _normalize_session handles exceptions."""
        manager = SessionManager()

        class MockNode:
            id = 1
            name = "test-node"

            @property
            def bad_property(self):
                raise Exception("Bad property")

        # Pass a value that would cause exception
        result = manager._normalize_session(None, MockNode(), "rtsp")

        assert result is None

    def test_calculate_summary(self, app_context):
        """Test _calculate_summary."""
        manager = SessionManager()

        sessions = [
            {"protocol": "rtsp", "node_name": "node1", "path": "cam1"},
            {"protocol": "rtsp", "node_name": "node1", "path": "cam2"},
            {"protocol": "webrtc", "node_name": "node2", "path": "cam1"},
        ]

        summary = manager._calculate_summary(sessions)

        assert summary["total_viewers"] == 3
        assert summary["by_protocol"]["rtsp"] == 2
        assert summary["by_protocol"]["webrtc"] == 1
        assert summary["by_node"]["node1"] == 2
        assert summary["by_node"]["node2"] == 1
        assert summary["by_path"]["cam1"] == 2
        assert summary["by_path"]["cam2"] == 1

    def test_fetch_node_sessions_404(
        self, app_context, db_session, sample_node, mock_httpx
    ):
        """Test _fetch_node_sessions with 404 (protocol not enabled)."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_httpx["get"].return_value = mock_response

        manager = SessionManager()
        sessions, errors = manager._fetch_node_sessions(sample_node, "rtsp")

        # 404 should not be treated as error (protocol not enabled)
        assert len(sessions) == 0
        assert len(errors) == 0
