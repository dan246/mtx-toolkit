"""
Tests for RecordingPipelineMonitor service.
"""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import (
    Recording,
    RecordingPipelineMetric,
    RecordingPipelineStatus,
    Stream,
    StreamEvent,
    StreamStatus,
)
from app.services.recording_pipeline_monitor import RecordingPipelineMonitor


class TestCheckStreamPipeline:
    """Tests for RecordingPipelineMonitor.check_stream_pipeline method."""

    @patch.object(RecordingPipelineMonitor, "_measure_write_latency")
    @patch.object(RecordingPipelineMonitor, "_detect_segment_gaps")
    def test_healthy_pipeline(
        self,
        mock_gaps,
        mock_latency,
        app_context,
        db_session,
        sample_stream_with_recording,
    ):
        """Test healthy pipeline with low latency and no gaps."""
        mock_gaps.return_value = {
            "has_gap": False,
            "gap_seconds": 0.5,
            "message": "No significant gap",
        }
        mock_latency.return_value = 50.0  # 50ms - well under warning threshold

        monitor = RecordingPipelineMonitor()
        result = monitor.check_stream_pipeline(sample_stream_with_recording)

        assert result["stream_id"] == sample_stream_with_recording.id
        assert result["status"] == RecordingPipelineStatus.HEALTHY.value
        assert result["issues"] == []
        assert result["write_latency_ms"] == 50.0

        db_session.refresh(sample_stream_with_recording)
        assert (
            sample_stream_with_recording.recording_pipeline_status
            == RecordingPipelineStatus.HEALTHY.value
        )

    @patch.object(RecordingPipelineMonitor, "_measure_write_latency")
    @patch.object(RecordingPipelineMonitor, "_detect_segment_gaps")
    def test_warning_pipeline_high_write_latency(
        self,
        mock_gaps,
        mock_latency,
        app_context,
        db_session,
        sample_stream_with_recording,
    ):
        """Test warning pipeline when write latency exceeds warning threshold."""
        mock_gaps.return_value = {"has_gap": False, "gap_seconds": 0}
        mock_latency.return_value = 800.0  # 800ms - over 500ms warning threshold

        monitor = RecordingPipelineMonitor()
        result = monitor.check_stream_pipeline(sample_stream_with_recording)

        assert result["status"] == RecordingPipelineStatus.WARNING.value
        assert len(result["issues"]) > 0
        assert any("latency" in issue.lower() for issue in result["issues"])

    @patch.object(RecordingPipelineMonitor, "_measure_write_latency")
    @patch.object(RecordingPipelineMonitor, "_detect_segment_gaps")
    def test_critical_pipeline_very_high_write_latency(
        self,
        mock_gaps,
        mock_latency,
        app_context,
        db_session,
        sample_stream_with_recording,
    ):
        """Test critical pipeline when write latency exceeds critical threshold."""
        mock_gaps.return_value = {"has_gap": False, "gap_seconds": 0}
        mock_latency.return_value = 3000.0  # 3000ms - over 2000ms critical threshold

        monitor = RecordingPipelineMonitor()
        result = monitor.check_stream_pipeline(sample_stream_with_recording)

        assert result["status"] == RecordingPipelineStatus.CRITICAL.value
        assert any("critical" in issue.lower() for issue in result["issues"])

        # Should create a write slow event
        events = StreamEvent.query.filter_by(
            stream_id=sample_stream_with_recording.id,
        ).all()
        event_types = [e.event_type for e in events]
        assert "recording_write_slow" in event_types

    @patch.object(RecordingPipelineMonitor, "_measure_write_latency")
    @patch.object(RecordingPipelineMonitor, "_detect_segment_gaps")
    def test_segment_gap_detection(
        self,
        mock_gaps,
        mock_latency,
        app_context,
        db_session,
        sample_stream_with_recording,
    ):
        """Test pipeline detects segment gaps."""
        mock_gaps.return_value = {
            "has_gap": True,
            "gap_seconds": 8.0,
            "newer_segment_start": "2026-01-01T12:05:08",
            "older_segment_end": "2026-01-01T12:05:00",
        }
        mock_latency.return_value = 50.0

        monitor = RecordingPipelineMonitor()
        result = monitor.check_stream_pipeline(sample_stream_with_recording)

        assert result["status"] in [
            RecordingPipelineStatus.WARNING.value,
            RecordingPipelineStatus.CRITICAL.value,
        ]
        assert any("gap" in issue.lower() for issue in result["issues"])
        assert result["segment_gap"]["has_gap"] is True

    @patch.object(RecordingPipelineMonitor, "_measure_write_latency")
    @patch.object(RecordingPipelineMonitor, "_detect_segment_gaps")
    def test_large_segment_gap_critical(
        self,
        mock_gaps,
        mock_latency,
        app_context,
        db_session,
        sample_stream_with_recording,
    ):
        """Test large segment gap triggers critical status."""
        # segment_gap_warning is 5.0, so gap > 10.0 (5.0 * 2) triggers critical
        mock_gaps.return_value = {
            "has_gap": True,
            "gap_seconds": 15.0,
            "newer_segment_start": "2026-01-01T12:05:15",
            "older_segment_end": "2026-01-01T12:05:00",
        }
        mock_latency.return_value = 50.0

        monitor = RecordingPipelineMonitor()
        result = monitor.check_stream_pipeline(sample_stream_with_recording)

        assert result["status"] == RecordingPipelineStatus.CRITICAL.value

    def test_recording_not_enabled(self, app_context, db_session, sample_stream):
        """Test check returns unknown for streams with recording not enabled."""
        monitor = RecordingPipelineMonitor()
        result = monitor.check_stream_pipeline(sample_stream)

        assert result["status"] == RecordingPipelineStatus.UNKNOWN.value
        assert "not enabled" in result["message"]

    @patch.object(RecordingPipelineMonitor, "_measure_write_latency")
    @patch.object(RecordingPipelineMonitor, "_detect_segment_gaps")
    def test_pipeline_stores_metric(
        self,
        mock_gaps,
        mock_latency,
        app_context,
        db_session,
        sample_stream_with_recording,
    ):
        """Test check_stream_pipeline stores a RecordingPipelineMetric."""
        mock_gaps.return_value = {"has_gap": False, "gap_seconds": None}
        mock_latency.return_value = 100.0

        initial_count = RecordingPipelineMetric.query.filter_by(
            stream_id=sample_stream_with_recording.id
        ).count()

        monitor = RecordingPipelineMonitor()
        monitor.check_stream_pipeline(sample_stream_with_recording)

        new_count = RecordingPipelineMetric.query.filter_by(
            stream_id=sample_stream_with_recording.id
        ).count()
        assert new_count == initial_count + 1


