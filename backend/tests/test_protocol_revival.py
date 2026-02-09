"""
Tests for Protocol-Aware Path Revival Service.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import EventType, SourceProtocol, Stream, StreamEvent, StreamStatus
from app.services.protocol_revival import (
    HLSRevivalStrategy,
    ProtocolRevivalManager,
    RevivalResult,
    RTMPRevivalStrategy,
    RTSPRevivalStrategy,
    WebRTCRevivalStrategy,
)


class TestRevivalResult:
    """Tests for RevivalResult data class."""

    def test_revival_result_success(self):
        """Test RevivalResult with success."""
        result = RevivalResult(
            success=True,
            protocol="rtsp",
            message="Kicked 1 session",
            details={"kicked_sessions": 1},
        )
        assert result.success is True
        assert result.protocol == "rtsp"
        assert result.message == "Kicked 1 session"
        assert result.details == {"kicked_sessions": 1}

    def test_revival_result_to_dict(self):
        """Test RevivalResult.to_dict method."""
        result = RevivalResult(success=False, protocol="rtmp", message="Failed")
        d = result.to_dict()
        assert d["success"] is False
        assert d["protocol"] == "rtmp"
        assert d["message"] == "Failed"
        assert "timestamp" in d


class TestDetectSourceType:
    """Tests for protocol detection in strategies."""

    def test_detect_rtsp_source(self, app_context):
        """Test RTSP strategy detects rtspSource type."""
        strategy = RTSPRevivalStrategy()
        path_data = {"source": {"type": "rtspSource", "id": "rtsp://cam/stream"}}
        assert strategy.detect_source_type(path_data) is True

    def test_detect_rtsp_source_negative(self, app_context):
        """Test RTSP strategy does not match non-RTSP sources."""
        strategy = RTSPRevivalStrategy()
        path_data = {"source": {"type": "rtmpConn", "id": "something"}}
        assert strategy.detect_source_type(path_data) is False

    def test_detect_rtmp_source(self, app_context):
        """Test RTMP strategy detects rtmpConn type."""
        strategy = RTMPRevivalStrategy()
        path_data = {"source": {"type": "rtmpConn", "id": "something"}}
        assert strategy.detect_source_type(path_data) is True

    def test_detect_rtmp_source_negative(self, app_context):
        """Test RTMP strategy does not match non-RTMP sources."""
        strategy = RTMPRevivalStrategy()
        path_data = {"source": {"type": "rtspSource", "id": "something"}}
        assert strategy.detect_source_type(path_data) is False

    def test_detect_webrtc_source(self, app_context):
        """Test WebRTC strategy detects webrtcSession type."""
        strategy = WebRTCRevivalStrategy()
        path_data = {"source": {"type": "webrtcSession"}}
        assert strategy.detect_source_type(path_data) is True

    def test_detect_webrtc_source_whip(self, app_context):
        """Test WebRTC strategy detects whipSource type."""
        strategy = WebRTCRevivalStrategy()
        path_data = {"source": {"type": "whipSource"}}
        assert strategy.detect_source_type(path_data) is True

    def test_detect_webrtc_source_whep(self, app_context):
        """Test WebRTC strategy detects whepSource type."""
        strategy = WebRTCRevivalStrategy()
        path_data = {"source": {"type": "whepSource"}}
        assert strategy.detect_source_type(path_data) is True

    def test_detect_webrtc_source_negative(self, app_context):
        """Test WebRTC strategy does not match non-WebRTC sources."""
        strategy = WebRTCRevivalStrategy()
        path_data = {"source": {"type": "rtspSource"}}
        assert strategy.detect_source_type(path_data) is False

    def test_detect_hls_source(self, app_context):
        """Test HLS strategy detects hlsSource type."""
        strategy = HLSRevivalStrategy()
        path_data = {"source": {"type": "hlsSource"}}
        assert strategy.detect_source_type(path_data) is True

    def test_detect_no_source(self, app_context):
        """Test strategies handle missing source gracefully."""
        strategy = RTSPRevivalStrategy()
        assert strategy.detect_source_type({"source": None}) is False
        assert strategy.detect_source_type({}) is False


class TestRTSPRevival:
    """Tests for RTSP revival strategy."""

    @patch("app.services.protocol_revival.httpx.get")
    @patch("app.services.protocol_revival.httpx.post")
    @patch("app.services.protocol_revival.time.sleep")
    def test_rtsp_revival_kicks_sessions(
        self, mock_sleep, mock_post, mock_get, app_context, db_session, sample_stream
    ):
        """Test RTSP revival kicks matching sessions."""
        # Mock session list response
        session_list_response = MagicMock()
        session_list_response.status_code = 200
        session_list_response.json.return_value = {
            "items": [
                {"id": "session-1", "path": sample_stream.path},
                {"id": "session-2", "path": "other/path"},
            ]
        }
        mock_get.return_value = session_list_response

        # Mock kick response
        kick_response = MagicMock()
        kick_response.status_code = 200
        mock_post.return_value = kick_response

        strategy = RTSPRevivalStrategy()
        result = strategy.revive(sample_stream, "http://localhost:9998")

        assert result.success is True
        assert result.protocol == "rtsp"
        assert "Kicked" in result.message
        mock_post.assert_called()

    @patch("app.services.protocol_revival.httpx.get")
    def test_rtsp_revival_no_sessions(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test RTSP revival when no sessions found."""
        session_list_response = MagicMock()
        session_list_response.status_code = 200
        session_list_response.json.return_value = {"items": []}
        mock_get.return_value = session_list_response

        strategy = RTSPRevivalStrategy()
        result = strategy.revive(sample_stream, "http://localhost:9998")

        assert result.success is False
        assert "No RTSP sessions found" in result.message

    @patch("app.services.protocol_revival.httpx.get")
    def test_rtsp_revival_api_error(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test RTSP revival handles API errors gracefully."""
        mock_get.side_effect = Exception("Connection refused")

        strategy = RTSPRevivalStrategy()
        result = strategy.revive(sample_stream, "http://localhost:9998")

        assert result.success is False
        # The exception is caught per-session-type, so final message reflects
        # no sessions found rather than a crash
        assert result.protocol == "rtsp"


class TestRTMPRevival:
    """Tests for RTMP revival strategy."""

    @patch("app.services.protocol_revival.httpx.post")
    @patch("app.services.protocol_revival.httpx.delete")
    @patch("app.services.protocol_revival.httpx.get")
    @patch("app.services.protocol_revival.time.sleep")
    def test_rtmp_revival_resets_config(
        self,
        mock_sleep,
        mock_get,
        mock_delete,
        mock_post,
        app_context,
        db_session,
        sample_stream,
    ):
        """Test RTMP revival deletes and re-adds path config."""
        # Mock get config
        config_response = MagicMock()
        config_response.status_code = 200
        config_response.json.return_value = {
            "source": "rtmp://source/live",
            "sourceOnDemand": False,
        }
        mock_get.return_value = config_response

        # Mock delete
        delete_response = MagicMock()
        delete_response.status_code = 200
        mock_delete.return_value = delete_response

        # Mock re-add
        add_response = MagicMock()
        add_response.status_code = 200
        mock_post.return_value = add_response

        strategy = RTMPRevivalStrategy()
        result = strategy.revive(sample_stream, "http://localhost:9998")

        assert result.success is True
        assert result.protocol == "rtmp"
        assert "reset successfully" in result.message

        mock_get.assert_called_once()
        mock_delete.assert_called_once()
        mock_post.assert_called_once()

    @patch("app.services.protocol_revival.httpx.get")
    def test_rtmp_revival_config_fetch_failure(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test RTMP revival handles config fetch failure."""
        config_response = MagicMock()
        config_response.status_code = 404
        mock_get.return_value = config_response

        strategy = RTMPRevivalStrategy()
        result = strategy.revive(sample_stream, "http://localhost:9998")

        assert result.success is False
        assert "Failed to get path config" in result.message

    @patch("app.services.protocol_revival.httpx.post")
    @patch("app.services.protocol_revival.httpx.delete")
    @patch("app.services.protocol_revival.httpx.get")
    @patch("app.services.protocol_revival.time.sleep")
    def test_rtmp_revival_re_add_failure(
        self,
        mock_sleep,
        mock_get,
        mock_delete,
        mock_post,
        app_context,
        db_session,
        sample_stream,
    ):
        """Test RTMP revival handles re-add failure."""
        config_response = MagicMock()
        config_response.status_code = 200
        config_response.json.return_value = {"source": "rtmp://src"}
        mock_get.return_value = config_response

        mock_delete.return_value = MagicMock(status_code=200)

        add_response = MagicMock()
        add_response.status_code = 500
        mock_post.return_value = add_response

        strategy = RTMPRevivalStrategy()
        result = strategy.revive(sample_stream, "http://localhost:9998")

        assert result.success is False
        assert "Failed to re-add" in result.message


class TestVerifyRecovery:
    """Tests for verify_recovery across strategies."""

    @patch("app.services.protocol_revival.httpx.get")
    def test_verify_recovery_success(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test verify_recovery returns True when stream is ready."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [{"name": sample_stream.path, "ready": True}]
        }
        mock_get.return_value = mock_response

        strategy = RTSPRevivalStrategy()
        assert strategy.verify_recovery(sample_stream, "http://localhost:9998") is True

    @patch("app.services.protocol_revival.httpx.get")
    def test_verify_recovery_not_ready(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test verify_recovery returns False when stream is not ready."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [{"name": sample_stream.path, "ready": False}]
        }
        mock_get.return_value = mock_response

        strategy = RTSPRevivalStrategy()
        assert strategy.verify_recovery(sample_stream, "http://localhost:9998") is False

    @patch("app.services.protocol_revival.httpx.get")
    def test_verify_recovery_api_error(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test verify_recovery returns False on API error."""
        mock_get.side_effect = Exception("Connection refused")

        strategy = RTMPRevivalStrategy()
        assert strategy.verify_recovery(sample_stream, "http://localhost:9998") is False


class TestProtocolRevivalManager:
    """Tests for ProtocolRevivalManager orchestrator."""

    @patch("app.services.protocol_revival.httpx.get")
    def test_detect_source_protocol_rtsp(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test detecting RTSP source protocol."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "name": sample_stream.path,
                    "source": {"type": "rtspSource"},
                }
            ]
        }
        mock_get.return_value = mock_response

        manager = ProtocolRevivalManager()
        result = manager.detect_source_protocol(sample_stream, "http://localhost:9998")
        assert result == SourceProtocol.RTSP

    @patch("app.services.protocol_revival.httpx.get")
    def test_detect_source_protocol_rtmp(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test detecting RTMP source protocol."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "name": sample_stream.path,
                    "source": {"type": "rtmpConn"},
                }
            ]
        }
        mock_get.return_value = mock_response

        manager = ProtocolRevivalManager()
        result = manager.detect_source_protocol(sample_stream, "http://localhost:9998")
        assert result == SourceProtocol.RTMP

    @patch("app.services.protocol_revival.httpx.get")
    def test_detect_source_protocol_unknown(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test detecting unknown source protocol."""
        mock_get.side_effect = Exception("Connection error")

        manager = ProtocolRevivalManager()
        result = manager.detect_source_protocol(sample_stream, "http://localhost:9998")
        assert result == SourceProtocol.UNKNOWN

    @patch("app.services.protocol_revival.httpx.get")
    @patch("app.services.protocol_revival.httpx.post")
    @patch("app.services.protocol_revival.time.sleep")
    def test_revive_path_with_strategy(
        self,
        mock_sleep,
        mock_post,
        mock_get,
        app_context,
        db_session,
        sample_stream,
    ):
        """Test revive_path selects correct strategy and executes revival."""
        # Mock paths list for strategy selection
        path_list_response = MagicMock()
        path_list_response.status_code = 200
        path_list_response.json.return_value = {
            "items": [
                {
                    "name": sample_stream.path,
                    "source": {"type": "rtspSource"},
                    "ready": True,
                }
            ]
        }

        # Mock session list for RTSP revival
        session_list_response = MagicMock()
        session_list_response.status_code = 200
        session_list_response.json.return_value = {
            "items": [{"id": "sess-1", "path": sample_stream.path}]
        }

        # Mock kick response
        kick_response = MagicMock()
        kick_response.status_code = 200

        # First call: paths/list for strategy selection
        # Subsequent calls: RTSP session lists and verify
        mock_get.side_effect = [
            path_list_response,  # strategy selection
            session_list_response,  # rtspsessions
            session_list_response,  # rtspssessions
            path_list_response,  # verify recovery
        ]
        mock_post.return_value = kick_response

        manager = ProtocolRevivalManager()
        result = manager.revive_path(sample_stream)

        assert result["success"] is True
        assert result["protocol"] == "rtsp"

        # Check that events were created
        events = StreamEvent.query.filter_by(stream_id=sample_stream.id).all()
        assert len(events) >= 2  # start + result event

    @patch("app.services.protocol_revival.httpx.get")
    def test_revive_path_fallback_to_generic(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test revive_path falls back when no strategy matches."""
        # Return path data with unknown source type
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "name": sample_stream.path,
                    "source": {"type": "unknownType"},
                }
            ]
        }
        mock_get.return_value = mock_response

        manager = ProtocolRevivalManager()
        result = manager.revive_path(sample_stream)

        assert result["success"] is False
        assert result["protocol"] == "unknown"
        assert "No protocol-specific strategy" in result["message"]

        # Should still create events
        events = StreamEvent.query.filter_by(stream_id=sample_stream.id).all()
        event_types = [e.event_type for e in events]
        assert EventType.PROTOCOL_REVIVAL_STARTED.value in event_types
        assert EventType.PROTOCOL_REVIVAL_FAILED.value in event_types

    @patch("app.services.protocol_revival.httpx.get")
    def test_revive_path_no_path_data(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test revive_path when API returns no matching path."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_get.return_value = mock_response

        manager = ProtocolRevivalManager()
        result = manager.revive_path(sample_stream)

        assert result["success"] is False

    @patch("app.services.protocol_revival.httpx.get")
    def test_revive_path_api_error(
        self, mock_get, app_context, db_session, sample_stream
    ):
        """Test revive_path when API call fails."""
        mock_get.side_effect = Exception("Connection refused")

        manager = ProtocolRevivalManager()
        result = manager.revive_path(sample_stream)

        # Falls back to no strategy found
        assert result["success"] is False


class TestClassifyProtocol:
    """Tests for ProtocolRevivalManager._classify_protocol."""

    def test_classify_rtsp(self, app_context):
        """Test classifying RTSP protocol."""
        manager = ProtocolRevivalManager()
        result = manager._classify_protocol({"source": {"type": "rtspSource"}})
        assert result == SourceProtocol.RTSP

    def test_classify_rtmp(self, app_context):
        """Test classifying RTMP protocol."""
        manager = ProtocolRevivalManager()
        result = manager._classify_protocol({"source": {"type": "rtmpConn"}})
        assert result == SourceProtocol.RTMP

    def test_classify_webrtc(self, app_context):
        """Test classifying WebRTC/WHIP protocol."""
        manager = ProtocolRevivalManager()
        result = manager._classify_protocol({"source": {"type": "webrtcSession"}})
        assert result == SourceProtocol.WHIP

    def test_classify_whep(self, app_context):
        """Test classifying WHEP protocol."""
        manager = ProtocolRevivalManager()
        result = manager._classify_protocol({"source": {"type": "whepSource"}})
        assert result == SourceProtocol.WHEP

    def test_classify_hls(self, app_context):
        """Test classifying HLS protocol."""
        manager = ProtocolRevivalManager()
        result = manager._classify_protocol({"source": {"type": "hlsSource"}})
        assert result == SourceProtocol.HLS

    def test_classify_srt(self, app_context):
        """Test classifying SRT protocol."""
        manager = ProtocolRevivalManager()
        result = manager._classify_protocol({"source": {"type": "srtConn"}})
        assert result == SourceProtocol.SRT

    def test_classify_unknown(self, app_context):
        """Test classifying unknown protocol."""
        manager = ProtocolRevivalManager()
        result = manager._classify_protocol({"source": {"type": "somethingNew"}})
        assert result == SourceProtocol.UNKNOWN

    def test_classify_no_source(self, app_context):
        """Test classifying when source is missing."""
        manager = ProtocolRevivalManager()
        result = manager._classify_protocol({"source": None})
        assert result == SourceProtocol.UNKNOWN
