"""
Sessions API endpoints.
Real-time viewer session data from MediaMTX nodes.
"""

from flask import Blueprint, jsonify, request

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.route("/", methods=["GET"])
def list_sessions():
    """
    List all viewer sessions across all nodes.

    Query Parameters:
        node_id: Filter by specific node ID
        protocol: Filter by protocol (rtsp, rtsps, webrtc, rtmp, srt)
        path: Filter by stream path
        page: Page number (default: 1)
        per_page: Items per page (default: 50)

    Returns:
        JSON with sessions list, pagination info, and summary
    """
    from app.services.session_manager import SessionManager

    node_id = request.args.get("node_id", type=int)
    protocol = request.args.get("protocol")
    path = request.args.get("path")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    # Validate protocol
    valid_protocols = ["rtsp", "rtsps", "webrtc", "rtmp", "srt"]
    if protocol and protocol not in valid_protocols:
        return (
            jsonify(
                {
                    "error": f"Invalid protocol. Must be one of: {', '.join(valid_protocols)}"
                }
            ),
            400,
        )

    manager = SessionManager()
    result = manager.get_all_sessions(
        node_id=node_id,
        protocol=protocol,
        path=path,
        page=page,
        per_page=per_page,
    )

    return jsonify(result)


@sessions_bp.route("/summary", methods=["GET"])
def get_summary():
    """
    Get summary statistics of all viewer sessions.

    Returns:
        JSON with total viewers and breakdown by protocol, node, and path
    """
    from app.services.session_manager import SessionManager

    manager = SessionManager()
    result = manager.get_sessions_summary()

    return jsonify(result)


@sessions_bp.route("/node/<int:node_id>", methods=["GET"])
def get_node_sessions(node_id: int):
    """
    Get all viewer sessions from a specific node.

    Args:
        node_id: The node ID to fetch sessions from

    Query Parameters:
        protocol: Filter by protocol (rtsp, rtsps, webrtc, rtmp, srt)
        page: Page number (default: 1)
        per_page: Items per page (default: 50)

    Returns:
        JSON with sessions list and summary for the specific node
    """
    from app.services.session_manager import SessionManager

    protocol = request.args.get("protocol")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    manager = SessionManager()
    result = manager.get_all_sessions(
        node_id=node_id,
        protocol=protocol,
        page=page,
        per_page=per_page,
    )

    return jsonify(result)


@sessions_bp.route("/stream/<int:stream_id>", methods=["GET"])
def get_stream_sessions(stream_id: int):
    """
    Get all viewer sessions for a specific stream.

    Args:
        stream_id: The stream ID to fetch viewers for

    Query Parameters:
        page: Page number (default: 1)
        per_page: Items per page (default: 50)

    Returns:
        JSON with sessions list for viewers of this specific stream
    """
    from app.services.session_manager import SessionManager

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    manager = SessionManager()
    result = manager.get_path_sessions(path="", stream_id=stream_id)

    # Apply pagination manually since get_path_sessions doesn't support it directly
    sessions = result.get("sessions", [])
    total = len(sessions)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    return jsonify(
        {
            "sessions": sessions[start_idx:end_idx],
            "summary": result.get("summary", {}),
            "total": total,
            "page": page,
            "pages": (total + per_page - 1) // per_page if total > 0 else 1,
        }
    )


@sessions_bp.route("/path/<path:stream_path>", methods=["GET"])
def get_path_viewers(stream_path: str):
    """
    Get all viewer sessions for a specific stream path.

    Args:
        stream_path: The stream path to fetch viewers for

    Query Parameters:
        page: Page number (default: 1)
        per_page: Items per page (default: 50)

    Returns:
        JSON with sessions list for viewers of this specific path
    """
    from app.services.session_manager import SessionManager

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    manager = SessionManager()
    result = manager.get_all_sessions(
        path=stream_path,
        page=page,
        per_page=per_page,
    )

    return jsonify(result)


@sessions_bp.route("/kick", methods=["POST"])
def kick_session():
    """
    Kick (disconnect) a viewer session.

    Request Body:
        node_id: The node ID where the session is (required)
        session_id: The session ID to kick (required)
        protocol: The protocol (rtsp, rtsps, webrtc, rtmp, srt) (required)

    Returns:
        JSON with success status and message
    """
    from app.services.session_manager import SessionManager

    data = request.get_json()
    node_id = data.get("node_id")
    session_id = data.get("session_id")
    protocol = data.get("protocol")

    if not all([node_id, session_id, protocol]):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Missing required fields: node_id, session_id, protocol",
                }
            ),
            400,
        )

    manager = SessionManager()
    result = manager.kick_session(
        node_id=node_id,
        session_id=session_id,
        protocol=protocol,
    )

    return jsonify(result)
