"""
Tests for HealthChecker service.
"""
import pytest
import json
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

from app.models import Stream, StreamStatus, StreamEvent, EventType
from app.services.health_checker import HealthChecker, StreamProbeResult


class TestStreamProbeResult:
    """Tests for StreamProbeResult dataclass."""

    def test_default_values(self):
        """Test StreamProbeResult default values."""
        result = StreamProbeResult(
            is_healthy=True,
            status=StreamStatus.HEALTHY
        )
        assert result.is_healthy is True
        assert result.status == StreamStatus.HEALTHY
        assert result.issues == []
        assert result.fps is None

    def test_with_all_fields(self):
        """Test StreamProbeResult with all fields."""
        result = StreamProbeResult(
            is_healthy=True,
            status=StreamStatus.HEALTHY,
            fps=30.0,
            bitrate=4000000,
            latency_ms=50,
            keyframe_interval=2.0,
            width=1920,
            height=1080,
            codec='h264',
            audio_codec='aac',
            issues=[],
            raw_data={'test': 'data'}
        )
        assert result.fps == 30.0
        assert result.width == 1920
        assert result.codec == 'h264'

    def test_with_issues(self):
        """Test StreamProbeResult with issues."""
        result = StreamProbeResult(
            is_healthy=False,
            status=StreamStatus.DEGRADED,
            issues=['Low FPS: 8.5', 'No audio stream']
        )
        assert len(result.issues) == 2
        assert 'Low FPS' in result.issues[0]


