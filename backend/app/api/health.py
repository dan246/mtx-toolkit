"""
Health check API endpoints.
E2E stream health monitoring with ffprobe/gstreamer.
"""

from flask import Blueprint, jsonify, request

from app.services.health_checker import HealthChecker

health_bp = Blueprint("health", __name__)
checker = HealthChecker()


@health_bp.route("/", methods=["GET"])
def get_health_status():
    """Get overall system health status."""
    return jsonify(
        {
            "status": "ok",
            "service": "mtx-toolkit",
            "checks": {
                "database": "ok",
                "redis": checker.check_redis(),
                "mediamtx": checker.check_mediamtx_api(),
            },
        }
    )


@health_bp.route("/streams", methods=["GET"])
def get_streams_health():
    """Get health status of all monitored streams."""
    node_id = request.args.get("node_id", type=int)
    status_filter = request.args.get("status")

    results = checker.get_all_streams_health(node_id=node_id, status=status_filter)
    return jsonify(results)


@health_bp.route("/streams/<int:stream_id>", methods=["GET"])
def get_stream_health(stream_id: int):
    """Get detailed health info for a specific stream."""
    result = checker.get_stream_health(stream_id)
    if not result:
        return jsonify({"error": "Stream not found"}), 404
    return jsonify(result)


@health_bp.route("/streams/<int:stream_id>/probe", methods=["POST"])
def probe_stream(stream_id: int):
    """Manually trigger a health probe for a stream."""
    result = checker.probe_stream(stream_id)
    return jsonify(result)


@health_bp.route("/probe", methods=["POST"])
def probe_url():
    """Probe a stream URL directly (without saving)."""
    data = request.get_json()
    url = data.get("url")
    protocol = data.get("protocol", "rtsp")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    result = checker.probe_url(url, protocol)
    return jsonify(result)


@health_bp.route("/playback-report", methods=["POST"])
def submit_playback_report():
    """Receive client-side playback health report."""
    from app import db
    from app.models import ClientPlaybackReport, Stream

    data = request.get_json()
    stream_id = data.get("stream_id")

    if not stream_id:
        return jsonify({"error": "stream_id is required"}), 400

    stream = Stream.query.get(stream_id)
    if not stream:
        return jsonify({"error": "Stream not found"}), 404

    report = ClientPlaybackReport(
        stream_id=stream_id,
        client_id=data.get("client_id"),
        client_ip=request.remote_addr,
        stall_count=data.get("stall_count", 0),
        stall_duration_ms=data.get("stall_duration_ms", 0),
        buffer_underrun_count=data.get("buffer_underrun_count", 0),
        frames_decoded=data.get("frames_decoded"),
        frames_dropped=data.get("frames_dropped"),
        current_level=data.get("current_level"),
        recovery_action=data.get("recovery_action"),
        error_type=data.get("error_type"),
    )
    db.session.add(report)
    db.session.commit()

    return jsonify({"success": True, "report_id": report.id}), 201


@health_bp.route("/playback-reports/<int:stream_id>", methods=["GET"])
def get_playback_reports(stream_id: int):
    """Get recent playback reports for a stream."""
    from app.models import ClientPlaybackReport

    limit = request.args.get("limit", 50, type=int)

    reports = (
        ClientPlaybackReport.query.filter_by(stream_id=stream_id)
        # id is the tie-breaker so ordering is stable when rows share a
        # created_at timestamp (sub-second collisions in fast inserts/tests).
        .order_by(
            ClientPlaybackReport.created_at.desc(),
            ClientPlaybackReport.id.desc(),
        )
        .limit(limit)
        .all()
    )

    return jsonify(
        {
            "stream_id": stream_id,
            "reports": [
                {
                    "id": r.id,
                    "client_id": r.client_id,
                    "client_ip": r.client_ip,
                    "stall_count": r.stall_count,
                    "stall_duration_ms": r.stall_duration_ms,
                    "buffer_underrun_count": r.buffer_underrun_count,
                    "frames_decoded": r.frames_decoded,
                    "frames_dropped": r.frames_dropped,
                    "current_level": r.current_level,
                    "recovery_action": r.recovery_action,
                    "error_type": r.error_type,
                    "created_at": r.created_at.isoformat(),
                }
                for r in reports
            ],
            "total": len(reports),
        }
    )


@health_bp.route("/quick-check", methods=["POST"])
def quick_check_all():
    """
    Fast health check using MediaMTX API.
    Can check 1000+ streams in seconds.
    """
    from app.services.health_checker import HealthChecker

    checker = HealthChecker()
    result = checker.quick_check_all_nodes()
    return jsonify(result)


@health_bp.route("/quick-check/<int:node_id>", methods=["POST"])
def quick_check_node(node_id: int):
    """Fast health check for a specific node."""
    from app.services.health_checker import HealthChecker

    checker = HealthChecker()
    result = checker.quick_check_node(node_id)
    return jsonify(result)
