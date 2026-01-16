"""
Tests for database models.
"""
import pytest
from datetime import datetime, timedelta

from app import db
from app.models import (
    MediaMTXNode, Stream, StreamEvent, Recording, ConfigSnapshot,
    StreamStatus, EventType
)


class TestStreamStatus:
    """Tests for StreamStatus enum."""

    def test_status_values(self):
        """Test that all expected status values exist."""
        assert StreamStatus.HEALTHY.value == "healthy"
        assert StreamStatus.DEGRADED.value == "degraded"
        assert StreamStatus.UNHEALTHY.value == "unhealthy"
        assert StreamStatus.UNKNOWN.value == "unknown"

    def test_status_is_string_enum(self):
        """Test that status enum is a string enum."""
        assert isinstance(StreamStatus.HEALTHY, str)
        assert StreamStatus.HEALTHY == "healthy"


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values(self):
        """Test that all expected event types exist."""
        expected_types = [
            'black_screen', 'frozen', 'audio_silent', 'fps_drop',
            'keyframe_issue', 'high_latency', 'disconnected', 'reconnected',
            'remediation_started', 'remediation_success', 'remediation_failed'
        ]
        for event_type in expected_types:
            assert hasattr(EventType, event_type.upper())


class TestMediaMTXNode:
    """Tests for MediaMTXNode model."""

    def test_create_node(self, app_context, db_session):
        """Test creating a MediaMTX node."""
        node = MediaMTXNode(
            name='production-node-1',
            api_url='http://192.168.1.10:9997',
            rtsp_url='rtsp://192.168.1.10:8554',
            environment='production',
            is_active=True
        )
        db_session.add(node)
        db_session.commit()

        assert node.id is not None
        assert node.name == 'production-node-1'
        assert node.environment == 'production'
        assert node.is_active is True
        assert node.created_at is not None

    def test_node_unique_name(self, app_context, db_session):
        """Test that node names must be unique."""
        node1 = MediaMTXNode(name='unique-node', api_url='http://localhost:9997')
        db_session.add(node1)
        db_session.commit()

        node2 = MediaMTXNode(name='unique-node', api_url='http://localhost:9998')
        db_session.add(node2)

        with pytest.raises(Exception):
            db_session.commit()

    def test_node_streams_relationship(self, app_context, db_session, sample_node):
        """Test node to streams relationship."""
        stream = Stream(
            node_id=sample_node.id,
            path='test/stream1',
            name='Test Stream'
        )
        db_session.add(stream)
        db_session.commit()

        assert sample_node.streams.count() == 1
        assert sample_node.streams.first().path == 'test/stream1'

    def test_node_default_values(self, app_context, db_session):
        """Test node default values."""
        node = MediaMTXNode(name='default-test', api_url='http://localhost:9997')
        db_session.add(node)
        db_session.commit()

        assert node.environment == 'production'
        assert node.is_active is True
        assert node.last_seen is not None

    def test_node_updated_at(self, app_context, db_session):
        """Test that updated_at is automatically set on update."""
        node = MediaMTXNode(name='update-test', api_url='http://localhost:9997')
        db_session.add(node)
        db_session.commit()

        original_updated = node.updated_at

        node.api_url = 'http://localhost:9998'
        db_session.commit()

        # updated_at should be >= original
        assert node.updated_at >= original_updated