class TestSuggestMitigation:
    """Tests for RecordingPipelineMonitor._suggest_mitigation method."""

    def test_suggest_mitigation_critical_latency(self, app_context):
        """Test suggestions for critical write latency."""
        monitor = RecordingPipelineMonitor()
        suggestions = monitor._suggest_mitigation(
            {
                "write_latency": 3000.0,
                "gap": {"has_gap": False},
                "status": RecordingPipelineStatus.CRITICAL,
            }
        )

        assert len(suggestions) > 0
        assert any("SSD" in s or "faster disk" in s for s in suggestions)
        assert any("Immediate attention" in s for s in suggestions)

    def test_suggest_mitigation_warning_latency(self, app_context):
        """Test suggestions for warning-level write latency."""
        monitor = RecordingPipelineMonitor()
        suggestions = monitor._suggest_mitigation(
            {
                "write_latency": 800.0,
                "gap": {"has_gap": False},
                "status": RecordingPipelineStatus.WARNING,
            }
        )

        assert len(suggestions) > 0
        assert any("iostat" in s for s in suggestions)

    def test_suggest_mitigation_large_gap(self, app_context):
        """Test suggestions for large segment gap."""
        monitor = RecordingPipelineMonitor()
        suggestions = monitor._suggest_mitigation(
            {
                "write_latency": 50.0,
                "gap": {"has_gap": True, "gap_seconds": 15.0},
                "status": RecordingPipelineStatus.WARNING,
            }
        )

        assert len(suggestions) > 0
        assert any("stream source" in s.lower() for s in suggestions)

    def test_suggest_mitigation_healthy(self, app_context):
        """Test no suggestions for healthy pipeline."""
        monitor = RecordingPipelineMonitor()
        suggestions = monitor._suggest_mitigation(
            {
                "write_latency": 50.0,
                "gap": {"has_gap": False},
                "status": RecordingPipelineStatus.HEALTHY,
            }
        )

        assert len(suggestions) == 0


