"""
Celery tasks for background processing.
"""
from app.celery_app import celery_app
from app import create_app, db
from app.models import Stream, MediaMTXNode, Recording, StreamStatus
from datetime import datetime, timedelta


@celery_app.task(bind=True, soft_time_limit=60, time_limit=90)
def quick_check_all_nodes(self):
    """
    Fast health check using MediaMTX API.
    Can check 1000+ streams in seconds.
    """
    app = create_app()
    with app.app_context():
        from app.services.health_checker import HealthChecker
        checker = HealthChecker()
        return checker.quick_check_all_nodes()


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660)
def check_all_streams_health(self):
    """Check health of all streams using parallel sub-tasks."""
    from celery import group

    app = create_app()
    with app.app_context():
        # Get streams that need checking
        streams = Stream.query.filter_by(status=StreamStatus.UNKNOWN.value).limit(10).all()
        streams += Stream.query.filter(
            Stream.last_check < datetime.utcnow() - timedelta(seconds=30)
        ).limit(20).all()

        if not streams:
            return {'checked': 0, 'results': []}

        # Dispatch parallel probe tasks
        stream_ids = [s.id for s in streams]
        job = group(probe_stream_task.s(sid) for sid in stream_ids)
        result = job.apply_async()

        # Wait for results with timeout
        try:
            results = result.get(timeout=300)
        except Exception as e:
            return {'checked': len(stream_ids), 'error': str(e), 'partial': True}

        return {'checked': len(results), 'results': results}


@celery_app.task(bind=True)
def sync_all_fleet_nodes(self):
    """Sync streams from all active fleet nodes."""
    app = create_app()
    with app.app_context():
        from app.services.fleet_manager import FleetManager

        manager = FleetManager()
        result = manager.sync_all_nodes()
        return result


@celery_app.task(bind=True)
def run_retention_cleanup(self):
    """Run retention cleanup."""
    app = create_app()
    with app.app_context():
        from app.services.retention_manager import RetentionManager

        manager = RetentionManager()
        result = manager.cleanup(dry_run=False)
        return result


@celery_app.task(bind=True)
def archive_old_recordings(self):
    """Archive recordings older than threshold."""
    app = create_app()
    with app.app_context():
        from app.services.retention_manager import RetentionManager

        manager = RetentionManager()
        policy = manager.get_policy()
        archive_after_days = policy.get('archive_after_days', 3)

        # Find recordings to archive
        threshold = datetime.utcnow() - timedelta(days=archive_after_days)
        recordings = Recording.query.filter(
            Recording.start_time < threshold,
            Recording.is_archived == False
        ).limit(50).all()

        archived = 0
        for recording in recordings:
            result = manager.archive_recording(recording)
            if result.get('success'):
                archived += 1

        return {'archived': archived, 'total_checked': len(recordings)}


@celery_app.task(bind=True, soft_time_limit=30, time_limit=45)
def probe_stream_task(self, stream_id: int):
    """Probe a specific stream (async task)."""
    app = create_app()
    with app.app_context():
        from app.services.health_checker import HealthChecker
        from app.services.auto_remediation import AutoRemediation

        checker = HealthChecker()
        result = checker.probe_stream(stream_id)

        # Auto-remediate if unhealthy
        stream = Stream.query.get(stream_id)
        if stream and stream.status == StreamStatus.UNHEALTHY.value:
            remediation = AutoRemediation()
            if remediation.should_auto_remediate(stream):
                remediation.remediate_stream(stream)

        return result


@celery_app.task(bind=True)
def remediate_stream_task(self, stream_id: int):
    """Remediate a specific stream (async task)."""
    app = create_app()
    with app.app_context():
        from app.services.auto_remediation import AutoRemediation
        from app.models import Stream

        stream = Stream.query.get(stream_id)
        if not stream:
            return {'error': 'Stream not found'}

        remediation = AutoRemediation()
        return remediation.remediate_stream(stream)
