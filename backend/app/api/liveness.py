"""
Liveness API endpoints.
Frame-level liveness probe monitoring.
"""

from flask import Blueprint, jsonify, request

from app.models import LivenessProbeResult, Stream

liveness_bp = Blueprint("liveness", __name__)


@liveness_bp.route("/streams", methods=["GET"])
def list_liveness_streams():
    """List all streams with liveness classification filter."""
    classification = request.args.get("classification")

    query = Stream.query
    if classification:
        query = query.filter_by(liveness_classification=classification)

    streams = query.all()
    return jsonify(
        {
            "streams": [
                {
                    "id": s.id,
                    "path": s.path,
                    "name": s.name,
                    "status": s.status,
                    "liveness_classification": s.liveness_classification,
                    "liveness_last_check": (
                        s.liveness_last_check.isoformat()
                        if s.liveness_last_check
                        else None
                    ),
                    "consecutive_freeze_checks": s.consecutive_freeze_checks,
                    "freeze_started_at": (
                        s.freeze_started_at.isoformat() if s.freeze_started_at else None
                    ),
                }
                for s in streams
            ],
            "total": len(streams),
        }
    )


@liveness_bp.route("/streams/<int:stream_id>", methods=["GET"])
def get_liveness_stream(stream_id: int):
    """Get liveness detail with recent probes."""
    stream = Stream.query.get_or_404(stream_id)

    recent_probes = (
        LivenessProbeResult.query.filter_by(stream_id=stream_id)
        .order_by(LivenessProbeResult.created_at.desc())
        .limit(10)
        .all()
    )

    return jsonify(
        {
            "id": stream.id,
            "path": stream.path,
            "name": stream.name,
            "status": stream.status,
            "liveness_classification": stream.liveness_classification,
            "liveness_last_check": (
                stream.liveness_last_check.isoformat()
                if stream.liveness_last_check
                else None
            ),
            "last_pts": stream.last_pts,
            "last_frame_hash": stream.last_frame_hash,
            "consecutive_freeze_checks": stream.consecutive_freeze_checks,
            "freeze_started_at": (
                stream.freeze_started_at.isoformat()
                if stream.freeze_started_at
                else None
            ),
            "recent_probes": [
                {
                    "id": p.id,
                    "classification": p.classification,
                    "pts_value": p.pts_value,
                    "pts_delta": p.pts_delta,
                    "frame_hash_changed": p.frame_hash_changed,
                    "brightness": p.brightness,
                    "audio_rms": p.audio_rms,
                    "keyframe_present": p.keyframe_present,
                    "probe_duration_ms": p.probe_duration_ms,
                    "created_at": p.created_at.isoformat(),
                }
                for p in recent_probes
            ],
        }
    )


@liveness_bp.route("/streams/<int:stream_id>/probe", methods=["POST"])
def trigger_probe(stream_id: int):
    """Manually trigger a liveness probe."""
    from app.services.liveness_probe import LivenessProbe

    stream = Stream.query.get_or_404(stream_id)
    probe = LivenessProbe()
    result = probe.probe_stream(stream)
    return jsonify(result)


@liveness_bp.route("/history/<int:stream_id>", methods=["GET"])
def get_probe_history(stream_id: int):
    """Get probe history for trend charts."""
    limit = request.args.get("limit", 100, type=int)

    probes = (
        LivenessProbeResult.query.filter_by(stream_id=stream_id)
        .order_by(LivenessProbeResult.created_at.desc())
        .limit(limit)
        .all()
    )

    return jsonify(
        {
            "stream_id": stream_id,
            "probes": [
                {
                    "id": p.id,
                    "classification": p.classification,
                    "pts_value": p.pts_value,
                    "pts_delta": p.pts_delta,
                    "frame_hash_changed": p.frame_hash_changed,
                    "brightness": p.brightness,
                    "audio_rms": p.audio_rms,
                    "keyframe_present": p.keyframe_present,
                    "probe_duration_ms": p.probe_duration_ms,
                    "created_at": p.created_at.isoformat(),
                }
                for p in probes
            ],
            "total": len(probes),
        }
    )
