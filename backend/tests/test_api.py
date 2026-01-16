"""
Tests for API endpoints.
"""
import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime

from app import db
from app.models import Stream, MediaMTXNode, StreamStatus, Recording


class TestHealthAPI:
    """Tests for Health API endpoints."""

    def test_get_health_status(self, app_context, client):
        """Test getting overall health status."""
        with patch('app.api.health.checker.check_redis', return_value='ok'), \
             patch('app.api.health.checker.check_mediamtx_api', return_value='ok'):
            response = client.get('/api/health/')

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
        assert 'checks' in data

    def test_get_streams_health(self, app_context, client, sample_stream):
        """Test getting streams health."""
        response = client.get('/api/health/streams')

        assert response.status_code == 200
        data = response.get_json()
        assert 'streams' in data
        assert 'summary' in data

    def test_get_streams_health_filtered(self, app_context, client, sample_node, sample_stream):
        """Test getting streams health filtered by node."""
        response = client.get(f'/api/health/streams?node_id={sample_node.id}')

        assert response.status_code == 200
        data = response.get_json()
        assert 'streams' in data

    def test_get_stream_health(self, app_context, client, sample_stream):
        """Test getting specific stream health."""
        response = client.get(f'/api/health/streams/{sample_stream.id}')

        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == sample_stream.id

    def test_get_stream_health_not_found(self, app_context, client):
        """Test getting health of non-existent stream."""
        response = client.get('/api/health/streams/99999')

        assert response.status_code == 404

    def test_probe_stream(self, app_context, client, sample_stream, mock_subprocess, ffprobe_response):
        """Test probing a stream."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(ffprobe_response),
            stderr=''
        )

        response = client.post(f'/api/health/streams/{sample_stream.id}/probe')

        assert response.status_code == 200

    def test_probe_url(self, app_context, client, mock_subprocess, ffprobe_response):
        """Test probing a URL directly."""
        mock_subprocess['run'].return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(ffprobe_response),
            stderr=''
        )

        response = client.post('/api/health/probe', json={
            'url': 'rtsp://localhost:8554/test',
            'protocol': 'rtsp'
        })

        assert response.status_code == 200
        data = response.get_json()
        assert 'is_healthy' in data

    def test_probe_url_missing(self, app_context, client):
        """Test probing without URL."""
        response = client.post('/api/health/probe', json={})

        assert response.status_code == 400

    def test_quick_check_all(self, app_context, client, sample_node, mock_httpx, mediamtx_api_response):
        """Test quick check all nodes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mediamtx_api_response
        mock_httpx['get'].return_value = mock_response

        response = client.post('/api/health/quick-check')

        assert response.status_code == 200
        data = response.get_json()
        assert 'nodes_checked' in data

    def test_quick_check_node(self, app_context, client, sample_node, mock_httpx, mediamtx_api_response):
        """Test quick check specific node."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mediamtx_api_response
        mock_httpx['get'].return_value = mock_response

        response = client.post(f'/api/health/quick-check/{sample_node.id}')

        assert response.status_code == 200


class TestStreamsAPI:
    """Tests for Streams API endpoints."""

    def test_list_streams(self, app_context, client, sample_stream):
        """Test listing streams."""
        response = client.get('/api/streams/')

        assert response.status_code == 200
        data = response.get_json()
        assert 'streams' in data
        assert 'total' in data
        assert len(data['streams']) >= 1

    def test_list_streams_pagination(self, app_context, client, sample_stream):
        """Test streams pagination."""
        response = client.get('/api/streams/?page=1&per_page=10')

        assert response.status_code == 200
        data = response.get_json()
        assert data['page'] == 1
        assert 'pages' in data

    def test_list_streams_filtered(self, app_context, client, sample_stream):
        """Test listing streams filtered by status."""
        response = client.get('/api/streams/?status=healthy')

        assert response.status_code == 200
        data = response.get_json()
        for stream in data['streams']:
            assert stream['status'] == 'healthy'

    def test_list_streams_search(self, app_context, client, sample_stream):
        """Test searching streams."""
        response = client.get('/api/streams/?search=test')

        assert response.status_code == 200
        data = response.get_json()
        assert len(data['streams']) >= 1

    def test_get_stream(self, app_context, client, sample_stream):
        """Test getting stream details."""
        response = client.get(f'/api/streams/{sample_stream.id}')

        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == sample_stream.id
        assert data['path'] == sample_stream.path

    def test_get_stream_not_found(self, app_context, client):
        """Test getting non-existent stream."""
        response = client.get('/api/streams/99999')

        assert response.status_code == 404

    def test_create_stream(self, app_context, client, sample_node):
        """Test creating a stream."""
        response = client.post('/api/streams/', json={
            'node_id': sample_node.id,
            'path': 'new/stream',
            'name': 'New Stream',
            'protocol': 'rtsp',
            'auto_remediate': True
        })

        assert response.status_code == 201
        data = response.get_json()
        assert 'id' in data

    def test_create_stream_invalid_node(self, app_context, client):
        """Test creating stream with invalid node."""
        response = client.post('/api/streams/', json={
            'node_id': 99999,
            'path': 'test/stream'
        })

        assert response.status_code == 404

    def test_update_stream(self, app_context, client, sample_stream):
        """Test updating a stream."""
        response = client.put(f'/api/streams/{sample_stream.id}', json={
            'name': 'Updated Name',
            'auto_remediate': False
        })

        assert response.status_code == 200

        # Verify update
        db.session.refresh(sample_stream)
        assert sample_stream.name == 'Updated Name'
        assert sample_stream.auto_remediate is False

    def test_delete_stream(self, app_context, client, db_session, sample_node):
        """Test deleting a stream."""
        # Create stream to delete
        stream = Stream(node_id=sample_node.id, path='to/delete')
        db_session.add(stream)
        db_session.commit()
        stream_id = stream.id

        response = client.delete(f'/api/streams/{stream_id}')

        assert response.status_code == 200

        # Verify deleted
        assert Stream.query.get(stream_id) is None

    def test_trigger_remediation(self, app_context, client, sample_stream, mock_httpx):
        """Test triggering manual remediation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx['post'].return_value = mock_response

        with patch('time.sleep'):
            response = client.post(f'/api/streams/{sample_stream.id}/remediate')

        assert response.status_code == 200
        data = response.get_json()
        assert 'success' in data

    def test_get_playback(self, app_context, client, sample_stream, sample_node):
        """Test getting playback URLs."""
        response = client.get(f'/api/streams/{sample_stream.id}/playback')

        assert response.status_code == 200
        data = response.get_json()
        assert 'hls_url' in data
        assert sample_stream.path in data['hls_url']

    def test_get_playback_config(self, app_context, client, sample_node):
        """Test getting playback configuration."""
        response = client.get('/api/streams/playback/config')

        assert response.status_code == 200
        data = response.get_json()
        assert 'hls_port' in data
        assert 'nodes' in data

    def test_get_thumbnail_not_found(self, app_context, client, sample_stream):
        """Test getting thumbnail when not cached."""
        with patch('app.api.streams.thumbnail_service.get_cached_thumbnail', return_value=None):
            response = client.get(f'/api/streams/{sample_stream.id}/thumbnail')

        assert response.status_code == 404

    def test_generate_thumbnails_batch(self, app_context, client, sample_stream):
        """Test batch thumbnail generation."""
        with patch('app.api.streams.thumbnail_service.generate_thumbnail'):
            response = client.post('/api/streams/thumbnail/batch', json={
                'stream_ids': [sample_stream.id],
                'sync': True
            })

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'completed'