class TestStream:
    """Tests for Stream model."""

    def test_create_stream(self, app_context, db_session, sample_node):
        """Test creating a stream."""
        stream = Stream(
            node_id=sample_node.id,
            path='camera/entrance',
            name='Entrance Camera',
            source_url='rtsp://192.168.1.100:554/main',
            protocol='rtsp',
            status=StreamStatus.HEALTHY.value
        )
        db_session.add(stream)
        db_session.commit()

        assert stream.id is not None
        assert stream.path == 'camera/entrance'
        assert stream.status == 'healthy'

    def test_stream_unique_path_per_node(self, app_context, db_session, sample_node):
        """Test that path must be unique per node."""
        stream1 = Stream(node_id=sample_node.id, path='unique/path')
        db_session.add(stream1)
        db_session.commit()

        stream2 = Stream(node_id=sample_node.id, path='unique/path')
        db_session.add(stream2)

        with pytest.raises(Exception):
            db_session.commit()

    def test_stream_default_status(self, app_context, db_session, sample_node):
        """Test stream default status is unknown."""
        stream = Stream(node_id=sample_node.id, path='test/default')
        db_session.add(stream)
        db_session.commit()

        assert stream.status == StreamStatus.UNKNOWN.value

    def test_stream_auto_remediate_default(self, app_context, db_session, sample_node):
        """Test stream auto_remediate defaults to True."""
        stream = Stream(node_id=sample_node.id, path='test/auto')
        db_session.add(stream)
        db_session.commit()

        assert stream.auto_remediate is True

    def test_stream_node_relationship(self, app_context, db_session, sample_stream):
        """Test stream to node relationship."""
        assert sample_stream.node is not None
        assert sample_stream.node.name == 'test-node'

    def test_stream_events_relationship(self, app_context, db_session, sample_stream):
        """Test stream to events relationship."""
        event = StreamEvent(
            stream_id=sample_stream.id,
            event_type=EventType.DISCONNECTED.value,
            message='Test event'
        )
        db_session.add(event)
        db_session.commit()

        assert sample_stream.events.count() == 1

    def test_stream_recordings_relationship(self, app_context, db_session, sample_stream):
        """Test stream to recordings relationship."""
        recording = Recording(
            stream_id=sample_stream.id,
            file_path='/recordings/test.mp4',
            start_time=datetime.utcnow()
        )
        db_session.add(recording)
        db_session.commit()

        assert sample_stream.recordings.count() == 1

    def test_stream_cascade_delete_events(self, app_context, db_session, sample_node):
        """Test that deleting a stream cascades to events."""
        stream = Stream(node_id=sample_node.id, path='cascade/test')
        db_session.add(stream)
        db_session.commit()

        event = StreamEvent(stream_id=stream.id, event_type='disconnected')
        db_session.add(event)
        db_session.commit()

        db_session.delete(stream)
        db_session.commit()

        assert StreamEvent.query.filter_by(stream_id=stream.id).count() == 0

    def test_stream_metrics(self, app_context, db_session, sample_node):
        """Test stream metric fields."""
        stream = Stream(
            node_id=sample_node.id,
            path='test/metrics',
            fps=30.0,
            bitrate=4000000,
            latency_ms=100,
            keyframe_interval=2.0
        )
        db_session.add(stream)
        db_session.commit()

        assert stream.fps == 30.0
        assert stream.bitrate == 4000000
        assert stream.latency_ms == 100
        assert stream.keyframe_interval == 2.0


class TestStreamEvent:
    """Tests for StreamEvent model."""

    def test_create_event(self, app_context, db_session, sample_stream):
        """Test creating a stream event."""
        event = StreamEvent(
            stream_id=sample_stream.id,
            event_type=EventType.BLACK_SCREEN.value,
            severity='warning',
            message='Black screen detected for 5 seconds'
        )
        db_session.add(event)
        db_session.commit()

        assert event.id is not None
        assert event.event_type == 'black_screen'
        assert event.severity == 'warning'

    def test_event_default_severity(self, app_context, db_session, sample_stream):
        """Test event default severity is warning."""
        event = StreamEvent(
            stream_id=sample_stream.id,
            event_type=EventType.FPS_DROP.value
        )
        db_session.add(event)
        db_session.commit()

        assert event.severity == 'warning'

    def test_event_resolved(self, app_context, db_session, sample_stream):
        """Test marking event as resolved."""
        event = StreamEvent(
            stream_id=sample_stream.id,
            event_type=EventType.DISCONNECTED.value
        )
        db_session.add(event)
        db_session.commit()

        assert event.resolved is False

        event.resolved = True
        event.resolved_at = datetime.utcnow()
        db_session.commit()

        assert event.resolved is True
        assert event.resolved_at is not None

    def test_event_stream_relationship(self, app_context, db_session, sample_event):
        """Test event to stream relationship."""
        assert sample_event.stream is not None
        assert sample_event.stream.path == 'test/stream1'


