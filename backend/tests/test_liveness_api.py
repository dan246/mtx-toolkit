"""
Tests for Liveness API endpoints.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import LivenessClassification, LivenessProbeResult, Stream, StreamStatus


class TestLivenessAPI:
    """Tests for /api/liveness endpoints."""

    def test_list_liveness_streams(
        self, client, app_context, db_session, sample_stream_with_liveness
    ):
        """Test listing all streams with liveness data."""
        response = client.get("/api/liveness/streams")
        assert response.status_code == 200

        data = response.get_json()
        assert "streams" in data
        assert "total" in data
        assert data["total"] >= 1

        stream = data["streams"][0]
        assert "id" in stream
        assert "path" in stream
        assert "liveness_classification" in stream
        assert "consecutive_freeze_checks" in stream

    def test_list_liveness_streams_filtered(
        self, client, app_context, db_session, sample_stream_with_liveness
    ):
        """Test listing streams filtered by classification."""
        response = client.get("/api/liveness/streams?classification=live")
        assert response.status_code == 200

        data = response.get_json()
        assert data["total"] >= 1
        for stream in data["streams"]:
            assert stream["liveness_classification"] == "live"

    def test_list_liveness_streams_filtered_no_match(
        self, client, app_context, db_session, sample_stream_with_liveness
    ):
        """Test listing streams with non-matching filter returns empty."""
        response = client.get("/api/liveness/streams?classification=frozen")
        assert response.status_code == 200

        data = response.get_json()
        # sample_stream_with_liveness has classification=live
        # so filtering for frozen should not include it
        for stream in data["streams"]:
            assert stream["liveness_classification"] == "frozen"

    def test_list_liveness_streams_all(
        self,
        client,
        app_context,
        db_session,
        sample_stream,
        sample_stream_with_liveness,
    ):
        """Test listing all streams without filter."""
        response = client.get("/api/liveness/streams")
        assert response.status_code == 200

        data = response.get_json()
        assert data["total"] >= 2

    def test_get_liveness_stream_detail(
        self, client, app_context, db_session, sample_stream_with_liveness
    ):
        """Test getting liveness detail for a specific stream."""
        stream_id = sample_stream_with_liveness.id
        response = client.get(f"/api/liveness/streams/{stream_id}")
        assert response.status_code == 200

        data = response.get_json()
        assert data["id"] == stream_id
        assert data["path"] == sample_stream_with_liveness.path
        assert data["liveness_classification"] == "live"
        assert data["last_pts"] == 90000
        assert data["last_frame_hash"] == "abc123def456"
        assert "recent_probes" in data

    def test_get_liveness_stream_detail_not_found(
        self, client, app_context, db_session
    ):
        """Test getting liveness detail for non-existent stream."""
        response = client.get("/api/liveness/streams/99999")
        assert response.status_code == 404

    def test_get_liveness_stream_detail_with_probes(
        self,
        client,
        app_context,
        db_session,
        sample_stream_with_liveness,
        sample_liveness_probe_result,
    ):
        """Test getting liveness detail includes recent probe results."""
        stream_id = sample_stream_with_liveness.id
        response = client.get(f"/api/liveness/streams/{stream_id}")
        assert response.status_code == 200

        data = response.get_json()
        assert len(data["recent_probes"]) >= 1
        probe = data["recent_probes"][0]
        assert probe["classification"] == "live"
        assert probe["pts_value"] == 90000
        assert probe["pts_delta"] == 3000
        assert probe["frame_hash_changed"] is True
        assert probe["brightness"] == 128.0
        assert probe["audio_rms"] == -20.0

    def test_get_probe_history(
        self,
        client,
        app_context,
        db_session,
        sample_stream_with_liveness,
        sample_liveness_probe_result,
    ):
        """Test getting probe history for a stream."""
        stream_id = sample_stream_with_liveness.id
        response = client.get(f"/api/liveness/history/{stream_id}")
        assert response.status_code == 200

        data = response.get_json()
        assert data["stream_id"] == stream_id
        assert "probes" in data
        assert data["total"] >= 1

        probe = data["probes"][0]
        assert "id" in probe
        assert "classification" in probe
        assert "pts_value" in probe
        assert "created_at" in probe

    def test_get_probe_history_with_limit(
        self,
        client,
        app_context,
        db_session,
        sample_stream_with_liveness,
    ):
        """Test getting probe history with custom limit."""
        stream_id = sample_stream_with_liveness.id

        # Create multiple probe results
        for i in range(5):
            probe_result = LivenessProbeResult(
                stream_id=stream_id,
                classification=LivenessClassification.LIVE.value,
                pts_value=90000 + i * 3000,
                pts_delta=3000,
                frame_hash="hash_" + str(i),
                frame_hash_changed=True,
                brightness=128.0,
                audio_rms=-20.0,
                probe_duration_ms=100,
            )
            db_session.add(probe_result)
        db_session.commit()

        response = client.get(f"/api/liveness/history/{stream_id}?limit=3")
        assert response.status_code == 200

        data = response.get_json()
        assert data["total"] == 3

    def test_get_probe_history_empty(
        self, client, app_context, db_session, sample_stream
    ):
        """Test getting probe history for stream with no probes."""
        response = client.get(f"/api/liveness/history/{sample_stream.id}")
        assert response.status_code == 200

        data = response.get_json()
        assert data["probes"] == []
        assert data["total"] == 0

    def test_trigger_manual_probe(
        self, client, app_context, db_session, sample_stream_with_liveness
    ):
        """Test manually triggering a liveness probe via API."""
        stream_id = sample_stream_with_liveness.id

        with patch("app.services.liveness_probe.LivenessProbe") as MockProbe:
            mock_instance = MagicMock()
            mock_instance.probe_stream.return_value = {
                "stream_id": stream_id,
                "classification": "live",
                "pts_value": 93000,
                "pts_delta": 3000,
                "frame_hash_changed": True,
                "brightness": 130.0,
                "audio_rms": -22.0,
                "keyframe_present": True,
                "probe_duration_ms": 200,
                "severity": "info",
            }
            MockProbe.return_value = mock_instance

            response = client.post(f"/api/liveness/streams/{stream_id}/probe")
            assert response.status_code == 200

            data = response.get_json()
            assert data["stream_id"] == stream_id
            assert data["classification"] == "live"
            assert data["severity"] == "info"

            mock_instance.probe_stream.assert_called_once()

    def test_trigger_manual_probe_not_found(self, client, app_context, db_session):
        """Test triggering probe for non-existent stream."""
        response = client.post("/api/liveness/streams/99999/probe")
        assert response.status_code == 404
