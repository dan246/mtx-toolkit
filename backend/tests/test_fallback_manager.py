"""
Tests for FallbackManager service.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import EventType, FallbackType, Stream, StreamEvent, StreamStatus
from app.services.fallback_manager import FallbackManager


class TestActivateFallback:
    """Tests for FallbackManager.activate_fallback method."""

    @patch("app.services.fallback_manager.httpx.patch")
    def test_activate_color_bars(
        self,
        mock_patch,
        app_context,
        db_session,
        sample_stream_with_fallback,
    ):
        """Test activating color bars fallback."""
        stream = sample_stream_with_fallback
        stream.fallback_type = FallbackType.COLOR_BARS.value
        db_session.commit()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_patch.return_value = mock_response

        manager = FallbackManager()
        result = manager.activate_fallback(stream)

        assert result["success"] is True
        assert "color_bars" in result["message"]
        assert result["fallback_source"] is not None
        assert "testsrc2" in result["fallback_source"]

        db_session.refresh(stream)
        assert stream.fallback_active is True
        assert stream.fallback_activated_at is not None

        # Check event was created
        events = StreamEvent.query.filter_by(
            stream_id=stream.id,
            event_type=EventType.FALLBACK_ACTIVATED.value,
        ).all()
        assert len(events) == 1

    @patch("app.services.fallback_manager.httpx.patch")
    def test_activate_custom_image(
        self,
        mock_patch,
        app_context,
        db_session,
        sample_stream_with_fallback,
    ):
        """Test activating custom image fallback."""
        stream = sample_stream_with_fallback
        stream.fallback_type = FallbackType.CUSTOM_IMAGE.value
        stream.fallback_image_path = "/assets/custom.png"
        db_session.commit()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_patch.return_value = mock_response

        manager = FallbackManager()
        result = manager.activate_fallback(stream)

        assert result["success"] is True
        assert result["fallback_source"] is not None
        assert "/assets/custom.png" in result["fallback_source"]

    @patch("app.services.fallback_manager.httpx.patch")
    def test_activate_last_frame_fallback(
        self,
        mock_patch,
        app_context,
        db_session,
        sample_stream_with_fallback,
    ):
        """Test activating last frame fallback."""
        stream = sample_stream_with_fallback
        stream.fallback_type = FallbackType.LAST_FRAME.value
        db_session.commit()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_patch.return_value = mock_response

        # Mock thumbnail service
        with patch(
            "app.services.fallback_manager.FallbackManager._generate_last_frame_source"
        ) as mock_last_frame:
            mock_last_frame.return_value = "ffmpeg:loop=1:i=/tmp/thumb.jpg:rate=25"

            manager = FallbackManager()
            result = manager.activate_fallback(stream)

        assert result["success"] is True
        assert result["fallback_source"] is not None

    def test_activate_when_none_configured(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test activating fallback when none is configured."""
        stream = sample_stream_with_fallback
        stream.fallback_type = FallbackType.NONE.value
        db_session.commit()

        manager = FallbackManager()
        result = manager.activate_fallback(stream)

        assert result["success"] is False
        assert "No fallback configured" in result["message"]

    @patch("app.services.fallback_manager.httpx.patch")
    def test_activate_when_already_active(
        self,
        mock_patch,
        app_context,
        db_session,
        sample_stream_with_fallback,
    ):
        """Test activating fallback when already active."""
        stream = sample_stream_with_fallback
        stream.fallback_active = True
        stream.fallback_activated_at = datetime.utcnow()
        db_session.commit()

        manager = FallbackManager()
        result = manager.activate_fallback(stream)

        assert result["success"] is False
        assert "already active" in result["message"]

    @patch("app.services.fallback_manager.httpx.patch")
    def test_activate_patch_failure(
        self,
        mock_patch,
        app_context,
        db_session,
        sample_stream_with_fallback,
    ):
        """Test activating fallback when MediaMTX patch fails."""
        stream = sample_stream_with_fallback
        stream.fallback_type = FallbackType.COLOR_BARS.value
        db_session.commit()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_patch.return_value = mock_response

        manager = FallbackManager()
        result = manager.activate_fallback(stream)

        assert result["success"] is False
        assert "Failed to patch" in result["message"]

    @patch("app.services.fallback_manager.httpx.patch")
    def test_activate_exception_handling(
        self,
        mock_patch,
        app_context,
        db_session,
        sample_stream_with_fallback,
    ):
        """Test activating fallback handles exceptions."""
        stream = sample_stream_with_fallback
        stream.fallback_type = FallbackType.COLOR_BARS.value
        db_session.commit()

        mock_patch.side_effect = Exception("Connection refused")

        manager = FallbackManager()
        result = manager.activate_fallback(stream)

        assert result["success"] is False
        assert "failed" in result["message"].lower()


