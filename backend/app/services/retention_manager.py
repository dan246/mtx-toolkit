"""
Retention Manager Service.
Recording retention, disk management, and archival.
"""

import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from flask import current_app

from app import db
from app.models import MediaMTXNode, Recording, Stream, StreamEvent


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
        self.recording_path = (
            Path(current_app.config.get("RECORDING_BASE_PATH", "/recordings"))
            if current_app
            else Path("/recordings")
        )
        self.disk_threshold = (
            (current_app.config.get("DISK_USAGE_THRESHOLD", 0.85))
            if current_app
            else 0.85
        )

        # Default retention policy
        self.default_policy = {
            "continuous_retention_days": 7,
            "event_retention_days": 30,
            "manual_retention_days": 90,
            "archive_after_days": 3,
            "min_free_space_gb": 50,
            "archive_path": "/mnt/nas/recordings",
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current retention and disk status."""
        disk_usage = self._get_disk_usage()

        # Get recording stats
        total_recordings = Recording.query.count()
        total_size = db.session.query(db.func.sum(Recording.file_size)).scalar() or 0

        # Recordings by type
        continuous = Recording.query.filter_by(segment_type="continuous").count()
        event_triggered = Recording.query.filter_by(segment_type="event").count()
        manual = Recording.query.filter_by(segment_type="manual").count()

        # Expiring soon (next 24h)
        expiring_soon = Recording.query.filter(
            Recording.expires_at <= datetime.utcnow() + timedelta(hours=24),
            Recording.expires_at > datetime.utcnow(),
        ).count()

        # Archived
        archived = Recording.query.filter_by(is_archived=True).count()

        return {
            "disk": {
                "total_gb": disk_usage["total_gb"],
                "used_gb": disk_usage["used_gb"],
                "free_gb": disk_usage["free_gb"],
                "usage_percent": disk_usage["usage_percent"],
                "threshold_percent": self.disk_threshold * 100,
                "is_critical": disk_usage["usage_percent"] >= self.disk_threshold * 100,
            },
            "recordings": {
                "total": total_recordings,
                "total_size_gb": round(total_size / (1024**3), 2),
                "by_type": {
                    "continuous": continuous,
                    "event": event_triggered,
                    "manual": manual,
                },
                "expiring_soon": expiring_soon,
                "archived": archived,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _get_disk_usage(self) -> Dict[str, float]:
        """Get disk usage for recording path."""
        try:
            stat = shutil.disk_usage(self.recording_path)
            return {
                "total_gb": round(stat.total / (1024**3), 2),
                "used_gb": round(stat.used / (1024**3), 2),
                "free_gb": round(stat.free / (1024**3), 2),
                "usage_percent": round(stat.used / stat.total * 100, 1),
            }
        except Exception:
            return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "usage_percent": 0}

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
            Recording.expires_at <= datetime.utcnow(), Recording.is_archived.is_(False)
        ).all()

        for recording in expired:
            if dry_run:
                deleted.append(
                    {
                        "id": recording.id,
                        "file_path": recording.file_path,
                        "size": recording.file_size,
                        "reason": "expired",
                    }
                )
            else:
                try:
                    if os.path.exists(recording.file_path):
                        os.remove(recording.file_path)
                    freed_bytes += recording.file_size or 0
                    deleted.append(
                        {
                            "id": recording.id,
                            "file_path": recording.file_path,
                            "size": recording.file_size,
                            "reason": "expired",
                        }
                    )
                    db.session.delete(recording)
                except Exception:
                    pass

        # Check if we need emergency cleanup
        disk_usage = self._get_disk_usage()
        if disk_usage["usage_percent"] >= self.disk_threshold * 100:
            # Delete oldest continuous recordings first
            oldest = (
                Recording.query.filter_by(segment_type="continuous", is_archived=False)
                .order_by(Recording.start_time)
                .limit(100)
                .all()
            )

            for recording in oldest:
                if disk_usage["free_gb"] >= self.default_policy["min_free_space_gb"]:
                    break

                if dry_run:
                    deleted.append(
                        {
                            "id": recording.id,
                            "file_path": recording.file_path,
                            "size": recording.file_size,
                            "reason": "disk_pressure",
                        }
                    )
                else:
                    try:
                        if os.path.exists(recording.file_path):
                            os.remove(recording.file_path)
                        freed_bytes += recording.file_size or 0
                        deleted.append(
                            {
                                "id": recording.id,
                                "file_path": recording.file_path,
                                "size": recording.file_size,
                                "reason": "disk_pressure",
                            }
                        )
                        db.session.delete(recording)
                    except Exception:
                        pass

        if not dry_run:
            db.session.commit()

        return {
            "dry_run": dry_run,
            "deleted_count": len(deleted),
            "freed_gb": round(freed_bytes / (1024**3), 2),
            "deleted": deleted,
        }

    def archive_recording(self, recording: Recording) -> Dict[str, Any]:
        """Archive a recording to NAS storage."""
        archive_base = Path(self.default_policy["archive_path"])

        # Create archive path structure: /nas/recordings/YYYY/MM/DD/stream_name/
        archive_dir = archive_base / recording.start_time.strftime("%Y/%m/%d")
        if recording.stream:
            archive_dir = archive_dir / recording.stream.path.replace("/", "_")

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
                "archive_path": str(dest),
            }

        except Exception as e:
            return {"success": False, "error": str(e), "recording_id": recording.id}

    def get_policy(self) -> Dict[str, Any]:
        """Get current retention policy."""
        return self.default_policy

    def update_policy(self, new_policy: Dict[str, Any]) -> Dict[str, Any]:
        """Update retention policy."""
        valid_keys = [
            "continuous_retention_days",
            "event_retention_days",
            "manual_retention_days",
            "archive_after_days",
            "min_free_space_gb",
            "archive_path",
        ]

        updated = []
        for key in valid_keys:
            if key in new_policy:
                self.default_policy[key] = new_policy[key]
                updated.append(key)

        return {
            "success": True,
            "updated_fields": updated,
            "current_policy": self.default_policy,
        }

    def search_recordings(
        self, stream_path: str = None, start_time: str = None, end_time: str = None
    ) -> Dict[str, Any]:
        """Search recordings by criteria."""
        query = Recording.query

        if stream_path:
            query = query.join(Stream).filter(Stream.path.ilike(f"%{stream_path}%"))

        if start_time:
            start_dt = datetime.fromisoformat(start_time)
            query = query.filter(Recording.start_time >= start_dt)

        if end_time:
            end_dt = datetime.fromisoformat(end_time)
            query = query.filter(Recording.end_time <= end_dt)

        recordings = query.order_by(Recording.start_time.desc()).limit(100).all()

        return {
            "results": [
                {
                    "id": r.id,
                    "stream_id": r.stream_id,
                    "stream_path": r.stream.path if r.stream else None,
                    "file_path": r.file_path,
                    "start_time": r.start_time.isoformat(),
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "duration_seconds": r.duration_seconds,
                    "segment_type": r.segment_type,
                }
                for r in recordings
            ],
            "total": len(recordings),
        }

    def get_playback_url(self, recording: Recording) -> Dict[str, Any]:
        """Generate a playback URL for a recording."""
        if recording.is_archived and recording.archive_path:
            file_path = recording.archive_path
        else:
            file_path = recording.file_path

        # Use transcode endpoint for .ts files (browser compatibility)
        ext = Path(file_path).suffix.lower()
        if ext == ".ts":
            url = f"/api/recordings/{recording.id}/transcode"
        else:
            url = f"/api/recordings/{recording.id}/stream"

        return {
            "recording_id": recording.id,
            "file_path": file_path,
            "playback_url": url,
            "download_url": f"/api/recordings/{recording.id}/download",
            "duration_seconds": recording.duration_seconds,
            "format": self._detect_format(file_path),
        }

    def _detect_format(self, file_path: str) -> str:
        """Detect video format from file path."""
        ext = Path(file_path).suffix.lower()
        formats = {
            ".mp4": "video/mp4",
            ".mkv": "video/x-matroska",
            ".ts": "video/mp2t",
            ".flv": "video/x-flv",
            ".webm": "video/webm",
        }
        return formats.get(ext, "video/mp4")

    def start_event_recording(
        self,
        stream: Stream,
        event: StreamEvent,
        duration_seconds: int = 60,
        pre_buffer_seconds: int = 10,
    ) -> Dict[str, Any]:
        """
        Start an event-triggered recording.

        This captures video around the event time using ffmpeg.
        """
        # Build output path
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_dir = self.recording_path / stream.path.replace("/", "_")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"event_{event.id}_{timestamp}.mp4"

        # Build source URL
        node = stream.node
        if stream.source_url:
            source_url = stream.source_url
        else:
            base_url = node.api_url.replace(":9997", ":8554")
            source_url = f"rtsp://{base_url.split('://')[1]}/{stream.path}"

        # Start recording with ffmpeg
        cmd = [
            "ffmpeg",
            "-i",
            source_url,
            "-t",
            str(duration_seconds),
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output_file),
        ]

        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            # Create recording entry
            recording = Recording(
                stream_id=stream.id,
                file_path=str(output_file),
                start_time=datetime.utcnow(),
                segment_type="event",
                triggered_by_event_id=event.id,
                retention_days=self.default_policy["event_retention_days"],
                expires_at=datetime.utcnow()
                + timedelta(days=self.default_policy["event_retention_days"]),
            )
            db.session.add(recording)
            db.session.commit()

            return {
                "success": True,
                "recording_id": recording.id,
                "output_file": str(output_file),
                "duration": duration_seconds,
                "process_pid": process.pid,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def scan_recordings(
        self, node_id: Optional[int] = None, force_rescan: bool = False
    ) -> Dict[str, Any]:
        """
        Scan local recording directory and index files to database.

        Args:
            node_id: Optional node ID to filter streams by
            force_rescan: If True, re-scan and update existing records

        Returns:
            Dictionary with scan statistics
        """
        stats = {"scanned": 0, "added": 0, "skipped": 0, "errors": 0, "error_details": []}

        try:
            scan_result = self._scan_local_directory(node_id, force_rescan)
            stats.update(scan_result)
        except Exception as e:
            stats["errors"] += 1
            stats["error_details"].append(f"Scan failed: {str(e)}")

        return {
            "success": stats["errors"] == 0 or stats["added"] > 0,
            "stats": stats,
        }

    def _scan_local_directory(
        self, node_id: Optional[int] = None, force_rescan: bool = False
    ) -> Dict[str, Any]:
        """
        Scan local recording directory for video files.

        Recording structure: /recordings/{stream_path}/{YYYY-MM-DD_HH-mm-ss}.ts
        """
        stats = {"scanned": 0, "added": 0, "skipped": 0, "errors": 0, "error_details": []}

        if not self.recording_path.exists():
            stats["error_details"].append(
                f"Recording path does not exist: {self.recording_path}"
            )
            stats["errors"] += 1
            return stats

        # Get streams to match against (optionally filtered by node)
        stream_query = Stream.query
        if node_id:
            stream_query = stream_query.filter_by(node_id=node_id)
        streams = {s.path: s for s in stream_query.all()}

        # Scan directory structure
        for stream_dir in self.recording_path.iterdir():
            if not stream_dir.is_dir():
                continue

            stream_path = stream_dir.name
            stream = self._find_stream_by_path(stream_path, streams, node_id)

            # Scan recording files in this stream directory
            for recording_file in stream_dir.iterdir():
                if not recording_file.is_file():
                    continue

                # Only process video files
                if recording_file.suffix.lower() not in [".ts", ".mp4", ".mkv", ".flv"]:
                    continue

                stats["scanned"] += 1
                file_path = str(recording_file)

                # Check if already indexed
                existing = Recording.query.filter_by(file_path=file_path).first()
                if existing and not force_rescan:
                    stats["skipped"] += 1
                    continue

                # Parse recording file
                parsed = self._parse_recording_file(recording_file)
                if not parsed:
                    stats["errors"] += 1
                    stats["error_details"].append(
                        f"Failed to parse: {recording_file.name}"
                    )
                    continue

                try:
                    if existing and force_rescan:
                        # Update existing record
                        existing.file_size = parsed["file_size"]
                        existing.start_time = parsed["start_time"]
                        if stream:
                            existing.stream_id = stream.id
                        stats["added"] += 1
                    else:
                        # Create new record
                        if not stream:
                            # Create a placeholder stream if none exists
                            stats["errors"] += 1
                            stats["error_details"].append(
                                f"No matching stream for path: {stream_path}"
                            )
                            continue

                        recording = Recording(
                            stream_id=stream.id,
                            file_path=file_path,
                            file_size=parsed["file_size"],
                            start_time=parsed["start_time"],
                            segment_type="continuous",
                            expires_at=parsed["start_time"]
                            + timedelta(days=self.default_policy["continuous_retention_days"]),
                        )
                        db.session.add(recording)
                        stats["added"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    stats["error_details"].append(f"Error indexing {file_path}: {str(e)}")

        db.session.commit()
        return stats

    def _parse_recording_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Parse recording filename to extract metadata.

        Expected format: YYYY-MM-DD_HH-mm-ss.ts
        Example: 2026-01-17_04-40-07.ts
        """
        # Pattern: YYYY-MM-DD_HH-mm-ss
        pattern = r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})"
        match = re.search(pattern, file_path.stem)

        if not match:
            return None

        try:
            timestamp_str = match.group(1)
            start_time = datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
            file_size = file_path.stat().st_size

            return {
                "start_time": start_time,
                "file_size": file_size,
            }
        except (ValueError, OSError):
            return None

    def _find_stream_by_path(
        self,
        stream_path: str,
        streams_cache: Dict[str, Stream],
        node_id: Optional[int] = None,
    ) -> Optional[Stream]:
        """
        Find a Stream by path, with flexible matching.

        Handles cases where directory name might differ slightly from stream path.
        """
        # Direct match
        if stream_path in streams_cache:
            return streams_cache[stream_path]

        # Try with/without leading slash
        alt_path = (
            f"/{stream_path}" if not stream_path.startswith("/") else stream_path[1:]
        )
        if alt_path in streams_cache:
            return streams_cache[alt_path]

        # Fuzzy match: replace underscores/dashes
        for path, stream in streams_cache.items():
            normalized_path = path.replace("-", "_").replace("/", "_").lower()
            normalized_search = stream_path.replace("-", "_").replace("/", "_").lower()
            if normalized_path == normalized_search:
                return stream

        return None
