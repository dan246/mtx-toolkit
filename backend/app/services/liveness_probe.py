"""
Frame-Liveness Probe Service.
Detects frozen frames, black screens, stale PTS, and silent audio.
"""

import hashlib
import json
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, Optional

from flask import current_app

from app import db
from app.models import (
    EventType,
    LivenessClassification,
    LivenessProbeResult,
    Stream,
    StreamEvent,
    StreamStatus,
)
from app.utils.logging import get_logger, redact_url

logger = get_logger(__name__)


class LivenessProbe:
    """
    Lightweight frame-level liveness probe.
    Detects fake-alive streams: connected but frozen/black/stale/silent.
    """

    def __init__(self):
        self.timeout = (
            current_app.config.get("LIVENESS_PROBE_TIMEOUT", 5) if current_app else 5
        )
        self.pts_stale_ms = (
            current_app.config.get("LIVENESS_PTS_STALE_MS", 2000)
            if current_app
            else 2000
        )
        self.black_threshold = (
            current_app.config.get("LIVENESS_BLACK_THRESHOLD", 10.0)
            if current_app
            else 10.0
        )
        self.freeze_short_sec = (
            current_app.config.get("LIVENESS_FREEZE_SHORT_SEC", 15)
            if current_app
            else 15
        )
        self.freeze_long_sec = (
            current_app.config.get("LIVENESS_FREEZE_LONG_SEC", 60)
            if current_app
            else 60
        )

    def probe_stream(self, stream: Stream) -> Dict[str, Any]:
        """Run a single liveness probe on a stream."""
        start_time = time.time()

        node = stream.node
        if stream.source_url:
            url = stream.source_url
        else:
            rtsp_base = (
                node.rtsp_url
                if node and node.rtsp_url
                else (
                    current_app.config.get("MEDIAMTX_RTSP_URL", "rtsp://localhost:8555")
                    if current_app
                    else "rtsp://localhost:8555"
                )
            )
            url = f"{rtsp_base}/{stream.path}"

        # Collect probe data
        pts_value = self._get_pts(url)
        frame_hash, brightness = self._get_frame_info(url)
        audio_rms = self._get_audio_rms(url)
        keyframe_present = self._check_keyframe(url)

        # Calculate deltas
        pts_delta = None
        if pts_value is not None and stream.last_pts is not None:
            pts_delta = pts_value - stream.last_pts

        frame_hash_changed = True
        if frame_hash and stream.last_frame_hash:
            frame_hash_changed = frame_hash != stream.last_frame_hash

        # Classify
        classification = self.classify(
            pts_delta, frame_hash_changed, brightness, audio_rms, keyframe_present
        )

        probe_duration_ms = int((time.time() - start_time) * 1000)

        # Store result
        result = LivenessProbeResult(
            stream_id=stream.id,
            classification=classification.value,
            pts_value=pts_value,
            pts_delta=pts_delta,
            frame_hash=frame_hash,
            frame_hash_changed=frame_hash_changed,
            brightness=brightness,
            audio_rms=audio_rms,
            keyframe_present=keyframe_present,
            probe_duration_ms=probe_duration_ms,
        )
        db.session.add(result)

        # Update stream
        old_classification = stream.liveness_classification
        stream.liveness_classification = classification.value
        stream.liveness_last_check = datetime.utcnow()
        if pts_value is not None:
            stream.last_pts = pts_value
        if frame_hash:
            stream.last_frame_hash = frame_hash

        # Track freeze duration
        if classification in (
            LivenessClassification.FROZEN,
            LivenessClassification.BLACK_SCREEN,
            LivenessClassification.STALE,
        ):
            if stream.freeze_started_at is None:
                stream.freeze_started_at = datetime.utcnow()
            stream.consecutive_freeze_checks = (
                stream.consecutive_freeze_checks or 0
            ) + 1
        else:
            stream.freeze_started_at = None
            stream.consecutive_freeze_checks = 0

        # Create events on state changes
        if old_classification != classification.value:
            self._create_liveness_event(stream, old_classification, classification)

        db.session.commit()

        return {
            "stream_id": stream.id,
            "classification": classification.value,
            "pts_value": pts_value,
            "pts_delta": pts_delta,
            "frame_hash_changed": frame_hash_changed,
            "brightness": brightness,
            "audio_rms": audio_rms,
            "keyframe_present": keyframe_present,
            "probe_duration_ms": probe_duration_ms,
            "severity": self.determine_severity(stream, classification),
        }

    def classify(
        self,
        pts_delta: Optional[int],
        frame_hash_changed: bool,
        brightness: Optional[float],
        audio_rms: Optional[float],
        keyframe_present: Optional[bool],
    ) -> LivenessClassification:
        """Classify stream liveness based on probe metrics."""
        # Stale PTS: not advancing
        if pts_delta is not None and abs(pts_delta) < self.pts_stale_ms:
            return LivenessClassification.STALE

        # Black screen
        if brightness is not None and brightness < self.black_threshold:
            return LivenessClassification.BLACK_SCREEN

        # Frozen: same frame hash
        if not frame_hash_changed:
            return LivenessClassification.FROZEN

        # Silent audio (audio-only issue, video may be fine)
        if audio_rms is not None and audio_rms < -50.0:
            return LivenessClassification.SILENT

        # Everything looks good
        return LivenessClassification.LIVE

    def determine_severity(
        self, stream: Stream, classification: LivenessClassification
    ) -> str:
        """Determine severity based on freeze duration."""
        if classification == LivenessClassification.LIVE:
            return "info"

        if stream.freeze_started_at:
            freeze_duration = (
                datetime.utcnow() - stream.freeze_started_at
            ).total_seconds()
            if freeze_duration > self.freeze_long_sec:
                return "critical"
            elif freeze_duration > self.freeze_short_sec:
                return "error"

        if classification == LivenessClassification.SILENT:
            return "warning"

        return "warning"

    def probe_all_ready_streams(self) -> Dict[str, Any]:
        """Probe all healthy/degraded streams."""
        streams = Stream.query.filter(
            Stream.status.in_([StreamStatus.HEALTHY.value, StreamStatus.DEGRADED.value])
        ).all()

        results = []
        for stream in streams:
            try:
                result = self.probe_stream(stream)
                results.append(result)
            except Exception as e:
                results.append({"stream_id": stream.id, "error": str(e)})

        return {
            "probed": len(results),
            "results": results,
        }

    def _get_pts(self, url: str) -> Optional[int]:
        """Get current PTS value from stream.

        Modern ffmpeg exposes the presentation timestamp as ``pts`` /
        ``best_effort_timestamp``; the legacy ``pkt_pts`` field was removed
        years ago. We request all of them and pick the first that is present
        so the probe works across ffmpeg versions.
        """
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "frame=pts,best_effort_timestamp,pkt_pts",
                "-read_intervals",
                "%+0.5",
                "-of",
                "json",
            ]
            if url.startswith("rtsp://"):
                cmd.extend(["-rtsp_transport", "tcp"])
            cmd.append(url)

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                frames = data.get("frames", [])
                if frames:
                    last = frames[-1]
                    for field in ("pts", "best_effort_timestamp", "pkt_pts"):
                        value = last.get(field)
                        if value is not None and value != "N/A":
                            try:
                                return int(value)
                            except (TypeError, ValueError):
                                continue
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("pts_probe_failed", url=redact_url(url), error=str(exc))
        return None

    def _get_frame_info(self, url: str) -> tuple:
        """Get frame hash and brightness."""
        frame_hash = None
        brightness = None
        try:
            # Capture one frame and compute hash + brightness
            cmd = [
                "ffmpeg",
                "-i",
                url,
                "-frames:v",
                "1",
                "-vf",
                "format=gray",
                "-f",
                "rawvideo",
                "-",
            ]
            if url.startswith("rtsp://"):
                cmd.insert(1, "-rtsp_transport")
                cmd.insert(2, "tcp")

            result = subprocess.run(cmd, capture_output=True, timeout=self.timeout)
            if result.returncode == 0 and result.stdout:
                raw = result.stdout
                frame_hash = hashlib.sha256(raw).hexdigest()
                # Average brightness
                if len(raw) > 0:
                    brightness = sum(raw) / len(raw)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("frame_info_probe_failed", url=redact_url(url), error=str(exc))
        return frame_hash, brightness

    def _get_audio_rms(self, url: str) -> Optional[float]:
        """Get audio RMS level in dB."""
        try:
            cmd = [
                "ffmpeg",
                "-i",
                url,
                "-t",
                "1",
                "-af",
                "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
                "-f",
                "null",
                "-",
            ]
            if url.startswith("rtsp://"):
                cmd.insert(1, "-rtsp_transport")
                cmd.insert(2, "tcp")

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            if result.stderr:
                for line in result.stderr.split("\n"):
                    if "RMS_level" in line:
                        parts = line.split("=")
                        if len(parts) >= 2:
                            try:
                                return float(parts[-1].strip())
                            except ValueError:
                                pass
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("audio_rms_probe_failed", url=redact_url(url), error=str(exc))
        return None

    def _check_keyframe(self, url: str) -> Optional[bool]:
        """Check if keyframes are present in stream."""
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "frame=key_frame",
                "-read_intervals",
                "%+1",
                "-of",
                "json",
            ]
            if url.startswith("rtsp://"):
                cmd.extend(["-rtsp_transport", "tcp"])
            cmd.append(url)

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                frames = data.get("frames", [])
                return any(f.get("key_frame") == 1 for f in frames)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("keyframe_probe_failed", url=redact_url(url), error=str(exc))
        return None

    def _create_liveness_event(
        self,
        stream: Stream,
        old_classification: str,
        new_classification: LivenessClassification,
    ):
        """Create event when liveness classification changes."""
        event_map = {
            LivenessClassification.FROZEN: EventType.FROZEN_DETECTED,
            LivenessClassification.BLACK_SCREEN: EventType.BLACK_SCREEN_DETECTED,
            LivenessClassification.STALE: EventType.STALE_PTS_DETECTED,
            LivenessClassification.SILENT: EventType.AUDIO_SILENT_DETECTED,
            LivenessClassification.LIVE: EventType.LIVENESS_RECOVERED,
        }

        event_type = event_map.get(new_classification, EventType.LIVENESS_RECOVERED)
        severity = self.determine_severity(stream, new_classification)

        event = StreamEvent(
            stream_id=stream.id,
            event_type=event_type.value,
            severity=severity,
            message=(
                f"Liveness changed: {old_classification} -> "
                f"{new_classification.value} for stream {stream.path}"
            ),
        )
        db.session.add(event)

    def get_liveness_summary(self) -> Dict[str, int]:
        """Get summary counts by classification."""
        result = {}
        for cls in LivenessClassification:
            count = Stream.query.filter_by(liveness_classification=cls.value).count()
            result[cls.value] = count
        return result
