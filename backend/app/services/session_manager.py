"""
Session Manager Service.
Fetches and aggregates viewer sessions from all MediaMTX nodes.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.models import MediaMTXNode, Stream


class SessionManager:
    """
    Session management for tracking viewers across MediaMTX nodes.

    Features:
    - Fetch sessions from all protocols (RTSP, RTSPS, WebRTC, RTMP, SRT)
    - Aggregate sessions across nodes
    - Filter and summarize session data
    """

    SESSION_ENDPOINTS = {
        "rtsp": "/v3/rtspsessions/list",
        "rtsps": "/v3/rtspssessions/list",
        "webrtc": "/v3/webrtcsessions/list",
        "rtmp": "/v3/rtmpconns/list",
        "srt": "/v3/srtconns/list",
    }

    KICK_ENDPOINTS = {
        "rtsp": "/v3/rtspsessions/kick/",
        "rtsps": "/v3/rtspssessions/kick/",
        "webrtc": "/v3/webrtcsessions/kick/",
        "rtmp": "/v3/rtmpconns/kick/",
        "srt": "/v3/srtconns/kick/",
    }

    def __init__(self):
        self.timeout = 10

    def get_all_sessions(
        self,
        node_id: Optional[int] = None,
        protocol: Optional[str] = None,
        path: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
        viewers_only: bool = True,
    ) -> Dict[str, Any]:
        """
        Get all sessions from all nodes or a specific node.

        Args:
            node_id: Filter by specific node
            protocol: Filter by protocol (rtsp, rtsps, webrtc, rtmp, srt)
            path: Filter by stream path
            page: Page number for pagination
            per_page: Number of items per page
            viewers_only: If True, only return viewers (state=read), not publishers

        Returns:
            Dict with sessions list and summary
        """
        # Get target nodes
        if node_id:
            nodes = MediaMTXNode.query.filter_by(id=node_id, is_active=True).all()
        else:
            nodes = MediaMTXNode.query.filter_by(is_active=True).all()

        all_sessions = []
        errors = []

        for node in nodes:
            node_sessions, node_errors = self._fetch_node_sessions(node, protocol)
            all_sessions.extend(node_sessions)
            errors.extend(node_errors)

        # Filter to only show viewers (read state), not publishers
        if viewers_only:
            all_sessions = [s for s in all_sessions if s.get("state") == "read"]

        # Filter by path if specified
        if path:
            all_sessions = [s for s in all_sessions if s.get("path") == path]

        # Sort by created time (most recent first)
        all_sessions.sort(key=lambda x: x.get("created", ""), reverse=True)

        # Calculate summary before pagination
        summary = self._calculate_summary(all_sessions)

        # Apply pagination
        total = len(all_sessions)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_sessions = all_sessions[start_idx:end_idx]

        return {
            "sessions": paginated_sessions,
            "summary": summary,
            "total": total,
            "page": page,
            "pages": (total + per_page - 1) // per_page if total > 0 else 1,
            "errors": errors if errors else None,
        }

    def get_node_sessions(self, node_id: int) -> Dict[str, Any]:
        """Get all sessions from a specific node."""
        return self.get_all_sessions(node_id=node_id)

    def get_path_sessions(
        self, path: str, stream_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get all sessions viewing a specific path.

        Args:
            path: The stream path to filter by
            stream_id: Optional stream ID to look up the path from database
        """
        # If stream_id provided, look up the path
        if stream_id:
            stream = Stream.query.get(stream_id)
            if stream:
                path = stream.path

        return self.get_all_sessions(path=path)

    def get_sessions_summary(self) -> Dict[str, Any]:
        """Get summary statistics without full session list."""
        result = self.get_all_sessions(per_page=10000)  # Get all for accurate summary
        return {
            "summary": result["summary"],
            "total_viewers": result["summary"]["total_viewers"],
            "errors": result.get("errors"),
        }

    def _fetch_node_sessions(
        self, node: MediaMTXNode, protocol_filter: Optional[str] = None
    ) -> tuple[List[Dict], List[Dict]]:
        """
        Fetch all sessions from a single node.

        Returns:
            Tuple of (sessions list, errors list)
        """
        sessions = []
        errors = []

        # Determine which endpoints to query
        endpoints = self.SESSION_ENDPOINTS
        if protocol_filter and protocol_filter in endpoints:
            endpoints = {protocol_filter: endpoints[protocol_filter]}

        for protocol, endpoint in endpoints.items():
            try:
                response = httpx.get(f"{node.api_url}{endpoint}", timeout=self.timeout)

                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])

                    for item in items:
                        session = self._normalize_session(item, node, protocol)
                        if session:
                            sessions.append(session)
                elif response.status_code != 404:
                    # 404 means the endpoint doesn't exist (protocol not enabled)
                    errors.append(
                        {
                            "node_id": node.id,
                            "node_name": node.name,
                            "protocol": protocol,
                            "error": f"HTTP {response.status_code}",
                        }
                    )

            except httpx.TimeoutException:
                errors.append(
                    {
                        "node_id": node.id,
                        "node_name": node.name,
                        "protocol": protocol,
                        "error": "Connection timeout",
                    }
                )
            except Exception as e:
                errors.append(
                    {
                        "node_id": node.id,
                        "node_name": node.name,
                        "protocol": protocol,
                        "error": str(e),
                    }
                )

        return sessions, errors

    def _normalize_session(
        self, item: Dict, node: MediaMTXNode, protocol: str
    ) -> Optional[Dict[str, Any]]:
        """
        Normalize session data from different protocol endpoints.

        Different protocols have slightly different response formats,
        this method normalizes them to a common structure.
        """
        try:
            # Common fields across all protocols
            session_id = item.get("id", "")
            created = item.get("created", "")
            remote_addr = item.get("remoteAddr", "")
            state = item.get("state", "unknown")

            # Extract client IP and port from remote_addr
            client_ip = remote_addr
            client_port = 0
            if ":" in remote_addr:
                # Handle IPv6 addresses like [::1]:port
                if remote_addr.startswith("["):
                    bracket_end = remote_addr.rfind("]")
                    if bracket_end != -1 and ":" in remote_addr[bracket_end:]:
                        client_ip = remote_addr[1:bracket_end]
                        try:
                            client_port = int(remote_addr[bracket_end + 2 :])
                        except ValueError:
                            pass
                else:
                    # IPv4 address:port
                    parts = remote_addr.rsplit(":", 1)
                    client_ip = parts[0]
                    if len(parts) > 1:
                        try:
                            client_port = int(parts[1])
                        except ValueError:
                            pass

            # Calculate duration if created time exists
            duration_seconds = 0
            if created:
                try:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    duration_seconds = int(
                        (datetime.now(created_dt.tzinfo) - created_dt).total_seconds()
                    )
                except Exception:
                    pass

            # Protocol-specific fields
            path = item.get("path", "")
            bytes_received = item.get("bytesReceived", 0)
            bytes_sent = item.get("bytesSent", 0)

            # Transport info (RTSP-specific)
            transport = item.get("transport", "")

            return {
                "id": session_id,
                "node_id": node.id,
                "node_name": node.name,
                "path": path,
                "protocol": protocol,
                "remote_addr": remote_addr,
                "client_ip": client_ip,
                "client_port": client_port,
                "state": state,
                "created": created,
                "duration_seconds": duration_seconds,
                "bytes_received": bytes_received,
                "bytes_sent": bytes_sent,
                "transport": transport,
            }

        except Exception:
            return None

    def kick_session(
        self,
        node_id: int,
        session_id: str,
        protocol: str,
    ) -> Dict[str, Any]:
        """
        Kick (disconnect) a viewer session.

        Args:
            node_id: The node ID where the session is
            session_id: The session ID to kick
            protocol: The protocol (rtsp, rtsps, webrtc, rtmp, srt)

        Returns:
            Dict with success status and message
        """
        node = MediaMTXNode.query.filter_by(id=node_id, is_active=True).first()
        if not node:
            return {"success": False, "error": "Node not found"}

        if protocol not in self.KICK_ENDPOINTS:
            return {"success": False, "error": f"Invalid protocol: {protocol}"}

        endpoint = self.KICK_ENDPOINTS[protocol]

        try:
            response = httpx.post(
                f"{node.api_url}{endpoint}{session_id}", timeout=self.timeout
            )

            kicked = response.status_code == 200
            return {
                "success": kicked,
                "kicked": kicked,
                "message": (
                    f"Session {session_id} kicked successfully"
                    if kicked
                    else f"Failed to kick: HTTP {response.status_code}"
                ),
            }

        except httpx.TimeoutException:
            return {"success": False, "error": "Connection timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _calculate_summary(self, sessions: List[Dict]) -> Dict[str, Any]:
        """Calculate summary statistics from sessions list."""
        by_protocol: Dict[str, int] = {}
        by_node: Dict[str, int] = {}
        by_path: Dict[str, int] = {}

        for session in sessions:
            # Count by protocol
            protocol = session.get("protocol", "unknown")
            by_protocol[protocol] = by_protocol.get(protocol, 0) + 1

            # Count by node
            node_name = session.get("node_name", "unknown")
            by_node[node_name] = by_node.get(node_name, 0) + 1

            # Count by path
            path = session.get("path", "unknown")
            by_path[path] = by_path.get(path, 0) + 1

        return {
            "total_viewers": len(sessions),
            "by_protocol": by_protocol,
            "by_node": by_node,
            "by_path": by_path,
        }