class TestDetectSegmentGaps:
    """Tests for RecordingPipelineMonitor._detect_segment_gaps method."""

    def test_no_gap_between_segments(
        self, app_context, db_session, sample_stream_with_recording
    ):
        """Test no gap detected when segments are contiguous."""
        stream = sample_stream_with_recording

        # Update recordings to be contiguous (gap < 5s)
        recordings = (
            Recording.query.filter_by(stream_id=stream.id)
            .order_by(Recording.start_time.desc())
            .limit(2)
            .all()
        )
        if len(recordings) >= 2:
            newer = recordings[0]
            older = recordings[1]
            older.end_time = newer.start_time - timedelta(seconds=1)
            db_session.commit()

        monitor = RecordingPipelineMonitor()
        result = monitor._detect_segment_gaps(stream)

        assert result["has_gap"] is False

    def test_gap_detected_between_segments(
        self, app_context, db_session, sample_stream_with_recording
    ):
        """Test gap detected when segments have significant gap."""
        stream = sample_stream_with_recording

        recordings = (
            Recording.query.filter_by(stream_id=stream.id)
            .order_by(Recording.start_time.desc())
            .limit(2)
            .all()
        )
        if len(recordings) >= 2:
            newer = recordings[0]
            older = recordings[1]
            # Create a 30-second gap
            older.end_time = newer.start_time - timedelta(seconds=30)
            db_session.commit()

        monitor = RecordingPipelineMonitor()
        result = monitor._detect_segment_gaps(stream)

        assert result["has_gap"] is True
        assert result["gap_seconds"] > 5.0

    def test_not_enough_segments(self, app_context, db_session, sample_node):
        """Test when fewer than 2 segments exist."""
        stream = Stream(
            node_id=sample_node.id,
            path="test/single_rec",
            name="Single Recording Stream",
            source_url="rtsp://192.168.1.100:554/single",
            protocol="rtsp",
            status=StreamStatus.HEALTHY.value,
            recording_enabled=True,
        )
        db_session.add(stream)
        db_session.commit()

        recording = Recording(
            stream_id=stream.id,
            file_path="/recordings/single/rec_0.ts",
            file_size=1024 * 1024,
            duration_seconds=300,
            start_time=datetime.utcnow(),
        )
        db_session.add(recording)
        db_session.commit()

        monitor = RecordingPipelineMonitor()
        result = monitor._detect_segment_gaps(stream)

        assert result["has_gap"] is False
        assert "Not enough segments" in result.get("message", "")


class TestMeasureWriteLatency:
    """Tests for RecordingPipelineMonitor._measure_write_latency method."""

    @patch("app.services.recording_pipeline_monitor.tempfile.NamedTemporaryFile")
    @patch("app.services.recording_pipeline_monitor.os.fsync")
    @patch("app.services.recording_pipeline_monitor.time.time")
    def test_measure_disk_io_latency(
        self, mock_time, mock_fsync, mock_tempfile, app_context
    ):
        """Test disk IO latency measurement."""
        mock_time.side_effect = [1000.0, 1000.1]  # 100ms
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_tempfile.return_value = mock_file

        monitor = RecordingPipelineMonitor()
        with patch("pathlib.Path.exists", return_value=True):
            result = monitor._measure_disk_io_latency()

        assert result == 100.0  # 0.1 seconds = 100ms

    def test_measure_write_latency_no_directory(self, app_context):
        """Test measure_write_latency when directory doesn't exist."""
        monitor = RecordingPipelineMonitor()

        with patch("pathlib.Path.exists", return_value=False):
            result = monitor._measure_write_latency(
                MagicMock(path="nonexistent/path", recording_enabled=True)
            )

        assert result is None


