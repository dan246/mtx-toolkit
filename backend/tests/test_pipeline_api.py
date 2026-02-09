"""
Tests for Recording Pipeline API endpoints.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import (
    Recording,
    RecordingPipelineMetric,
    RecordingPipelineStatus,
    Stream,
    StreamStatus,
)


class TestPipelineAPI:
    """Tests for /api/pipeline endpoints."""

    def test_get_pipeline_status(
        self, client, app_context, db_session, sample_stream_with_recording
    ):
        """Test getting aggregated pipeline health status."""
        response = client.get("/api/pipeline/status")
        assert response.status_code == 200

        data = response.get_json()
        assert "total_recording_streams" in data
        assert "by_status" in data
        assert "avg_write_latency_ms" in data
        assert data["total_recording_streams"] >= 1

    def test_get_pipeline_status_empty(self, client, app_context, db_session):
        """Test pipeline status with no recording streams."""
        response = client.get("/api/pipeline/status")
        assert response.status_code == 200

        data = response.get_json()
        assert data["total_recording_streams"] == 0

    def test_get_stream_pipeline(
        self, client, app_context, db_session, sample_stream_with_recording
    ):
        """Test getting per-stream pipeline detail."""
        stream_id = sample_stream_with_recording.id
        response = client.get(f"/api/pipeline/streams/{stream_id}")
        assert response.status_code == 200

        data = response.get_json()
        assert data["stream_id"] == stream_id
        assert data["path"] == sample_stream_with_recording.path
        assert data["recording_enabled"] is True
        assert (
            data["recording_pipeline_status"] == RecordingPipelineStatus.UNKNOWN.value
        )
        assert "recording_last_segment_at" in data
        assert "recording_avg_write_latency_ms" in data

    def test_get_stream_pipeline_not_found(self, client, app_context, db_session):
        """Test getting pipeline detail for non-existent stream."""
        response = client.get("/api/pipeline/streams/99999")
        assert response.status_code == 404

    def test_get_stream_pipeline_metrics(
        self, client, app_context, db_session, sample_stream_with_recording
    ):
        """Test getting time-series pipeline metrics."""
        stream_id = sample_stream_with_recording.id

        # Create some metrics
        for i in range(5):
            metric = RecordingPipelineMetric(
                stream_id=stream_id,
                segment_write_duration_ms=100.0 + i * 20,
                segment_size_bytes=1024 * 1024 * (10 + i),
                disk_io_latency_ms=50.0 + i * 10,
                segment_gap_seconds=None if i < 3 else 6.0,
            )
            db_session.add(metric)
        db_session.commit()

        response = client.get(f"/api/pipeline/streams/{stream_id}/metrics")
        assert response.status_code == 200

        data = response.get_json()
        assert data["stream_id"] == stream_id
        assert "metrics" in data
        assert data["total"] == 5

        metric = data["metrics"][0]
        assert "id" in metric
        assert "segment_write_duration_ms" in metric
        assert "segment_size_bytes" in metric
        assert "disk_io_latency_ms" in metric
        assert "segment_gap_seconds" in metric
        assert "created_at" in metric

    def test_get_stream_pipeline_metrics_with_limit(
        self, client, app_context, db_session, sample_stream_with_recording
    ):
        """Test getting metrics with custom limit."""
        stream_id = sample_stream_with_recording.id

        for i in range(10):
            metric = RecordingPipelineMetric(
                stream_id=stream_id,
                disk_io_latency_ms=50.0 + i,
            )
            db_session.add(metric)
        db_session.commit()

        response = client.get(f"/api/pipeline/streams/{stream_id}/metrics?limit=3")
        assert response.status_code == 200

        data = response.get_json()
        assert data["total"] == 3

    def test_get_stream_pipeline_metrics_empty(
        self, client, app_context, db_session, sample_stream_with_recording
    ):
        """Test getting metrics when none exist."""
        stream_id = sample_stream_with_recording.id
        response = client.get(f"/api/pipeline/streams/{stream_id}/metrics")
        assert response.status_code == 200

        data = response.get_json()
        assert data["metrics"] == []
        assert data["total"] == 0

    def test_get_stream_pipeline_metrics_not_found(
        self, client, app_context, db_session
    ):
        """Test getting metrics for non-existent stream."""
        response = client.get("/api/pipeline/streams/99999/metrics")
        assert response.status_code == 404

    def test_get_all_gaps(
        self, client, app_context, db_session, sample_stream_with_recording
    ):
        """Test getting all detected segment gaps."""
        with patch(
            "app.services.retention_manager.RetentionManager"
        ) as MockRetentionManager:
            mock_manager = MagicMock()
            mock_manager.get_segment_timeline.return_value = {
                "stream_id": sample_stream_with_recording.id,
                "gaps": [
                    {
                        "start": "2026-01-01T12:00:00",
                        "end": "2026-01-01T12:00:15",
                        "duration_seconds": 15.0,
                    },
                ],
                "total_gaps": 1,
            }
            MockRetentionManager.return_value = mock_manager

            response = client.get("/api/pipeline/gaps")
            assert response.status_code == 200

            data = response.get_json()
            assert "gaps" in data
            assert "total" in data

    def test_get_all_gaps_empty(self, client, app_context, db_session):
        """Test getting gaps when no recording streams exist."""
        with patch(
            "app.services.retention_manager.RetentionManager"
        ) as MockRetentionManager:
            mock_manager = MagicMock()
            MockRetentionManager.return_value = mock_manager

            response = client.get("/api/pipeline/gaps")
            assert response.status_code == 200

            data = response.get_json()
            assert data["gaps"] == []
            assert data["total"] == 0

    def test_get_all_gaps_multiple_streams(
        self, client, app_context, db_session, sample_node
    ):
        """Test getting gaps across multiple recording-enabled streams."""
        streams = []
        for i in range(2):
            stream = Stream(
                node_id=sample_node.id,
                path=f"test/gap_stream_{i}",
                name=f"Gap Stream {i}",
                source_url=f"rtsp://192.168.1.100:554/gap{i}",
                protocol="rtsp",
                status=StreamStatus.HEALTHY.value,
                recording_enabled=True,
            )
            db_session.add(stream)
            streams.append(stream)
        db_session.commit()

        with patch(
            "app.services.retention_manager.RetentionManager"
        ) as MockRetentionManager:
            mock_manager = MagicMock()

            def mock_timeline(stream, hours=24):
                return {
                    "stream_id": stream.id,
                    "gaps": [
                        {
                            "start": "2026-01-01T12:00:00",
                            "end": "2026-01-01T12:00:10",
                            "duration_seconds": 10.0,
                        }
                    ],
                    "total_gaps": 1,
                }

            mock_manager.get_segment_timeline.side_effect = mock_timeline
            MockRetentionManager.return_value = mock_manager

            response = client.get("/api/pipeline/gaps")
            assert response.status_code == 200

            data = response.get_json()
            assert data["total"] >= 2

    def test_trigger_pipeline_check(
        self, client, app_context, db_session, sample_stream_with_recording
    ):
        """Test manually triggering a pipeline health check."""
        stream_id = sample_stream_with_recording.id

        with patch(
            "app.services.recording_pipeline_monitor.RecordingPipelineMonitor"
        ) as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.check_stream_pipeline.return_value = {
                "stream_id": stream_id,
                "status": RecordingPipelineStatus.HEALTHY.value,
                "issues": [],
                "write_latency_ms": 75.0,
                "segment_gap": {"has_gap": False},
                "suggestions": [],
            }
            MockMonitor.return_value = mock_instance

            response = client.post(f"/api/pipeline/streams/{stream_id}/check")
            assert response.status_code == 200

            data = response.get_json()
            assert data["stream_id"] == stream_id
            assert data["status"] == RecordingPipelineStatus.HEALTHY.value
            mock_instance.check_stream_pipeline.assert_called_once()

    def test_trigger_pipeline_check_not_found(self, client, app_context, db_session):
        """Test triggering check for non-existent stream."""
        response = client.post("/api/pipeline/streams/99999/check")
        assert response.status_code == 404

    def test_trigger_pipeline_check_returns_issues(
        self, client, app_context, db_session, sample_stream_with_recording
    ):
        """Test pipeline check returning issues."""
        stream_id = sample_stream_with_recording.id

        with patch(
            "app.services.recording_pipeline_monitor.RecordingPipelineMonitor"
        ) as MockMonitor:
            mock_instance = MagicMock()
            mock_instance.check_stream_pipeline.return_value = {
                "stream_id": stream_id,
                "status": RecordingPipelineStatus.WARNING.value,
                "issues": ["High write latency: 800ms"],
                "write_latency_ms": 800.0,
                "segment_gap": {"has_gap": False},
                "suggestions": ["Monitor disk IO utilization with iostat"],
            }
            MockMonitor.return_value = mock_instance

            response = client.post(f"/api/pipeline/streams/{stream_id}/check")
            assert response.status_code == 200

            data = response.get_json()
            assert data["status"] == RecordingPipelineStatus.WARNING.value
            assert len(data["issues"]) == 1
            assert len(data["suggestions"]) == 1
