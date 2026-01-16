"""
Health check API endpoints.
E2E stream health monitoring with ffprobe/gstreamer.
"""
from flask import Blueprint, jsonify, request
from app.services.health_checker import HealthChecker

health_bp = Blueprint('health', __name__)
checker = HealthChecker()


@health_bp.route('/', methods=['GET'])
def get_health_status():
    """Get overall system health status."""
    return jsonify({
        "status": "ok",
        "service": "mtx-toolkit",
        "checks": {
            "database": "ok",
            "redis": checker.check_redis(),
            "mediamtx": checker.check_mediamtx_api()
        }
    })


@health_bp.route('/streams', methods=['GET'])
def get_streams_health():
    """Get health status of all monitored streams."""
    node_id = request.args.get('node_id', type=int)
    status_filter = request.args.get('status')

    results = checker.get_all_streams_health(node_id=node_id, status=status_filter)
    return jsonify(results)


@health_bp.route('/streams/<int:stream_id>', methods=['GET'])
def get_stream_health(stream_id: int):
    """Get detailed health info for a specific stream."""
    result = checker.get_stream_health(stream_id)
    if not result:
        return jsonify({"error": "Stream not found"}), 404
    return jsonify(result)


@health_bp.route('/streams/<int:stream_id>/probe', methods=['POST'])
def probe_stream(stream_id: int):
    """Manually trigger a health probe for a stream."""
    result = checker.probe_stream(stream_id)
    return jsonify(result)


@health_bp.route('/probe', methods=['POST'])
def probe_url():
    """Probe a stream URL directly (without saving)."""
    data = request.get_json()
    url = data.get('url')
    protocol = data.get('protocol', 'rtsp')

    if not url:
        return jsonify({"error": "URL is required"}), 400

    result = checker.probe_url(url, protocol)
    return jsonify(result)


@health_bp.route('/quick-check', methods=['POST'])
def quick_check_all():
    """
    Fast health check using MediaMTX API.
    Can check 1000+ streams in seconds.
    """
    from app.services.health_checker import HealthChecker
    checker = HealthChecker()
    result = checker.quick_check_all_nodes()
    return jsonify(result)


@health_bp.route('/quick-check/<int:node_id>', methods=['POST'])
def quick_check_node(node_id: int):
    """Fast health check for a specific node."""
    from app.services.health_checker import HealthChecker
    checker = HealthChecker()
    result = checker.quick_check_node(node_id)
    return jsonify(result)
