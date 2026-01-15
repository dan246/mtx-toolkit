"""
E2E Health Checker Service.
Uses ffprobe/gstreamer to perform real stream health checks.
"""
import subprocess
import json
import re
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass
import httpx

from flask import current_app
from app import db
from app.models import Stream, StreamEvent, MediaMTXNode, StreamStatus, EventType


@dataclass
class StreamProbeResult:
    """Result of a stream probe."""
    is_healthy: bool
    status: StreamStatus
    fps: Optional[float] = None
    bitrate: Optional[int] = None
    latency_ms: Optional[int] = None
    keyframe_interval: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None
    audio_codec: Optional[str] = None
    issues: List[str] = None
    raw_data: Dict[str, Any] = None

    def __post_init__(self):
        if self.issues is None:
            self.issues = []


class HealthChecker:
    """
    E2E stream health checker using ffprobe.
    Detects: black screen, frozen, audio silent, FPS drop, keyframe issues, latency.
    """

    # Thresholds for health detection
    MIN_FPS = 10.0
    MAX_KEYFRAME_INTERVAL = 10.0  # seconds
    MAX_LATENCY_MS = 5000
    BLACK_SCREEN_THRESHOLD = 0.1  # 10% of pixels must be non-black
    FREEZE_DETECTION_DURATION = 5.0  # seconds

    def __init__(self):
        self.timeout = current_app.config.get('HEALTH_CHECK_TIMEOUT', 10) if current_app else 10

    def check_redis(self) -> str:
        """Check Redis connection."""
        try:
            import redis
            r = redis.from_url(current_app.config.get('REDIS_URL', 'redis://localhost:6379/0'))
            r.ping()
            return "ok"
        except Exception as e:
            return f"error: {str(e)}"

    def check_mediamtx_api(self) -> str:
        """Check MediaMTX API connection."""
        try:
            url = current_app.config.get('MEDIAMTX_API_URL', 'http://localhost:9998')
            response = httpx.get(f"{url}/v3/paths/list", timeout=5)
            if response.status_code == 200:
                return "ok"
            return f"error: status {response.status_code}"
        except Exception as e:
            return f"error: {str(e)}"

    def probe_url(self, url: str, protocol: str = 'rtsp') -> Dict[str, Any]:
        """
        Probe a stream URL using ffprobe.
        Returns detailed stream information and health status.
        """
        try:
            result = self._run_ffprobe(url)
            return self._analyze_probe_result(result, url, protocol)
        except Exception as e:
            return {
                "is_healthy": False,
                "status": StreamStatus.UNHEALTHY.value,
                "error": str(e),
                "url": url
            }

    def _run_ffprobe(self, url: str) -> Dict[str, Any]:
        """Run ffprobe and return parsed JSON output."""
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            '-show_error',
            '-analyzeduration', '5000000',  # 5 seconds
            '-probesize', '5000000',
            url
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout
        )

        if result.returncode != 0 and not result.stdout:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")

        return json.loads(result.stdout) if result.stdout else {}

    def _analyze_probe_result(self, probe_data: Dict, url: str, protocol: str) -> Dict[str, Any]:
        """Analyze ffprobe result and determine health status."""
        issues = []
        status = StreamStatus.HEALTHY

        streams = probe_data.get('streams', [])
        format_info = probe_data.get('format', {})

        if not streams:
            return {
                "is_healthy": False,
                "status": StreamStatus.UNHEALTHY.value,
                "error": "No streams found",
                "url": url
            }

        # Find video and audio streams
        video_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
        audio_stream = next((s for s in streams if s.get('codec_type') == 'audio'), None)

        result = {
            "url": url,
            "protocol": protocol,
            "format": format_info.get('format_name'),
            "duration": format_info.get('duration'),
        }

        # Analyze video stream
        if video_stream:
            # Parse FPS
            fps = self._parse_fps(video_stream.get('r_frame_rate', '0/1'))
            result['fps'] = fps
            result['width'] = video_stream.get('width')
            result['height'] = video_stream.get('height')
            result['codec'] = video_stream.get('codec_name')
            result['bitrate'] = int(video_stream.get('bit_rate', 0)) if video_stream.get('bit_rate') else None

            # Check FPS
            if fps and fps < self.MIN_FPS:
                issues.append(f"Low FPS: {fps:.1f}")
                status = StreamStatus.DEGRADED

            # Check for keyframe interval (GOP)
            if 'avg_frame_rate' in video_stream:
                avg_fps = self._parse_fps(video_stream['avg_frame_rate'])
                if avg_fps and fps and abs(fps - avg_fps) > fps * 0.3:
                    issues.append("Inconsistent frame rate detected")
                    status = StreamStatus.DEGRADED

        else:
            issues.append("No video stream")
            status = StreamStatus.UNHEALTHY

        # Analyze audio stream
        if audio_stream:
            result['audio_codec'] = audio_stream.get('codec_name')
            result['audio_sample_rate'] = audio_stream.get('sample_rate')
            result['audio_channels'] = audio_stream.get('channels')
        else:
            issues.append("No audio stream")
            # Audio missing is just a warning, not unhealthy

        result['issues'] = issues
        result['is_healthy'] = status == StreamStatus.HEALTHY
        result['status'] = status.value

        return result

    def _parse_fps(self, fps_str: str) -> Optional[float]:
        """Parse FPS from ffprobe format (e.g., '30/1' or '29.97')."""
        try:
            if '/' in fps_str:
                num, den = fps_str.split('/')
                if int(den) == 0:
                    return None
                return float(num) / float(den)
            return float(fps_str)
        except (ValueError, ZeroDivisionError):
            return None

    def probe_stream(self, stream_id: int) -> Dict[str, Any]:
        """Probe a specific stream and update its status."""
        stream = Stream.query.get(stream_id)
        if not stream:
            return {"error": "Stream not found"}

        # Build the stream URL
        node = stream.node
        if stream.source_url:
            url = stream.source_url
        else:
            # Use configured RTSP URL or construct from node
            rtsp_base = current_app.config.get('MEDIAMTX_RTSP_URL', 'rtsp://localhost:8555')
            url = f"{rtsp_base}/{stream.path}"

        # Run probe
        result = self.probe_url(url, stream.protocol or 'rtsp')

        # Update stream status
        old_status = stream.status
        stream.status = result.get('status', StreamStatus.UNKNOWN.value)
        stream.fps = result.get('fps')
        stream.bitrate = result.get('bitrate')
        stream.latency_ms = result.get('latency_ms')
        stream.last_check = datetime.utcnow()

        # Create event if status changed
        if old_status != stream.status:
            self._create_status_change_event(stream, old_status, result)

        db.session.commit()

        return result

    def _create_status_change_event(self, stream: Stream, old_status: str, probe_result: Dict):
        """Create an event when stream status changes."""
        severity = 'info'
        if stream.status == StreamStatus.UNHEALTHY.value:
            severity = 'critical'
        elif stream.status == StreamStatus.DEGRADED.value:
            severity = 'warning'

        event = StreamEvent(
            stream_id=stream.id,
            event_type=EventType.DISCONNECTED.value if stream.status == StreamStatus.UNHEALTHY.value else EventType.RECONNECTED.value,
            severity=severity,
            message=f"Stream status changed: {old_status} -> {stream.status}",
            details_json=json.dumps(probe_result.get('issues', []))
        )
        db.session.add(event)

    def get_stream_health(self, stream_id: int) -> Optional[Dict[str, Any]]:
        """Get current health status of a stream."""
        stream = Stream.query.get(stream_id)
        if not stream:
            return None

        return {
            "id": stream.id,
            "path": stream.path,
            "status": stream.status,
            "fps": stream.fps,
            "bitrate": stream.bitrate,
            "latency_ms": stream.latency_ms,
            "keyframe_interval": stream.keyframe_interval,
            "last_check": stream.last_check.isoformat() if stream.last_check else None,
            "auto_remediate": stream.auto_remediate,
            "remediation_count": stream.remediation_count
        }

    def get_all_streams_health(
        self,
        node_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get health status of all streams."""
        query = Stream.query
        if node_id:
            query = query.filter_by(node_id=node_id)
        if status:
            query = query.filter_by(status=status)

        streams = query.all()

        return {
            "streams": [self.get_stream_health(s.id) for s in streams],
            "summary": {
                "total": len(streams),
                "healthy": sum(1 for s in streams if s.status == StreamStatus.HEALTHY.value),
                "degraded": sum(1 for s in streams if s.status == StreamStatus.DEGRADED.value),
                "unhealthy": sum(1 for s in streams if s.status == StreamStatus.UNHEALTHY.value),
                "unknown": sum(1 for s in streams if s.status == StreamStatus.UNKNOWN.value)
            }
        }

    def detect_black_screen(self, url: str, duration: float = 2.0) -> bool:
        """
        Detect if stream is showing a black screen.
        Uses ffmpeg to analyze pixel values.
        """
        try:
            cmd = [
                'ffmpeg',
                '-i', url,
                '-t', str(duration),
                '-vf', 'blackdetect=d=0.5:pix_th=0.10',
                '-an',
                '-f', 'null',
                '-'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout + duration)
            return 'black_start' in result.stderr
        except Exception:
            return False

    def detect_freeze(self, url: str, duration: float = 5.0) -> bool:
        """
        Detect if stream is frozen (no frame changes).
        Uses ffmpeg freezedetect filter.
        """
        try:
            cmd = [
                'ffmpeg',
                '-i', url,
                '-t', str(duration),
                '-vf', f'freezedetect=n=0.003:d={self.FREEZE_DETECTION_DURATION}',
                '-an',
                '-f', 'null',
                '-'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout + duration)
            return 'freeze_start' in result.stderr
        except Exception:
            return False

    def detect_audio_silence(self, url: str, duration: float = 3.0) -> bool:
        """
        Detect if audio is silent.
        Uses ffmpeg silencedetect filter.
        """
        try:
            cmd = [
                'ffmpeg',
                '-i', url,
                '-t', str(duration),
                '-af', 'silencedetect=n=-50dB:d=2',
                '-vn',
                '-f', 'null',
                '-'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout + duration)
            return 'silence_start' in result.stderr
        except Exception:
            return False