class TestDeactivateFallback:
    """Tests for FallbackManager.deactivate_fallback method."""

    @patch("app.services.fallback_manager.httpx.patch")
    def test_deactivate_restores_source(
        self,
        mock_patch,
        app_context,
        db_session,
        sample_stream_with_fallback,
    ):
        """Test deactivating fallback restores the original source."""
        stream = sample_stream_with_fallback
        stream.fallback_active = True
        stream.fallback_activated_at = datetime.utcnow()
        db_session.commit()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_patch.return_value = mock_response

        manager = FallbackManager()
        result = manager.deactivate_fallback(stream)

        assert result["success"] is True
        assert "source restored" in result["message"]

        db_session.refresh(stream)
        assert stream.fallback_active is False
        assert stream.fallback_activated_at is None

        # Check the patch was called with original source
        call_args = mock_patch.call_args
        assert call_args is not None
        json_payload = (
            call_args[1].get("json") or call_args[0][1]
            if len(call_args[0]) > 1
            else call_args[1].get("json")
        )
        assert json_payload["source"] == stream.source_url

        # Check event was created
        events = StreamEvent.query.filter_by(
            stream_id=stream.id,
            event_type=EventType.FALLBACK_DEACTIVATED.value,
        ).all()
        assert len(events) == 1

    def test_deactivate_when_not_active(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test deactivating fallback when not active."""
        stream = sample_stream_with_fallback
        stream.fallback_active = False
        db_session.commit()

        manager = FallbackManager()
        result = manager.deactivate_fallback(stream)

        assert result["success"] is False
        assert "No fallback is active" in result["message"]

    @patch("app.services.fallback_manager.httpx.patch")
    def test_deactivate_patch_failure(
        self,
        mock_patch,
        app_context,
        db_session,
        sample_stream_with_fallback,
    ):
        """Test deactivating fallback when MediaMTX patch fails."""
        stream = sample_stream_with_fallback
        stream.fallback_active = True
        stream.fallback_activated_at = datetime.utcnow()
        db_session.commit()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_patch.return_value = mock_response

        manager = FallbackManager()
        result = manager.deactivate_fallback(stream)

        assert result["success"] is False
        assert "Failed to restore source" in result["message"]


class TestConfigureFallback:
    """Tests for FallbackManager.configure_fallback method."""

    def test_configure_fallback(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test configuring fallback type for a stream."""
        manager = FallbackManager()
        result = manager.configure_fallback(
            sample_stream_with_fallback.id,
            FallbackType.CUSTOM_IMAGE.value,
            image_path="/assets/custom.png",
        )

        assert result["success"] is True
        assert result["fallback_type"] == FallbackType.CUSTOM_IMAGE.value

        db_session.refresh(sample_stream_with_fallback)
        assert (
            sample_stream_with_fallback.fallback_type == FallbackType.CUSTOM_IMAGE.value
        )
        assert sample_stream_with_fallback.fallback_image_path == "/assets/custom.png"

    def test_configure_fallback_stream_not_found(self, app_context, db_session):
        """Test configuring fallback for non-existent stream."""
        manager = FallbackManager()
        result = manager.configure_fallback(99999, FallbackType.COLOR_BARS.value)

        assert result["success"] is False
        assert "Stream not found" in result["message"]

    def test_configure_fallback_invalid_type(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test configuring fallback with invalid type."""
        manager = FallbackManager()
        result = manager.configure_fallback(
            sample_stream_with_fallback.id, "invalid_type"
        )

        assert result["success"] is False
        assert "Invalid fallback type" in result["message"]

    def test_configure_fallback_to_none(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test configuring fallback to none (disable)."""
        manager = FallbackManager()
        result = manager.configure_fallback(
            sample_stream_with_fallback.id, FallbackType.NONE.value
        )

        assert result["success"] is True
        assert result["fallback_type"] == FallbackType.NONE.value


class TestGetFallbackStatus:
    """Tests for FallbackManager.get_fallback_status method."""

    def test_get_fallback_status(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test getting fallback status for a stream."""
        manager = FallbackManager()
        status = manager.get_fallback_status(sample_stream_with_fallback.id)

        assert status is not None
        assert status["stream_id"] == sample_stream_with_fallback.id
        assert status["fallback_type"] == FallbackType.COLOR_BARS.value
        assert status["fallback_active"] is False
        assert status["fallback_activated_at"] is None

    def test_get_fallback_status_active(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test getting fallback status when active."""
        stream = sample_stream_with_fallback
        stream.fallback_active = True
        stream.fallback_activated_at = datetime.utcnow()
        db_session.commit()

        manager = FallbackManager()
        status = manager.get_fallback_status(stream.id)

        assert status["fallback_active"] is True
        assert status["fallback_activated_at"] is not None

    def test_get_fallback_status_not_found(self, app_context, db_session):
        """Test getting fallback status for non-existent stream."""
        manager = FallbackManager()
        status = manager.get_fallback_status(99999)

        assert status is None


class TestGenerateSources:
    """Tests for fallback source generation methods."""

    def test_generate_color_bars_source(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test color bars source URL generation."""
        manager = FallbackManager()
        params = {"width": 1920, "height": 1080, "fps": 30}
        source = manager._generate_color_bars_source(
            sample_stream_with_fallback, params
        )

        assert source is not None
        assert "testsrc2" in source
        assert "1920x1080" in source
        assert "rate=30" in source

    def test_generate_image_source_with_path(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test image source URL generation with custom path."""
        stream = sample_stream_with_fallback
        stream.fallback_image_path = "/custom/image.png"
        db_session.commit()

        manager = FallbackManager()
        params = {"fps": 25}
        source = manager._generate_image_source(stream, params)

        assert source is not None
        assert "/custom/image.png" in source
        assert "loop=1" in source

    def test_generate_image_source_default(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test image source URL generation with default path."""
        stream = sample_stream_with_fallback
        stream.fallback_image_path = None
        db_session.commit()

        manager = FallbackManager()
        params = {"fps": 25}
        source = manager._generate_image_source(stream, params)

        assert source is not None
        assert "fallback.png" in source

    def test_get_stream_params_defaults(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test _get_stream_params returns defaults."""
        manager = FallbackManager()
        params = manager._get_stream_params(
            sample_stream_with_fallback, "http://localhost:9998"
        )

        assert params["width"] == 1920
        assert params["height"] == 1080
        assert params["fps"] == 25
        assert params["codec"] == "libx264"

    def test_get_stream_params_with_fps(
        self, app_context, db_session, sample_stream_with_fallback
    ):
        """Test _get_stream_params uses stream FPS when available."""
        stream = sample_stream_with_fallback
        stream.fps = 60.0
        db_session.commit()

        manager = FallbackManager()
        params = manager._get_stream_params(stream, "http://localhost:9998")

        assert params["fps"] == 60