class TestRecording:
    """Tests for Recording model."""

    def test_create_recording(self, app_context, db_session, sample_stream):
        """Test creating a recording."""
        start_time = datetime.utcnow()
        recording = Recording(
            stream_id=sample_stream.id,
            file_path='/recordings/test_stream/20240101_120000.mp4',
            file_size=1024 * 1024 * 500,  # 500MB
            duration_seconds=3600,
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            segment_type='continuous'
        )
        db_session.add(recording)
        db_session.commit()

        assert recording.id is not None
        assert recording.file_size == 1024 * 1024 * 500
        assert recording.duration_seconds == 3600
        assert recording.segment_type == 'continuous'

    def test_recording_default_segment_type(self, app_context, db_session, sample_stream):
        """Test recording default segment type is continuous."""
        recording = Recording(
            stream_id=sample_stream.id,
            file_path='/recordings/test.mp4',
            start_time=datetime.utcnow()
        )
        db_session.add(recording)
        db_session.commit()

        assert recording.segment_type == 'continuous'

    def test_recording_event_triggered(self, app_context, db_session, sample_stream, sample_event):
        """Test event-triggered recording."""
        recording = Recording(
            stream_id=sample_stream.id,
            file_path='/recordings/event_123.mp4',
            start_time=datetime.utcnow(),
            segment_type='event',
            triggered_by_event_id=sample_event.id
        )
        db_session.add(recording)
        db_session.commit()

        assert recording.segment_type == 'event'
        assert recording.triggered_by_event_id == sample_event.id

    def test_recording_archival(self, app_context, db_session, sample_stream):
        """Test recording archival fields."""
        recording = Recording(
            stream_id=sample_stream.id,
            file_path='/recordings/test.mp4',
            start_time=datetime.utcnow(),
            is_archived=False
        )
        db_session.add(recording)
        db_session.commit()

        assert recording.is_archived is False

        recording.is_archived = True
        recording.archive_path = '/mnt/nas/recordings/test.mp4'
        db_session.commit()

        assert recording.is_archived is True
        assert recording.archive_path == '/mnt/nas/recordings/test.mp4'

    def test_recording_retention(self, app_context, db_session, sample_stream):
        """Test recording retention fields."""
        recording = Recording(
            stream_id=sample_stream.id,
            file_path='/recordings/test.mp4',
            start_time=datetime.utcnow(),
            retention_days=30,
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        db_session.add(recording)
        db_session.commit()

        assert recording.retention_days == 30
        assert recording.expires_at > datetime.utcnow()


class TestConfigSnapshot:
    """Tests for ConfigSnapshot model."""

    def test_create_snapshot(self, app_context, db_session, sample_node):
        """Test creating a config snapshot."""
        config_yaml = """
paths:
  test/stream:
    source: rtsp://192.168.1.100:554/stream
"""
        snapshot = ConfigSnapshot(
            node_id=sample_node.id,
            config_hash='abc123def456',
            config_yaml=config_yaml,
            environment='production'
        )
        db_session.add(snapshot)
        db_session.commit()

        assert snapshot.id is not None
        assert snapshot.config_hash == 'abc123def456'
        assert 'test/stream' in snapshot.config_yaml

    def test_snapshot_applied(self, app_context, db_session, sample_node):
        """Test snapshot applied status."""
        snapshot = ConfigSnapshot(
            node_id=sample_node.id,
            config_hash='hash123',
            config_yaml='paths: {}',
            applied=False
        )
        db_session.add(snapshot)
        db_session.commit()

        assert snapshot.applied is False

        snapshot.applied = True
        snapshot.applied_at = datetime.utcnow()
        snapshot.applied_by = 'admin'
        db_session.commit()

        assert snapshot.applied is True
        assert snapshot.applied_by == 'admin'

    def test_snapshot_rollback_reference(self, app_context, db_session, sample_node):
        """Test snapshot rollback reference."""
        original = ConfigSnapshot(
            node_id=sample_node.id,
            config_hash='original',
            config_yaml='paths: {}'
        )
        db_session.add(original)
        db_session.commit()

        rollback = ConfigSnapshot(
            node_id=sample_node.id,
            config_hash='rollback',
            config_yaml='paths: {}',
            rollback_of=original.id,
            notes='Rollback due to error'
        )
        db_session.add(rollback)
        db_session.commit()

        assert rollback.rollback_of == original.id
        assert rollback.notes == 'Rollback due to error'

    def test_snapshot_without_node(self, app_context, db_session):
        """Test creating a snapshot without a node (global config)."""
        snapshot = ConfigSnapshot(
            node_id=None,
            config_hash='global_hash',
            config_yaml='logLevel: debug',
            environment='development'
        )
        db_session.add(snapshot)
        db_session.commit()

        assert snapshot.id is not None
        assert snapshot.node_id is None
