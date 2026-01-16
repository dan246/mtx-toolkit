"""
Tests for AutoRemediation service.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from app import db
from app.models import Stream, StreamEvent, StreamStatus, EventType
from app.services.auto_remediation import (
    AutoRemediation, RemediationAction, RemediationResult
)


class TestRemediationResult:
    """Tests for RemediationResult class."""

    def test_create_result(self):
        """Test creating a remediation result."""
        result = RemediationResult(
            success=True,
            action=RemediationAction.RECONNECT,
            message='Successfully reconnected',
            details={'attempt': 1}
        )

        assert result.success is True
        assert result.action == RemediationAction.RECONNECT
        assert result.message == 'Successfully reconnected'
        assert result.details == {'attempt': 1}
        assert result.timestamp is not None

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = RemediationResult(
            success=False,
            action=RemediationAction.RESTART_PATH,
            message='Failed to restart'
        )
        result_dict = result.to_dict()

        assert result_dict['success'] is False
        assert result_dict['action'] == 'restart_path'
        assert result_dict['message'] == 'Failed to restart'
        assert 'timestamp' in result_dict


class TestRemediationAction:
    """Tests for RemediationAction enum."""

    def test_action_values(self):
        """Test remediation action values."""
        assert RemediationAction.RECONNECT.value == 'reconnect'
        assert RemediationAction.RESTART_SIDECAR.value == 'restart_sidecar'
        assert RemediationAction.RESTART_PATH.value == 'restart_path'
        assert RemediationAction.RESTART_MEDIAMTX.value == 'restart_mediamtx'


class TestAutoRemediation:
    """Tests for AutoRemediation service."""

    def test_calculate_backoff_initial(self, app_context):
        """Test initial backoff calculation."""
        remediation = AutoRemediation()
        delay = remediation.calculate_backoff(0)

        # First attempt: base_delay * 2^0 = 0.1 * 1 = 0.1
        # Plus jitter (up to 30%)
        assert 0.1 <= delay <= 0.13

    def test_calculate_backoff_exponential(self, app_context):
        """Test exponential backoff."""
        remediation = AutoRemediation()

        delay0 = remediation.calculate_backoff(0)
        delay1 = remediation.calculate_backoff(1)
        delay2 = remediation.calculate_backoff(2)

        # Each delay should roughly double (minus jitter variance)
        assert delay1 > delay0
        assert delay2 > delay1

    def test_calculate_backoff_max_cap(self, app_context):
        """Test backoff is capped at max delay."""
        remediation = AutoRemediation()
        delay = remediation.calculate_backoff(10)  # Very high attempt number

        assert delay <= remediation.config['max_delay']

    def test_should_auto_remediate_enabled(self, app_context, db_session, sample_stream):
        """Test should_auto_remediate when enabled."""
        remediation = AutoRemediation()
        result = remediation.should_auto_remediate(sample_stream)

        assert result is True

    def test_should_auto_remediate_disabled(self, app_context, db_session, sample_node):
        """Test should_auto_remediate when disabled."""
        stream = Stream(
            node_id=sample_node.id,
            path='test/disabled',
            auto_remediate=False
        )
        db_session.add(stream)
        db_session.commit()

        remediation = AutoRemediation()
        result = remediation.should_auto_remediate(stream)

        assert result is False

    def test_should_auto_remediate_cooldown(self, app_context, db_session, sample_stream):
        """Test should_auto_remediate respects cooldown."""
        sample_stream.last_remediation = datetime.utcnow()
        db_session.commit()

        remediation = AutoRemediation()
        result = remediation.should_auto_remediate(sample_stream)

        # Should be false due to cooldown
        assert result is False

    def test_should_auto_remediate_after_cooldown(self, app_context, db_session, sample_stream):
        """Test should_auto_remediate after cooldown expires."""
        sample_stream.last_remediation = datetime.utcnow() - timedelta(minutes=10)
        db_session.commit()

        remediation = AutoRemediation()
        result = remediation.should_auto_remediate(sample_stream)

        assert result is True

    def test_should_auto_remediate_circuit_breaker(self, app_context, db_session, sample_stream):
        """Test circuit breaker after too many failures."""
        # Create many recent failed remediations
        for i in range(15):
            event = StreamEvent(
                stream_id=sample_stream.id,
                event_type=EventType.REMEDIATION_FAILED.value,
                created_at=datetime.utcnow() - timedelta(minutes=i)
            )
            db_session.add(event)
        db_session.commit()

        remediation = AutoRemediation()
        result = remediation.should_auto_remediate(sample_stream)

        # Should be false due to circuit breaker
        assert result is False

    def test_determine_start_level_no_history(self, app_context, db_session, sample_stream):
        """Test start level with no remediation history."""
        remediation = AutoRemediation()
        level = remediation._determine_start_level(sample_stream)

        assert level == 1  # Start from reconnect

    def test_determine_start_level_some_history(self, app_context, db_session, sample_stream):
        """Test start level with some remediation history."""
        # Create 3 recent remediations
        for i in range(3):
            event = StreamEvent(
                stream_id=sample_stream.id,
                event_type=EventType.REMEDIATION_STARTED.value,
                created_at=datetime.utcnow() - timedelta(minutes=i * 10)
            )
            db_session.add(event)
        db_session.commit()

        remediation = AutoRemediation()
        level = remediation._determine_start_level(sample_stream)

        assert level == 2  # Skip to restart sidecar

    def test_determine_start_level_many_failures(self, app_context, db_session, sample_stream):
        """Test start level with many recent remediations."""
        # Create 6 recent remediations
        for i in range(6):
            event = StreamEvent(
                stream_id=sample_stream.id,
                event_type=EventType.REMEDIATION_STARTED.value,
                created_at=datetime.utcnow() - timedelta(minutes=i * 5)
            )
            db_session.add(event)
        db_session.commit()

        remediation = AutoRemediation()
        level = remediation._determine_start_level(sample_stream)

        assert level == 3  # Skip to restart path

    def test_try_reconnect_success(self, app_context, db_session, sample_stream, mock_httpx):
        """Test successful reconnect attempt."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx['post'].return_value = mock_response

        with patch('time.sleep'):
            remediation = AutoRemediation()
            result = remediation._try_reconnect(sample_stream, 0)

        assert result.success is True
        assert result.action == RemediationAction.RECONNECT

    def test_try_reconnect_failure(self, app_context, db_session, sample_stream, mock_httpx):
        """Test failed reconnect attempt."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_httpx['post'].return_value = mock_response

        remediation = AutoRemediation()
        result = remediation._try_reconnect(sample_stream, 0)

        assert result.success is False
        assert '500' in result.message

    def test_try_reconnect_exception(self, app_context, db_session, sample_stream, mock_httpx):
        """Test reconnect with exception."""
        mock_httpx['post'].side_effect = Exception('Connection refused')

        remediation = AutoRemediation()
        result = remediation._try_reconnect(sample_stream, 0)

        assert result.success is False
        assert 'Connection refused' in result.message

    def test_try_restart_sidecar_success(self, app_context, db_session, sample_stream, mock_httpx):
        """Test successful sidecar restart."""
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {'source': 'rtsp://test'}
        mock_httpx['get'].return_value = mock_get_response

        mock_delete_response = MagicMock()
        mock_delete_response.status_code = 204
        mock_httpx['delete'].return_value = mock_delete_response

        mock_patch_response = MagicMock()
        mock_patch_response.status_code = 200
        mock_httpx['patch'].return_value = mock_patch_response

        with patch('time.sleep'):
            remediation = AutoRemediation()
            result = remediation._try_restart_sidecar(sample_stream, 0)

        assert result.success is True
        assert result.action == RemediationAction.RESTART_SIDECAR

    def test_try_restart_sidecar_get_config_failure(self, app_context, db_session, sample_stream, mock_httpx):
        """Test sidecar restart when get config fails."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_httpx['get'].return_value = mock_response

        remediation = AutoRemediation()
        result = remediation._try_restart_sidecar(sample_stream, 0)

        assert result.success is False

    def test_try_restart_path_success(self, app_context, db_session, sample_stream, mock_httpx):
        """Test successful path restart."""
        mock_delete_response = MagicMock()
        mock_delete_response.status_code = 204
        mock_httpx['delete'].return_value = mock_delete_response

        mock_patch_response = MagicMock()
        mock_patch_response.status_code = 200
        mock_httpx['patch'].return_value = mock_patch_response

        with patch('time.sleep'):
            remediation = AutoRemediation()
            result = remediation._try_restart_path(sample_stream, 0)

        assert result.success is True
        assert result.action == RemediationAction.RESTART_PATH

    def test_try_restart_path_no_source(self, app_context, db_session, sample_node):
        """Test path restart without source URL."""
        stream = Stream(
            node_id=sample_node.id,
            path='test/no-source',
            source_url=None
        )
        db_session.add(stream)
        db_session.commit()

        with patch('time.sleep'), patch('httpx.delete') as mock_delete:
            mock_delete.return_value = MagicMock(status_code=204)

            remediation = AutoRemediation()
            result = remediation._try_restart_path(stream, 0)

        # Should complete but may need verification
        assert result.action == RemediationAction.RESTART_PATH

    def test_try_restart_mediamtx_success(self, app_context, db_session, sample_stream, mock_subprocess):
        """Test successful MediaMTX restart."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout='mediamtx',
            stderr=''
        )

        with patch('time.sleep'):
            remediation = AutoRemediation()
            result = remediation._try_restart_mediamtx(sample_stream, 0)

        assert result.success is True
        assert result.action == RemediationAction.RESTART_MEDIAMTX

    def test_try_restart_mediamtx_failure(self, app_context, db_session, sample_stream, mock_subprocess):
        """Test failed MediaMTX restart."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='Error: No such container'
        )

        remediation = AutoRemediation()
        result = remediation._try_restart_mediamtx(sample_stream, 0)

        assert result.success is False
        assert 'No such container' in result.message

    def test_try_restart_mediamtx_timeout(self, app_context, db_session, sample_stream, mock_subprocess):
        """Test MediaMTX restart timeout."""
        import subprocess
        mock_subprocess['run'].side_effect = subprocess.TimeoutExpired(
            cmd='docker', timeout=60
        )

        remediation = AutoRemediation()
        result = remediation._try_restart_mediamtx(sample_stream, 0)

        assert result.success is False

    def test_remediate_stream_success_first_try(self, app_context, db_session, sample_unhealthy_stream, mock_httpx):
        """Test successful remediation on first try."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx['post'].return_value = mock_response

        with patch('time.sleep'):
            remediation = AutoRemediation()
            result = remediation.remediate_stream(sample_unhealthy_stream)

        assert result['success'] is True
        assert sample_unhealthy_stream.remediation_count == 1
        assert sample_unhealthy_stream.last_remediation is not None

    def test_remediate_stream_creates_events(self, app_context, db_session, sample_unhealthy_stream, mock_httpx):
        """Test that remediation creates start and end events."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx['post'].return_value = mock_response

        initial_events = StreamEvent.query.filter_by(
            stream_id=sample_unhealthy_stream.id
        ).count()

        with patch('time.sleep'):
            remediation = AutoRemediation()
            remediation.remediate_stream(sample_unhealthy_stream)

        final_events = StreamEvent.query.filter_by(
            stream_id=sample_unhealthy_stream.id
        ).count()

        # Should have at least 2 new events (start and success/failure)
        assert final_events >= initial_events + 2

    def test_remediate_stream_force_level(self, app_context, db_session, sample_unhealthy_stream, mock_httpx):
        """Test remediation with forced start level."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'source': 'rtsp://test'}
        mock_httpx['get'].return_value = mock_response
        mock_httpx['delete'].return_value = MagicMock(status_code=204)
        mock_httpx['patch'].return_value = MagicMock(status_code=200)

        with patch('time.sleep'):
            remediation = AutoRemediation()
            result = remediation.remediate_stream(sample_unhealthy_stream, force_level=2)

        # Should have skipped level 1 (reconnect)
        actions = [a['action'] for a in result['attempts']]
        assert 'reconnect' not in actions

    def test_remediate_stream_all_levels_fail(self, app_context, db_session, sample_unhealthy_stream, mock_httpx, mock_subprocess):
        """Test remediation when all levels fail."""
        # Make all HTTP calls fail
        mock_httpx['post'].side_effect = Exception('Connection refused')
        mock_httpx['get'].side_effect = Exception('Connection refused')
        mock_httpx['delete'].side_effect = Exception('Connection refused')
        mock_httpx['patch'].side_effect = Exception('Connection refused')

        # Make subprocess fail
        mock_subprocess['run'].return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='Error'
        )

        with patch('time.sleep'):
            remediation = AutoRemediation()
            # Reduce max attempts for faster test
            remediation.config['max_attempts'] = 1
            result = remediation.remediate_stream(sample_unhealthy_stream)

        assert result['success'] is False
        assert len(result['attempts']) > 0

    def test_config_defaults(self, app_context):
        """Test remediation config defaults."""
        remediation = AutoRemediation()

        assert remediation.config['max_attempts'] == 3  # From test config
        assert remediation.config['base_delay'] == 0.1
        assert remediation.config['max_delay'] == 1.0
        assert remediation.config['jitter_factor'] == 0.3

    def test_backoff_includes_jitter(self, app_context):
        """Test that backoff includes jitter randomness."""
        remediation = AutoRemediation()

        # Run multiple times and check for variance
        delays = [remediation.calculate_backoff(1) for _ in range(10)]

        # Should have some variance due to jitter
        assert len(set(delays)) > 1
