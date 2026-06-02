"""
Database models for MTX Toolkit.
"""

from datetime import datetime
from enum import Enum

from werkzeug.security import check_password_hash, generate_password_hash

from app import db


class StreamStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class LivenessClassification(str, Enum):
    LIVE = "live"
    FROZEN = "frozen"
    BLACK_SCREEN = "black_screen"
    STALE = "stale"
    SILENT = "silent"
    UNKNOWN = "unknown"


class SourceProtocol(str, Enum):
    RTSP = "rtsp"
    RTMP = "rtmp"
    WHEP = "whep"
    WHIP = "whip"
    HLS = "hls"
    SRT = "srt"
    UNKNOWN = "unknown"


class FallbackType(str, Enum):
    COLOR_BARS = "color_bars"
    CUSTOM_IMAGE = "custom_image"
    LAST_FRAME = "last_frame"
    NONE = "none"


class RecordingPipelineStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
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
    # Phase 1: Liveness
    FROZEN_DETECTED = "frozen_detected"
    BLACK_SCREEN_DETECTED = "black_screen_detected"
    STALE_PTS_DETECTED = "stale_pts_detected"
    AUDIO_SILENT_DETECTED = "audio_silent_detected"
    LIVENESS_RECOVERED = "liveness_recovered"
    SOFT_RESET_STARTED = "soft_reset_started"
    SOFT_RESET_SUCCESS = "soft_reset_success"
    SOFT_RESET_FAILED = "soft_reset_failed"
    # Phase 2: Protocol Revival
    PROTOCOL_REVIVAL_STARTED = "protocol_revival_started"
    PROTOCOL_REVIVAL_SUCCESS = "protocol_revival_success"
    PROTOCOL_REVIVAL_FAILED = "protocol_revival_failed"
    # Phase 3: Fallback
    FALLBACK_ACTIVATED = "fallback_activated"
    FALLBACK_DEACTIVATED = "fallback_deactivated"
    # Phase 4: Client Playback
    CLIENT_PLAYBACK_STALL = "client_playback_stall"
    CLIENT_PLAYBACK_ERROR = "client_playback_error"
    # Phase 5: Recording Pipeline
    RECORDING_SEGMENT_GAP = "recording_segment_gap"
    RECORDING_WRITE_SLOW = "recording_write_slow"
    RECORDING_PIPELINE_DEGRADED = "recording_pipeline_degraded"


class User(db.Model):
    """Application user for authentication and authorization."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="admin")  # admin/operator/viewer
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "is_active": self.is_active,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


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

    # Phase 1: Liveness
    liveness_classification = db.Column(db.String(50), default="unknown")
    liveness_last_check = db.Column(db.DateTime)
    last_pts = db.Column(db.BigInteger)
    last_frame_hash = db.Column(db.String(64))
    freeze_started_at = db.Column(db.DateTime)
    consecutive_freeze_checks = db.Column(db.Integer, default=0)

    # Phase 2: Source Protocol
    source_protocol = db.Column(db.String(50), default="unknown")

    # Phase 3: Fallback
    fallback_type = db.Column(db.String(50), default="none")
    fallback_image_path = db.Column(db.String(1024))
    fallback_active = db.Column(db.Boolean, default=False)
    fallback_activated_at = db.Column(db.DateTime)

    # Phase 5: Recording Pipeline
    recording_pipeline_status = db.Column(db.String(50), default="unknown")
    recording_last_segment_at = db.Column(db.DateTime)
    recording_avg_write_latency_ms = db.Column(db.Float)

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


class LivenessProbeResult(db.Model):
    """Phase 1: Liveness probe result for trend analysis."""

    __tablename__ = "liveness_probe_results"

    id = db.Column(db.Integer, primary_key=True)
    stream_id = db.Column(
        db.Integer, db.ForeignKey("streams.id", ondelete="CASCADE"), nullable=False
    )
    classification = db.Column(db.String(50), nullable=False)
    pts_value = db.Column(db.BigInteger)
    pts_delta = db.Column(db.BigInteger)
    frame_hash = db.Column(db.String(64))
    frame_hash_changed = db.Column(db.Boolean)
    brightness = db.Column(db.Float)  # 0-255
    audio_rms = db.Column(db.Float)  # dB
    keyframe_present = db.Column(db.Boolean)
    probe_duration_ms = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    stream = db.relationship(
        "Stream",
        backref=db.backref(
            "liveness_probes", cascade="all, delete-orphan", passive_deletes=True
        ),
    )


class ClientPlaybackReport(db.Model):
    """Phase 4: Client-side playback health report."""

    __tablename__ = "client_playback_reports"

    id = db.Column(db.Integer, primary_key=True)
    stream_id = db.Column(
        db.Integer, db.ForeignKey("streams.id", ondelete="CASCADE"), nullable=False
    )
    client_id = db.Column(db.String(255))
    client_ip = db.Column(db.String(45))
    stall_count = db.Column(db.Integer, default=0)
    stall_duration_ms = db.Column(db.Integer, default=0)
    buffer_underrun_count = db.Column(db.Integer, default=0)
    frames_decoded = db.Column(db.Integer)
    frames_dropped = db.Column(db.Integer)
    current_level = db.Column(db.Integer)
    recovery_action = db.Column(db.String(50))  # seek_nudge/level_switch/full_reload
    error_type = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    stream = db.relationship(
        "Stream",
        backref=db.backref(
            "playback_reports", cascade="all, delete-orphan", passive_deletes=True
        ),
    )


class RecordingPipelineMetric(db.Model):
    """Phase 5: Recording pipeline health metrics."""

    __tablename__ = "recording_pipeline_metrics"

    id = db.Column(db.Integer, primary_key=True)
    stream_id = db.Column(
        db.Integer, db.ForeignKey("streams.id", ondelete="CASCADE"), nullable=False
    )
    segment_write_duration_ms = db.Column(db.Float)
    segment_size_bytes = db.Column(db.BigInteger)
    disk_io_latency_ms = db.Column(db.Float)
    segment_gap_seconds = db.Column(db.Float)
    expected_segment_time = db.Column(db.DateTime)
    actual_segment_time = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    stream = db.relationship(
        "Stream",
        backref=db.backref(
            "pipeline_metrics", cascade="all, delete-orphan", passive_deletes=True
        ),
    )
