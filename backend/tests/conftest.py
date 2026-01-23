"""
Pytest configuration and fixtures for MTX Toolkit backend tests.
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# Set testing environment before importing app
os.environ["FLASK_ENV"] = "testing"

from app import create_app, db
from app.models import (
    ConfigSnapshot,
    EventType,
    IPBlacklist,
    MediaMTXNode,
    Recording,
    Stream,
    StreamEvent,
    StreamStatus,
)


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    app = create_app("testing")
    app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "MEDIAMTX_API_URL": "http://localhost:9998",
            "MEDIAMTX_RTSP_URL": "rtsp://localhost:8555",
            "REDIS_URL": "redis://localhost:6379/0",
            "RECORDING_BASE_PATH": "/tmp/test_recordings",
            "HEALTH_CHECK_TIMEOUT": 5,
            "RETRY_MAX_ATTEMPTS": 3,
            "RETRY_BASE_DELAY": 0.1,
            "RETRY_MAX_DELAY": 1.0,
        }
    )
    return app


@pytest.fixture(scope="function")
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(scope="function")
def app_context(app):
    """Create application context."""
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def db_session(app_context):
    """Create database session for testing."""
    yield db.session
    db.session.rollback()


@pytest.fixture
def sample_node(db_session):
    """Create a sample MediaMTX node."""
    node = MediaMTXNode(
        name="test-node",
        api_url="http://localhost:9998",
        rtsp_url="rtsp://localhost:8555",
        environment="testing",
        is_active=True,
    )
    db_session.add(node)
    db_session.commit()
    return node


@pytest.fixture
def sample_stream(db_session, sample_node):
    """Create a sample stream."""
    stream = Stream(
        node_id=sample_node.id,
        path="test/stream1",
        name="Test Stream 1",
        source_url="rtsp://192.168.1.100:554/stream1",
        protocol="rtsp",
        status=StreamStatus.HEALTHY.value,
        auto_remediate=True,
    )
    db_session.add(stream)
    db_session.commit()
    return stream


@pytest.fixture
def sample_unhealthy_stream(db_session, sample_node):
    """Create a sample unhealthy stream."""
    stream = Stream(
        node_id=sample_node.id,
        path="test/unhealthy",
        name="Unhealthy Stream",
        source_url="rtsp://192.168.1.100:554/bad",
        protocol="rtsp",
        status=StreamStatus.UNHEALTHY.value,
        auto_remediate=True,
    )
    db_session.add(stream)
    db_session.commit()
    return stream


@pytest.fixture
def sample_event(db_session, sample_stream):
    """Create a sample stream event."""
    event = StreamEvent(
        stream_id=sample_stream.id,
        event_type=EventType.DISCONNECTED.value,
        severity="critical",
        message="Stream disconnected",
    )
    db_session.add(event)
    db_session.commit()
    return event


@pytest.fixture
def sample_recording(db_session, sample_stream):
    """Create a sample recording."""
    recording = Recording(
        stream_id=sample_stream.id,
        file_path="/recordings/test_stream1/2024-01-01_120000.mp4",
        file_size=1024 * 1024 * 100,  # 100MB
        duration_seconds=3600,
        start_time=datetime.utcnow(),
        segment_type="continuous",
        retention_days=7,
    )
    db_session.add(recording)
    db_session.commit()
    return recording


@pytest.fixture
def sample_config_snapshot(db_session, sample_node):
    """Create a sample config snapshot."""
    config_yaml = """
paths:
  test/stream1:
    source: rtsp://192.168.1.100:554/stream1
  test/stream2:
    source: rtsp://192.168.1.100:554/stream2
"""
    snapshot = ConfigSnapshot(
        node_id=sample_node.id,
        config_hash="abc123",
        config_yaml=config_yaml,
        environment="testing",
        applied=True,
        applied_at=datetime.utcnow(),
    )
    db_session.add(snapshot)
    db_session.commit()
    return snapshot


@pytest.fixture
def mock_httpx():
    """Mock httpx for external API calls."""
    with patch("httpx.get") as mock_get, patch("httpx.post") as mock_post, patch(
        "httpx.patch"
    ) as mock_patch, patch("httpx.delete") as mock_delete:
        yield {
            "get": mock_get,
            "post": mock_post,
            "patch": mock_patch,
            "delete": mock_delete,
        }


@pytest.fixture
def mock_subprocess():
    """Mock subprocess for ffprobe/ffmpeg calls."""
    with patch("subprocess.run") as mock_run, patch("subprocess.Popen") as mock_popen:
        yield {"run": mock_run, "popen": mock_popen}


@pytest.fixture
def mediamtx_api_response():
    """Sample MediaMTX API response."""
    return {
        "items": [
            {
                "name": "test/stream1",
                "ready": True,
                "source": {
                    "type": "rtspSource",
                    "id": "rtsp://192.168.1.100:554/stream1",
                },
                "bytesReceived": 1000000,
            },
            {
                "name": "test/stream2",
                "ready": False,
                "source": {
                    "type": "rtspSource",
                    "id": "rtsp://192.168.1.100:554/stream2",
                },
                "bytesReceived": 0,
            },
            {
                "name": "test/ondemand",
                "ready": False,
                "source": None,
                "confName": "test/ondemand",
            },
        ]
    }


@pytest.fixture
def ffprobe_response():
    """Sample ffprobe JSON response."""
    return {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
                "r_frame_rate": "30/1",
                "bit_rate": "4000000",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            },
        ],
        "format": {"format_name": "rtsp", "duration": None},
    }
