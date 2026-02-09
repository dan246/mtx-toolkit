"""
Dashboard API endpoints.
Aggregated data for UI visualization.
"""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app import db
from app.models import MediaMTXNode, Recording, Stream, StreamEvent

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/overview", methods=["GET"])
def overview():
    """Get dashboard overview statistics."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Node stats
    total_nodes = MediaMTXNode.query.filter_by(is_active=True).count()

    # Stream stats
    total_streams = Stream.query.count()
    healthy_streams = Stream.query.filter_by(status="healthy").count()
    degraded_streams = Stream.query.filter_by(status="degraded").count()
    unhealthy_streams = Stream.query.filter_by(status="unhealthy").count()

    # Event stats (last 24h)
    events_24h = StreamEvent.query.filter(
        StreamEvent.created_at >= now - timedelta(hours=24)
    ).count()

    critical_events = StreamEvent.query.filter(
        StreamEvent.created_at >= now - timedelta(hours=24),
        StreamEvent.severity == "critical",
        StreamEvent.resolved.is_(False),
    ).count()

    # Recording stats
    recordings_today = Recording.query.filter(
        Recording.created_at >= today_start
    ).count()

    total_recording_size = db.session.query(func.sum(Recording.file_size)).scalar() or 0

    return jsonify(
        {
            "nodes": {"total": total_nodes},
            "streams": {
                "total": total_streams,
                "healthy": healthy_streams,
                "degraded": degraded_streams,
                "unhealthy": unhealthy_streams,
                "health_rate": (
                    round(healthy_streams / total_streams * 100, 1)
                    if total_streams > 0
                    else 0
                ),
            },
            "events": {"last_24h": events_24h, "critical_unresolved": critical_events},
            "recordings": {
                "today": recordings_today,
                "total_size_gb": round(total_recording_size / (1024**3), 2),
            },
            "timestamp": now.isoformat(),
        }
    )


@dashboard_bp.route("/streams/status", methods=["GET"])
def streams_status():
    """Get streams grouped by status for dashboard."""
    streams = Stream.query.all()

    by_status = {"healthy": [], "degraded": [], "unhealthy": [], "unknown": []}

    for stream in streams:
        status = stream.status or "unknown"
        by_status.get(status, by_status["unknown"]).append(
            {
                "id": stream.id,
                "path": stream.path,
                "name": stream.name,
                "node_id": stream.node_id,
                "fps": stream.fps,
                "latency_ms": stream.latency_ms,
                "last_check": (
                    stream.last_check.isoformat() if stream.last_check else None
                ),
            }
        )

    return jsonify(by_status)


@dashboard_bp.route("/events/recent", methods=["GET"])
def recent_events():
    """Get recent events for dashboard feed."""
    limit = request.args.get("limit", 50, type=int)
    severity = request.args.get("severity")

    query = StreamEvent.query
    if severity:
        query = query.filter_by(severity=severity)

    events = query.order_by(StreamEvent.created_at.desc()).limit(limit).all()

    return jsonify(
        {
            "events": [
                {
                    "id": e.id,
                    "stream_id": e.stream_id,
                    "stream_path": e.stream.path if e.stream else None,
                    "event_type": e.event_type,
                    "severity": e.severity,
                    "message": e.message,
                    "resolved": e.resolved,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ]
        }
    )


@dashboard_bp.route("/metrics/timeline", methods=["GET"])
def metrics_timeline():
    """Get metrics timeline for charts."""
    stream_id = request.args.get("stream_id", type=int)
    hours = request.args.get("hours", 24, type=int)
    # metric parameter reserved for future filtering
    _ = request.args.get("metric", "all")

    # This would typically query a time-series database
    # For now, return sample data structure
    now = datetime.utcnow()

    return jsonify(
        {
            "stream_id": stream_id,
            "period_hours": hours,
            "metrics": {"fps": [], "bitrate": [], "latency": [], "health_score": []},
            "timestamp": now.isoformat(),
        }
    )


@dashboard_bp.route("/alerts/active", methods=["GET"])
def active_alerts():
    """Get currently active alerts."""
    alerts = (
        StreamEvent.query.filter(
            StreamEvent.resolved.is_(False),
            StreamEvent.severity.in_(["warning", "error", "critical"]),
        )
        .order_by(StreamEvent.created_at.desc())
        .all()
    )

    return jsonify(
        {
            "alerts": [
                {
                    "id": a.id,
                    "stream_id": a.stream_id,
                    "stream_path": a.stream.path if a.stream else None,
                    "event_type": a.event_type,
                    "severity": a.severity,
                    "message": a.message,
                    "created_at": a.created_at.isoformat(),
                    "duration_minutes": int(
                        (datetime.utcnow() - a.created_at).total_seconds() / 60
                    ),
                }
                for a in alerts
            ],
            "total": len(alerts),
            "by_severity": {
                "critical": sum(1 for a in alerts if a.severity == "critical"),
                "error": sum(1 for a in alerts if a.severity == "error"),
                "warning": sum(1 for a in alerts if a.severity == "warning"),
            },
        }
    )


@dashboard_bp.route("/nodes/status", methods=["GET"])
def nodes_status():
    """Get node status for dashboard."""
    nodes = MediaMTXNode.query.filter_by(is_active=True).all()

    return jsonify(
        {
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "environment": n.environment,
                    "last_seen": n.last_seen.isoformat() if n.last_seen else None,
                    "is_online": (
                        (datetime.utcnow() - n.last_seen).seconds < 60
                        if n.last_seen
                        else False
                    ),
                    "stream_count": n.streams.count(),
                    "healthy_streams": n.streams.filter_by(status="healthy").count(),
                }
                for n in nodes
            ]
        }
    )


@dashboard_bp.route("/liveness", methods=["GET"])
def liveness_summary():
    """Get liveness summary counts by classification."""
    from app.services.liveness_probe import LivenessProbe

    probe = LivenessProbe()
    summary = probe.get_liveness_summary()
    return jsonify(summary)


@dashboard_bp.route("/pipeline", methods=["GET"])
def pipeline_summary():
    """Get recording pipeline health summary."""
    from app.services.recording_pipeline_monitor import RecordingPipelineMonitor

    monitor = RecordingPipelineMonitor()
    data = monitor.get_pipeline_dashboard_data()
    return jsonify(data)


@dashboard_bp.route("/playback-health", methods=["GET"])
def playback_health_summary():
    """Get aggregated client playback health."""
    from app.models import ClientPlaybackReport

    recent = ClientPlaybackReport.query.filter(
        ClientPlaybackReport.created_at >= datetime.utcnow() - timedelta(hours=1)
    ).all()

    total_stalls = sum(r.stall_count or 0 for r in recent)
    total_reports = len(recent)
    total_dropped = sum(r.frames_dropped or 0 for r in recent)
    total_decoded = sum(r.frames_decoded or 0 for r in recent)

    recovery_actions = {}
    for r in recent:
        if r.recovery_action:
            recovery_actions[r.recovery_action] = (
                recovery_actions.get(r.recovery_action, 0) + 1
            )

    return jsonify(
        {
            "total_reports": total_reports,
            "total_stalls": total_stalls,
            "total_frames_dropped": total_dropped,
            "total_frames_decoded": total_decoded,
            "drop_rate": (
                round(total_dropped / total_decoded * 100, 2)
                if total_decoded > 0
                else 0
            ),
            "recovery_actions": recovery_actions,
        }
    )


@dashboard_bp.route("/events/cleanup", methods=["POST"])
def cleanup_events():
    """
    Clean up old events.

    Request body:
        days (int): Delete events older than this many days (default: 7)
        resolved_only (bool): Only delete resolved events (default: False)
    """
    data = request.get_json() or {}
    days = data.get("days", 7)
    resolved_only = data.get("resolved_only", False)

    cutoff = datetime.utcnow() - timedelta(days=days)

    query = StreamEvent.query.filter(StreamEvent.created_at < cutoff)
    if resolved_only:
        query = query.filter(StreamEvent.resolved.is_(True))

    count = query.count()
    query.delete(synchronize_session=False)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "deleted_count": count,
            "cutoff_date": cutoff.isoformat(),
            "resolved_only": resolved_only,
        }
    )


@dashboard_bp.route("/events/resolve-all", methods=["POST"])
def resolve_all_events():
    """Mark all unresolved events as resolved."""
    count = StreamEvent.query.filter(StreamEvent.resolved.is_(False)).update(
        {"resolved": True, "resolved_at": datetime.utcnow()}
    )
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "resolved_count": count,
        }
    )


@dashboard_bp.route("/events/clear-resolved", methods=["POST"])
def clear_resolved_events():
    """Delete all resolved events."""
    count = StreamEvent.query.filter(StreamEvent.resolved.is_(True)).delete(
        synchronize_session=False
    )
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "deleted_count": count,
        }
    )
