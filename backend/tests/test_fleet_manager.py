"""
Tests for FleetManager service.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app import db
from app.models import MediaMTXNode, Stream, StreamStatus
from app.services.fleet_manager import FleetManager


class TestFleetManager:
    """Tests for FleetManager service."""

    def test_detect_protocol_rtsp(self, app_context):
        """Test protocol detection for RTSP."""
        manager = FleetManager()
        path_data = {'source': {'type': 'rtspSource'}}

        assert manager._detect_protocol(path_data) == 'rtsp'

    def test_detect_protocol_rtmp(self, app_context):
        """Test protocol detection for RTMP."""
        manager = FleetManager()
        path_data = {'source': {'type': 'rtmpSource'}}

        assert manager._detect_protocol(path_data) == 'rtmp'

    def test_detect_protocol_webrtc(self, app_context):
        """Test protocol detection for WebRTC."""
        manager = FleetManager()
        path_data = {'source': {'type': 'webrtcSession'}}

        assert manager._detect_protocol(path_data) == 'webrtc'

    def test_detect_protocol_hls(self, app_context):
        """Test protocol detection for HLS."""
        manager = FleetManager()
        path_data = {'source': {'type': 'hlsSource'}}

        assert manager._detect_protocol(path_data) == 'hls'

    def test_detect_protocol_unknown(self, app_context):
        """Test protocol detection for unknown type."""
        manager = FleetManager()
        path_data = {'source': {'type': 'something_else'}}

        assert manager._detect_protocol(path_data) == 'unknown'

    def test_detect_protocol_no_source(self, app_context):
        """Test protocol detection with no source."""
        manager = FleetManager()
        path_data = {'source': None}

        assert manager._detect_protocol(path_data) == 'unknown'

    def test_sync_node_streams_success(self, app_context, db_session, sample_node, mock_httpx, mediamtx_api_response):
        """Test successful stream sync."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mediamtx_api_response
        mock_httpx['get'].return_value = mock_response

        manager = FleetManager()
        result = manager.sync_node_streams(sample_node)

        assert result['success'] is True
        assert result['synced'] == 3  # 3 paths in mediamtx_api_response
        assert result['created'] > 0

    def test_sync_node_streams_api_error(self, app_context, db_session, sample_node, mock_httpx):
        """Test stream sync with API error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_httpx['get'].return_value = mock_response

        manager = FleetManager()
        result = manager.sync_node_streams(sample_node)

        assert result['success'] is False
        assert '500' in result['error']

    def test_sync_node_streams_connection_error(self, app_context, db_session, sample_node, mock_httpx):
        """Test stream sync with connection error."""
        mock_httpx['get'].side_effect = Exception('Connection refused')

        manager = FleetManager()
        result = manager.sync_node_streams(sample_node)

        assert result['success'] is False
        assert 'Connection refused' in result['error']

    def test_sync_node_streams_updates_existing(self, app_context, db_session, sample_node, sample_stream, mock_httpx):
        """Test that sync updates existing streams."""
        # Create response that includes the existing stream
        response_data = {
            'items': [{
                'name': sample_stream.path,
                'ready': True,
                'source': {'type': 'rtspSource', 'id': 'rtsp://new-source'}
            }]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_httpx['get'].return_value = mock_response

        manager = FleetManager()
        result = manager.sync_node_streams(sample_node)

        assert result['success'] is True
        assert result['updated'] > 0
        assert result['created'] == 0

    def test_sync_node_streams_deletes_stale(self, app_context, db_session, sample_node, mock_httpx):
        """Test that sync deletes stale streams."""
        # Create a stream that won't be in the API response
        stale_stream = Stream(
            node_id=sample_node.id,
            path='stale/stream',
            name='Stale Stream'
        )
        db_session.add(stale_stream)
        db_session.commit()

        # API response without the stale stream
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}
        mock_httpx['get'].return_value = mock_response

        manager = FleetManager()
        result = manager.sync_node_streams(sample_node)

        assert result['success'] is True
        assert result['deleted'] > 0

        # Verify stream was deleted
        assert Stream.query.filter_by(path='stale/stream').first() is None

    def test_sync_all_nodes(self, app_context, db_session, sample_node, mock_httpx, mediamtx_api_response):
        """Test syncing all nodes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mediamtx_api_response
        mock_httpx['get'].return_value = mock_response

        manager = FleetManager()
        result = manager.sync_all_nodes()

        assert result['total_nodes'] >= 1
        assert result['successful'] >= 1
        assert 'results' in result

    def test_sync_all_nodes_partial_failure(self, app_context, db_session, sample_node, mock_httpx):
        """Test sync all nodes with some failures."""
        # Create second node
        node2 = MediaMTXNode(
            name='node-2',
            api_url='http://192.168.1.11:9997',
            is_active=True
        )
        db_session.add(node2)
        db_session.commit()

        # First call succeeds, second fails
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}
        mock_httpx['get'].side_effect = [mock_response, Exception('Connection refused')]

        manager = FleetManager()
        result = manager.sync_all_nodes()

        assert result['total_nodes'] == 2
        assert result['successful'] == 1
        assert result['failed'] == 1

    def test_get_node_health_healthy(self, app_context, db_session, sample_node, mock_httpx):
        """Test getting health of a healthy node."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': [{'name': 'stream1'}]}
        mock_httpx['get'].return_value = mock_response

        manager = FleetManager()
        result = manager.get_node_health(sample_node)

        assert result['is_healthy'] is True
        assert result['api_responsive'] is True
        assert result['path_count'] == 1

    def test_get_node_health_unhealthy(self, app_context, db_session, sample_node, mock_httpx):
        """Test getting health of an unhealthy node."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_httpx['get'].return_value = mock_response

        manager = FleetManager()
        result = manager.get_node_health(sample_node)

        assert result['is_healthy'] is False
        assert result['api_responsive'] is False

    def test_get_node_health_connection_error(self, app_context, db_session, sample_node, mock_httpx):
        """Test getting health with connection error."""
        mock_httpx['get'].side_effect = Exception('Connection refused')

        manager = FleetManager()
        result = manager.get_node_health(sample_node)

        assert result['is_healthy'] is False
        assert 'error' in result

    def test_check_all_nodes_health(self, app_context, db_session, sample_node, mock_httpx):
        """Test checking health of all nodes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}
        mock_httpx['get'].return_value = mock_response

        manager = FleetManager()
        result = manager.check_all_nodes_health()

        assert 'total_nodes' in result
        assert 'healthy' in result
        assert 'unhealthy' in result
        assert 'results' in result

    def test_apply_policy_to_fleet(self, app_context, db_session, sample_stream):
        """Test applying policy to fleet."""
        manager = FleetManager()
        result = manager.apply_policy_to_fleet({
            'auto_remediation_enabled': False,
            'recording_enabled': True
        })

        assert result['success'] is True
        assert result['streams_updated'] > 0

        # Verify stream was updated
        db_session.refresh(sample_stream)
        assert sample_stream.auto_remediate is False
        assert sample_stream.recording_enabled is True

    def test_apply_policy_to_fleet_by_environment(self, app_context, db_session, sample_node, sample_stream):
        """Test applying policy filtered by environment."""
        # Change node environment
        sample_node.environment = 'production'
        db_session.commit()

        manager = FleetManager()
        result = manager.apply_policy_to_fleet(
            {'auto_remediation_enabled': False},
            environment='production'
        )

        assert result['success'] is True
        assert result['streams_updated'] >= 1

    def test_apply_policy_to_fleet_no_match(self, app_context, db_session, sample_node, sample_stream):
        """Test applying policy with no matching streams."""
        sample_node.environment = 'development'
        db_session.commit()

        manager = FleetManager()
        result = manager.apply_policy_to_fleet(
            {'auto_remediation_enabled': False},
            environment='production'
        )

        assert result['success'] is True
        assert result['streams_updated'] == 0

    def test_get_fleet_metrics(self, app_context, db_session, sample_node, sample_stream, sample_unhealthy_stream):
        """Test getting fleet metrics."""
        sample_node.environment = 'production'
        sample_stream.bitrate = 4000000
        db_session.commit()

        manager = FleetManager()
        result = manager.get_fleet_metrics()

        assert 'nodes' in result
        assert 'streams' in result
        assert 'bandwidth' in result
        assert result['streams']['total'] >= 2
        assert result['streams']['healthy'] >= 1

    def test_get_fleet_metrics_empty(self, app_context, db_session):
        """Test getting fleet metrics with no data."""
        manager = FleetManager()
        result = manager.get_fleet_metrics()

        assert result['nodes']['total'] == 0
        assert result['streams']['total'] == 0
        assert result['streams']['health_percentage'] == 0

    def test_get_fleet_metrics_by_environment(self, app_context, db_session, sample_node):
        """Test fleet metrics grouped by environment."""
        sample_node.environment = 'production'
        db_session.commit()

        manager = FleetManager()
        result = manager.get_fleet_metrics()

        assert result['nodes']['by_environment']['production'] >= 1

    def test_rolling_update_no_config(self, app_context, db_session, sample_node):
        """Test rolling update without config snapshot."""
        manager = FleetManager()
        result = manager.rolling_update(config_snapshot_id=None)

        assert result['success'] is False
        assert 'config_snapshot_id required' in result['error']

    def test_rolling_update_config_not_found(self, app_context, db_session, sample_node):
        """Test rolling update with non-existent config."""
        manager = FleetManager()
        result = manager.rolling_update(config_snapshot_id=999)

        assert result['success'] is False
        assert 'not found' in result['error']

    def test_rolling_update_no_nodes(self, app_context, db_session, sample_config_snapshot):
        """Test rolling update with no matching nodes."""
        # Deactivate all nodes
        MediaMTXNode.query.update({'is_active': False})
        db_session.commit()

        manager = FleetManager()
        result = manager.rolling_update(
            config_snapshot_id=sample_config_snapshot.id
        )

        assert result['success'] is False
        assert 'No nodes found' in result['error']

    def test_rolling_update_success(self, app_context, db_session, sample_node, sample_config_snapshot, mock_httpx):
        """Test successful rolling update."""
        # Mock config fetch
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {'paths': {}}
        mock_httpx['get'].return_value = mock_get

        # Mock config apply
        mock_patch = MagicMock()
        mock_patch.status_code = 200
        mock_httpx['patch'].return_value = mock_patch

        with patch('time.sleep'):
            manager = FleetManager()
            result = manager.rolling_update(
                config_snapshot_id=sample_config_snapshot.id
            )

        assert result['success'] is True
        assert result['total_nodes'] >= 1

    def test_rolling_update_batch_failure(self, app_context, db_session, sample_node, sample_config_snapshot, mock_httpx):
        """Test rolling update stops on batch failure."""
        # Mock config fetch failure
        mock_get = MagicMock()
        mock_get.status_code = 500
        mock_httpx['get'].return_value = mock_get
        mock_httpx['patch'].side_effect = Exception('Apply failed')

        manager = FleetManager()
        result = manager.rolling_update(
            config_snapshot_id=sample_config_snapshot.id
        )

        assert result['success'] is False
        assert 'failures' in result['error']

    def test_rolling_update_by_environment(self, app_context, db_session, sample_node, sample_config_snapshot, mock_httpx):
        """Test rolling update filtered by environment."""
        sample_node.environment = 'staging'
        db_session.commit()

        # Create production node
        prod_node = MediaMTXNode(
            name='prod-node',
            api_url='http://prod:9997',
            environment='production',
            is_active=True
        )
        db_session.add(prod_node)
        db_session.commit()

        # Mock successful apply
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {'paths': {}}
        mock_httpx['get'].return_value = mock_get

        mock_patch = MagicMock()
        mock_patch.status_code = 200
        mock_httpx['patch'].return_value = mock_patch

        manager = FleetManager()
        result = manager.rolling_update(
            environment='production',
            config_snapshot_id=sample_config_snapshot.id
        )

        # Should only update production node
        assert result['total_nodes'] == 1

    def test_sync_updates_node_last_seen(self, app_context, db_session, sample_node, mock_httpx, mediamtx_api_response):
        """Test that sync updates node last_seen timestamp."""
        old_last_seen = sample_node.last_seen

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mediamtx_api_response
        mock_httpx['get'].return_value = mock_response

        manager = FleetManager()
        manager.sync_node_streams(sample_node)

        db_session.refresh(sample_node)
        assert sample_node.last_seen >= old_last_seen