class TestHealthChecker:
    """Tests for HealthChecker service."""

    def test_parse_fps_fraction(self, app_context):
        """Test parsing FPS from fraction format."""
        checker = HealthChecker()
        assert checker._parse_fps('30/1') == 30.0
        assert checker._parse_fps('60/2') == 30.0
        assert checker._parse_fps('29970/1000') == pytest.approx(29.97, rel=0.01)

    def test_parse_fps_decimal(self, app_context):
        """Test parsing FPS from decimal format."""
        checker = HealthChecker()
        assert checker._parse_fps('30.0') == 30.0
        assert checker._parse_fps('29.97') == pytest.approx(29.97, rel=0.01)

    def test_parse_fps_zero_denominator(self, app_context):
        """Test parsing FPS with zero denominator."""
        checker = HealthChecker()
        assert checker._parse_fps('30/0') is None

    def test_parse_fps_invalid(self, app_context):
        """Test parsing invalid FPS string."""
        checker = HealthChecker()
        assert checker._parse_fps('invalid') is None
        assert checker._parse_fps('') is None

    def test_quick_check_node_not_found(self, app_context, db_session):
        """Test quick check with non-existent node."""
        checker = HealthChecker()
        result = checker.quick_check_node(999)
        assert 'error' in result
        assert result['error'] == 'Node not found'

    def test_quick_check_node_success(self, app_context, db_session, sample_node, sample_stream, mock_httpx, mediamtx_api_response):
        """Test successful quick check of node."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mediamtx_api_response
        mock_httpx['get'].return_value = mock_response

        checker = HealthChecker()
        result = checker.quick_check_node(sample_node.id)

        assert result['success'] is True
        assert result['node_id'] == sample_node.id
        assert 'updated' in result
        assert 'healthy' in result

    def test_quick_check_node_api_error(self, app_context, db_session, sample_node, mock_httpx):
        """Test quick check with API error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_httpx['get'].return_value = mock_response

        checker = HealthChecker()
        result = checker.quick_check_node(sample_node.id)

        assert 'error' in result
        assert '500' in result['error']

    def test_quick_check_node_connection_error(self, app_context, db_session, sample_node, mock_httpx):
        """Test quick check with connection error."""
        mock_httpx['get'].side_effect = Exception('Connection refused')

        checker = HealthChecker()
        result = checker.quick_check_node(sample_node.id)

        assert 'error' in result
        assert 'Connection refused' in result['error']

    def test_quick_check_all_nodes(self, app_context, db_session, sample_node, mock_httpx, mediamtx_api_response):
        """Test quick check of all nodes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mediamtx_api_response
        mock_httpx['get'].return_value = mock_response

        checker = HealthChecker()
        result = checker.quick_check_all_nodes()

        assert 'nodes_checked' in result
        assert 'total_healthy' in result
        assert 'results' in result

    def test_analyze_probe_result_healthy(self, app_context, ffprobe_response):
        """Test analyzing a healthy probe result."""
        checker = HealthChecker()
        result = checker._analyze_probe_result(
            ffprobe_response,
            'rtsp://localhost:8554/test',
            'rtsp'
        )

        assert result['is_healthy'] is True
        assert result['status'] == 'healthy'
        assert result['fps'] == 30.0
        assert result['codec'] == 'h264'
        assert result['audio_codec'] == 'aac'

    def test_analyze_probe_result_no_streams(self, app_context):
        """Test analyzing probe result with no streams."""
        checker = HealthChecker()
        result = checker._analyze_probe_result(
            {'streams': [], 'format': {}},
            'rtsp://localhost:8554/test',
            'rtsp'
        )

        assert result['is_healthy'] is False
        assert result['status'] == 'unhealthy'
        assert result['error'] == 'No streams found'

    def test_analyze_probe_result_low_fps(self, app_context):
        """Test analyzing probe result with low FPS."""
        checker = HealthChecker()
        probe_data = {
            'streams': [{
                'codec_type': 'video',
                'codec_name': 'h264',
                'avg_frame_rate': '5/1',
                'r_frame_rate': '5/1',
                'width': 1920,
                'height': 1080
            }],
            'format': {'format_name': 'rtsp'}
        }
        result = checker._analyze_probe_result(
            probe_data,
            'rtsp://localhost:8554/test',
            'rtsp'
        )

        assert result['is_healthy'] is False
        assert result['status'] == 'degraded'
        assert any('Low FPS' in issue for issue in result['issues'])

    def test_analyze_probe_result_no_video(self, app_context):
        """Test analyzing probe result without video stream."""
        checker = HealthChecker()
        probe_data = {
            'streams': [{
                'codec_type': 'audio',
                'codec_name': 'aac'
            }],
            'format': {'format_name': 'rtsp'}
        }
        result = checker._analyze_probe_result(
            probe_data,
            'rtsp://localhost:8554/test',
            'rtsp'
        )

        assert result['is_healthy'] is False
        assert result['status'] == 'unhealthy'
        assert 'No video stream' in result['issues']

    def test_analyze_probe_result_no_audio(self, app_context, ffprobe_response):
        """Test analyzing probe result without audio stream."""
        checker = HealthChecker()
        probe_data = {
            'streams': [ffprobe_response['streams'][0]],  # Only video
            'format': {'format_name': 'rtsp'}
        }
        result = checker._analyze_probe_result(
            probe_data,
            'rtsp://localhost:8554/test',
            'rtsp'
        )

        assert 'No audio stream' in result['issues']
        # No audio should be a warning, not unhealthy
        assert result['status'] != 'unhealthy'

    def test_probe_url_success(self, app_context, mock_subprocess, ffprobe_response):
        """Test probing URL successfully."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(ffprobe_response),
            stderr=''
        )

        checker = HealthChecker()
        result = checker.probe_url('rtsp://localhost:8554/test', 'rtsp')

        assert result['is_healthy'] is True
        mock_subprocess['run'].assert_called_once()

    def test_probe_url_ffprobe_error(self, app_context, mock_subprocess):
        """Test probing URL with ffprobe error."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='Connection refused'
        )

        checker = HealthChecker()
        result = checker.probe_url('rtsp://localhost:8554/test', 'rtsp')

        assert result['is_healthy'] is False
        assert 'error' in result

    def test_probe_url_timeout(self, app_context, mock_subprocess):
        """Test probing URL with timeout."""
        import subprocess
        mock_subprocess['run'].side_effect = subprocess.TimeoutExpired(
            cmd='ffprobe', timeout=10
        )

        checker = HealthChecker()
        result = checker.probe_url('rtsp://localhost:8554/test', 'rtsp')

        assert result['is_healthy'] is False
        assert 'error' in result

    def test_probe_stream_not_found(self, app_context, db_session):
        """Test probing non-existent stream."""
        checker = HealthChecker()
        result = checker.probe_stream(999)

        assert 'error' in result
        assert result['error'] == 'Stream not found'

    def test_probe_stream_success(self, app_context, db_session, sample_stream, mock_subprocess, ffprobe_response):
        """Test probing stream successfully."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(ffprobe_response),
            stderr=''
        )

        checker = HealthChecker()
        result = checker.probe_stream(sample_stream.id)

        assert result['is_healthy'] is True
        # Stream should be updated
        db_session.refresh(sample_stream)
        assert sample_stream.status == StreamStatus.HEALTHY.value

    def test_probe_stream_creates_event_on_status_change(self, app_context, db_session, sample_unhealthy_stream, mock_subprocess, ffprobe_response):
        """Test that probing stream creates event on status change."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(ffprobe_response),
            stderr=''
        )

        checker = HealthChecker()
        checker.probe_stream(sample_unhealthy_stream.id)

        # Check that an event was created
        events = StreamEvent.query.filter_by(stream_id=sample_unhealthy_stream.id).all()
        assert len(events) > 0

    def test_get_stream_health(self, app_context, db_session, sample_stream):
        """Test getting stream health status."""
        checker = HealthChecker()
        result = checker.get_stream_health(sample_stream.id)

        assert result is not None
        assert result['id'] == sample_stream.id
        assert result['path'] == sample_stream.path
        assert result['status'] == sample_stream.status

    def test_get_stream_health_not_found(self, app_context, db_session):
        """Test getting health of non-existent stream."""
        checker = HealthChecker()
        result = checker.get_stream_health(999)

        assert result is None

    def test_get_all_streams_health(self, app_context, db_session, sample_stream, sample_unhealthy_stream):
        """Test getting health of all streams."""
        checker = HealthChecker()
        result = checker.get_all_streams_health()

        assert 'streams' in result
        assert 'summary' in result
        assert result['summary']['total'] == 2
        assert result['summary']['healthy'] == 1
        assert result['summary']['unhealthy'] == 1

    def test_get_all_streams_health_filtered_by_status(self, app_context, db_session, sample_stream, sample_unhealthy_stream):
        """Test getting health filtered by status."""
        checker = HealthChecker()
        result = checker.get_all_streams_health(status='healthy')

        assert result['summary']['total'] == 1

    def test_get_all_streams_health_filtered_by_node(self, app_context, db_session, sample_node, sample_stream):
        """Test getting health filtered by node."""
        checker = HealthChecker()
        result = checker.get_all_streams_health(node_id=sample_node.id)

        assert result['summary']['total'] >= 1

    def test_detect_black_screen(self, app_context, mock_subprocess):
        """Test black screen detection."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout='',
            stderr='[blackdetect @ 0x...] black_start:0 black_end:2'
        )

        checker = HealthChecker()
        result = checker.detect_black_screen('rtsp://localhost:8554/test')

        assert result is True

    def test_detect_black_screen_no_black(self, app_context, mock_subprocess):
        """Test black screen detection when no black screen."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout='',
            stderr='frame=60 fps=30'
        )

        checker = HealthChecker()
        result = checker.detect_black_screen('rtsp://localhost:8554/test')

        assert result is False

    def test_detect_freeze(self, app_context, mock_subprocess):
        """Test freeze detection."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout='',
            stderr='[freezedetect @ 0x...] freeze_start:0 freeze_end:5'
        )

        checker = HealthChecker()
        result = checker.detect_freeze('rtsp://localhost:8554/test')

        assert result is True

    def test_detect_freeze_no_freeze(self, app_context, mock_subprocess):
        """Test freeze detection when no freeze."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout='',
            stderr='frame=150 fps=30'
        )

        checker = HealthChecker()
        result = checker.detect_freeze('rtsp://localhost:8554/test')

        assert result is False

    def test_detect_audio_silence(self, app_context, mock_subprocess):
        """Test audio silence detection."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout='',
            stderr='[silencedetect @ 0x...] silence_start: 0'
        )

        checker = HealthChecker()
        result = checker.detect_audio_silence('rtsp://localhost:8554/test')

        assert result is True

    def test_detect_audio_silence_no_silence(self, app_context, mock_subprocess):
        """Test audio silence detection when no silence."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout='',
            stderr='size=N/A time=00:00:03'
        )

        checker = HealthChecker()
        result = checker.detect_audio_silence('rtsp://localhost:8554/test')

        assert result is False

    def test_check_redis_success(self, app_context):
        """Test Redis check success."""
        with patch('redis.from_url') as mock_redis:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_redis.return_value = mock_client

            checker = HealthChecker()
            result = checker.check_redis()

            assert result == 'ok'

    def test_check_redis_failure(self, app_context):
        """Test Redis check failure."""
        with patch('redis.from_url') as mock_redis:
            mock_redis.side_effect = Exception('Connection refused')

            checker = HealthChecker()
            result = checker.check_redis()

            assert 'error' in result

    def test_check_mediamtx_api_success(self, app_context, mock_httpx):
        """Test MediaMTX API check success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx['get'].return_value = mock_response

        checker = HealthChecker()
        result = checker.check_mediamtx_api()

        assert result == 'ok'

    def test_check_mediamtx_api_failure(self, app_context, mock_httpx):
        """Test MediaMTX API check failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_httpx['get'].return_value = mock_response

        checker = HealthChecker()
        result = checker.check_mediamtx_api()

        assert 'error' in result
        assert '500' in result

    def test_check_mediamtx_api_connection_error(self, app_context, mock_httpx):
        """Test MediaMTX API check with connection error."""
        mock_httpx['get'].side_effect = Exception('Connection refused')

        checker = HealthChecker()
        result = checker.check_mediamtx_api()

        assert 'error' in result

    def test_measure_fps(self, app_context, mock_subprocess):
        """Test FPS measurement by frame counting."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                'streams': [{'nb_read_frames': '60'}]
            }),
            stderr=''
        )

        checker = HealthChecker()
        result = checker._measure_fps('rtsp://localhost:8554/test', duration=2.0)

        assert result == 30.0  # 60 frames / 2 seconds

    def test_measure_fps_no_frames(self, app_context, mock_subprocess):
        """Test FPS measurement with no frames."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                'streams': [{'nb_read_frames': '0'}]
            }),
            stderr=''
        )

        checker = HealthChecker()
        result = checker._measure_fps('rtsp://localhost:8554/test')

        assert result is None

    def test_measure_fps_error(self, app_context, mock_subprocess):
        """Test FPS measurement with error."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='Error'
        )

        checker = HealthChecker()
        result = checker._measure_fps('rtsp://localhost:8554/test')

        assert result is None

    def test_thresholds(self, app_context):
        """Test that health check thresholds are set correctly."""
        checker = HealthChecker()

        assert checker.MIN_FPS == 10.0
        assert checker.MAX_KEYFRAME_INTERVAL == 10.0
        assert checker.MAX_LATENCY_MS == 5000
        assert checker.BLACK_SCREEN_THRESHOLD == 0.1
        assert checker.FREEZE_DETECTION_DURATION == 5.0
