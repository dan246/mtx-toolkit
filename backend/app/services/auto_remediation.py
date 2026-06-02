"""
Auto-Remediation Service.
Handles automatic recovery of failed streams with backoff and jitter.
"""

import json
import random
import subprocess
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict

import httpx
from flask import current_app

from app import db
from app.models import EventType, Stream, StreamEvent
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RemediationAction(str, Enum):
    """Types of remediation actions."""

    SOFT_RESET = "soft_reset"
    RECONNECT = "reconnect"
    RESTART_SIDECAR = "restart_sidecar"
    RESTART_PATH = "restart_path"
    RESTART_MEDIAMTX = "restart_mediamtx"


class RemediationResult:
    """Result of a remediation attempt."""

    def __init__(
        self,
        success: bool,
        action: RemediationAction,
        message: str,
        details: Dict = None,
    ):
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
            "timestamp": self.timestamp.isoformat(),
        }


class AutoRemediation:
    """
    Auto-remediation service with tiered retry strategy.

    Levels:
    0. Soft reset (flush buffer / re-pull source)
    1. Reconnect / Protocol-aware revival
    2. Restart sidecar (ffmpeg/gstreamer process)
    3. Restart specific path in MediaMTX
    4. Restart entire MediaMTX (last resort)
    """

    def __init__(self):
        self.config = {
            "max_attempts": (
                current_app.config.get("RETRY_MAX_ATTEMPTS", 5) if current_app else 5
            ),
            "base_delay": (
                current_app.config.get("RETRY_BASE_DELAY", 1.0) if current_app else 1.0
            ),
            "max_delay": (
                current_app.config.get("RETRY_MAX_DELAY", 60.0) if current_app else 60.0
            ),
            "jitter_factor": 0.3,  # 30% jitter
        }

    def calculate_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff with jitter.
        backoff = base_delay * 2^attempt * (1 + random_jitter)
        """
        base = self.config["base_delay"]
        max_delay = self.config["max_delay"]
        jitter = self.config["jitter_factor"]

        # Exponential backoff
        delay = base * (2**attempt)

        # Add jitter
        jitter_amount = delay * jitter * random.random()
        delay += jitter_amount

        # Cap at max delay
        return min(delay, max_delay)

    def remediate_stream(
        self,
        stream: Stream,
        force_level: int = None,
        trigger_source: str = "health_check",
    ) -> Dict[str, Any]:
        """
        Perform remediation on a stream.
        Tries increasingly aggressive actions until success.

        Args:
            stream: The stream to remediate
            force_level: Force starting at a specific level
            trigger_source: What triggered this ("liveness", "health_check", "manual")
        """
        # Activate fallback if configured
        fallback_activated = False
        if stream.fallback_type and stream.fallback_type != "none":
            try:
                from app.services.fallback_manager import FallbackManager

                fallback_mgr = FallbackManager()
                fb_result = fallback_mgr.activate_fallback(stream)
                fallback_activated = fb_result.get("success", False)
            except Exception as exc:
                logger.warning(
                    "fallback_activation_failed",
                    stream_id=stream.id,
                    path=stream.path,
                    error=str(exc),
                )

        # Create start event
        start_event = StreamEvent(
            stream_id=stream.id,
            event_type=EventType.REMEDIATION_STARTED.value,
            severity="info",
            message=f"Starting remediation for stream {stream.path} (trigger: {trigger_source})",
        )
        db.session.add(start_event)

        results = []
        success = False

        # Determine starting level
        if force_level is not None:
            start_level = force_level
        elif trigger_source == "liveness":
            start_level = 0  # Liveness triggers start at SOFT_RESET
        else:
            start_level = self._determine_start_level(stream)

        actions = [
            (0, RemediationAction.SOFT_RESET, self._try_soft_reset),
            (1, RemediationAction.RECONNECT, self._try_reconnect),
            (2, RemediationAction.RESTART_SIDECAR, self._try_restart_sidecar),
            (3, RemediationAction.RESTART_PATH, self._try_restart_path),
            (4, RemediationAction.RESTART_MEDIAMTX, self._try_restart_mediamtx),
        ]

        for level, action, handler in actions:
            if level < start_level:
                continue

            for attempt in range(self.config["max_attempts"]):
                result = handler(stream, attempt)
                results.append(result.to_dict())

                if result.success:
                    success = True
                    break

                # Wait before next attempt (skip after the final attempt so we
                # don't burn backoff time that risks the Celery task time limit)
                if attempt < self.config["max_attempts"] - 1:
                    delay = self.calculate_backoff(attempt)
                    time.sleep(delay)

            if success:
                break

        # Update stream
        stream.remediation_count += 1
        stream.last_remediation = datetime.utcnow()

        # Deactivate fallback if remediation succeeded
        if fallback_activated:
            try:
                from app.services.fallback_manager import FallbackManager

                fallback_mgr = FallbackManager()
                if success:
                    fallback_mgr.deactivate_fallback(stream)
                # On failure, keep fallback active
            except Exception as exc:
                logger.warning(
                    "fallback_deactivation_failed",
                    stream_id=stream.id,
                    path=stream.path,
                    error=str(exc),
                )

        # Create result event
        end_event = StreamEvent(
            stream_id=stream.id,
            event_type=(
                EventType.REMEDIATION_SUCCESS.value
                if success
                else EventType.REMEDIATION_FAILED.value
            ),
            severity="info" if success else "error",
            message=(
                f"Remediation {'succeeded' if success else 'failed'} "
                f"for stream {stream.path}"
            ),
            details_json=json.dumps(results),
        )
        db.session.add(end_event)
        db.session.commit()

        return {
            "success": success,
            "stream_id": stream.id,
            "stream_path": stream.path,
            "trigger_source": trigger_source,
            "fallback_activated": fallback_activated,
            "attempts": results,
            "total_attempts": len(results),
        }

    def _determine_start_level(self, stream: Stream) -> int:
        """Determine which remediation level to start at based on history."""
        # If stream has been remediated many times recently, start at higher level
        recent_remediations = StreamEvent.query.filter(
            StreamEvent.stream_id == stream.id,
            StreamEvent.event_type == EventType.REMEDIATION_STARTED.value,
            StreamEvent.created_at >= datetime.utcnow() - timedelta(hours=1),
        ).count()

        if recent_remediations >= 5:
            return 3  # Skip to restart path
        elif recent_remediations >= 2:
            return 2  # Skip to restart sidecar
        return 0  # Start from soft reset

    def _try_soft_reset(self, stream: Stream, attempt: int) -> RemediationResult:
        """Level 0: Soft reset - flush buffer / re-pull source via MediaMTX API."""
        try:
            node = stream.node
            api_url = node.api_url

            # Create soft reset event
            event = StreamEvent(
                stream_id=stream.id,
                event_type=EventType.SOFT_RESET_STARTED.value,
                severity="info",
                message=f"Soft reset attempt {attempt + 1} for {stream.path}",
            )
            db.session.add(event)

            # Get current path config
            response = httpx.get(
                f"{api_url}/v3/config/paths/get/{stream.path}", timeout=10
            )
            if response.status_code != 200:
                result_event = StreamEvent(
                    stream_id=stream.id,
                    event_type=EventType.SOFT_RESET_FAILED.value,
                    severity="warning",
                    message=f"Soft reset failed: could not get config (HTTP {response.status_code})",
                )
                db.session.add(result_event)
                return RemediationResult(
                    success=False,
                    action=RemediationAction.SOFT_RESET,
                    message=f"Failed to get path config: HTTP {response.status_code}",
                )

            config = response.json()
            source = config.get("source", "")

            if source:
                # Patch source to empty then back to force re-pull
                httpx.patch(
                    f"{api_url}/v3/config/paths/patch/{stream.path}",
                    json={"source": ""},
                    timeout=10,
                )
                time.sleep(1)
                httpx.patch(
                    f"{api_url}/v3/config/paths/patch/{stream.path}",
                    json={"source": source},
                    timeout=10,
                )
                time.sleep(2)

                result_event = StreamEvent(
                    stream_id=stream.id,
                    event_type=EventType.SOFT_RESET_SUCCESS.value,
                    severity="info",
                    message=f"Soft reset succeeded on attempt {attempt + 1}",
                )
                db.session.add(result_event)

                return RemediationResult(
                    success=True,
                    action=RemediationAction.SOFT_RESET,
                    message=f"Soft reset succeeded on attempt {attempt + 1}",
                )

            return RemediationResult(
                success=False,
                action=RemediationAction.SOFT_RESET,
                message="No source configured, cannot soft reset",
            )

        except Exception as e:
            return RemediationResult(
                success=False,
                action=RemediationAction.SOFT_RESET,
                message=f"Soft reset failed: {str(e)}",
            )

    def _try_reconnect(self, stream: Stream, attempt: int) -> RemediationResult:
        """Level 1: Try protocol-aware revival, fall back to generic reconnect."""
        # Try protocol-aware revival first
        try:
            from app.services.protocol_revival import ProtocolRevivalManager

            revival_mgr = ProtocolRevivalManager()
            result = revival_mgr.revive_path(stream)
            if result.get("success"):
                return RemediationResult(
                    success=True,
                    action=RemediationAction.RECONNECT,
                    message=f"Protocol revival succeeded: {result.get('message', '')}",
                    details=result,
                )
        except Exception:
            pass

        # Fall back to generic reconnect (kick sessions)
        try:
            node = stream.node
            api_url = node.api_url
            kicked_count = 0

            # Get all RTSP sessions and kick those on this path
            for session_type in ["rtspsessions", "rtspssessions"]:
                try:
                    list_resp = httpx.get(
                        f"{api_url}/v3/{session_type}/list", timeout=10
                    )
                    if list_resp.status_code == 200:
                        data = list_resp.json()
                        items = (
                            data.get("items", []) if isinstance(data, dict) else data
                        )
                        for session in items:
                            session_path = session.get("path", "")
                            session_id = session.get("id", "")
                            if session_path == stream.path and session_id:
                                kick_resp = httpx.post(
                                    f"{api_url}/v3/{session_type}/kick/{session_id}",
                                    timeout=10,
                                )
                                if kick_resp.status_code in [200, 204]:
                                    kicked_count += 1
                except Exception:
                    pass  # Continue with other session types

            if kicked_count > 0:
                time.sleep(2)
                return RemediationResult(
                    success=True,
                    action=RemediationAction.RECONNECT,
                    message=f"Successfully kicked {kicked_count} session(s) on attempt {attempt + 1}",
                    details={"kicked_sessions": kicked_count},
                )

            return RemediationResult(
                success=False,
                action=RemediationAction.RECONNECT,
                message="No active sessions found to kick, escalating to next level",
            )

        except Exception as e:
            return RemediationResult(
                success=False,
                action=RemediationAction.RECONNECT,
                message=f"Reconnect failed: {str(e)}",
            )

    def _try_restart_sidecar(self, stream: Stream, attempt: int) -> RemediationResult:
        """
        Restart the sidecar process (ffmpeg/gstreamer) for this stream.
        This is less disruptive than restarting the entire path.
        Uses correct MediaMTX API v3 endpoints.
        """
        try:
            node = stream.node
            api_url = node.api_url

            # Get current path config using correct endpoint
            response = httpx.get(
                f"{api_url}/v3/config/paths/get/{stream.path}",
                timeout=10,
            )
            if response.status_code != 200:
                return RemediationResult(
                    success=False,
                    action=RemediationAction.RESTART_SIDECAR,
                    message=f"Failed to get path config: HTTP {response.status_code}",
                )

            path_config = response.json()

            # Remove the path using correct endpoint
            delete_resp = httpx.delete(
                f"{api_url}/v3/config/paths/delete/{stream.path}",
                timeout=10,
            )
            if delete_resp.status_code not in [200, 204]:
                return RemediationResult(
                    success=False,
                    action=RemediationAction.RESTART_SIDECAR,
                    message=f"Failed to delete path: HTTP {delete_resp.status_code}",
                )

            time.sleep(1)

            # Re-add the path using correct endpoint
            add_resp = httpx.post(
                f"{api_url}/v3/config/paths/add/{stream.path}",
                json=path_config,
                timeout=10,
            )

            if add_resp.status_code not in [200, 201, 204]:
                return RemediationResult(
                    success=False,
                    action=RemediationAction.RESTART_SIDECAR,
                    message=f"Failed to re-add path: HTTP {add_resp.status_code}",
                )

            time.sleep(3)

            return RemediationResult(
                success=True,
                action=RemediationAction.RESTART_SIDECAR,
                message=f"Successfully restarted sidecar on attempt {attempt + 1}",
            )

        except Exception as e:
            return RemediationResult(
                success=False,
                action=RemediationAction.RESTART_SIDECAR,
                message=f"Sidecar restart failed: {str(e)}",
            )

    def _try_restart_path(self, stream: Stream, attempt: int) -> RemediationResult:
        """Restart the entire path in MediaMTX using correct API v3 endpoints."""
        try:
            node = stream.node
            api_url = node.api_url

            # Delete the path using correct endpoint (response intentionally ignored)
            httpx.delete(
                f"{api_url}/v3/config/paths/delete/{stream.path}",
                timeout=10,
            )

            # Path might not exist, which is OK
            time.sleep(2)

            # Recreate with source using correct endpoint
            if stream.source_url:
                create_resp = httpx.post(
                    f"{api_url}/v3/config/paths/add/{stream.path}",
                    json={"source": stream.source_url},
                    timeout=10,
                )

                if create_resp.status_code in [200, 201, 204]:
                    time.sleep(3)
                    return RemediationResult(
                        success=True,
                        action=RemediationAction.RESTART_PATH,
                        message=f"Successfully restarted path on attempt {attempt + 1}",
                    )

                return RemediationResult(
                    success=False,
                    action=RemediationAction.RESTART_PATH,
                    message=f"Failed to recreate path: HTTP {create_resp.status_code}",
                    details={
                        "response": create_resp.text[:200] if create_resp.text else ""
                    },
                )

            return RemediationResult(
                success=False,
                action=RemediationAction.RESTART_PATH,
                message="No source URL configured for stream",
            )

        except Exception as e:
            return RemediationResult(
                success=False,
                action=RemediationAction.RESTART_PATH,
                message=f"Path restart failed: {str(e)}",
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
                ["docker", "restart", container_name],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                # Wait for MediaMTX to come back up
                time.sleep(10)
                return RemediationResult(
                    success=True,
                    action=RemediationAction.RESTART_MEDIAMTX,
                    message=f"Successfully restarted MediaMTX on attempt {attempt + 1}",
                )

            return RemediationResult(
                success=False,
                action=RemediationAction.RESTART_MEDIAMTX,
                message=f"MediaMTX restart failed: {result.stderr}",
            )

        except Exception as e:
            return RemediationResult(
                success=False,
                action=RemediationAction.RESTART_MEDIAMTX,
                message=f"MediaMTX restart failed: {str(e)}",
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
            StreamEvent.created_at >= datetime.utcnow() - timedelta(hours=1),
        ).count()

        if recent_count >= 10:
            return False  # Too many recent failures, needs manual intervention

        return True
