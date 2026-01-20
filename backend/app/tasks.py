"""
Celery tasks for background processing.
"""

from datetime import datetime, timedelta

from app import create_app, db
from app.celery_app import celery_app
from app.models import Recording, Stream, StreamStatus

# 建立共享的 Flask app 實例，避免每個 task 都建立新的連線池
_app = None


def get_app():
    """Get or create the shared Flask app instance."""
    global _app
    if _app is None:
        _app = create_app()
    return _app


@celery_app.task(bind=True, soft_time_limit=60, time_limit=90)
def quick_check_all_nodes(self):
    """
    Fast health check using MediaMTX API.
    Can check 1000+ streams in seconds.
    """
    app = get_app()
    with app.app_context():
        from app.services.health_checker import HealthChecker

        checker = HealthChecker()
        return checker.quick_check_all_nodes()


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660)
def check_all_streams_health(self):
    """Deep check streams using ffprobe to get FPS, codec, etc."""
    from celery import group

    app = get_app()
    with app.app_context():
        # Get all streams that need deep probe (no FPS data)
        streams = Stream.query.filter((Stream.fps.is_(None)) | (Stream.fps == 0)).all()

        # If all have FPS, rotate through healthy streams to keep data fresh
        if not streams:
            streams = (
                Stream.query.filter(Stream.status == StreamStatus.HEALTHY.value)
                .order_by(Stream.updated_at.asc())
                .limit(50)
                .all()
            )

        if not streams:
            return {"checked": 0, "results": []}

        # Dispatch parallel probe tasks
        stream_ids = [s.id for s in streams]
        job = group(probe_stream_task.s(sid) for sid in stream_ids)
        result = job.apply_async()

        # Wait for results with timeout
        try:
            results = result.get(timeout=300)
        except Exception as e:
            return {"checked": len(stream_ids), "error": str(e), "partial": True}

        return {"checked": len(results), "results": results}


@celery_app.task(bind=True)
def sync_all_fleet_nodes(self):
    """Sync streams from all active fleet nodes."""
    app = get_app()
    with app.app_context():
        from app.services.fleet_manager import FleetManager

        manager = FleetManager()
        result = manager.sync_all_nodes()
        return result


@celery_app.task(bind=True)
def run_retention_cleanup(self):
    """Run retention cleanup."""
    app = get_app()
    with app.app_context():
        from app.services.retention_manager import RetentionManager

        manager = RetentionManager()
        result = manager.cleanup(dry_run=False)
        return result


@celery_app.task(bind=True)
def archive_old_recordings(self):
    """Archive recordings older than threshold."""
    app = get_app()
    with app.app_context():
        from app.services.retention_manager import RetentionManager

        manager = RetentionManager()
        policy = manager.get_policy()
        archive_after_days = policy.get("archive_after_days", 3)

        # Find recordings to archive
        threshold = datetime.utcnow() - timedelta(days=archive_after_days)
        recordings = (
            Recording.query.filter(
                Recording.start_time < threshold, Recording.is_archived.is_(False)
            )
            .limit(50)
            .all()
        )

        archived = 0
        for recording in recordings:
            result = manager.archive_recording(recording)
            if result.get("success"):
                archived += 1

        return {"archived": archived, "total_checked": len(recordings)}


@celery_app.task(bind=True, soft_time_limit=60, time_limit=90)
def probe_stream_task(self, stream_id: int):
    """Probe a specific stream (async task)."""
    app = get_app()
    with app.app_context():
        from app.services.health_checker import HealthChecker

        checker = HealthChecker()
        result = checker.probe_stream(stream_id)
        return result


@celery_app.task(bind=True)
def remediate_stream_task(self, stream_id: int):
    """Remediate a specific stream (async task)."""
    app = get_app()
    with app.app_context():
        from app.models import Stream
        from app.services.auto_remediation import AutoRemediation

        stream = Stream.query.get(stream_id)
        if not stream:
            return {"error": "Stream not found"}

        remediation = AutoRemediation()
        return remediation.remediate_stream(stream)


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360)
def generate_thumbnails_task(self):
    """Generate thumbnails for healthy streams."""
    app = get_app()
    with app.app_context():
        from app.models import MediaMTXNode
        from app.services.thumbnail_service import thumbnail_service

        # Get healthy streams, prioritize those without recent thumbnails
        streams = Stream.query.filter_by(status="healthy").limit(50).all()

        generated = 0
        failed = 0
        for stream in streams:
            node = MediaMTXNode.query.get(stream.node_id)
            if node:
                result = thumbnail_service.generate_thumbnail(
                    stream.path, node.id, node.api_url
                )
                if result:
                    generated += 1
                else:
                    failed += 1

        return {"generated": generated, "failed": failed, "total": len(streams)}


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180)
def scan_recordings_task(self):
    """Scan recording directory and index new files to database."""
    app = get_app()
    with app.app_context():
        from app.services.retention_manager import RetentionManager

        manager = RetentionManager()
        result = manager.scan_recordings(force_rescan=False)
        return result
