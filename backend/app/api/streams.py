"""
Streams management API endpoints.
"""

import os
from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, abort, jsonify, request, send_file

from app import db
from app.models import MediaMTXNode, Stream
from app.services.thumbnail_service import thumbnail_service

streams_bp = Blueprint("streams", __name__)

# HLS port configuration (MediaMTX default is 8888)
HLS_PORT = int(os.getenv("MEDIAMTX_HLS_PORT", "8888"))


@streams_bp.route("/", methods=["GET"])
def list_streams():
    """List all monitored streams."""
    node_id = request.args.get("node_id", type=int)
    status = request.args.get("status")
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    query = Stream.query
    if node_id:
        query = query.filter_by(node_id=node_id)
    if status:
        query = query.filter_by(status=status)
    if search:
        # Search in path and name (case-insensitive)
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(Stream.path.ilike(search_pattern), Stream.name.ilike(search_pattern))
        )

    pagination = query.order_by(Stream.path).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify(
        {
            "streams": [
                {
                    "id": s.id,
                    "node_id": s.node_id,
                    "path": s.path,
                    "name": s.name,
                    "source_url": s.source_url,
                    "protocol": s.protocol,
                    "status": s.status,
                    "fps": s.fps,
                    "bitrate": s.bitrate,
                    "viewers": s.viewers,
                    "bytes_received": s.bytes_received,
                    "bytes_sent": s.bytes_sent,
                    "frames_in_error": s.frames_in_error,
                    "source_type": s.source_type,
                    "codec": s.codec,
                    "width": s.width,
                    "height": s.height,
                    "online_since": (
                        s.online_since.isoformat() if s.online_since else None
                    ),
                    "uptime_seconds": (
                        int((datetime.utcnow() - s.online_since).total_seconds())
                        if s.online_since
                        else None
                    ),
                    "auto_remediate": s.auto_remediate,
                    "recording_enabled": s.recording_enabled,
                    "last_check": s.last_check.isoformat() if s.last_check else None,
                }
                for s in pagination.items
            ],
            "total": pagination.total,
            "page": page,
            "pages": pagination.pages,
        }
    )


@streams_bp.route("/<int:stream_id>", methods=["GET"])
def get_stream(stream_id: int):
    """Get stream details."""
    stream = Stream.query.get_or_404(stream_id)
    return jsonify(
        {
            "id": stream.id,
            "node_id": stream.node_id,
            "path": stream.path,
            "name": stream.name,
            "source_url": stream.source_url,
            "protocol": stream.protocol,
            "status": stream.status,
            "fps": stream.fps,
            "bitrate": stream.bitrate,
            "latency_ms": stream.latency_ms,
            "keyframe_interval": stream.keyframe_interval,
            "auto_remediate": stream.auto_remediate,
            "remediation_count": stream.remediation_count,
            "last_remediation": (
                stream.last_remediation.isoformat() if stream.last_remediation else None
            ),
            "recording_enabled": stream.recording_enabled,
            "last_check": stream.last_check.isoformat() if stream.last_check else None,
            "created_at": stream.created_at.isoformat(),
            "updated_at": stream.updated_at.isoformat(),
        }
    )


@streams_bp.route("/", methods=["POST"])
def create_stream():
    """Create a new stream to monitor."""
    data = request.get_json()

    # Validate node exists
    node = MediaMTXNode.query.get(data.get("node_id"))
    if not node:
        return jsonify({"error": "Node not found"}), 404

    stream = Stream(
        node_id=data["node_id"],
        path=data["path"],
        name=data.get("name"),
        source_url=data.get("source_url"),
        protocol=data.get("protocol", "rtsp"),
        auto_remediate=data.get("auto_remediate", True),
        recording_enabled=data.get("recording_enabled", False),
    )

    db.session.add(stream)
    db.session.commit()

    return jsonify({"id": stream.id, "message": "Stream created"}), 201


@streams_bp.route("/<int:stream_id>", methods=["PUT"])
def update_stream(stream_id: int):
    """Update stream configuration."""
    stream = Stream.query.get_or_404(stream_id)
    data = request.get_json()

    for field in [
        "name",
        "source_url",
        "protocol",
        "auto_remediate",
        "recording_enabled",
    ]:
        if field in data:
            setattr(stream, field, data[field])

    db.session.commit()
    return jsonify({"message": "Stream updated"})


@streams_bp.route("/<int:stream_id>", methods=["DELETE"])
def delete_stream(stream_id: int):
    """Delete a stream from monitoring."""
    stream = Stream.query.get_or_404(stream_id)
    db.session.delete(stream)
    db.session.commit()
    return jsonify({"message": "Stream deleted"})


@streams_bp.route("/<int:stream_id>/remediate", methods=["POST"])
def trigger_remediation(stream_id: int):
    """Manually trigger remediation for a stream."""
    from app.services.auto_remediation import AutoRemediation

    stream = Stream.query.get_or_404(stream_id)
    remediation = AutoRemediation()
    result = remediation.remediate_stream(stream)

    return jsonify(result)


