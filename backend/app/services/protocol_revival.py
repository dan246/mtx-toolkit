"""
Protocol-Aware Path Revival Service.
Strategy pattern for protocol-specific stream recovery.
"""

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from app import db
from app.models import EventType, SourceProtocol, Stream, StreamEvent


class RevivalResult:
    """Result of a revival attempt."""

    def __init__(
        self, success: bool, protocol: str, message: str, details: Dict = None
    ):
        self.success = success
        self.protocol = protocol
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "protocol": self.protocol,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class ProtocolRevivalStrategy(ABC):
    """Base class for protocol-specific revival strategies."""

    @abstractmethod
    def detect_source_type(self, path_data: Dict) -> bool:
        """Check if this strategy applies to the given source."""

    @abstractmethod
    def revive(self, stream: Stream, node_api_url: str) -> RevivalResult:
        """Execute protocol-specific revival."""

    @abstractmethod
    def verify_recovery(self, stream: Stream, node_api_url: str) -> bool:
        """Verify the stream recovered after revival."""


class RTSPRevivalStrategy(ProtocolRevivalStrategy):
    """RTSP-specific revival: kick source session, rebuild TCP transport."""

    def detect_source_type(self, path_data: Dict) -> bool:
        source = path_data.get("source") or {}
        return "rtsp" in source.get("type", "").lower()

    def revive(self, stream: Stream, node_api_url: str) -> RevivalResult:
        try:
            kicked = 0
            for session_type in ["rtspsessions", "rtspssessions"]:
                try:
                    resp = httpx.get(
                        f"{node_api_url}/v3/{session_type}/list", timeout=10
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        items = (
                            data.get("items", []) if isinstance(data, dict) else data
                        )
                        for session in items:
                            if session.get("path") == stream.path:
                                session_id = session.get("id", "")
                                if session_id:
                                    kick_resp = httpx.post(
                                        f"{node_api_url}/v3/{session_type}/kick/{session_id}",
                                        timeout=10,
                                    )
                                    if kick_resp.status_code in [200, 204]:
                                        kicked += 1
                except Exception:
                    pass

            if kicked > 0:
                time.sleep(2)
                return RevivalResult(
                    success=True,
                    protocol="rtsp",
                    message=f"Kicked {kicked} RTSP session(s)",
                    details={"kicked_sessions": kicked},
                )

            return RevivalResult(
                success=False,
                protocol="rtsp",
                message="No RTSP sessions found to kick",
            )
        except Exception as e:
            return RevivalResult(
                success=False, protocol="rtsp", message=f"RTSP revival failed: {e}"
            )

    def verify_recovery(self, stream: Stream, node_api_url: str) -> bool:
        try:
            resp = httpx.get(f"{node_api_url}/v3/paths/list", timeout=5)
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    if item.get("name") == stream.path:
                        return item.get("ready", False)
        except Exception:
            pass
        return False


class RTMPRevivalStrategy(ProtocolRevivalStrategy):
    """RTMP-specific revival: reset ingest state via config patch."""

    def detect_source_type(self, path_data: Dict) -> bool:
        source = path_data.get("source") or {}
        return "rtmp" in source.get("type", "").lower()

    def revive(self, stream: Stream, node_api_url: str) -> RevivalResult:
        try:
            # Get current config
            resp = httpx.get(
                f"{node_api_url}/v3/config/paths/get/{stream.path}", timeout=10
            )
            if resp.status_code != 200:
                return RevivalResult(
                    success=False,
                    protocol="rtmp",
                    message=f"Failed to get path config: HTTP {resp.status_code}",
                )

            config = resp.json()

            # Delete and re-add to reset ingest state
            httpx.delete(
                f"{node_api_url}/v3/config/paths/delete/{stream.path}", timeout=10
            )
            time.sleep(1)

            add_resp = httpx.post(
                f"{node_api_url}/v3/config/paths/add/{stream.path}",
                json=config,
                timeout=10,
            )

            if add_resp.status_code in [200, 201, 204]:
                time.sleep(2)
                return RevivalResult(
                    success=True,
                    protocol="rtmp",
                    message="RTMP ingest state reset successfully",
                )

            return RevivalResult(
                success=False,
                protocol="rtmp",
                message=f"Failed to re-add RTMP path: HTTP {add_resp.status_code}",
            )
        except Exception as e:
            return RevivalResult(
                success=False, protocol="rtmp", message=f"RTMP revival failed: {e}"
            )

    def verify_recovery(self, stream: Stream, node_api_url: str) -> bool:
        try:
            resp = httpx.get(f"{node_api_url}/v3/paths/list", timeout=5)
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    if item.get("name") == stream.path:
                        return item.get("ready", False)
        except Exception:
            pass
        return False


class WebRTCRevivalStrategy(ProtocolRevivalStrategy):
    """WebRTC-specific revival: destroy/recreate WHIP/WHEP session."""

    def detect_source_type(self, path_data: Dict) -> bool:
        source = path_data.get("source") or {}
        source_type = source.get("type", "").lower()
        return "webrtc" in source_type or "whip" in source_type or "whep" in source_type

    def revive(self, stream: Stream, node_api_url: str) -> RevivalResult:
        try:
            # Kick all WebRTC sessions on this path
            kicked = 0
            for session_type in ["webrtcsessions"]:
                try:
                    resp = httpx.get(
                        f"{node_api_url}/v3/{session_type}/list", timeout=10
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        items = (
                            data.get("items", []) if isinstance(data, dict) else data
                        )
                        for session in items:
                            if session.get("path") == stream.path:
                                session_id = session.get("id", "")
                                if session_id:
                                    kick_resp = httpx.post(
                                        f"{node_api_url}/v3/{session_type}/kick/{session_id}",
                                        timeout=10,
                                    )
                                    if kick_resp.status_code in [200, 204]:
                                        kicked += 1
                except Exception:
                    pass

            if kicked > 0:
                time.sleep(3)
                return RevivalResult(
                    success=True,
                    protocol="webrtc",
                    message=f"Kicked {kicked} WebRTC session(s) for ICE restart",
                    details={"kicked_sessions": kicked},
                )

            return RevivalResult(
                success=False,
                protocol="webrtc",
                message="No WebRTC sessions found to kick",
            )
        except Exception as e:
            return RevivalResult(
                success=False, protocol="webrtc", message=f"WebRTC revival failed: {e}"
            )

    def verify_recovery(self, stream: Stream, node_api_url: str) -> bool:
        try:
            resp = httpx.get(f"{node_api_url}/v3/paths/list", timeout=5)
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    if item.get("name") == stream.path:
                        return item.get("ready", False)
        except Exception:
            pass
        return False


class HLSRevivalStrategy(ProtocolRevivalStrategy):
    """HLS-specific revival: rebuild playlist, re-segment."""

    def detect_source_type(self, path_data: Dict) -> bool:
        source = path_data.get("source") or {}
        return "hls" in source.get("type", "").lower()

    def revive(self, stream: Stream, node_api_url: str) -> RevivalResult:
        try:
            # Get config, delete, re-add
            resp = httpx.get(
                f"{node_api_url}/v3/config/paths/get/{stream.path}", timeout=10
            )
            if resp.status_code != 200:
                return RevivalResult(
                    success=False,
                    protocol="hls",
                    message=f"Failed to get path config: HTTP {resp.status_code}",
                )

            config = resp.json()

            httpx.delete(
                f"{node_api_url}/v3/config/paths/delete/{stream.path}", timeout=10
            )
            time.sleep(2)

            add_resp = httpx.post(
                f"{node_api_url}/v3/config/paths/add/{stream.path}",
                json=config,
                timeout=10,
            )

            if add_resp.status_code in [200, 201, 204]:
                time.sleep(3)
                return RevivalResult(
                    success=True,
                    protocol="hls",
                    message="HLS playlist rebuilt successfully",
                )

            return RevivalResult(
                success=False,
                protocol="hls",
                message=f"Failed to re-add HLS path: HTTP {add_resp.status_code}",
            )
        except Exception as e:
            return RevivalResult(
                success=False, protocol="hls", message=f"HLS revival failed: {e}"
            )

    def verify_recovery(self, stream: Stream, node_api_url: str) -> bool:
        try:
            resp = httpx.get(f"{node_api_url}/v3/paths/list", timeout=5)
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    if item.get("name") == stream.path:
                        return item.get("ready", False)
        except Exception:
            pass
        return False


class ProtocolRevivalManager:
    """Manages protocol-aware stream revival."""

    def __init__(self):
        self.strategies = [
            RTSPRevivalStrategy(),
            RTMPRevivalStrategy(),
            WebRTCRevivalStrategy(),
            HLSRevivalStrategy(),
        ]

    def detect_source_protocol(
        self, stream: Stream, node_api_url: str
    ) -> SourceProtocol:
        """Detect source protocol from MediaMTX API."""
        try:
            resp = httpx.get(f"{node_api_url}/v3/paths/list", timeout=5)
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    if item.get("name") == stream.path:
                        return self._classify_protocol(item)
        except Exception:
            pass
        return SourceProtocol.UNKNOWN

    def _classify_protocol(self, path_data: Dict) -> SourceProtocol:
        """Classify protocol from path data."""
        source = path_data.get("source") or {}
        source_type = source.get("type", "").lower()

        if "rtsp" in source_type:
            return SourceProtocol.RTSP
        elif "rtmp" in source_type:
            return SourceProtocol.RTMP
        elif "webrtc" in source_type or "whip" in source_type:
            return SourceProtocol.WHIP
        elif "whep" in source_type:
            return SourceProtocol.WHEP
        elif "hls" in source_type:
            return SourceProtocol.HLS
        elif "srt" in source_type:
            return SourceProtocol.SRT
        return SourceProtocol.UNKNOWN

    def _get_strategy(self, path_data: Dict) -> Optional[ProtocolRevivalStrategy]:
        """Find matching revival strategy for path data."""
        for strategy in self.strategies:
            if strategy.detect_source_type(path_data):
                return strategy
        return None

    def revive_path(self, stream: Stream) -> Dict[str, Any]:
        """Execute protocol-aware revival for a stream."""
        node = stream.node
        api_url = node.api_url

        # Create start event
        start_event = StreamEvent(
            stream_id=stream.id,
            event_type=EventType.PROTOCOL_REVIVAL_STARTED.value,
            severity="info",
            message=f"Starting protocol revival for {stream.path}",
        )
        db.session.add(start_event)

        # Get path data for strategy selection
        try:
            resp = httpx.get(f"{api_url}/v3/paths/list", timeout=5)
            path_data = {}
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    if item.get("name") == stream.path:
                        path_data = item
                        break
        except Exception:
            path_data = {}

        strategy = self._get_strategy(path_data)
        if not strategy:
            # Fallback to generic
            result = RevivalResult(
                success=False,
                protocol="unknown",
                message="No protocol-specific strategy found",
            )
        else:
            result = strategy.revive(stream, api_url)

            # Verify recovery
            if result.success:
                time.sleep(2)
                verified = strategy.verify_recovery(stream, api_url)
                if not verified:
                    result = RevivalResult(
                        success=False,
                        protocol=result.protocol,
                        message="Revival executed but recovery not verified",
                        details=result.details,
                    )

        # Create result event
        end_event = StreamEvent(
            stream_id=stream.id,
            event_type=(
                EventType.PROTOCOL_REVIVAL_SUCCESS.value
                if result.success
                else EventType.PROTOCOL_REVIVAL_FAILED.value
            ),
            severity="info" if result.success else "warning",
            message=result.message,
            details_json=json.dumps(result.to_dict()),
        )
        db.session.add(end_event)
        db.session.commit()

        return result.to_dict()
