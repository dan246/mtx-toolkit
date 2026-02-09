"""
Recording Pipeline Monitor Service.
Detects recording failures by monitoring write latency, segment gaps, and disk IO.
"""

import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import current_app

from app import db
from app.models import (
    EventType,
    Recording,
    RecordingPipelineMetric,
    RecordingPipelineStatus,
    Stream,
    StreamEvent,
)


class RecordingPipelineMonitor:
    """
    Monitors recording pipeline health.
    Detects segment gaps, write latency issues, and disk IO problems.
    """

    def __init__(self):
        self.write_latency_warning = (
            current_app.config.get("PIPELINE_WRITE_LATENCY_WARNING_MS", 500)
            if current_app
            else 500
        )
        self.write_latency_critical = (
            current_app.config.get("PIPELINE_WRITE_LATENCY_CRITICAL_MS", 2000)
            if current_app
            else 2000
        )
        self.segment_gap_warning = (
            current_app.config.get("PIPELINE_SEGMENT_GAP_WARNING_SEC", 5.0)
            if current_app
            else 5.0
        )
        self.recording_path = (
            Path(current_app.config.get("RECORDING_BASE_PATH", "/recordings"))
            if current_app
            else Path("/recordings")
        )

    def check_stream_pipeline(self, stream: Stream) -> Dict[str, Any]:
        """Check recording pipeline health for a single stream."""
        if not stream.recording_enabled:
            return {
                "stream_id": stream.id,
                "status": RecordingPipelineStatus.UNKNOWN.value,
                "message": "Recording not enabled",
            }

        issues = []
        status = RecordingPipelineStatus.HEALTHY

        # Check segment gaps
        gap_result = self._detect_segment_gaps(stream)
        if gap_result.get("has_gap"):
            gap_sec = gap_result.get("gap_seconds", 0)
            if gap_sec > self.segment_gap_warning * 2:
                status = RecordingPipelineStatus.CRITICAL
                issues.append(f"Large segment gap: {gap_sec:.1f}s")
            else:
                status = RecordingPipelineStatus.WARNING
                issues.append(f"Segment gap detected: {gap_sec:.1f}s")

            # Create event
            event = StreamEvent(
                stream_id=stream.id,
                event_type=EventType.RECORDING_SEGMENT_GAP.value,
                severity=(
                    "warning" if status == RecordingPipelineStatus.WARNING else "error"
                ),
                message=f"Recording segment gap: {gap_sec:.1f}s",
            )
            db.session.add(event)

        # Measure write latency
        write_latency = self._measure_write_latency(stream)
        if write_latency is not None:
            if write_latency > self.write_latency_critical:
                status = RecordingPipelineStatus.CRITICAL
                issues.append(f"Critical write latency: {write_latency:.0f}ms")

                event = StreamEvent(
                    stream_id=stream.id,
                    event_type=EventType.RECORDING_WRITE_SLOW.value,
                    severity="error",
                    message=f"Recording write latency critical: {write_latency:.0f}ms",
                )
                db.session.add(event)
            elif write_latency > self.write_latency_warning:
                if status != RecordingPipelineStatus.CRITICAL:
                    status = RecordingPipelineStatus.WARNING
                issues.append(f"High write latency: {write_latency:.0f}ms")

        # Store metric
        metric = RecordingPipelineMetric(
            stream_id=stream.id,
            disk_io_latency_ms=write_latency,
            segment_gap_seconds=gap_result.get("gap_seconds"),
        )
        db.session.add(metric)

        # Update stream
        old_status = stream.recording_pipeline_status
        stream.recording_pipeline_status = status.value
        stream.recording_avg_write_latency_ms = write_latency

        if old_status != status.value and status != RecordingPipelineStatus.HEALTHY:
            event = StreamEvent(
                stream_id=stream.id,
                event_type=EventType.RECORDING_PIPELINE_DEGRADED.value,
                severity=(
                    "warning" if status == RecordingPipelineStatus.WARNING else "error"
                ),
                message=f"Recording pipeline {status.value}: {'; '.join(issues)}",
            )
            db.session.add(event)

        db.session.commit()

        result = {
            "stream_id": stream.id,
            "status": status.value,
            "issues": issues,
            "write_latency_ms": write_latency,
            "segment_gap": gap_result,
            "suggestions": self._suggest_mitigation(
                {"write_latency": write_latency, "gap": gap_result, "status": status}
            ),
        }

        return result

    def check_all_pipelines(self) -> Dict[str, Any]:
        """Check all recording-enabled streams."""
        streams = Stream.query.filter_by(recording_enabled=True).all()

        results = []
        for stream in streams:
            try:
                result = self.check_stream_pipeline(stream)
                results.append(result)
            except Exception as e:
                results.append(
                    {
                        "stream_id": stream.id,
                        "status": RecordingPipelineStatus.UNKNOWN.value,
                        "error": str(e),
                    }
                )

        summary = {
            "total": len(results),
            "healthy": sum(
                1
                for r in results
                if r.get("status") == RecordingPipelineStatus.HEALTHY.value
            ),
            "warning": sum(
                1
                for r in results
                if r.get("status") == RecordingPipelineStatus.WARNING.value
            ),
            "critical": sum(
                1
                for r in results
                if r.get("status") == RecordingPipelineStatus.CRITICAL.value
            ),
        }

        return {"summary": summary, "results": results}

    def _detect_segment_gaps(self, stream: Stream) -> Dict[str, Any]:
        """Compare expected vs actual segment timestamps."""
        # Get last 2 recordings for this stream
        recent = (
            Recording.query.filter_by(stream_id=stream.id)
            .order_by(Recording.start_time.desc())
            .limit(2)
            .all()
        )

        if len(recent) < 2:
            return {"has_gap": False, "message": "Not enough segments to compare"}

        newer = recent[0]
        older = recent[1]

        # Calculate gap
        if older.end_time and newer.start_time:
            gap = (newer.start_time - older.end_time).total_seconds()
        elif older.start_time and older.duration_seconds and newer.start_time:
            expected_end = older.start_time + timedelta(seconds=older.duration_seconds)
            gap = (newer.start_time - expected_end).total_seconds()
        else:
            return {"has_gap": False, "message": "Cannot determine gap"}

        has_gap = gap > self.segment_gap_warning
        return {
            "has_gap": has_gap,
            "gap_seconds": round(gap, 1),
            "newer_segment_start": newer.start_time.isoformat(),
            "older_segment_end": (
                older.end_time.isoformat() if older.end_time else None
            ),
        }

    def _measure_write_latency(self, stream: Stream) -> Optional[float]:
        """Measure disk write speed for recording directory."""
        stream_dir = self.recording_path / stream.path.replace("/", "_")

        # If stream dir doesn't exist, use recording base path
        test_dir = stream_dir if stream_dir.exists() else self.recording_path

        if not test_dir.exists():
            return None

        return self._measure_disk_io_latency(test_dir)

    def _measure_disk_io_latency(self, directory: Path = None) -> Optional[float]:
        """Raw IO test write to measure disk latency in ms."""
        test_dir = directory or self.recording_path

        try:
            # Write a 1MB test file and measure time
            test_data = b"\x00" * (1024 * 1024)  # 1MB

            with tempfile.NamedTemporaryFile(dir=str(test_dir), delete=True) as f:
                start = time.time()
                f.write(test_data)
                f.flush()
                os.fsync(f.fileno())
                elapsed = time.time() - start

            return round(elapsed * 1000, 1)  # Convert to ms
        except Exception:
            return None

    def _suggest_mitigation(self, metrics: Dict) -> List[str]:
        """Return actionable suggestions based on metrics."""
        suggestions = []

        write_latency = metrics.get("write_latency")
        gap = metrics.get("gap", {})
        status = metrics.get("status")

        if write_latency and write_latency > self.write_latency_critical:
            suggestions.append("Consider moving recordings to a faster disk (SSD)")
            suggestions.append("Check for other processes with high disk IO")

        if write_latency and write_latency > self.write_latency_warning:
            suggestions.append("Monitor disk IO utilization with iostat")

        if gap.get("has_gap") and gap.get("gap_seconds", 0) > 10:
            suggestions.append("Check stream source stability")
            suggestions.append("Verify MediaMTX recording configuration")

        if status == RecordingPipelineStatus.CRITICAL:
            suggestions.append(
                "Immediate attention required - recordings may be failing"
            )

        return suggestions

    def get_pipeline_dashboard_data(self) -> Dict[str, Any]:
        """Get aggregated pipeline data for dashboard."""
        streams = Stream.query.filter_by(recording_enabled=True).all()

        by_status = {}
        for s in RecordingPipelineStatus:
            by_status[s.value] = sum(
                1 for st in streams if st.recording_pipeline_status == s.value
            )

        # Recent metrics
        recent_metrics = (
            RecordingPipelineMetric.query.filter(
                RecordingPipelineMetric.created_at
                >= datetime.utcnow() - timedelta(hours=1)
            )
            .order_by(RecordingPipelineMetric.created_at.desc())
            .limit(100)
            .all()
        )

        avg_latency = None
        if recent_metrics:
            latencies = [
                m.disk_io_latency_ms
                for m in recent_metrics
                if m.disk_io_latency_ms is not None
            ]
            if latencies:
                avg_latency = round(sum(latencies) / len(latencies), 1)

        return {
            "total_recording_streams": len(streams),
            "by_status": by_status,
            "avg_write_latency_ms": avg_latency,
            "recent_gaps": sum(
                1
                for m in recent_metrics
                if m.segment_gap_seconds
                and m.segment_gap_seconds > self.segment_gap_warning
            ),
        }
