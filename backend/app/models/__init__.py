"""
Database models for MTX Toolkit.
"""

from datetime import datetime
from enum import Enum

from app import db


class StreamStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class EventType(str, Enum):
    BLACK_SCREEN = "black_screen"
    FROZEN = "frozen"
    AUDIO_SILENT = "audio_silent"
    FPS_DROP = "fps_drop"
    KEYFRAME_ISSUE = "keyframe_issue"
    HIGH_LATENCY = "high_latency"
    DISCONNECTED = "disconnected"
    RECONNECTED = "reconnected"
    REMEDIATION_STARTED = "remediation_started"
    REMEDIATION_SUCCESS = "remediation_success"
    REMEDIATION_FAILED = "remediation_failed"


class MediaMTXNode(db.Model):
    """Fleet management - MediaMTX node."""

    __tablename__ = "mediamtx_nodes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    api_url = db.Column(db.String(512), nullable=False)
    rtsp_url = db.Column(db.String(512))  # RTSP base URL for health checks
    environment = db.Column(db.String(50), default="production")  # dev/stage/prod
    is_active = db.Column(db.Boolean, default=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    metadata_json = db.Column(db.Text)  # JSON for extra node info

    streams = db.relationship("Stream", backref="node", lazy="dynamic")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Stream(db.Model):
    """Stream/Path configuration and status."""

    __tablename__ = "streams"

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.Integer, db.ForeignKey("mediamtx_nodes.id"), nullable=False)
    path = db.Column(db.String(512), nullable=False)
    name = db.Column(db.String(255))
    source_url = db.Column(db.String(1024))
    protocol = db.Column(db.String(50))  # rtsp/rtmp/webrtc

    # Health status
    status = db.Column(db.String(50), default=StreamStatus.UNKNOWN.value)
    last_check = db.Column(db.DateTime)

    # Metrics
    fps = db.Column(db.Float)
    bitrate = db.Column(db.Integer)
    latency_ms = db.Column(db.Integer)
    keyframe_interval = db.Column(db.Float)

    # Auto-remediation
    auto_remediate = db.Column(db.Boolean, default=True)
    remediation_count = db.Column(db.Integer, default=0)
    last_remediation = db.Column(db.DateTime)

    # Recording
    recording_enabled = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    events = db.relationship(
        "StreamEvent", backref="stream", lazy="dynamic", cascade="all, delete-orphan"
    )
    recordings = db.relationship(
        "Recording", backref="stream", lazy="dynamic", cascade="all, delete-orphan"
    )

    __table_args__ = (db.UniqueConstraint("node_id", "path"),)


class StreamEvent(db.Model):
    """Stream health events and alerts."""

    __tablename__ = "stream_events"

    id = db.Column(db.Integer, primary_key=True)
    stream_id = db.Column(db.Integer, db.ForeignKey("streams.id"), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(
        db.String(20), default="warning"
    )  # info/warning/error/critical
    message = db.Column(db.Text)
    details_json = db.Column(db.Text)  # JSON for extra event details
    resolved = db.Column(db.Boolean, default=False)
    resolved_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Recording(db.Model):
    """Recording segments and retention management."""

    __tablename__ = "recordings"

    id = db.Column(db.Integer, primary_key=True)
    stream_id = db.Column(db.Integer, db.ForeignKey("streams.id"), nullable=False)
    file_path = db.Column(db.String(1024), nullable=False)
    file_size = db.Column(db.BigInteger)
    duration_seconds = db.Column(db.Integer)

    # Segment info
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime)
    segment_type = db.Column(
        db.String(50), default="continuous"
    )  # continuous/event/manual

    # Event-triggered recording
    triggered_by_event_id = db.Column(db.Integer, db.ForeignKey("stream_events.id"))

    # Retention
    retention_days = db.Column(db.Integer)
    expires_at = db.Column(db.DateTime)
    is_archived = db.Column(db.Boolean, default=False)
    archive_path = db.Column(db.String(1024))  # NAS path

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ConfigSnapshot(db.Model):
    """Config-as-Code versioning and rollback."""

    __tablename__ = "config_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.Integer, db.ForeignKey("mediamtx_nodes.id"))
    config_hash = db.Column(db.String(64), nullable=False)
    config_yaml = db.Column(db.Text, nullable=False)
    environment = db.Column(db.String(50))
    applied = db.Column(db.Boolean, default=False)
    applied_at = db.Column(db.DateTime)
    applied_by = db.Column(db.String(255))
    rollback_of = db.Column(db.Integer, db.ForeignKey("config_snapshots.id"))
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class IPBlacklist(db.Model):
    """IP blacklist for blocking viewers."""

    __tablename__ = "ip_blacklist"

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)  # IPv4 or IPv6
    reason = db.Column(db.String(255))
    blocked_by = db.Column(db.String(255))  # Who blocked this IP

    # Blocking scope
    path_pattern = db.Column(
        db.String(512)
    )  # Specific path or pattern, null = all paths
    node_id = db.Column(
        db.Integer, db.ForeignKey("mediamtx_nodes.id")
    )  # Specific node, null = all nodes

    # Temporary or permanent
    is_permanent = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime)  # For temporary blocks

    # Status
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationship
    node = db.relationship("MediaMTXNode", backref="blacklisted_ips")
