"""
Tests for ThumbnailService.
"""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.thumbnail_service import ThumbnailService


class TestThumbnailService:
    """Tests for ThumbnailService."""

    def test_init_creates_directory(self, app_context):
        """Test that init creates thumbnail directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            thumb_dir = os.path.join(temp_dir, "thumbnails")

            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", thumb_dir
            ):
                service = ThumbnailService()
                assert service.thumbnail_dir.exists()

    def test_get_thumbnail_path(self, app_context):
        """Test thumbnail path generation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()
                path = service._get_thumbnail_path("test/stream1", 1)

                assert path.suffix == ".jpg"
                assert path.parent == Path(temp_dir)

    def test_get_hls_url(self, app_context):
        """Test HLS URL derivation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()
                url = service._get_hls_url(
                    "test/stream1", "http://localhost:9998"
                )

                assert "test/stream1" in url
                assert "index.m3u8" in url

    def test_is_thumbnail_fresh_nonexistent(self, app_context):
        """Test freshness check for nonexistent thumbnail."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()
                path = Path(temp_dir) / "nonexistent.jpg"

                assert service._is_thumbnail_fresh(path) is False

    def test_is_thumbnail_fresh_old(self, app_context):
        """Test freshness check for old thumbnail."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ), patch(
                "app.services.thumbnail_service.THUMBNAIL_CACHE_SECONDS", 300
            ):
                service = ThumbnailService()
                path = Path(temp_dir) / "old.jpg"

                # Create old file
                with open(path, "wb") as f:
                    f.write(b"test")

                # Set mtime to old time
                old_time = datetime.now() - timedelta(seconds=600)
                os.utime(path, (old_time.timestamp(), old_time.timestamp()))

                assert service._is_thumbnail_fresh(path) is False

    def test_is_thumbnail_fresh_recent(self, app_context):
        """Test freshness check for recent thumbnail."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ), patch(
                "app.services.thumbnail_service.THUMBNAIL_CACHE_SECONDS", 300
            ):
                service = ThumbnailService()
                path = Path(temp_dir) / "recent.jpg"

                # Create recent file
                with open(path, "wb") as f:
                    f.write(b"test")

                assert service._is_thumbnail_fresh(path) is True

    def test_generate_thumbnail_cached(self, app_context):
        """Test generate thumbnail returns cached version."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()

                # Create a cached thumbnail
                thumb_path = service._get_thumbnail_path("test/stream1", 1)
                with open(thumb_path, "wb") as f:
                    f.write(b"cached thumbnail")

                result = service.generate_thumbnail(
                    "test/stream1", 1, "http://localhost:9998"
                )

                assert result == str(thumb_path)

    def test_generate_thumbnail_ffmpeg_success(self, app_context, mock_subprocess):
        """Test thumbnail generation with ffmpeg success."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()

                # Mock successful ffmpeg run
                thumb_path = service._get_thumbnail_path("test/stream1", 1)

                def create_thumbnail(*args, **kwargs):
                    with open(thumb_path, "wb") as f:
                        f.write(b"thumbnail data")
                    return MagicMock(returncode=0)

                mock_subprocess["run"].side_effect = create_thumbnail

                result = service.generate_thumbnail(
                    "test/stream1", 1, "http://localhost:9998", force=True
                )

                assert result is not None
                assert os.path.exists(result)

    def test_generate_thumbnail_ffmpeg_failure(self, app_context, mock_subprocess):
        """Test thumbnail generation with ffmpeg failure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()

                # Mock failed ffmpeg run
                mock_subprocess["run"].return_value = MagicMock(
                    returncode=1, stderr="error"
                )

                result = service.generate_thumbnail(
                    "test/stream1", 1, "http://localhost:9998", force=True
                )

                assert result is None

    def test_generate_thumbnail_timeout(self, app_context, mock_subprocess):
        """Test thumbnail generation with timeout."""
        import subprocess

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()

                mock_subprocess["run"].side_effect = subprocess.TimeoutExpired(
                    cmd="ffmpeg", timeout=10
                )

                result = service.generate_thumbnail(
                    "test/stream1", 1, "http://localhost:9998", force=True
                )

                assert result is None

    def test_generate_thumbnail_exception(self, app_context, mock_subprocess):
        """Test thumbnail generation with exception."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()

                mock_subprocess["run"].side_effect = Exception("Unexpected error")

                result = service.generate_thumbnail(
                    "test/stream1", 1, "http://localhost:9998", force=True
                )

                assert result is None

    def test_get_cached_thumbnail_fresh(self, app_context):
        """Test getting cached thumbnail that is fresh."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()

                # Create a fresh thumbnail
                thumb_path = service._get_thumbnail_path("test/stream1", 1)
                with open(thumb_path, "wb") as f:
                    f.write(b"cached")

                result = service.get_cached_thumbnail("test/stream1", 1)

                assert result == str(thumb_path)

    def test_get_cached_thumbnail_stale(self, app_context):
        """Test getting cached thumbnail that is stale."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ), patch(
                "app.services.thumbnail_service.THUMBNAIL_CACHE_SECONDS", 1
            ):
                service = ThumbnailService()

                # Create a stale thumbnail
                thumb_path = service._get_thumbnail_path("test/stream1", 1)
                with open(thumb_path, "wb") as f:
                    f.write(b"stale")

                # Set mtime to old time
                old_time = datetime.now() - timedelta(seconds=10)
                os.utime(thumb_path, (old_time.timestamp(), old_time.timestamp()))

                result = service.get_cached_thumbnail("test/stream1", 1)

                assert result is None

    def test_get_thumbnail_generates_if_needed(self, app_context, mock_subprocess):
        """Test get_thumbnail generates if not cached."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()

                thumb_path = service._get_thumbnail_path("test/stream1", 1)

                def create_thumbnail(*args, **kwargs):
                    with open(thumb_path, "wb") as f:
                        f.write(b"thumbnail data")
                    return MagicMock(returncode=0)

                mock_subprocess["run"].side_effect = create_thumbnail

                result = service.get_thumbnail(
                    "test/stream1", 1, "http://localhost:9998"
                )

                assert result is not None

    def test_get_thumbnail_url(self, app_context):
        """Test getting thumbnail URL."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()
                url = service.get_thumbnail_url("test/stream1", 1)

                assert url.startswith("/api/streams/thumbnail/")
                assert url.endswith(".jpg")

    def test_cleanup_old_thumbnails(self, app_context):
        """Test cleaning up old thumbnails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()

                # Create old thumbnail
                old_path = Path(temp_dir) / "old_thumb.jpg"
                with open(old_path, "wb") as f:
                    f.write(b"old")

                # Set mtime to 48 hours ago
                old_time = datetime.now() - timedelta(hours=48)
                os.utime(old_path, (old_time.timestamp(), old_time.timestamp()))

                # Create recent thumbnail
                recent_path = Path(temp_dir) / "recent_thumb.jpg"
                with open(recent_path, "wb") as f:
                    f.write(b"recent")

                removed = service.cleanup_old_thumbnails(max_age_hours=24)

                assert removed == 1
                assert not old_path.exists()
                assert recent_path.exists()

    def test_cleanup_old_thumbnails_none_old(self, app_context):
        """Test cleanup when no old thumbnails exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.services.thumbnail_service.THUMBNAIL_DIR", temp_dir
            ):
                service = ThumbnailService()

                # Create only recent thumbnail
                recent_path = Path(temp_dir) / "recent_thumb.jpg"
                with open(recent_path, "wb") as f:
                    f.write(b"recent")

                removed = service.cleanup_old_thumbnails(max_age_hours=24)

                assert removed == 0
                assert recent_path.exists()
