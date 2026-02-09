"""
Tests for Playback Report API endpoints in /api/health.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import ClientPlaybackReport, Stream


class TestPlaybackReportAPI:
    """Tests for playback report endpoints in /api/health."""

    def test_submit_playback_report(
        self, client, app_context, db_session, sample_stream
    ):
        """Test submitting a client playback report."""
        response = client.post(
            "/api/health/playback-report",
            json={
                "stream_id": sample_stream.id,
                "client_id": "player-abc-123",
                "stall_count": 3,
                "stall_duration_ms": 1500,
                "buffer_underrun_count": 2,
                "frames_decoded": 9000,
                "frames_dropped": 15,
                "current_level": 4,
                "recovery_action": "seek_nudge",
                "error_type": None,
            },
        )
        assert response.status_code == 201

        data = response.get_json()
        assert data["success"] is True
        assert "report_id" in data
        assert data["report_id"] > 0

        # Verify saved in database
        report = ClientPlaybackReport.query.get(data["report_id"])
        assert report is not None
        assert report.stream_id == sample_stream.id
        assert report.client_id == "player-abc-123"
        assert report.stall_count == 3
        assert report.stall_duration_ms == 1500
        assert report.buffer_underrun_count == 2
        assert report.frames_decoded == 9000
        assert report.frames_dropped == 15
        assert report.current_level == 4
        assert report.recovery_action == "seek_nudge"

    def test_submit_report_missing_stream_id(self, client, app_context, db_session):
        """Test submitting report without stream_id."""
        response = client.post(
            "/api/health/playback-report",
            json={
                "client_id": "player-abc-123",
                "stall_count": 1,
            },
        )
        assert response.status_code == 400

        data = response.get_json()
        assert "error" in data
        assert "stream_id is required" in data["error"]

    def test_submit_report_invalid_stream(self, client, app_context, db_session):
        """Test submitting report with non-existent stream_id."""
        response = client.post(
            "/api/health/playback-report",
            json={
                "stream_id": 99999,
                "client_id": "player-abc-123",
                "stall_count": 1,
            },
        )
        assert response.status_code == 404

        data = response.get_json()
        assert "error" in data
        assert "Stream not found" in data["error"]

    def test_submit_report_minimal_data(
        self, client, app_context, db_session, sample_stream
    ):
        """Test submitting report with minimal required data."""
        response = client.post(
            "/api/health/playback-report",
            json={
                "stream_id": sample_stream.id,
            },
        )
        assert response.status_code == 201

        data = response.get_json()
        assert data["success"] is True

        # Verify defaults
        report = ClientPlaybackReport.query.get(data["report_id"])
        assert report.stall_count == 0
        assert report.stall_duration_ms == 0
        assert report.buffer_underrun_count == 0

    def test_submit_report_with_error_type(
        self, client, app_context, db_session, sample_stream
    ):
        """Test submitting report with error type."""
        response = client.post(
            "/api/health/playback-report",
            json={
                "stream_id": sample_stream.id,
                "client_id": "player-xyz",
                "error_type": "mediaError.fragParsingError",
                "recovery_action": "full_reload",
            },
        )
        assert response.status_code == 201

        data = response.get_json()
        report = ClientPlaybackReport.query.get(data["report_id"])
        assert report.error_type == "mediaError.fragParsingError"
        assert report.recovery_action == "full_reload"

    def test_submit_report_captures_client_ip(
        self, client, app_context, db_session, sample_stream
    ):
        """Test that submitting report captures client IP."""
        response = client.post(
            "/api/health/playback-report",
            json={
                "stream_id": sample_stream.id,
                "client_id": "player-ip-test",
            },
        )
        assert response.status_code == 201

        data = response.get_json()
        report = ClientPlaybackReport.query.get(data["report_id"])
        # In test client, remote_addr is typically 127.0.0.1
        assert report.client_ip is not None

    def test_get_playback_reports(self, client, app_context, db_session, sample_stream):
        """Test getting playback reports for a stream."""
        # Create some reports
        for i in range(3):
            report = ClientPlaybackReport(
                stream_id=sample_stream.id,
                client_id=f"player-{i}",
                client_ip="127.0.0.1",
                stall_count=i,
                stall_duration_ms=i * 500,
                buffer_underrun_count=i,
                frames_decoded=9000 + i * 100,
                frames_dropped=i * 5,
                current_level=4,
                recovery_action="seek_nudge" if i > 0 else None,
            )
            db_session.add(report)
        db_session.commit()

        response = client.get(f"/api/health/playback-reports/{sample_stream.id}")
        assert response.status_code == 200

        data = response.get_json()
        assert data["stream_id"] == sample_stream.id
        assert "reports" in data
        assert data["total"] == 3

        report = data["reports"][0]
        assert "id" in report
        assert "client_id" in report
        assert "client_ip" in report
        assert "stall_count" in report
        assert "stall_duration_ms" in report
        assert "buffer_underrun_count" in report
        assert "frames_decoded" in report
        assert "frames_dropped" in report
        assert "current_level" in report
        assert "recovery_action" in report
        assert "error_type" in report
        assert "created_at" in report

    def test_get_playback_reports_empty(
        self, client, app_context, db_session, sample_stream
    ):
        """Test getting reports when none exist."""
        response = client.get(f"/api/health/playback-reports/{sample_stream.id}")
        assert response.status_code == 200

        data = response.get_json()
        assert data["reports"] == []
        assert data["total"] == 0

    def test_get_playback_reports_with_limit(
        self, client, app_context, db_session, sample_stream
    ):
        """Test getting reports with custom limit."""
        for i in range(10):
            report = ClientPlaybackReport(
                stream_id=sample_stream.id,
                client_id=f"player-{i}",
                stall_count=i,
            )
            db_session.add(report)
        db_session.commit()

        response = client.get(
            f"/api/health/playback-reports/{sample_stream.id}?limit=5"
        )
        assert response.status_code == 200

        data = response.get_json()
        assert data["total"] == 5

    def test_get_playback_reports_ordered_by_latest(
        self, client, app_context, db_session, sample_stream
    ):
        """Test reports are ordered by most recent first."""
        for i in range(3):
            report = ClientPlaybackReport(
                stream_id=sample_stream.id,
                client_id=f"player-{i}",
                stall_count=i,
            )
            db_session.add(report)
        db_session.commit()

        response = client.get(f"/api/health/playback-reports/{sample_stream.id}")
        assert response.status_code == 200

        data = response.get_json()
        reports = data["reports"]
        # Most recent should come first (highest stall_count was added last)
        if len(reports) >= 2:
            assert reports[0]["id"] >= reports[1]["id"]

    def test_get_playback_reports_different_streams(
        self, client, app_context, db_session, sample_stream, sample_node
    ):
        """Test reports are filtered by stream_id."""
        # Create another stream
        other_stream = Stream(
            node_id=sample_node.id,
            path="test/other",
            name="Other Stream",
            source_url="rtsp://192.168.1.100:554/other",
            protocol="rtsp",
            status="healthy",
        )
        db_session.add(other_stream)
        db_session.commit()

        # Add reports to both streams
        report1 = ClientPlaybackReport(
            stream_id=sample_stream.id,
            client_id="player-1",
            stall_count=1,
        )
        report2 = ClientPlaybackReport(
            stream_id=other_stream.id,
            client_id="player-2",
            stall_count=2,
        )
        db_session.add_all([report1, report2])
        db_session.commit()

        # Get reports for sample_stream only
        response = client.get(f"/api/health/playback-reports/{sample_stream.id}")
        assert response.status_code == 200

        data = response.get_json()
        assert data["total"] == 1
        assert data["reports"][0]["client_id"] == "player-1"

        # Get reports for other_stream only
        response = client.get(f"/api/health/playback-reports/{other_stream.id}")
        assert response.status_code == 200

        data = response.get_json()
        assert data["total"] == 1
        assert data["reports"][0]["client_id"] == "player-2"
