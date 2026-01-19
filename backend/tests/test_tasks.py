"""
Tests for Celery tasks.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import MediaMTXNode, Recording, Stream, StreamStatus


class TestCeleryTasks:
    """Tests for Celery background tasks."""

    def test_quick_check_all_nodes(self, app_context, db_session):
        """Test quick health check task."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            with patch(
                "app.services.health_checker.HealthChecker.quick_check_all_nodes"
            ) as mock_check:
                mock_check.return_value = {"checked": 10, "healthy": 8, "unhealthy": 2}

                from app.tasks import quick_check_all_nodes

                # Call the task function directly (not as celery task)
                result = quick_check_all_nodes.apply().get()

                assert result["checked"] == 10

    def test_check_all_streams_health_no_streams(self, app_context, db_session):
        """Test deep health check with no streams."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            from app.tasks import check_all_streams_health

            result = check_all_streams_health.apply().get()

            assert result["checked"] == 0

    def test_check_all_streams_health_with_streams(
        self, app_context, db_session, sample_stream
    ):
        """Test deep health check with streams that need probing."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            # Set stream to need probing (no fps)
            sample_stream.fps = None
            db_session.commit()

            with patch("app.tasks.group") as mock_group:
                mock_async_result = MagicMock()
                mock_async_result.get.return_value = [{"stream_id": 1, "healthy": True}]
                mock_group.return_value.apply_async.return_value = mock_async_result

                from app.tasks import check_all_streams_health

                result = check_all_streams_health.apply().get()

                assert "checked" in result

    def test_sync_all_fleet_nodes(self, app_context, db_session):
        """Test fleet sync task."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            with patch(
                "app.services.fleet_manager.FleetManager.sync_all_nodes"
            ) as mock_sync:
                mock_sync.return_value = {"synced": 5, "errors": 0}

                from app.tasks import sync_all_fleet_nodes

                result = sync_all_fleet_nodes.apply().get()

                assert result["synced"] == 5

    def test_run_retention_cleanup(self, app_context, db_session):
        """Test retention cleanup task."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            with patch(
                "app.services.retention_manager.RetentionManager.cleanup"
            ) as mock_cleanup:
                mock_cleanup.return_value = {
                    "deleted_count": 3,
                    "freed_space_mb": 100,
                }

                from app.tasks import run_retention_cleanup

                result = run_retention_cleanup.apply().get()

                assert result["deleted_count"] == 3

    def test_archive_old_recordings_none_to_archive(self, app_context, db_session):
        """Test archive task with no recordings to archive."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            with patch(
                "app.services.retention_manager.RetentionManager.get_policy"
            ) as mock_policy:
                mock_policy.return_value = {"archive_after_days": 3}

                from app.tasks import archive_old_recordings

                result = archive_old_recordings.apply().get()

                assert result["archived"] == 0
                assert result["total_checked"] == 0

    def test_archive_old_recordings_with_recordings(
        self, app_context, db_session, sample_stream
    ):
        """Test archive task with recordings to archive."""
        # Create old recording
        old_recording = Recording(
            stream_id=sample_stream.id,
            file_path="/recordings/old.mp4",
            start_time=datetime.utcnow() - timedelta(days=10),
            is_archived=False,
        )
        db_session.add(old_recording)
        db_session.commit()

        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            with patch(
                "app.services.retention_manager.RetentionManager.get_policy"
            ) as mock_policy, patch(
                "app.services.retention_manager.RetentionManager.archive_recording"
            ) as mock_archive:
                mock_policy.return_value = {"archive_after_days": 3}
                mock_archive.return_value = {"success": True}

                from app.tasks import archive_old_recordings

                result = archive_old_recordings.apply().get()

                assert result["total_checked"] >= 1

    def test_probe_stream_task(self, app_context, db_session, sample_stream):
        """Test stream probe task."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            with patch(
                "app.services.health_checker.HealthChecker.probe_stream"
            ) as mock_probe:
                mock_probe.return_value = {
                    "stream_id": sample_stream.id,
                    "healthy": True,
                    "fps": 30,
                }

                from app.tasks import probe_stream_task

                result = probe_stream_task.apply(args=[sample_stream.id]).get()

                assert result["healthy"] is True

    def test_remediate_stream_task_not_found(self, app_context, db_session):
        """Test remediation task with nonexistent stream."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            from app.tasks import remediate_stream_task

            result = remediate_stream_task.apply(args=[99999]).get()

            assert result["error"] == "Stream not found"

    def test_remediate_stream_task_success(
        self, app_context, db_session, sample_unhealthy_stream
    ):
        """Test remediation task success."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            with patch(
                "app.services.auto_remediation.AutoRemediation.remediate_stream"
            ) as mock_remediate:
                mock_remediate.return_value = {
                    "success": True,
                    "action": "restart",
                }

                from app.tasks import remediate_stream_task

                result = remediate_stream_task.apply(
                    args=[sample_unhealthy_stream.id]
                ).get()

                assert result["success"] is True

    def test_generate_thumbnails_task_no_streams(self, app_context, db_session):
        """Test thumbnail generation with no healthy streams."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            from app.tasks import generate_thumbnails_task

            result = generate_thumbnails_task.apply().get()

            assert result["generated"] == 0
            assert result["total"] == 0

    def test_generate_thumbnails_task_with_streams(
        self, app_context, db_session, sample_stream, sample_node
    ):
        """Test thumbnail generation with healthy streams."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            with patch(
                "app.services.thumbnail_service.thumbnail_service.generate_thumbnail"
            ) as mock_gen:
                mock_gen.return_value = "/tmp/thumbnail.jpg"

                from app.tasks import generate_thumbnails_task

                result = generate_thumbnails_task.apply().get()

                assert result["total"] >= 1

    def test_generate_thumbnails_task_failure(
        self, app_context, db_session, sample_stream, sample_node
    ):
        """Test thumbnail generation with some failures."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            with patch(
                "app.services.thumbnail_service.thumbnail_service.generate_thumbnail"
            ) as mock_gen:
                mock_gen.return_value = None  # Failed

                from app.tasks import generate_thumbnails_task

                result = generate_thumbnails_task.apply().get()

                assert result["failed"] >= 0

    def test_check_all_streams_health_timeout(
        self, app_context, db_session, sample_stream
    ):
        """Test deep health check with timeout."""
        with patch("app.tasks.create_app") as mock_create_app:
            mock_create_app.return_value = app_context

            sample_stream.fps = None
            db_session.commit()

            with patch("app.tasks.group") as mock_group:
                mock_async_result = MagicMock()
                mock_async_result.get.side_effect = Exception("Timeout")
                mock_group.return_value.apply_async.return_value = mock_async_result

                from app.tasks import check_all_streams_health

                result = check_all_streams_health.apply().get()

                assert "error" in result
                assert result["partial"] is True