@streams_bp.route("/<int:stream_id>/soft-reset", methods=["POST"])
def trigger_soft_reset(stream_id: int):
    """Trigger a soft reset for a stream."""
    from app.services.auto_remediation import AutoRemediation

    stream = Stream.query.get_or_404(stream_id)
    remediation = AutoRemediation()
    result = remediation.remediate_stream(
        stream, force_level=0, trigger_source="manual"
    )
    return jsonify(result)


@streams_bp.route("/<int:stream_id>/revive", methods=["POST"])
def trigger_revival(stream_id: int):
    """Trigger protocol-aware revival for a stream."""
    from app.services.protocol_revival import ProtocolRevivalManager

    stream = Stream.query.get_or_404(stream_id)
    manager = ProtocolRevivalManager()
    result = manager.revive_path(stream)
    return jsonify(result)


def _get_hls_base_url(node: MediaMTXNode, use_proxy: bool = True) -> str:
    """Derive HLS base URL from node's API URL.

    Args:
        node: The MediaMTX node
        use_proxy: If True, return relative path for nginx proxy (/hls/nodeX)
                   If False, return direct MediaMTX URL
    """
    if use_proxy:
        # Use nginx proxy path with node ID - works in Docker environment
        # nginx routes /hls/node1/, /hls/node3/ to different MediaMTX instances
        return f"/hls/node{node.id}"

    # Direct connection to MediaMTX (for development or direct access)
    parsed = urlparse(node.api_url)
    return f"http://{parsed.hostname}:{HLS_PORT}"


@streams_bp.route("/<int:stream_id>/playback", methods=["GET"])
def get_stream_playback(stream_id: int):
    """Get playback URLs for a stream (HLS/WebRTC)."""
    stream = Stream.query.get_or_404(stream_id)
    node = MediaMTXNode.query.get_or_404(stream.node_id)

    hls_base = _get_hls_base_url(node)

    return jsonify(
        {
            "stream_id": stream.id,
            "path": stream.path,
            "hls_url": f"{hls_base}/{stream.path}/index.m3u8",
            "hls_base_url": hls_base,
            "status": stream.status,
        }
    )


@streams_bp.route("/playback/config", methods=["GET"])
def get_playback_config():
    """Get global playback configuration for all streams."""
    # Get all active nodes and their HLS base URLs
    nodes = MediaMTXNode.query.filter_by(is_active=True).all()

    nodes_config = {}
    for node in nodes:
        nodes_config[node.id] = {
            "name": node.name,
            "hls_base_url": _get_hls_base_url(node),
            "environment": node.environment,
        }

    return jsonify({"hls_port": HLS_PORT, "nodes": nodes_config})


@streams_bp.route("/<int:stream_id>/thumbnail", methods=["GET"])
def get_stream_thumbnail(stream_id: int):
    """Get thumbnail image for a stream (cached only, no on-the-fly generation)."""
    stream = Stream.query.get_or_404(stream_id)
    node = MediaMTXNode.query.get_or_404(stream.node_id)

    # Only return cached thumbnail - no on-the-fly generation to avoid blocking
    thumb_path = thumbnail_service.get_cached_thumbnail(stream.path, node.id)

    if thumb_path and os.path.exists(thumb_path):
        return send_file(
            thumb_path, mimetype="image/jpeg", max_age=30  # Cache for 30 seconds
        )

    # Return 404 - frontend will show placeholder
    abort(404, description="Thumbnail not available")


@streams_bp.route("/thumbnail/batch", methods=["POST"])
def generate_thumbnails_batch():
    """Generate thumbnails for multiple streams (runs in background)."""
    import threading

    data = request.get_json() or {}
    stream_ids = data.get("stream_ids", [])
    force = data.get("force", False)
    sync = data.get("sync", False)  # If true, run synchronously

    if not stream_ids:
        # Generate for all healthy streams (limit 50)
        streams = Stream.query.filter_by(status="healthy").limit(50).all()
    else:
        streams = Stream.query.filter(Stream.id.in_(stream_ids)).all()

    # Prepare stream info for background processing
    stream_infos = []
    for stream in streams:
        node = MediaMTXNode.query.get(stream.node_id)
        if node:
            stream_infos.append(
                {
                    "stream_id": stream.id,
                    "path": stream.path,
                    "node_id": node.id,
                    "api_url": node.api_url,
                }
            )

    def generate_in_background(infos, force_regen):
        """Background thumbnail generation."""
        for info in infos:
            thumbnail_service.generate_thumbnail(
                info["path"], info["node_id"], info["api_url"], force=force_regen
            )

    if sync:
        # Synchronous generation (for testing)
        generate_in_background(stream_infos, force)
        return jsonify({"status": "completed", "total": len(stream_infos)})
    else:
        # Start background thread
        thread = threading.Thread(
            target=generate_in_background, args=(stream_infos, force)
        )
        thread.daemon = True
        thread.start()

        return jsonify(
            {
                "status": "started",
                "total": len(stream_infos),
                "message": "Thumbnail generation started in background",
            }
        )