class TestFleetAPI:
    """Tests for Fleet API endpoints."""

    def test_list_nodes(self, app_context, client, sample_node):
        """Test listing nodes."""
        response = client.get('/api/fleet/nodes')

        assert response.status_code == 200
        data = response.get_json()
        assert 'nodes' in data
        assert len(data['nodes']) >= 1

    def test_create_node(self, app_context, client):
        """Test creating a node."""
        response = client.post('/api/fleet/nodes', json={
            'name': 'new-node',
            'api_url': 'http://new-node:9997',
            'environment': 'development'
        })

        assert response.status_code == 201
        data = response.get_json()
        assert 'id' in data

    def test_update_node(self, app_context, client, sample_node):
        """Test updating a node."""
        response = client.put(f'/api/fleet/nodes/{sample_node.id}', json={
            'environment': 'production'
        })

        assert response.status_code == 200

    def test_delete_node(self, app_context, client, db_session):
        """Test deleting a node."""
        node = MediaMTXNode(name='to-delete', api_url='http://delete:9997')
        db_session.add(node)
        db_session.commit()
        node_id = node.id

        response = client.delete(f'/api/fleet/nodes/{node_id}')

        assert response.status_code == 200
        assert MediaMTXNode.query.get(node_id) is None

    def test_sync_node(self, app_context, client, sample_node, mock_httpx, mediamtx_api_response):
        """Test syncing node streams."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mediamtx_api_response
        mock_httpx['get'].return_value = mock_response

        response = client.post(f'/api/fleet/nodes/{sample_node.id}/sync')

        assert response.status_code == 200
        data = response.get_json()
        assert 'success' in data


class TestConfigAPI:
    """Tests for Config API endpoints."""

    def test_list_snapshots(self, app_context, client, sample_config_snapshot):
        """Test listing config snapshots."""
        response = client.get('/api/config/snapshots')

        assert response.status_code == 200
        data = response.get_json()
        assert 'snapshots' in data

    def test_get_snapshot(self, app_context, client, sample_config_snapshot):
        """Test getting specific snapshot."""
        response = client.get(f'/api/config/snapshots/{sample_config_snapshot.id}')

        assert response.status_code == 200
        data = response.get_json()
        assert 'config_yaml' in data

    def test_validate_config(self, app_context, client):
        """Test validating a config."""
        response = client.post('/api/config/validate', json={
            'config_yaml': 'paths:\n  test: {}'
        })

        assert response.status_code == 200
        data = response.get_json()
        assert 'valid' in data

    def test_plan_config(self, app_context, client, sample_node, mock_httpx):
        """Test planning a config change."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'paths': {}}
        mock_httpx['get'].return_value = mock_response

        response = client.post('/api/config/plan', json={
            'node_id': sample_node.id,
            'config_yaml': 'paths:\n  new: {}'
        })

        assert response.status_code == 200
        data = response.get_json()
        assert 'can_apply' in data

    def test_apply_config(self, app_context, client, sample_node, mock_httpx):
        """Test applying a config."""
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {'paths': {}}
        mock_httpx['get'].return_value = mock_get

        mock_patch = MagicMock()
        mock_patch.status_code = 200
        mock_httpx['patch'].return_value = mock_patch

        response = client.post('/api/config/apply', json={
            'node_id': sample_node.id,
            'config_yaml': 'paths:\n  test: {}'
        })

        assert response.status_code == 200
        data = response.get_json()
        assert 'success' in data


