"""
Fallback API endpoints.
Reader-preserving fallback stream management.
"""

from flask import Blueprint, jsonify, request

from app.models import Stream
from app.services.fallback_manager import FallbackManager

fallback_bp = Blueprint("fallback", __name__)


@fallback_bp.route("/streams/<int:stream_id>", methods=["GET"])
def get_fallback_config(stream_id: int):
    """Get fallback config and status for a stream."""
    manager = FallbackManager()
    status = manager.get_fallback_status(stream_id)
    if not status:
        return jsonify({"error": "Stream not found"}), 404
    return jsonify(status)


@fallback_bp.route("/streams/<int:stream_id>", methods=["PUT"])
def configure_fallback(stream_id: int):
    """Configure fallback type for a stream."""
    data = request.get_json()
    fallback_type = data.get("fallback_type")
    image_path = data.get("image_path")

    if not fallback_type:
        return jsonify({"error": "fallback_type is required"}), 400

    manager = FallbackManager()
    result = manager.configure_fallback(stream_id, fallback_type, image_path)

    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)


@fallback_bp.route("/streams/<int:stream_id>/activate", methods=["POST"])
def activate_fallback(stream_id: int):
    """Manually activate fallback for a stream."""
    stream = Stream.query.get_or_404(stream_id)
    manager = FallbackManager()
    result = manager.activate_fallback(stream)

    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)


@fallback_bp.route("/streams/<int:stream_id>/deactivate", methods=["POST"])
def deactivate_fallback(stream_id: int):
    """Manually deactivate fallback for a stream."""
    stream = Stream.query.get_or_404(stream_id)
    manager = FallbackManager()
    result = manager.deactivate_fallback(stream)

    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)


@fallback_bp.route("/active", methods=["GET"])
def list_active_fallbacks():
    """List all streams with active fallbacks."""
    streams = Stream.query.filter_by(fallback_active=True).all()
    return jsonify(
        {
            "streams": [
                {
                    "id": s.id,
                    "path": s.path,
                    "name": s.name,
                    "fallback_type": s.fallback_type,
                    "fallback_activated_at": (
                        s.fallback_activated_at.isoformat()
                        if s.fallback_activated_at
                        else None
                    ),
                }
                for s in streams
            ],
            "total": len(streams),
        }
    )
