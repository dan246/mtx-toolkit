"""
Recording Pipeline API endpoints.
Recording pipeline health monitoring.
"""

from flask import Blueprint, jsonify, request

from app.models import RecordingPipelineMetric, Stream

pipeline_bp = Blueprint("pipeline", __name__)


@pipeline_bp.route("/status", methods=["GET"])
def get_pipeline_status():
    """Get aggregated pipeline health status."""
    from app.services.recording_pipeline_monitor import RecordingPipelineMonitor

    monitor = RecordingPipelineMonitor()
    data = monitor.get_pipeline_dashboard_data()
    return jsonify(data)


@pipeline_bp.route("/streams/<int:stream_id>", methods=["GET"])
def get_stream_pipeline(stream_id: int):
    """Get per-stream pipeline detail."""
    stream = Stream.query.get_or_404(stream_id)
    return jsonify(
        {
            "stream_id": stream.id,
            "path": stream.path,
            "recording_enabled": stream.recording_enabled,
            "recording_pipeline_status": stream.recording_pipeline_status,
            "recording_last_segment_at": (
                stream.recording_last_segment_at.isoformat()
                if stream.recording_last_segment_at
                else None
            ),
            "recording_avg_write_latency_ms": stream.recording_avg_write_latency_ms,
        }
    )


@pipeline_bp.route("/streams/<int:stream_id>/metrics", methods=["GET"])
def get_stream_pipeline_metrics(stream_id: int):
    """Get time-series pipeline metrics for charts."""
    Stream.query.get_or_404(stream_id)
    limit = request.args.get("limit", 100, type=int)

    metrics = (
        RecordingPipelineMetric.query.filter_by(stream_id=stream_id)
        .order_by(RecordingPipelineMetric.created_at.desc())
        .limit(limit)
        .all()
    )

    return jsonify(
        {
            "stream_id": stream_id,
            "metrics": [
                {
                    "id": m.id,
                    "segment_write_duration_ms": m.segment_write_duration_ms,
                    "segment_size_bytes": m.segment_size_bytes,
                    "disk_io_latency_ms": m.disk_io_latency_ms,
                    "segment_gap_seconds": m.segment_gap_seconds,
                    "created_at": m.created_at.isoformat(),
                }
                for m in metrics
            ],
            "total": len(metrics),
        }
    )


@pipeline_bp.route("/gaps", methods=["GET"])
def get_all_gaps():
    """Get all detected segment gaps."""
    from app.services.retention_manager import RetentionManager

    manager = RetentionManager()
    streams = Stream.query.filter_by(recording_enabled=True).all()

    all_gaps = []
    for stream in streams:
        timeline = manager.get_segment_timeline(stream, hours=24)
        for gap in timeline.get("gaps", []):
            all_gaps.append(
                {
                    "stream_id": stream.id,
                    "stream_path": stream.path,
                    **gap,
                }
            )

    # Sort by duration descending
    all_gaps.sort(key=lambda g: g.get("duration_seconds", 0), reverse=True)

    return jsonify({"gaps": all_gaps, "total": len(all_gaps)})


@pipeline_bp.route("/streams/<int:stream_id>/check", methods=["POST"])
def trigger_pipeline_check(stream_id: int):
    """Manually trigger a pipeline health check."""
    from app.services.recording_pipeline_monitor import RecordingPipelineMonitor

    stream = Stream.query.get_or_404(stream_id)
    monitor = RecordingPipelineMonitor()
    result = monitor.check_stream_pipeline(stream)
    return jsonify(result)
