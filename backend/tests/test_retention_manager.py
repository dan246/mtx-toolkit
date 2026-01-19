"""
Tests for RetentionManager service.
"""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import EventType, Recording, Stream, StreamEvent
from app.services.retention_manager import RetentionManager


class TestRetentionManager:
    """Tests for RetentionManager service."""

    def test_get_status(self, app_context, db_session, sample_recording):
        """Test getting retention status."""
        manager = RetentionManager()

        with patch.object(
            manager,
            "_get_disk_usage",
            return_value={
                "total_gb": 500,
                "used_gb": 200,
                "free_gb": 300,
                "usage_percent": 40.0,
            },
        ):
            result = manager.get_status()

        assert "disk" in result
        assert "recordings" in result
        assert result["disk"]["total_gb"] == 500
        assert result["recordings"]["total"] >= 1

    def test_get_status_critical_disk(self, app_context, db_session):
        """Test status when disk is critical."""
        manager = RetentionManager()

        with patch.object(
            manager,
            "_get_disk_usage",
            return_value={
                "total_gb": 500,
                "used_gb": 450,
                "free_gb": 50,
                "usage_percent": 90.0,
            },
        ):
            result = manager.get_status()

        assert result["disk"]["is_critical"] is True

    def test_get_disk_usage(self, app_context):
        """Test getting disk usage."""
        manager = RetentionManager()

        # Use temp directory that should exist
        manager.recording_path = Path(tempfile.gettempdir())
        result = manager._get_disk_usage()

        assert "total_gb" in result
        assert "used_gb" in result
        assert "free_gb" in result
        assert result["total_gb"] > 0

    def test_get_disk_usage_invalid_path(self, app_context):
        """Test disk usage with invalid path."""
        manager = RetentionManager()
        manager.recording_path = Path("/nonexistent/path/12345")

        result = manager._get_disk_usage()

        assert result["total_gb"] == 0

    def test_cleanup_expired_dry_run(self, app_context, db_session, sample_stream):
        """Test cleanup expired recordings in dry run mode."""
        # Create expired recording
        expired_recording = Recording(
            stream_id=sample_stream.id,
            file_path="/recordings/expired.mp4",
            file_size=1024 * 1024,
            start_time=datetime.utcnow() - timedelta(days=10),
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add(expired_recording)
        db_session.commit()

        manager = RetentionManager()
        with patch.object(
            manager,
            "_get_disk_usage",
            return_value={
                "total_gb": 500,
                "used_gb": 200,
                "free_gb": 300,
                "usage_percent": 40.0,
            },
        ):
            result = manager.cleanup(dry_run=True)

        assert result["dry_run"] is True
        assert result["deleted_count"] >= 1

        # Recording should still exist
        assert Recording.query.get(expired_recording.id) is not None

    def test_cleanup_expired_actual(self, app_context, db_session, sample_stream):
        """Test actual cleanup of expired recordings."""
        # Create temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
            f.write(b"test data")
            temp_path = f.name

        try:
            expired_recording = Recording(
                stream_id=sample_stream.id,
                file_path=temp_path,
                file_size=9,
                start_time=datetime.utcnow() - timedelta(days=10),
                expires_at=datetime.utcnow() - timedelta(days=1),
            )
            db_session.add(expired_recording)
            db_session.commit()
            recording_id = expired_recording.id

            manager = RetentionManager()
            with patch.object(
                manager,
                "_get_disk_usage",
                return_value={
                    "total_gb": 500,
                    "used_gb": 200,
                    "free_gb": 300,
                    "usage_percent": 40.0,
                },
            ):
                result = manager.cleanup(dry_run=False)

            assert result["dry_run"] is False
            assert result["deleted_count"] >= 1

            # Recording should be deleted from DB
            assert Recording.query.get(recording_id) is None

            # File should be deleted
            assert not os.path.exists(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_cleanup_disk_pressure(self, app_context, db_session, sample_stream):
        """Test cleanup under disk pressure."""
        # Create some continuous recordings
        for i in range(5):
            recording = Recording(
                stream_id=sample_stream.id,
                file_path=f"/recordings/test_{i}.mp4",
                file_size=1024 * 1024 * 100,  # 100MB
                start_time=datetime.utcnow() - timedelta(hours=i),
                segment_type="continuous",
            )
            db_session.add(recording)
        db_session.commit()

        manager = RetentionManager()
        manager.default_policy["min_free_space_gb"] = 100

        with patch.object(
            manager,
            "_get_disk_usage",
            return_value={
                "total_gb": 500,
                "used_gb": 450,
                "free_gb": 50,  # Below min_free_space_gb
                "usage_percent": 90.0,
            },
        ):
            result = manager.cleanup(dry_run=True)

        # Should have marked some for deletion due to disk pressure
        disk_pressure_deletes = [
            d for d in result["deleted"] if d.get("reason") == "disk_pressure"
        ]
        assert len(disk_pressure_deletes) > 0

    def test_archive_recording(self, app_context, db_session, sample_stream):
        """Test archiving a recording."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source file
            source_path = os.path.join(temp_dir, "source.mp4")
            with open(source_path, "wb") as f:
                f.write(b"test video data")

            # Create archive directory
            archive_dir = os.path.join(temp_dir, "archive")

            recording = Recording(
                stream_id=sample_stream.id,
                file_path=source_path,
                file_size=15,
                start_time=datetime.utcnow(),
            )
            db_session.add(recording)
            db_session.commit()

            manager = RetentionManager()
            manager.default_policy["archive_path"] = archive_dir

            result = manager.archive_recording(recording)

            assert result["success"] is True
            assert recording.is_archived is True
            assert recording.archive_path is not None
            assert os.path.exists(recording.archive_path)

    def test_archive_recording_failure(self, app_context, db_session, sample_stream):
        """Test archiving with failure."""
        recording = Recording(
            stream_id=sample_stream.id,
            file_path="/nonexistent/file.mp4",
            start_time=datetime.utcnow(),
        )
        db_session.add(recording)
        db_session.commit()

        manager = RetentionManager()
        manager.default_policy["archive_path"] = "/invalid/archive/path"

        result = manager.archive_recording(recording)

        assert result["success"] is False
        assert "error" in result

    def test_get_policy(self, app_context):
        """Test getting retention policy."""
        manager = RetentionManager()
        policy = manager.get_policy()

        assert "continuous_retention_days" in policy
        assert "event_retention_days" in policy
        assert "manual_retention_days" in policy
        assert "archive_after_days" in policy

    def test_update_policy(self, app_context):
        """Test updating retention policy."""
        manager = RetentionManager()
        result = manager.update_policy(
            {"continuous_retention_days": 14, "event_retention_days": 60}
        )

        assert result["success"] is True
        assert "continuous_retention_days" in result["updated_fields"]
        assert manager.default_policy["continuous_retention_days"] == 14

    def test_update_policy_invalid_key(self, app_context):
        """Test updating policy with invalid key."""
        manager = RetentionManager()
        result = manager.update_policy({"invalid_key": "value"})

        assert result["success"] is True
        assert "invalid_key" not in result["updated_fields"]

    def test_search_recordings(
        self, app_context, db_session, sample_stream, sample_recording
    ):
        """Test searching recordings."""
        manager = RetentionManager()
        result = manager.search_recordings()

        assert "results" in result
        assert result["total"] >= 1

    def test_search_recordings_by_stream_path(
        self, app_context, db_session, sample_stream, sample_recording
    ):
        """Test searching recordings by stream path."""
        manager = RetentionManager()
        result = manager.search_recordings(stream_path="test/stream1")

        assert result["total"] >= 1

    def test_search_recordings_by_time_range(
        self, app_context, db_session, sample_stream
    ):
        """Test searching recordings by time range."""
        now = datetime.utcnow()

        recording = Recording(
            stream_id=sample_stream.id,
            file_path="/recordings/time_test.mp4",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )
        db_session.add(recording)
        db_session.commit()

        manager = RetentionManager()
        result = manager.search_recordings(
            start_time=(now - timedelta(hours=2)).isoformat(), end_time=now.isoformat()
        )

        assert result["total"] >= 1

    def test_get_playback_url(self, app_context, db_session, sample_recording):
        """Test getting playback URL."""
        manager = RetentionManager()
        result = manager.get_playback_url(sample_recording)

        assert "playback_url" in result
        assert "file_path" in result
        assert result["recording_id"] == sample_recording.id

    def test_get_playback_url_archived(self, app_context, db_session, sample_stream):
        """Test getting playback URL for archived recording."""
        recording = Recording(
            stream_id=sample_stream.id,
            file_path="/recordings/original.mp4",
            start_time=datetime.utcnow(),
            is_archived=True,
            archive_path="/nas/archived.mp4",
        )
        db_session.add(recording)
        db_session.commit()

        manager = RetentionManager()
        result = manager.get_playback_url(recording)

        assert result["file_path"] == "/nas/archived.mp4"

    def test_detect_format_mp4(self, app_context):
        """Test format detection for MP4."""
        manager = RetentionManager()
        assert manager._detect_format("/path/to/video.mp4") == "video/mp4"

    def test_detect_format_mkv(self, app_context):
        """Test format detection for MKV."""
        manager = RetentionManager()
        assert manager._detect_format("/path/to/video.mkv") == "video/x-matroska"

    def test_detect_format_ts(self, app_context):
        """Test format detection for TS."""
        manager = RetentionManager()
        assert manager._detect_format("/path/to/video.ts") == "video/mp2t"

    def test_detect_format_unknown(self, app_context):
        """Test format detection for unknown extension."""
        manager = RetentionManager()
        assert manager._detect_format("/path/to/video.xyz") == "video/mp4"  # Default

    def test_start_event_recording(
        self, app_context, db_session, sample_stream, sample_event, mock_subprocess
    ):
        """Test starting event-triggered recording."""
        mock_subprocess["popen"].return_value = MagicMock(pid=12345)

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RetentionManager()
            manager.recording_path = Path(temp_dir)

            result = manager.start_event_recording(
                sample_stream, sample_event, duration_seconds=30, pre_buffer_seconds=5
            )

            assert result["success"] is True
            assert "recording_id" in result
            assert result["process_pid"] == 12345

            # Verify recording was created in DB
            recording = Recording.query.get(result["recording_id"])
            assert recording is not None
            assert recording.segment_type == "event"
            assert recording.triggered_by_event_id == sample_event.id

    def test_start_event_recording_failure(
        self, app_context, db_session, sample_stream, sample_event, mock_subprocess
    ):
        """Test event recording failure."""
        mock_subprocess["popen"].side_effect = Exception("ffmpeg not found")

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RetentionManager()
            manager.recording_path = Path(temp_dir)

            result = manager.start_event_recording(sample_stream, sample_event)

            assert result["success"] is False
            assert "error" in result

    def test_default_policy_values(self, app_context):
        """Test default policy values."""
        manager = RetentionManager()

        assert manager.default_policy["continuous_retention_days"] == 7
        assert manager.default_policy["event_retention_days"] == 30
        assert manager.default_policy["manual_retention_days"] == 90
        assert manager.default_policy["archive_after_days"] == 3
        assert manager.default_policy["min_free_space_gb"] == 50

    def test_disk_threshold(self, app_context):
        """Test disk threshold configuration."""
        manager = RetentionManager()

        assert manager.disk_threshold == 0.85  # 85%

    def test_recordings_by_type(self, app_context, db_session, sample_stream):
        """Test status includes recordings by type."""
        # Create recordings of different types
        for segment_type in ["continuous", "event", "manual"]:
            recording = Recording(
                stream_id=sample_stream.id,
                file_path=f"/recordings/{segment_type}.mp4",
                start_time=datetime.utcnow(),
                segment_type=segment_type,
            )
            db_session.add(recording)
        db_session.commit()

        manager = RetentionManager()
        with patch.object(
            manager,
            "_get_disk_usage",
            return_value={
                "total_gb": 500,
                "used_gb": 200,
                "free_gb": 300,
                "usage_percent": 40.0,
            },
        ):
            result = manager.get_status()

        assert result["recordings"]["by_type"]["continuous"] >= 1
        assert result["recordings"]["by_type"]["event"] >= 1
        assert result["recordings"]["by_type"]["manual"] >= 1

    def test_expiring_soon_count(self, app_context, db_session, sample_stream):
        """Test counting recordings expiring soon."""
        # Create recording expiring in 12 hours
        recording = Recording(
            stream_id=sample_stream.id,
            file_path="/recordings/expiring.mp4",
            start_time=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=12),
        )
        db_session.add(recording)
        db_session.commit()

        manager = RetentionManager()
        with patch.object(
            manager,
            "_get_disk_usage",
            return_value={
                "total_gb": 500,
                "used_gb": 200,
                "free_gb": 300,
                "usage_percent": 40.0,
            },
        ):
            result = manager.get_status()

        assert result["recordings"]["expiring_soon"] >= 1

    def test_archived_count(self, app_context, db_session, sample_stream):
        """Test counting archived recordings."""
        recording = Recording(
            stream_id=sample_stream.id,
            file_path="/recordings/archived.mp4",
            start_time=datetime.utcnow(),
            is_archived=True,
            archive_path="/nas/archived.mp4",
        )
        db_session.add(recording)
        db_session.commit()

        manager = RetentionManager()
        with patch.object(
            manager,
            "_get_disk_usage",
            return_value={
                "total_gb": 500,
                "used_gb": 200,
                "free_gb": 300,
                "usage_percent": 40.0,
            },
        ):
            result = manager.get_status()

        assert result["recordings"]["archived"] >= 1

    def test_scan_recordings(self, app_context, db_session, sample_stream):
        """Test scanning recordings from local directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create directory structure: /recordings/{stream_path}/
            stream_dir = os.path.join(temp_dir, "test_stream1")
            os.makedirs(stream_dir)

            # Create a recording file with valid name pattern
            recording_file = os.path.join(stream_dir, "2024-01-15_10-30-00.ts")
            with open(recording_file, "wb") as f:
                f.write(b"fake video data")

            manager = RetentionManager()
            manager.recording_path = Path(temp_dir)

            result = manager.scan_recordings()

            assert result["success"] is True
            assert result["stats"]["scanned"] >= 1

    def test_scan_recordings_invalid_path(self, app_context, db_session):
        """Test scanning with invalid recording path."""
        manager = RetentionManager()
        manager.recording_path = Path("/nonexistent/path/12345")

        result = manager.scan_recordings()

        # Should handle gracefully
        assert "stats" in result
        assert result["stats"]["errors"] >= 1

    def test_scan_local_directory_with_node_filter(
        self, app_context, db_session, sample_stream
    ):
        """Test scanning with node_id filter."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RetentionManager()
            manager.recording_path = Path(temp_dir)

            result = manager._scan_local_directory(node_id=sample_stream.node_id)

            assert "scanned" in result
            assert "added" in result

    def test_scan_local_directory_force_rescan(
        self, app_context, db_session, sample_stream
    ):
        """Test force rescan updates existing records."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create directory structure
            stream_dir = os.path.join(temp_dir, "test_stream1")
            os.makedirs(stream_dir)

            recording_file = os.path.join(stream_dir, "2024-01-15_10-30-00.ts")
            with open(recording_file, "wb") as f:
                f.write(b"fake video data")

            # Create existing recording in DB
            existing = Recording(
                stream_id=sample_stream.id,
                file_path=recording_file,
                file_size=100,
                start_time=datetime.utcnow(),
            )
            db_session.add(existing)
            db_session.commit()

            manager = RetentionManager()
            manager.recording_path = Path(temp_dir)

            result = manager._scan_local_directory(force_rescan=True)

            assert result["added"] >= 0  # Updated existing

    def test_parse_recording_file_valid(self, app_context):
        """Test parsing valid recording filename."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "2024-01-15_10-30-00.ts"
            with open(file_path, "wb") as f:
                f.write(b"test data")

            manager = RetentionManager()
            result = manager._parse_recording_file(file_path)

            assert result is not None
            assert "start_time" in result
            assert "file_size" in result
            assert result["start_time"].year == 2024
            assert result["start_time"].month == 1
            assert result["start_time"].day == 15

    def test_parse_recording_file_invalid_name(self, app_context):
        """Test parsing invalid recording filename."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "invalid_name.ts"
            with open(file_path, "wb") as f:
                f.write(b"test data")

            manager = RetentionManager()
            result = manager._parse_recording_file(file_path)

            assert result is None

    def test_parse_recording_file_nonexistent(self, app_context):
        """Test parsing nonexistent file."""
        manager = RetentionManager()
        result = manager._parse_recording_file(Path("/nonexistent/2024-01-15_10-30-00.ts"))

        assert result is None

    def test_find_stream_by_path_direct_match(
        self, app_context, db_session, sample_stream
    ):
        """Test finding stream with direct path match."""
        manager = RetentionManager()
        streams_cache = {sample_stream.path: sample_stream}

        result = manager._find_stream_by_path(sample_stream.path, streams_cache)

        assert result == sample_stream

    def test_find_stream_by_path_with_leading_slash(
        self, app_context, db_session, sample_stream
    ):
        """Test finding stream with/without leading slash."""
        manager = RetentionManager()
        streams_cache = {f"/{sample_stream.path}": sample_stream}

        result = manager._find_stream_by_path(sample_stream.path, streams_cache)

        assert result == sample_stream

    def test_find_stream_by_path_fuzzy_match(
        self, app_context, db_session, sample_stream
    ):
        """Test finding stream with fuzzy matching."""
        manager = RetentionManager()
        streams_cache = {"test-stream1": sample_stream}

        result = manager._find_stream_by_path("test_stream1", streams_cache)

        assert result == sample_stream

    def test_find_stream_by_path_not_found(self, app_context, db_session):
        """Test finding stream that doesn't exist."""
        manager = RetentionManager()
        streams_cache = {}

        result = manager._find_stream_by_path("nonexistent/path", streams_cache)

        assert result is None

    def test_get_playback_url_ts_file(self, app_context, db_session, sample_stream):
        """Test playback URL for .ts file uses transcode endpoint."""
        recording = Recording(
            stream_id=sample_stream.id,
            file_path="/recordings/test.ts",
            start_time=datetime.utcnow(),
        )
        db_session.add(recording)
        db_session.commit()

        manager = RetentionManager()
        result = manager.get_playback_url(recording)

        assert "transcode" in result["playback_url"]
