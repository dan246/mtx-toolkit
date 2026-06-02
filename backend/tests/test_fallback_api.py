"""
Tests for Fallback API endpoints.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import FallbackType, Stream, StreamStatus


class TestFallbackAPI:
    """Tests for /api/fallback endpoints."""

    def test_get_fallback_config(
        self, client, app_context, db_session, sample_stream_with_fallback
    ):
        """Test getting fallback configuration for a stream."""
        stream_id = sample_stream_with_fallback.id
        response = client.get(f"/api/fallback/streams/{stream_id}")
        assert response.status_code == 200

        data = response.get_json()
        assert data["stream_id"] == stream_id
        assert data["fallback_type"] == FallbackType.COLOR_BARS.value
        assert data["fallback_active"] is False

    def test_get_fallback_config_not_found(self, client, app_context, db_session):
        """Test getting fallback config for non-existent stream."""
        response = client.get("/api/fallback/streams/99999")
        assert response.status_code == 404

        data = response.get_json()
        assert "error" in data

    def test_configure_fallback(
        self, client, app_context, db_session, sample_stream_with_fallback
    ):
        """Test configuring fallback type via PUT."""
        stream_id = sample_stream_with_fallback.id
        response = client.put(
            f"/api/fallback/streams/{stream_id}",
            json={
                "fallback_type": FallbackType.CUSTOM_IMAGE.value,
                "image_path": "/assets/custom.png",
            },
        )
        assert response.status_code == 200

        data = response.get_json()
        assert data["success"] is True
        assert data["fallback_type"] == FallbackType.CUSTOM_IMAGE.value

    def test_configure_fallback_missing_type(
        self, client, app_context, db_session, sample_stream_with_fallback
    ):
        """Test configuring fallback without specifying type."""
        stream_id = sample_stream_with_fallback.id
        response = client.put(
            f"/api/fallback/streams/{stream_id}",
            json={},
        )
        assert response.status_code == 400

        data = response.get_json()
        assert "error" in data
        assert "fallback_type is required" in data["error"]

    def test_configure_fallback_invalid_type(
        self, client, app_context, db_session, sample_stream_with_fallback
    ):
        """Test configuring fallback with invalid type."""
        stream_id = sample_stream_with_fallback.id
        response = client.put(
            f"/api/fallback/streams/{stream_id}",
            json={"fallback_type": "invalid_type"},
        )
        assert response.status_code == 400

        data = response.get_json()
        assert data["success"] is False

    def test_configure_fallback_stream_not_found(self, client, app_context, db_session):
        """Test configuring fallback for non-existent stream."""
        response = client.put(
            "/api/fallback/streams/99999",
            json={"fallback_type": FallbackType.COLOR_BARS.value},
        )
        assert response.status_code == 400

        data = response.get_json()
        assert data["success"] is False

    def test_activate_fallback(
        self, client, app_context, db_session, sample_stream_with_fallback
    ):
        """Test activating fallback for a stream."""
        stream_id = sample_stream_with_fallback.id

        with patch("app.api.fallback.FallbackManager") as MockManager:
            mock_instance = MagicMock()
            mock_instance.activate_fallback.return_value = {
                "success": True,
                "message": "Fallback (color_bars) activated",
                "fallback_source": "ffmpeg:testsrc2=size=1920x1080:rate=25",
            }
            MockManager.return_value = mock_instance

            response = client.post(f"/api/fallback/streams/{stream_id}/activate")
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is True
            assert "activated" in data["message"]

    def test_activate_fallback_not_configured(
        self, client, app_context, db_session, sample_stream_with_fallback
    ):
        """Test activating fallback when none configured."""
        stream = sample_stream_with_fallback
        stream.fallback_type = FallbackType.NONE.value
        db_session.commit()

        with patch("app.api.fallback.FallbackManager") as MockManager:
            mock_instance = MagicMock()
            mock_instance.activate_fallback.return_value = {
                "success": False,
                "message": "No fallback configured",
            }
            MockManager.return_value = mock_instance

            response = client.post(f"/api/fallback/streams/{stream.id}/activate")
            assert response.status_code == 400

            data = response.get_json()
            assert data["success"] is False

    def test_activate_fallback_stream_not_found(self, client, app_context, db_session):
        """Test activating fallback for non-existent stream."""
        response = client.post("/api/fallback/streams/99999/activate")
        assert response.status_code == 404

    def test_deactivate_fallback(
        self, client, app_context, db_session, sample_stream_with_fallback
    ):
        """Test deactivating fallback for a stream."""
        stream = sample_stream_with_fallback
        stream.fallback_active = True
        stream.fallback_activated_at = datetime.utcnow()
        db_session.commit()

        with patch("app.api.fallback.FallbackManager") as MockManager:
            mock_instance = MagicMock()
            mock_instance.deactivate_fallback.return_value = {
                "success": True,
                "message": "Fallback deactivated, source restored",
            }
            MockManager.return_value = mock_instance

            response = client.post(f"/api/fallback/streams/{stream.id}/deactivate")
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is True
            assert "deactivated" in data["message"]

    def test_deactivate_fallback_not_active(
        self, client, app_context, db_session, sample_stream_with_fallback
    ):
        """Test deactivating fallback when not active."""
        stream = sample_stream_with_fallback

        with patch("app.api.fallback.FallbackManager") as MockManager:
            mock_instance = MagicMock()
            mock_instance.deactivate_fallback.return_value = {
                "success": False,
                "message": "No fallback is active",
            }
            MockManager.return_value = mock_instance

            response = client.post(f"/api/fallback/streams/{stream.id}/deactivate")
            assert response.status_code == 400

            data = response.get_json()
            assert data["success"] is False

    def test_deactivate_fallback_stream_not_found(
        self, client, app_context, db_session
    ):
        """Test deactivating fallback for non-existent stream."""
        response = client.post("/api/fallback/streams/99999/deactivate")
        assert response.status_code == 404

    def test_list_active_fallbacks_empty(self, client, app_context, db_session):
        """Test listing active fallbacks when none active."""
        response = client.get("/api/fallback/active")
        assert response.status_code == 200

        data = response.get_json()
        assert data["streams"] == []
        assert data["total"] == 0

    def test_list_active_fallbacks(
        self, client, app_context, db_session, sample_stream_with_fallback
    ):
        """Test listing active fallbacks."""
        stream = sample_stream_with_fallback
        stream.fallback_active = True
        stream.fallback_activated_at = datetime.utcnow()
        db_session.commit()

        response = client.get("/api/fallback/active")
        assert response.status_code == 200

        data = response.get_json()
        assert data["total"] >= 1
        assert len(data["streams"]) >= 1

        active = data["streams"][0]
        assert active["id"] == stream.id
        assert active["fallback_type"] == stream.fallback_type
        assert active["fallback_activated_at"] is not None

    def test_list_active_fallbacks_multiple(
        self, client, app_context, db_session, sample_node
    ):
        """Test listing multiple active fallbacks."""
        for i in range(3):
            stream = Stream(
                node_id=sample_node.id,
                path=f"test/fallback_{i}",
                name=f"Fallback Stream {i}",
                source_url=f"rtsp://192.168.1.100:554/fb{i}",
                protocol="rtsp",
                status=StreamStatus.HEALTHY.value,
                fallback_type=FallbackType.COLOR_BARS.value,
                fallback_active=True,
                fallback_activated_at=datetime.utcnow(),
            )
            db_session.add(stream)
        db_session.commit()

        response = client.get("/api/fallback/active")
        assert response.status_code == 200

        data = response.get_json()
        assert data["total"] >= 3
