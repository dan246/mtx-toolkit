"""
Tests for Sessions API endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestSessionsAPI:
    """Tests for Sessions API endpoints."""

    def test_list_sessions(self, client, app_context, db_session, sample_node):
        """Test listing all sessions."""
        with patch("app.services.session_manager.SessionManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_all_sessions.return_value = {
                "sessions": [
                    {
                        "id": "session-1",
                        "client_ip": "192.168.1.100",
                        "protocol": "rtsp",
                        "path": "cam1",
                        "state": "read",
                    }
                ],
                "summary": {"total_viewers": 1, "by_protocol": {"rtsp": 1}},
                "total": 1,
                "page": 1,
                "pages": 1,
                "errors": None,
            }
            mock_manager_class.return_value = mock_manager

            response = client.get("/api/sessions/")
            assert response.status_code == 200

            data = response.get_json()
            assert data["total"] == 1
            assert len(data["sessions"]) == 1

    def test_list_sessions_with_filters(
        self, client, app_context, db_session, sample_node
    ):
        """Test listing sessions with filters."""
        with patch("app.services.session_manager.SessionManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_all_sessions.return_value = {
                "sessions": [],
                "summary": {"total_viewers": 0},
                "total": 0,
                "page": 1,
                "pages": 1,
                "errors": None,
            }
            mock_manager_class.return_value = mock_manager

            response = client.get(
                "/api/sessions/?node_id=1&protocol=rtsp&path=cam1&page=2&per_page=25"
            )
            assert response.status_code == 200

            mock_manager.get_all_sessions.assert_called_once_with(
                node_id=1,
                protocol="rtsp",
                path="cam1",
                page=2,
                per_page=25,
            )

    def test_list_sessions_invalid_protocol(self, client, app_context):
        """Test listing sessions with invalid protocol."""
        response = client.get("/api/sessions/?protocol=invalid")
        assert response.status_code == 400

        data = response.get_json()
        assert "Invalid protocol" in data["error"]

    def test_get_summary(self, client, app_context, db_session, sample_node):
        """Test getting sessions summary."""
        with patch("app.services.session_manager.SessionManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_sessions_summary.return_value = {
                "summary": {
                    "total_viewers": 10,
                    "by_protocol": {"rtsp": 8, "webrtc": 2},
                    "by_node": {"node1": 10},
                },
                "total_viewers": 10,
                "errors": None,
            }
            mock_manager_class.return_value = mock_manager

            response = client.get("/api/sessions/summary")
            assert response.status_code == 200

            data = response.get_json()
            assert data["total_viewers"] == 10

    def test_get_node_sessions(self, client, app_context, db_session, sample_node):
        """Test getting sessions for a specific node."""
        with patch("app.services.session_manager.SessionManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_all_sessions.return_value = {
                "sessions": [],
                "summary": {"total_viewers": 0},
                "total": 0,
                "page": 1,
                "pages": 1,
                "errors": None,
            }
            mock_manager_class.return_value = mock_manager

            response = client.get(f"/api/sessions/node/{sample_node.id}")
            assert response.status_code == 200

    def test_get_stream_sessions(self, client, app_context, db_session, sample_stream):
        """Test getting sessions for a specific stream."""
        with patch("app.services.session_manager.SessionManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_path_sessions.return_value = {
                "sessions": [],
                "summary": {"total_viewers": 0},
            }
            mock_manager_class.return_value = mock_manager

            response = client.get(f"/api/sessions/stream/{sample_stream.id}")
            assert response.status_code == 200

            data = response.get_json()
            assert "sessions" in data
            assert "total" in data

    def test_get_path_viewers(self, client, app_context, db_session, sample_node):
        """Test getting viewers for a specific path."""
        with patch("app.services.session_manager.SessionManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_all_sessions.return_value = {
                "sessions": [],
                "summary": {"total_viewers": 0},
                "total": 0,
                "page": 1,
                "pages": 1,
                "errors": None,
            }
            mock_manager_class.return_value = mock_manager

            response = client.get("/api/sessions/path/cam1")
            assert response.status_code == 200

    def test_kick_session_success(self, client, app_context, db_session, sample_node):
        """Test kicking a session successfully."""
        with patch("app.services.session_manager.SessionManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.kick_session.return_value = {
                "success": True,
                "kicked": True,
                "message": "Session kicked successfully",
            }
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/sessions/kick",
                json={
                    "node_id": sample_node.id,
                    "session_id": "session-123",
                    "protocol": "rtsp",
                },
            )
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is True

    def test_kick_session_missing_fields(self, client, app_context):
        """Test kicking session with missing fields."""
        response = client.post(
            "/api/sessions/kick",
            json={
                "node_id": 1,
                # Missing session_id and protocol
            },
        )
        assert response.status_code == 400

        data = response.get_json()
        assert data["success"] is False
        assert "Missing required fields" in data["error"]

    def test_kick_session_failure(self, client, app_context, db_session, sample_node):
        """Test kicking session that fails."""
        with patch("app.services.session_manager.SessionManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.kick_session.return_value = {
                "success": False,
                "error": "Session not found",
            }
            mock_manager_class.return_value = mock_manager

            response = client.post(
                "/api/sessions/kick",
                json={
                    "node_id": sample_node.id,
                    "session_id": "non-existent",
                    "protocol": "rtsp",
                },
            )
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is False
