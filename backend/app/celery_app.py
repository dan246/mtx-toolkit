"""
Celery application configuration.
Background tasks for health checking, remediation, and retention.
"""
from celery import Celery
from celery.schedules import crontab
import os

# Create Celery app
celery_app = Celery(
    'mtx_toolkit',
    broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    include=['app.tasks']
)

# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    worker_prefetch_multiplier=1,
)

# Scheduled tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    # Quick health check every 10 seconds (API-based, very fast)
    'quick-health-check': {
        'task': 'app.tasks.quick_check_all_nodes',
        'schedule': 10.0,
    },
    # Deep health check (ffprobe) every 5 minutes for detailed diagnostics
    'deep-health-check': {
        'task': 'app.tasks.check_all_streams_health',
        'schedule': 300.0,
    },
    # Sync all fleet nodes every 5 minutes
    'sync-fleet-nodes': {
        'task': 'app.tasks.sync_all_fleet_nodes',
        'schedule': 300.0,
    },
    # Retention cleanup every hour
    'retention-cleanup': {
        'task': 'app.tasks.run_retention_cleanup',
        'schedule': crontab(minute=0),  # Every hour
    },
    # Archive old recordings daily at 3 AM
    'archive-recordings': {
        'task': 'app.tasks.archive_old_recordings',
        'schedule': crontab(hour=3, minute=0),
    },
}