class TestRecordingsAPI:
    """Tests for Recordings API endpoints."""

    def test_list_recordings(self, app_context, client, sample_recording):
        """Test listing recordings."""
        response = client.get('/api/recordings/')

        assert response.status_code == 200
        data = response.get_json()
        assert 'recordings' in data

    def test_get_recording(self, app_context, client, sample_recording):
        """Test getting specific recording."""
        response = client.get(f'/api/recordings/{sample_recording.id}')

        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == sample_recording.id

    def test_get_retention_status(self, app_context, client):
        """Test getting retention status."""
        with patch('app.api.recordings.retention_mgr.get_status', return_value={
            'disk': {'total_gb': 500, 'used_gb': 200, 'free_gb': 300, 'usage_percent': 40.0},
            'recordings': {'total': 10, 'total_size_gb': 5.0}
        }):
            response = client.get('/api/recordings/retention/status')

        assert response.status_code == 200
        data = response.get_json()
        assert 'disk' in data

    def test_get_retention_policy(self, app_context, client):
        """Test getting retention policy."""
        response = client.get('/api/recordings/retention/policy')

        assert response.status_code == 200
        data = response.get_json()
        assert 'continuous_retention_days' in data


class TestDashboardAPI:
    """Tests for Dashboard API endpoints."""

    def test_get_dashboard_overview(self, app_context, client, sample_node, sample_stream):
        """Test getting dashboard overview."""
        response = client.get('/api/dashboard/overview')

        assert response.status_code == 200
        data = response.get_json()
        assert 'nodes' in data
        assert 'streams' in data
        assert 'events' in data
        assert 'recordings' in data

    def test_get_streams_status(self, app_context, client, sample_stream):
        """Test getting streams by status."""
        response = client.get('/api/dashboard/streams/status')

        assert response.status_code == 200
        data = response.get_json()
        assert 'healthy' in data
        assert 'unhealthy' in data

    def test_get_recent_events(self, app_context, client, sample_event):
        """Test getting recent events."""
        response = client.get('/api/dashboard/events/recent')

        assert response.status_code == 200
        data = response.get_json()
        assert 'events' in data

    def test_get_active_alerts(self, app_context, client, sample_event):
        """Test getting active alerts."""
        response = client.get('/api/dashboard/alerts/active')

        assert response.status_code == 200
        data = response.get_json()
        assert 'alerts' in data
        assert 'total' in data

    def test_get_nodes_status(self, app_context, client, sample_node):
        """Test getting nodes status."""
        response = client.get('/api/dashboard/nodes/status')

        assert response.status_code == 200
        data = response.get_json()
        assert 'nodes' in data
