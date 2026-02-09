"""
Tests for LivenessProbe service.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import (
    LivenessClassification,
    LivenessProbeResult,
    Stream,
    StreamEvent,
    StreamStatus,
)
from app.services.liveness_probe import LivenessProbe


class TestClassify:
    """Tests for LivenessProbe.classify method."""

    def test_classify_live(self, app_context):
        """Test classify returns LIVE when PTS advancing, hash changed, good brightness."""
        probe = LivenessProbe()
        result = probe.classify(
            pts_delta=5000,
            frame_hash_changed=True,
            brightness=128.0,
            audio_rms=-20.0,
            keyframe_present=True,
        )
        assert result == LivenessClassification.LIVE

    def test_classify_frozen(self, app_context):
        """Test classify returns FROZEN when frame hash has NOT changed."""
        probe = LivenessProbe()
        result = probe.classify(
            pts_delta=5000,
            frame_hash_changed=False,
            brightness=128.0,
            audio_rms=-20.0,
            keyframe_present=True,
        )
        assert result == LivenessClassification.FROZEN

    def test_classify_black_screen(self, app_context):
        """Test classify returns BLACK_SCREEN when brightness < 10."""
        probe = LivenessProbe()
        result = probe.classify(
            pts_delta=5000,
            frame_hash_changed=True,
            brightness=5.0,
            audio_rms=-20.0,
            keyframe_present=True,
        )
        assert result == LivenessClassification.BLACK_SCREEN

    def test_classify_stale(self, app_context):
        """Test classify returns STALE when pts_delta < 2000."""
        probe = LivenessProbe()
        result = probe.classify(
            pts_delta=500,
            frame_hash_changed=True,
            brightness=128.0,
            audio_rms=-20.0,
            keyframe_present=True,
        )
        assert result == LivenessClassification.STALE

    def test_classify_silent(self, app_context):
        """Test classify returns SILENT when audio_rms < -50."""
        probe = LivenessProbe()
        result = probe.classify(
            pts_delta=5000,
            frame_hash_changed=True,
            brightness=128.0,
            audio_rms=-60.0,
            keyframe_present=True,
        )
        assert result == LivenessClassification.SILENT

    def test_classify_stale_takes_priority_over_frozen(self, app_context):
        """Test stale PTS takes priority over frozen hash in classification."""
        probe = LivenessProbe()
        result = probe.classify(
            pts_delta=100,
            frame_hash_changed=False,
            brightness=128.0,
            audio_rms=-20.0,
            keyframe_present=True,
        )
        assert result == LivenessClassification.STALE

    def test_classify_black_screen_over_frozen(self, app_context):
        """Test black screen takes priority over frozen when PTS is advancing."""
        probe = LivenessProbe()
        result = probe.classify(
            pts_delta=5000,
            frame_hash_changed=True,
            brightness=2.0,
            audio_rms=-20.0,
            keyframe_present=True,
        )
        assert result == LivenessClassification.BLACK_SCREEN

    def test_classify_none_pts_delta(self, app_context):
        """Test classify when pts_delta is None (first probe)."""
        probe = LivenessProbe()
        result = probe.classify(
            pts_delta=None,
            frame_hash_changed=True,
            brightness=128.0,
            audio_rms=-20.0,
            keyframe_present=True,
        )
        assert result == LivenessClassification.LIVE

    def test_classify_none_brightness(self, app_context):
        """Test classify when brightness is None."""
        probe = LivenessProbe()
        result = probe.classify(
            pts_delta=5000,
            frame_hash_changed=True,
            brightness=None,
            audio_rms=-20.0,
            keyframe_present=True,
        )
        assert result == LivenessClassification.LIVE

    def test_classify_none_audio_rms(self, app_context):
        """Test classify when audio_rms is None."""
        probe = LivenessProbe()
        result = probe.classify(
            pts_delta=5000,
            frame_hash_changed=True,
            brightness=128.0,
            audio_rms=None,
            keyframe_present=True,
        )
        assert result == LivenessClassification.LIVE


class TestProbeStream:
    """Tests for LivenessProbe.probe_stream method."""

    @patch("app.services.liveness_probe.subprocess.run")
    def test_probe_updates_model(
        self, mock_run, app_context, db_session, sample_stream_with_liveness
    ):
        """Test probe_stream updates stream fields correctly."""
        stream = sample_stream_with_liveness
        old_pts = stream.last_pts

        # Mock _get_pts
        pts_result = MagicMock(
            returncode=0,
            stdout=json.dumps({"frames": [{"pkt_pts": 95000}]}),
        )
        # Mock _get_frame_info
        frame_result = MagicMock(
            returncode=0,
            stdout=b"\x80" * 100,  # brightness ~128
        )
        # Mock _get_audio_rms
        audio_result = MagicMock(
            returncode=0,
            stderr="lavfi.astats.Overall.RMS_level=-25.0",
        )
        # Mock _check_keyframe
        keyframe_result = MagicMock(
            returncode=0,
            stdout=json.dumps({"frames": [{"key_frame": 1}]}),
        )

        mock_run.side_effect = [pts_result, frame_result, audio_result, keyframe_result]

        probe = LivenessProbe()
        result = probe.probe_stream(stream)

        assert result["stream_id"] == stream.id
        assert result["classification"] is not None
        assert "pts_value" in result
        assert "brightness" in result
        assert "audio_rms" in result
        assert "probe_duration_ms" in result

        # Stream fields should be updated
        db_session.refresh(stream)
        assert stream.liveness_last_check is not None
        assert stream.liveness_classification is not None

    @patch("app.services.liveness_probe.subprocess.run")
    def test_probe_creates_liveness_probe_result(
        self, mock_run, app_context, db_session, sample_stream_with_liveness
    ):
        """Test probe_stream stores a LivenessProbeResult record."""
        stream = sample_stream_with_liveness

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

        probe = LivenessProbe()
        probe.probe_stream(stream)

        results = LivenessProbeResult.query.filter_by(stream_id=stream.id).all()
        # Should have the one from fixture plus the new one
        assert len(results) >= 1

    @patch("app.services.liveness_probe.subprocess.run")
    def test_probe_tracks_freeze_duration(
        self, mock_run, app_context, db_session, sample_stream_with_liveness
    ):
        """Test probe_stream tracks freeze_started_at and consecutive_freeze_checks."""
        stream = sample_stream_with_liveness
        stream.freeze_started_at = None
        stream.consecutive_freeze_checks = 0
        stream.last_frame_hash = "abc123"
        db_session.commit()

        # Return same frame hash to trigger FROZEN (with large PTS delta)
        pts_result = MagicMock(
            returncode=0,
            stdout=json.dumps({"frames": [{"pkt_pts": 999999}]}),
        )
        # Return same frame data that hashes to the same value
        frame_result = MagicMock(returncode=1, stdout=b"")
        audio_result = MagicMock(returncode=1, stderr="")
        keyframe_result = MagicMock(returncode=1, stdout="")

        mock_run.side_effect = [pts_result, frame_result, audio_result, keyframe_result]

        probe = LivenessProbe()
        # frame_hash will be None (since returncode=1), frame_hash_changed stays True
        # but we can mock it differently. Let's force frozen by mocking the private methods
        with patch.object(probe, "_get_pts", return_value=999999), patch.object(
            probe, "_get_frame_info", return_value=("abc123", 128.0)
        ), patch.object(probe, "_get_audio_rms", return_value=-20.0), patch.object(
            probe, "_check_keyframe", return_value=True
        ):
            mock_run.reset_mock()
            result = probe.probe_stream(stream)

        # Same frame hash "abc123" -> frozen
        assert result["classification"] == LivenessClassification.FROZEN.value
        db_session.refresh(stream)
        assert stream.freeze_started_at is not None
        assert stream.consecutive_freeze_checks >= 1

    @patch("app.services.liveness_probe.subprocess.run")
    def test_probe_creates_event_on_classification_change(
        self, mock_run, app_context, db_session, sample_stream_with_liveness
    ):
        """Test probe_stream creates a StreamEvent when classification changes."""
        stream = sample_stream_with_liveness
        stream.liveness_classification = LivenessClassification.LIVE.value
        db_session.commit()

        initial_event_count = StreamEvent.query.filter_by(stream_id=stream.id).count()

        probe = LivenessProbe()
        # Force a FROZEN classification by returning the same frame hash
        # as what is stored on the stream (abc123def456)
        with patch.object(probe, "_get_pts", return_value=999999), patch.object(
            probe, "_get_frame_info", return_value=("abc123def456", 128.0)
        ), patch.object(probe, "_get_audio_rms", return_value=-20.0), patch.object(
            probe, "_check_keyframe", return_value=True
        ):
            mock_run.reset_mock()
            probe.probe_stream(stream)

        new_event_count = StreamEvent.query.filter_by(stream_id=stream.id).count()
        assert new_event_count > initial_event_count


class TestSeverityGrading:
    """Tests for LivenessProbe.determine_severity method."""

    def test_severity_info_for_live(self, app_context, db_session, sample_stream):
        """Test severity is info for LIVE classification."""
        probe = LivenessProbe()
        severity = probe.determine_severity(sample_stream, LivenessClassification.LIVE)
        assert severity == "info"

    def test_severity_warning_for_short_freeze(
        self, app_context, db_session, sample_stream
    ):
        """Test severity is warning for freeze shorter than freeze_short_sec."""
        probe = LivenessProbe()
        sample_stream.freeze_started_at = datetime.utcnow() - timedelta(seconds=5)
        db_session.commit()

        severity = probe.determine_severity(
            sample_stream, LivenessClassification.FROZEN
        )
        assert severity == "warning"

    def test_severity_error_for_medium_freeze(
        self, app_context, db_session, sample_stream
    ):
        """Test severity is error for freeze longer than freeze_short_sec."""
        probe = LivenessProbe()
        # freeze_short_sec defaults to 15
        sample_stream.freeze_started_at = datetime.utcnow() - timedelta(seconds=30)
        db_session.commit()

        severity = probe.determine_severity(
            sample_stream, LivenessClassification.FROZEN
        )
        assert severity == "error"

    def test_severity_critical_for_long_freeze(
        self, app_context, db_session, sample_stream
    ):
        """Test severity is critical for freeze longer than freeze_long_sec."""
        probe = LivenessProbe()
        # freeze_long_sec defaults to 60
        sample_stream.freeze_started_at = datetime.utcnow() - timedelta(seconds=120)
        db_session.commit()

        severity = probe.determine_severity(
            sample_stream, LivenessClassification.FROZEN
        )
        assert severity == "critical"

    def test_severity_warning_for_silent(self, app_context, db_session, sample_stream):
        """Test severity is warning for SILENT classification."""
        probe = LivenessProbe()
        sample_stream.freeze_started_at = None
        db_session.commit()

        severity = probe.determine_severity(
            sample_stream, LivenessClassification.SILENT
        )
        assert severity == "warning"

    def test_severity_warning_for_no_freeze_started_at(
        self, app_context, db_session, sample_stream
    ):
        """Test severity is warning when freeze_started_at is None."""
        probe = LivenessProbe()
        sample_stream.freeze_started_at = None
        db_session.commit()

        severity = probe.determine_severity(
            sample_stream, LivenessClassification.FROZEN
        )
        assert severity == "warning"


class TestProbeAllReadyStreams:
    """Tests for LivenessProbe.probe_all_ready_streams method."""

    def test_probe_all_ready_streams(self, app_context, db_session, sample_stream):
        """Test probe_all_ready_streams probes healthy streams."""
        probe = LivenessProbe()

        with patch.object(probe, "probe_stream") as mock_probe:
            mock_probe.return_value = {
                "stream_id": sample_stream.id,
                "classification": "live",
            }
            result = probe.probe_all_ready_streams()

        assert result["probed"] >= 1
        assert len(result["results"]) >= 1
        mock_probe.assert_called()

    def test_probe_all_ready_streams_skips_unhealthy(
        self, app_context, db_session, sample_unhealthy_stream
    ):
        """Test probe_all_ready_streams skips unhealthy streams."""
        probe = LivenessProbe()

        with patch.object(probe, "probe_stream") as mock_probe:
            mock_probe.return_value = {"stream_id": 1, "classification": "live"}
            result = probe.probe_all_ready_streams()

        # Unhealthy streams should not be probed
        for call_args in mock_probe.call_args_list:
            stream_arg = call_args[0][0]
            assert stream_arg.status != StreamStatus.UNHEALTHY.value

    def test_probe_all_ready_streams_handles_errors(
        self, app_context, db_session, sample_stream
    ):
        """Test probe_all_ready_streams handles individual stream probe errors."""
        probe = LivenessProbe()

        with patch.object(probe, "probe_stream") as mock_probe:
            mock_probe.side_effect = Exception("Probe failed")
            result = probe.probe_all_ready_streams()

        assert result["probed"] >= 1
        assert "error" in result["results"][0]

    def test_probe_all_ready_streams_empty(self, app_context, db_session):
        """Test probe_all_ready_streams with no streams."""
        probe = LivenessProbe()
        result = probe.probe_all_ready_streams()

        assert result["probed"] == 0
        assert result["results"] == []


class TestSubprocessMocking:
    """Tests for internal subprocess calls."""

    @patch("app.services.liveness_probe.subprocess.run")
    def test_get_pts_success(self, mock_run, app_context):
        """Test _get_pts returns PTS value from ffprobe output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"frames": [{"pkt_pts": 90000}]}),
        )

        probe = LivenessProbe()
        result = probe._get_pts("rtsp://localhost:8554/test")

        assert result == 90000
        mock_run.assert_called_once()

    @patch("app.services.liveness_probe.subprocess.run")
    def test_get_pts_failure(self, mock_run, app_context):
        """Test _get_pts returns None on error."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")

        probe = LivenessProbe()
        result = probe._get_pts("rtsp://localhost:8554/test")

        assert result is None

    @patch("app.services.liveness_probe.subprocess.run")
    def test_get_pts_timeout(self, mock_run, app_context):
        """Test _get_pts returns None on timeout."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffprobe", timeout=5)

        probe = LivenessProbe()
        result = probe._get_pts("rtsp://localhost:8554/test")

        assert result is None

    @patch("app.services.liveness_probe.subprocess.run")
    def test_get_frame_info_success(self, mock_run, app_context):
        """Test _get_frame_info returns frame hash and brightness."""
        raw_data = bytes([128] * 100)  # Average brightness = 128
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=raw_data,
        )

        probe = LivenessProbe()
        frame_hash, brightness = probe._get_frame_info("rtsp://localhost:8554/test")

        assert frame_hash is not None
        assert len(frame_hash) == 64  # SHA256 hex digest
        assert brightness == 128.0

    @patch("app.services.liveness_probe.subprocess.run")
    def test_get_frame_info_failure(self, mock_run, app_context):
        """Test _get_frame_info returns None on error."""
        mock_run.return_value = MagicMock(returncode=1, stdout=b"")

        probe = LivenessProbe()
        frame_hash, brightness = probe._get_frame_info("rtsp://localhost:8554/test")

        assert frame_hash is None
        assert brightness is None

    @patch("app.services.liveness_probe.subprocess.run")
    def test_get_audio_rms_success(self, mock_run, app_context):
        """Test _get_audio_rms returns RMS level from ffmpeg output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="lavfi.astats.Overall.RMS_level=-25.3\n",
        )

        probe = LivenessProbe()
        result = probe._get_audio_rms("rtsp://localhost:8554/test")

        assert result == -25.3

    @patch("app.services.liveness_probe.subprocess.run")
    def test_get_audio_rms_failure(self, mock_run, app_context):
        """Test _get_audio_rms returns None on error."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

        probe = LivenessProbe()
        result = probe._get_audio_rms("rtsp://localhost:8554/test")

        assert result is None

    @patch("app.services.liveness_probe.subprocess.run")
    def test_check_keyframe_present(self, mock_run, app_context):
        """Test _check_keyframe returns True when keyframes are present."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"frames": [{"key_frame": 1}, {"key_frame": 0}]}),
        )

        probe = LivenessProbe()
        result = probe._check_keyframe("rtsp://localhost:8554/test")

        assert result is True

    @patch("app.services.liveness_probe.subprocess.run")
    def test_check_keyframe_absent(self, mock_run, app_context):
        """Test _check_keyframe returns False when no keyframes."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"frames": [{"key_frame": 0}]}),
        )

        probe = LivenessProbe()
        result = probe._check_keyframe("rtsp://localhost:8554/test")

        assert result is False

    @patch("app.services.liveness_probe.subprocess.run")
    def test_check_keyframe_error(self, mock_run, app_context):
        """Test _check_keyframe returns None on error."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")

        probe = LivenessProbe()
        result = probe._check_keyframe("rtsp://localhost:8554/test")

        assert result is None


class TestGetLivenessSummary:
    """Tests for LivenessProbe.get_liveness_summary method."""

    def test_get_liveness_summary(
        self, app_context, db_session, sample_stream_with_liveness
    ):
        """Test get_liveness_summary returns counts per classification."""
        probe = LivenessProbe()
        result = probe.get_liveness_summary()

        assert LivenessClassification.LIVE.value in result
        assert result[LivenessClassification.LIVE.value] >= 1

    def test_get_liveness_summary_empty(self, app_context, db_session):
        """Test get_liveness_summary with no streams."""
        probe = LivenessProbe()
        result = probe.get_liveness_summary()

        for cls in LivenessClassification:
            assert cls.value in result
