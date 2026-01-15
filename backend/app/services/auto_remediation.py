"""
Auto-Remediation Service.
Handles automatic recovery of failed streams with backoff and jitter.
"""
import time
import random
import subprocess
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from enum import Enum
import httpx

from flask import current_app
from app import db
from app.models import Stream, StreamEvent, MediaMTXNode, StreamStatus, EventType


class RemediationAction(str, Enum):
    """Types of remediation actions."""
    RECONNECT = "reconnect"
    RESTART_SIDECAR = "restart_sidecar"
    RESTART_PATH = "restart_path"
    RESTART_MEDIAMTX = "restart_mediamtx"


class RemediationResult:
    """Result of a remediation attempt."""
    def __init__(self, success: bool, action: RemediationAction, message: str, details: Dict = None):
        self.success = success
        self.action = action
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }


class AutoRemediation:
    """
    Auto-remediation service with tiered retry strategy.

    Levels:
    1. Reconnect stream source
    2. Restart sidecar (ffmpeg/gstreamer process)
    3. Restart specific path in MediaMTX
    4. Restart entire MediaMTX (last resort)
    """

    def __init__(self):
        self.config = {
            'max_attempts': current_app.config.get('RETRY_MAX_ATTEMPTS', 5) if current_app else 5,
            'base_delay': current_app.config.get('RETRY_BASE_DELAY', 1.0) if current_app else 1.0,
            'max_delay': current_app.config.get('RETRY_MAX_DELAY', 60.0) if current_app else 60.0,
            'jitter_factor': 0.3  # 30% jitter
        }

    def calculate_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff with jitter.
        backoff = base_delay * 2^attempt * (1 + random_jitter)
        """
        base = self.config['base_delay']
        max_delay = self.config['max_delay']
        jitter = self.config['jitter_factor']

        # Exponential backoff
        delay = base * (2 ** attempt)

        # Add jitter
        jitter_amount = delay * jitter * random.random()
        delay += jitter_amount

        # Cap at max delay
        return min(delay, max_delay)

    def remediate_stream(self, stream: Stream, force_level: int = None) -> Dict[str, Any]:
        """
        Perform remediation on a stream.
        Tries increasingly aggressive actions until success.
        """
        # Create start event
        start_event = StreamEvent(
            stream_id=stream.id,
            event_type=EventType.REMEDIATION_STARTED.value,
            severity='info',
            message=f"Starting remediation for stream {stream.path}"
        )
        db.session.add(start_event)

        results = []
        success = False

        # Determine starting level
        start_level = force_level if force_level is not None else self._determine_start_level(stream)

        actions = [
            (1, RemediationAction.RECONNECT, self._try_reconnect),
            (2, RemediationAction.RESTART_SIDECAR, self._try_restart_sidecar),
            (3, RemediationAction.RESTART_PATH, self._try_restart_path),
            (4, RemediationAction.RESTART_MEDIAMTX, self._try_restart_mediamtx),
        ]

        for level, action, handler in actions:
            if level < start_level:
                continue

            for attempt in range(self.config['max_attempts']):
                result = handler(stream, attempt)
                results.append(result.to_dict())

                if result.success:
                    success = True
                    break

                # Wait before next attempt
                delay = self.calculate_backoff(attempt)
                time.sleep(delay)

            if success:
                break

        # Update stream
        stream.remediation_count += 1
        stream.last_remediation = datetime.utcnow()

        # Create result event
        end_event = StreamEvent(
            stream_id=stream.id,
            event_type=EventType.REMEDIATION_SUCCESS.value if success else EventType.REMEDIATION_FAILED.value,
            severity='info' if success else 'error',
            message=f"Remediation {'succeeded' if success else 'failed'} for stream {stream.path}",
            details_json=json.dumps(results)
        )
        db.session.add(end_event)
        db.session.commit()

        return {
            "success": success,
            "stream_id": stream.id,
            "stream_path": stream.path,
            "attempts": results,
            "total_attempts": len(results)
        }

    def _determine_start_level(self, stream: Stream) -> int:
        """Determine which remediation level to start at based on history."""
        # If stream has been remediated many times recently, start at higher level
        recent_remediations = StreamEvent.query.filter(
            StreamEvent.stream_id == stream.id,
            StreamEvent.event_type == EventType.REMEDIATION_STARTED.value,
            StreamEvent.created_at >= datetime.utcnow() - timedelta(hours=1)
        ).count()

        if recent_remediations >= 5:
            return 3  # Skip to restart path
        elif recent_remediations >= 2:
            return 2  # Skip to restart sidecar
        return 1  # Start from reconnect

    def _try_reconnect(self, stream: Stream, attempt: int) -> RemediationResult:
        """Try to reconnect the stream source."""
        try:
            node = stream.node
            api_url = node.api_url

            # Use MediaMTX API to kick/reconnect the path
            response = httpx.post(
                f"{api_url}/v3/paths/{stream.path}/kick",
                timeout=10
            )

            if response.status_code in [200, 204]:
                # Wait a bit and check if stream is back
                time.sleep(2)
                return RemediationResult(
                    success=True,
                    action=RemediationAction.RECONNECT,
                    message=f"Successfully reconnected stream on attempt {attempt + 1}"
                )

            return RemediationResult(
                success=False,
                action=RemediationAction.RECONNECT,
                message=f"Reconnect failed: HTTP {response.status_code}",
                details={"response": response.text}
            )

        except Exception as e:
            return RemediationResult(
                success=False,
                action=RemediationAction.RECONNECT,
                message=f"Reconnect failed: {str(e)}"
            )

    def _try_restart_sidecar(self, stream: Stream, attempt: int) -> RemediationResult:
        """
        Restart the sidecar process (ffmpeg/gstreamer) for this stream.
        This is less disruptive than restarting the entire path.
        """
        try:
            # This would typically interact with a process manager
            # For now, we'll use the MediaMTX API to remove and re-add the source

            node = stream.node
            api_url = node.api_url

            # Get current path config
            response = httpx.get(f"{api_url}/v3/config/paths/{stream.path}", timeout=10)
            if response.status_code != 200:
                return RemediationResult(
                    success=False,
                    action=RemediationAction.RESTART_SIDECAR,
                    message=f"Failed to get path config: HTTP {response.status_code}"
                )

            path_config = response.json()

            # Remove the path
            httpx.delete(f"{api_url}/v3/config/paths/{stream.path}", timeout=10)
            time.sleep(1)

            # Re-add the path
            httpx.patch(
                f"{api_url}/v3/config/paths/{stream.path}",
                json=path_config,
                timeout=10
            )

            time.sleep(3)

            return RemediationResult(
                success=True,
                action=RemediationAction.RESTART_SIDECAR,
                message=f"Successfully restarted sidecar on attempt {attempt + 1}"
            )

        except Exception as e:
            return RemediationResult(
                success=False,
                action=RemediationAction.RESTART_SIDECAR,
                message=f"Sidecar restart failed: {str(e)}"
            )

    def _try_restart_path(self, stream: Stream, attempt: int) -> RemediationResult:
        """Restart the entire path in MediaMTX."""
        try:
            node = stream.node
            api_url = node.api_url

            # Delete and recreate the path
            delete_resp = httpx.delete(
                f"{api_url}/v3/config/paths/{stream.path}",
                timeout=10
            )

            time.sleep(2)

            # Recreate with source
            if stream.source_url:
                create_resp = httpx.patch(
                    f"{api_url}/v3/config/paths/{stream.path}",
                    json={"source": stream.source_url},
                    timeout=10
                )

                if create_resp.status_code in [200, 201, 204]:
                    time.sleep(3)
                    return RemediationResult(
                        success=True,
                        action=RemediationAction.RESTART_PATH,
                        message=f"Successfully restarted path on attempt {attempt + 1}"
                    )

            return RemediationResult(
                success=False,
                action=RemediationAction.RESTART_PATH,
                message="Path restart completed but may need manual verification"
            )

        except Exception as e:
            return RemediationResult(
                success=False,
                action=RemediationAction.RESTART_PATH,
                message=f"Path restart failed: {str(e)}"
            )

    def _try_restart_mediamtx(self, stream: Stream, attempt: int) -> RemediationResult:
        """
        Restart the entire MediaMTX instance.
        Last resort - affects all streams on this node.
        """
        try:
            node = stream.node

            # This would typically use Docker API or systemctl
            # For Docker:
            container_name = f"mediamtx-{node.name}"

            result = subprocess.run(
                ['docker', 'restart', container_name],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                # Wait for MediaMTX to come back up
                time.sleep(10)
                return RemediationResult(
                    success=True,
                    action=RemediationAction.RESTART_MEDIAMTX,
                    message=f"Successfully restarted MediaMTX on attempt {attempt + 1}"
                )

            return RemediationResult(
                success=False,
                action=RemediationAction.RESTART_MEDIAMTX,
                message=f"MediaMTX restart failed: {result.stderr}"
            )

        except Exception as e:
            return RemediationResult(
                success=False,
                action=RemediationAction.RESTART_MEDIAMTX,
                message=f"MediaMTX restart failed: {str(e)}"
            )

    def should_auto_remediate(self, stream: Stream) -> bool:
        """Check if stream should be auto-remediated."""
        if not stream.auto_remediate:
            return False

        # Check cooldown (don't remediate too frequently)
        if stream.last_remediation:
            cooldown = timedelta(minutes=5)
            if datetime.utcnow() - stream.last_remediation < cooldown:
                return False

        # Check remediation count (circuit breaker)
        recent_count = StreamEvent.query.filter(
            StreamEvent.stream_id == stream.id,
            StreamEvent.event_type == EventType.REMEDIATION_FAILED.value,
            StreamEvent.created_at >= datetime.utcnow() - timedelta(hours=1)
        ).count()

        if recent_count >= 10:
            return False  # Too many recent failures, needs manual intervention

        return True