class TestCheckAllPipelines:
    """Tests for RecordingPipelineMonitor.check_all_pipelines method."""

    def test_check_all_pipelines(
        self, app_context, db_session, sample_stream_with_recording
    ):
        """Test checking all recording-enabled pipelines."""
        monitor = RecordingPipelineMonitor()

        with patch.object(monitor, "check_stream_pipeline") as mock_check:
            mock_check.return_value = {
                "stream_id": sample_stream_with_recording.id,
                "status": RecordingPipelineStatus.HEALTHY.value,
            }

            result = monitor.check_all_pipelines()

        assert "summary" in result
        assert "results" in result
        assert result["summary"]["total"] >= 1
        mock_check.assert_called()

    def test_check_all_pipelines_empty(self, app_context, db_session):
        """Test checking pipelines when no recording-enabled streams."""
        monitor = RecordingPipelineMonitor()
        result = monitor.check_all_pipelines()

        assert result["summary"]["total"] == 0
        assert result["results"] == []

    def test_check_all_pipelines_handles_errors(
        self, app_context, db_session, sample_stream_with_recording
    ):
        """Test check_all_pipelines handles individual stream errors."""
        monitor = RecordingPipelineMonitor()

        with patch.object(monitor, "check_stream_pipeline") as mock_check:
            mock_check.side_effect = Exception("Check failed")

            result = monitor.check_all_pipelines()

        assert result["summary"]["total"] >= 1
        assert "error" in result["results"][0]

    def test_check_all_pipelines_summary_counts(
        self, app_context, db_session, sample_node
    ):
        """Test check_all_pipelines counts statuses correctly."""
        # Create multiple recording-enabled streams
        for i in range(3):
            stream = Stream(
                node_id=sample_node.id,
                path=f"test/pipeline_{i}",
                name=f"Pipeline Stream {i}",
                source_url=f"rtsp://192.168.1.100:554/pipe{i}",
                protocol="rtsp",
                status=StreamStatus.HEALTHY.value,
                recording_enabled=True,
                recording_pipeline_status=RecordingPipelineStatus.UNKNOWN.value,
            )
            db_session.add(stream)
        db_session.commit()

        statuses = [
            RecordingPipelineStatus.HEALTHY.value,
            RecordingPipelineStatus.WARNING.value,
            RecordingPipelineStatus.CRITICAL.value,
        ]

        monitor = RecordingPipelineMonitor()

        with patch.object(monitor, "check_stream_pipeline") as mock_check:
            call_count = [0]

            def side_effect(stream):
                idx = call_count[0] % len(statuses)
                call_count[0] += 1
                return {
                    "stream_id": stream.id,
                    "status": statuses[idx],
                }

            mock_check.side_effect = side_effect

            result = monitor.check_all_pipelines()

        assert result["summary"]["total"] >= 3
        assert result["summary"]["healthy"] >= 1
        assert result["summary"]["warning"] >= 1
        assert result["summary"]["critical"] >= 1


class TestDashboardData:
    """Tests for RecordingPipelineMonitor.get_pipeline_dashboard_data method."""

    def test_dashboard_data(
        self, app_context, db_session, sample_stream_with_recording
    ):
        """Test getting pipeline dashboard data."""
        monitor = RecordingPipelineMonitor()
        data = monitor.get_pipeline_dashboard_data()

        assert "total_recording_streams" in data
        assert data["total_recording_streams"] >= 1
        assert "by_status" in data
        assert "avg_write_latency_ms" in data
        assert "recent_gaps" in data

    def test_dashboard_data_empty(self, app_context, db_session):
        """Test dashboard data with no recording streams."""
        monitor = RecordingPipelineMonitor()
        data = monitor.get_pipeline_dashboard_data()

        assert data["total_recording_streams"] == 0
        assert data["avg_write_latency_ms"] is None

    def test_dashboard_data_with_metrics(
        self, app_context, db_session, sample_stream_with_recording
    ):
        """Test dashboard data includes recent metrics in aggregation."""
        stream = sample_stream_with_recording

        # Add some recent metrics
        for i in range(5):
            metric = RecordingPipelineMetric(
                stream_id=stream.id,
                disk_io_latency_ms=100.0 + i * 50,
                segment_gap_seconds=1.0 if i < 3 else 8.0,
            )
            db_session.add(metric)
        db_session.commit()

        monitor = RecordingPipelineMonitor()
        data = monitor.get_pipeline_dashboard_data()

        assert data["avg_write_latency_ms"] is not None
        assert data["recent_gaps"] >= 0

    def test_dashboard_data_by_status_counts(
        self, app_context, db_session, sample_node
    ):
        """Test dashboard data counts streams by status."""
        for i, status in enumerate(RecordingPipelineStatus):
            stream = Stream(
                node_id=sample_node.id,
                path=f"test/dash_{i}",
                name=f"Dashboard Stream {i}",
                source_url=f"rtsp://192.168.1.100:554/dash{i}",
                protocol="rtsp",
                status=StreamStatus.HEALTHY.value,
                recording_enabled=True,
                recording_pipeline_status=status.value,
            )
            db_session.add(stream)
        db_session.commit()

        monitor = RecordingPipelineMonitor()
        data = monitor.get_pipeline_dashboard_data()

        for status in RecordingPipelineStatus:
            assert status.value in data["by_status"]
            assert data["by_status"][status.value] >= 1
