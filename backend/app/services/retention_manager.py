"""
Retention Manager Service.
Recording retention, disk management, and archival.
"""
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import subprocess
import json

from flask import current_app
from app import db
from app.models import Recording, Stream, StreamEvent


class RetentionManager:
    """
    Recording retention and storage management.

    Features:
    - Event-triggered segmented recording
    - Disk usage protection
    - NAS archival
    - SQLite/Postgres indexing for playback
    """

    def __init__(self):
        self.recording_path = Path(
            current_app.config.get('RECORDING_BASE_PATH', '/recordings')
        ) if current_app else Path('/recordings')
        self.disk_threshold = (
            current_app.config.get('DISK_USAGE_THRESHOLD', 0.85)
        ) if current_app else 0.85

        # Default retention policy
        self.default_policy = {
            'continuous_retention_days': 7,
            'event_retention_days': 30,
            'manual_retention_days': 90,
            'archive_after_days': 3,
            'min_free_space_gb': 50,
            'archive_path': '/mnt/nas/recordings'
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current retention and disk status."""
        disk_usage = self._get_disk_usage()

        # Get recording stats
        total_recordings = Recording.query.count()
        total_size = db.session.query(db.func.sum(Recording.file_size)).scalar() or 0

        # Recordings by type
        continuous = Recording.query.filter_by(segment_type='continuous').count()
        event_triggered = Recording.query.filter_by(segment_type='event').count()
        manual = Recording.query.filter_by(segment_type='manual').count()

        # Expiring soon (next 24h)
        expiring_soon = Recording.query.filter(
            Recording.expires_at <= datetime.utcnow() + timedelta(hours=24),
            Recording.expires_at > datetime.utcnow()
        ).count()

        # Archived
        archived = Recording.query.filter_by(is_archived=True).count()

        return {
            "disk": {
                "total_gb": disk_usage['total_gb'],
                "used_gb": disk_usage['used_gb'],
                "free_gb": disk_usage['free_gb'],
                "usage_percent": disk_usage['usage_percent'],
                "threshold_percent": self.disk_threshold * 100,
                "is_critical": disk_usage['usage_percent'] >= self.disk_threshold * 100
            },
            "recordings": {
                "total": total_recordings,
                "total_size_gb": round(total_size / (1024**3), 2),
                "by_type": {
                    "continuous": continuous,
                    "event": event_triggered,
                    "manual": manual
                },
                "expiring_soon": expiring_soon,
                "archived": archived
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    def _get_disk_usage(self) -> Dict[str, float]:
        """Get disk usage for recording path."""
        try:
            stat = shutil.disk_usage(self.recording_path)
            return {
                "total_gb": round(stat.total / (1024**3), 2),
                "used_gb": round(stat.used / (1024**3), 2),
                "free_gb": round(stat.free / (1024**3), 2),
                "usage_percent": round(stat.used / stat.total * 100, 1)
            }
        except Exception:
            return {
                "total_gb": 0,
                "used_gb": 0,
                "free_gb": 0,
                "usage_percent": 0
            }

    def cleanup(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Perform retention cleanup.

        1. Delete expired recordings
        2. Free space if disk is over threshold
        """
        deleted = []
        freed_bytes = 0

        # Find expired recordings
        expired = Recording.query.filter(
            Recording.expires_at <= datetime.utcnow(),
            Recording.is_archived == False
        ).all()

        for recording in expired:
            if dry_run:
                deleted.append({
                    "id": recording.id,
                    "file_path": recording.file_path,
                    "size": recording.file_size,
                    "reason": "expired"
                })
            else:
                try:
                    if os.path.exists(recording.file_path):
                        os.remove(recording.file_path)
                    freed_bytes += recording.file_size or 0
                    deleted.append({
                        "id": recording.id,
                        "file_path": recording.file_path,
                        "size": recording.file_size,
                        "reason": "expired"
                    })
                    db.session.delete(recording)
                except Exception as e:
                    pass

        # Check if we need emergency cleanup
        disk_usage = self._get_disk_usage()
        if disk_usage['usage_percent'] >= self.disk_threshold * 100:
            # Delete oldest continuous recordings first
            oldest = Recording.query.filter_by(
                segment_type='continuous',
                is_archived=False
            ).order_by(Recording.start_time).limit(100).all()

            for recording in oldest:
                if disk_usage['free_gb'] >= self.default_policy['min_free_space_gb']:
                    break

                if dry_run:
                    deleted.append({
                        "id": recording.id,
                        "file_path": recording.file_path,
                        "size": recording.file_size,
                        "reason": "disk_pressure"
                    })
                else:
                    try:
                        if os.path.exists(recording.file_path):
                            os.remove(recording.file_path)
                        freed_bytes += recording.file_size or 0
                        deleted.append({
                            "id": recording.id,
                            "file_path": recording.file_path,
                            "size": recording.file_size,
                            "reason": "disk_pressure"
                        })
                        db.session.delete(recording)
                    except Exception:
                        pass

        if not dry_run:
            db.session.commit()

        return {
            "dry_run": dry_run,
            "deleted_count": len(deleted),
            "freed_gb": round(freed_bytes / (1024**3), 2),
            "deleted": deleted
        }

    def archive_recording(self, recording: Recording) -> Dict[str, Any]:
        """Archive a recording to NAS storage."""
        archive_base = Path(self.default_policy['archive_path'])

        # Create archive path structure: /nas/recordings/YYYY/MM/DD/stream_name/
        archive_dir = archive_base / recording.start_time.strftime('%Y/%m/%d')
        if recording.stream:
            archive_dir = archive_dir / recording.stream.path.replace('/', '_')

        try:
            archive_dir.mkdir(parents=True, exist_ok=True)

            # Copy file to archive
            source = Path(recording.file_path)
            dest = archive_dir / source.name

            shutil.copy2(source, dest)

            # Update recording
            recording.is_archived = True
            recording.archive_path = str(dest)
            db.session.commit()

            return {
                "success": True,
                "recording_id": recording.id,
                "archive_path": str(dest)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "recording_id": recording.id
            }

    def get_policy(self) -> Dict[str, Any]:
        """Get current retention policy."""
        return self.default_policy

    def update_policy(self, new_policy: Dict[str, Any]) -> Dict[str, Any]:
        """Update retention policy."""
        valid_keys = [
            'continuous_retention_days',
            'event_retention_days',
            'manual_retention_days',
            'archive_after_days',
            'min_free_space_gb',
            'archive_path'
        ]

        updated = []
        for key in valid_keys:
            if key in new_policy:
                self.default_policy[key] = new_policy[key]
                updated.append(key)

        return {
            "success": True,
            "updated_fields": updated,
            "current_policy": self.default_policy
        }

    def search_recordings(
        self,
        stream_path: str = None,
        start_time: str = None,
        end_time: str = None
    ) -> Dict[str, Any]:
        """Search recordings by criteria."""
        query = Recording.query

        if stream_path:
            query = query.join(Stream).filter(Stream.path.ilike(f'%{stream_path}%'))

        if start_time:
            start_dt = datetime.fromisoformat(start_time)
            query = query.filter(Recording.start_time >= start_dt)

        if end_time:
            end_dt = datetime.fromisoformat(end_time)
            query = query.filter(Recording.end_time <= end_dt)

        recordings = query.order_by(Recording.start_time.desc()).limit(100).all()

        return {
            "results": [{
                "id": r.id,
                "stream_id": r.stream_id,
                "stream_path": r.stream.path if r.stream else None,
                "file_path": r.file_path,
                "start_time": r.start_time.isoformat(),
                "end_time": r.end_time.isoformat() if r.end_time else None,
                "duration_seconds": r.duration_seconds,
                "segment_type": r.segment_type
            } for r in recordings],
            "total": len(recordings)
        }

    def get_playback_url(self, recording: Recording) -> Dict[str, Any]:
        """Generate a playback URL for a recording."""
        # This would typically generate a signed URL or streaming endpoint
        # For now, return a basic file path reference

        if recording.is_archived and recording.archive_path:
            file_path = recording.archive_path
        else:
            file_path = recording.file_path

        return {
            "recording_id": recording.id,
            "file_path": file_path,
            "playback_url": f"/api/recordings/{recording.id}/download",
            "duration_seconds": recording.duration_seconds,
            "format": self._detect_format(file_path)
        }

    def _detect_format(self, file_path: str) -> str:
        """Detect video format from file path."""
        ext = Path(file_path).suffix.lower()
        formats = {
            '.mp4': 'video/mp4',
            '.mkv': 'video/x-matroska',
            '.ts': 'video/mp2t',
            '.flv': 'video/x-flv',
            '.webm': 'video/webm'
        }
        return formats.get(ext, 'video/mp4')

    def start_event_recording(
        self,
        stream: Stream,
        event: StreamEvent,
        duration_seconds: int = 60,
        pre_buffer_seconds: int = 10
    ) -> Dict[str, Any]:
        """
        Start an event-triggered recording.

        This captures video around the event time using ffmpeg.
        """
        # Build output path
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        output_dir = self.recording_path / stream.path.replace('/', '_')
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"event_{event.id}_{timestamp}.mp4"

        # Build source URL
        node = stream.node
        if stream.source_url:
            source_url = stream.source_url
        else:
            base_url = node.api_url.replace(':9997', ':8554')
            source_url = f"rtsp://{base_url.split('://')[1]}/{stream.path}"

        # Start recording with ffmpeg
        cmd = [
            'ffmpeg',
            '-i', source_url,
            '-t', str(duration_seconds),
            '-c:v', 'copy',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            str(output_file)
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Create recording entry
            recording = Recording(
                stream_id=stream.id,
                file_path=str(output_file),
                start_time=datetime.utcnow(),
                segment_type='event',
                triggered_by_event_id=event.id,
                retention_days=self.default_policy['event_retention_days'],
                expires_at=datetime.utcnow() + timedelta(
                    days=self.default_policy['event_retention_days']
                )
            )
            db.session.add(recording)
            db.session.commit()

            return {
                "success": True,
                "recording_id": recording.id,
                "output_file": str(output_file),
                "duration": duration_seconds,
                "process_pid": process.pid
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
