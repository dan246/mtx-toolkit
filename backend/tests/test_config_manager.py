"""
Tests for ConfigManager service.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app import db
from app.models import ConfigSnapshot, MediaMTXNode
from app.services.config_manager import ConfigManager, ConfigValidationError


class TestConfigManager:
    """Tests for ConfigManager service."""

    def test_validate_valid_config(self, app_context):
        """Test validating a valid config."""
        config_yaml = """
paths:
  test/stream1:
    source: rtsp://192.168.1.100:554/stream1
  test/stream2:
    source: rtsp://192.168.1.100:554/stream2
"""
        manager = ConfigManager()
        result = manager.validate(config_yaml)

        assert result['valid'] is True
        assert len(result['errors']) == 0
        assert 'config_hash' in result

    def test_validate_missing_paths(self, app_context):
        """Test validating config without paths."""
        config_yaml = """
logLevel: debug
"""
        manager = ConfigManager()
        result = manager.validate(config_yaml)

        assert result['valid'] is False
        assert any('paths' in error for error in result['errors'])

    def test_validate_invalid_yaml(self, app_context):
        """Test validating invalid YAML."""
        config_yaml = """
paths:
  invalid: [
"""
        manager = ConfigManager()
        result = manager.validate(config_yaml)

        assert result['valid'] is False
        assert any('YAML parse error' in error for error in result['errors'])

    def test_validate_paths_not_mapping(self, app_context):
        """Test validating paths that isn't a mapping."""
        config_yaml = """
paths:
  - item1
  - item2
"""
        manager = ConfigManager()
        result = manager.validate(config_yaml)

        assert result['valid'] is False
        assert any("'paths' must be a mapping" in error for error in result['errors'])

    def test_validate_invalid_source(self, app_context):
        """Test validating path with invalid source."""
        config_yaml = """
paths:
  test/stream:
    source:
      - item1
"""
        manager = ConfigManager()
        result = manager.validate(config_yaml)

        assert result['valid'] is False
        assert any('source must be a string' in error for error in result['errors'])

    def test_validate_warnings_low_timeout(self, app_context):
        """Test validation warnings for low timeout."""
        config_yaml = """
paths: {}
readTimeout: 2
writeTimeout: 3
"""
        manager = ConfigManager()
        result = manager.validate(config_yaml)

        assert result['valid'] is True
        assert len(result['warnings']) >= 2

    def test_validate_empty_path_config(self, app_context):
        """Test validating empty path config (valid)."""
        config_yaml = """
paths:
  test/stream:
"""
        manager = ConfigManager()
        result = manager.validate(config_yaml)

        # Empty path config is valid (uses defaults)
        assert result['valid'] is True

    def test_hash_config(self, app_context):
        """Test config hashing."""
        config_yaml1 = """
paths:
  a:
    source: test
"""
        config_yaml2 = """
paths:
  a:
    source: test
"""
        # Same content, different formatting
        config_yaml3 = "paths:\n  a:\n    source: test\n"

        manager = ConfigManager()
        hash1 = manager._hash_config(config_yaml1)
        hash2 = manager._hash_config(config_yaml2)
        hash3 = manager._hash_config(config_yaml3)

        # All should produce same hash (normalized)
        assert hash1 == hash2
        assert hash2 == hash3

    def test_hash_config_different(self, app_context):
        """Test that different configs produce different hashes."""
        config_yaml1 = "paths: {}"
        config_yaml2 = "paths:\n  test: {}"

        manager = ConfigManager()
        hash1 = manager._hash_config(config_yaml1)
        hash2 = manager._hash_config(config_yaml2)

        assert hash1 != hash2

    def test_diff_configs(self, app_context):
        """Test diffing two configs."""
        old_config = """
paths:
  stream1:
    source: rtsp://old
"""
        new_config = """
paths:
  stream1:
    source: rtsp://new
  stream2:
    source: rtsp://added
"""
        manager = ConfigManager()
        result = manager.diff(old_config, new_config)

        assert result['has_changes'] is True
        assert len(result['changes']) > 0

    def test_diff_no_changes(self, app_context):
        """Test diffing identical configs."""
        config = "paths: {}"

        manager = ConfigManager()
        result = manager.diff(config, config)

        assert result['has_changes'] is False
        assert len(result['changes']) == 0

    def test_diff_invalid_yaml(self, app_context):
        """Test diffing with invalid YAML."""
        old_config = "paths: {"
        new_config = "paths: {}"

        manager = ConfigManager()
        result = manager.diff(old_config, new_config)

        assert 'error' in result

    def test_diff_empty_old(self, app_context):
        """Test diffing with empty old config."""
        new_config = "paths:\n  test: {}"

        manager = ConfigManager()
        result = manager.diff("", new_config)

        assert result['has_changes'] is True

    def test_analyze_changes_added(self, app_context):
        """Test analyzing added changes."""
        old = {}
        new = {'key': 'value'}

        manager = ConfigManager()
        changes = manager._analyze_changes(old, new)

        assert len(changes) == 1
        assert changes[0]['type'] == 'added'
        assert changes[0]['path'] == 'key'

    def test_analyze_changes_removed(self, app_context):
        """Test analyzing removed changes."""
        old = {'key': 'value'}
        new = {}

        manager = ConfigManager()
        changes = manager._analyze_changes(old, new)

        assert len(changes) == 1
        assert changes[0]['type'] == 'removed'

    def test_analyze_changes_modified(self, app_context):
        """Test analyzing modified changes."""
        old = {'key': 'old_value'}
        new = {'key': 'new_value'}

        manager = ConfigManager()
        changes = manager._analyze_changes(old, new)

        assert len(changes) == 1
        assert changes[0]['type'] == 'modified'
        assert changes[0]['old_value'] == 'old_value'
        assert changes[0]['new_value'] == 'new_value'

    def test_analyze_changes_nested(self, app_context):
        """Test analyzing nested changes."""
        old = {'paths': {'stream1': {'source': 'old'}}}
        new = {'paths': {'stream1': {'source': 'new'}}}

        manager = ConfigManager()
        changes = manager._analyze_changes(old, new)

        assert len(changes) == 1
        assert 'paths.stream1.source' in changes[0]['path']

    def test_plan_valid_config(self, app_context, db_session, sample_node, mock_httpx):
        """Test planning a valid config change."""
        # Mock current config fetch
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'paths': {}}
        mock_httpx['get'].return_value = mock_response

        new_config = """
paths:
  test/stream:
    source: rtsp://test
"""
        manager = ConfigManager()
        result = manager.plan(sample_node.id, new_config)

        assert result['can_apply'] is True
        assert 'diff' in result
        assert 'validation' in result

    def test_plan_invalid_config(self, app_context, db_session, sample_node):
        """Test planning an invalid config."""
        invalid_config = "invalid: ["

        manager = ConfigManager()
        result = manager.plan(sample_node.id, invalid_config)

        assert result['can_apply'] is False
        assert 'validation' in result

    def test_plan_without_node(self, app_context, db_session):
        """Test planning without a node."""
        new_config = """
paths:
  test: {}
"""
        manager = ConfigManager()
        result = manager.plan(None, new_config)

        assert result['can_apply'] is True

    def test_apply_success(self, app_context, db_session, sample_node, mock_httpx):
        """Test successfully applying a config."""
        # Mock fetch current config
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {'paths': {}}
        mock_httpx['get'].return_value = mock_get

        # Mock apply
        mock_patch = MagicMock()
        mock_patch.status_code = 200
        mock_httpx['patch'].return_value = mock_patch

        new_config = """
paths:
  test/stream:
    source: rtsp://test
"""
        manager = ConfigManager()
        result = manager.apply(
            sample_node.id,
            new_config,
            environment='testing',
            notes='Test apply',
            applied_by='test_user'
        )

        assert result['success'] is True
        assert 'snapshot_id' in result
        assert 'backup_id' in result

        # Verify snapshot was created
        snapshot = ConfigSnapshot.query.get(result['snapshot_id'])
        assert snapshot is not None
        assert snapshot.applied is True

    def test_apply_validation_failure(self, app_context, db_session, sample_node):
        """Test apply with validation failure."""
        invalid_config = "invalid: ["

        manager = ConfigManager()
        result = manager.apply(sample_node.id, invalid_config)

        assert result['success'] is False
        assert 'Validation failed' in result['error']

    def test_apply_api_failure(self, app_context, db_session, sample_node, mock_httpx):
        """Test apply with API failure."""
        # Mock fetch success
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {'paths': {}}
        mock_httpx['get'].return_value = mock_get

        # Mock apply failure
        mock_patch = MagicMock()
        mock_patch.status_code = 500
        mock_httpx['patch'].return_value = mock_patch

        new_config = """
paths:
  test: {}
"""
        manager = ConfigManager()
        result = manager.apply(sample_node.id, new_config)

        assert result['success'] is False
        assert result['rolled_back'] is True

    def test_apply_without_node(self, app_context, db_session):
        """Test apply without a node (global config)."""
        new_config = """
paths:
  test: {}
"""
        manager = ConfigManager()
        result = manager.apply(None, new_config)

        assert result['success'] is True

    def test_rollback(self, app_context, db_session, sample_node, sample_config_snapshot, mock_httpx):
        """Test rolling back to a snapshot."""
        # Mock fetch and apply
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {'paths': {}}
        mock_httpx['get'].return_value = mock_get

        mock_patch = MagicMock()
        mock_patch.status_code = 200
        mock_httpx['patch'].return_value = mock_patch

        manager = ConfigManager()
        result = manager.rollback(sample_config_snapshot.id)

        assert result['success'] is True

    def test_rollback_not_found(self, app_context, db_session):
        """Test rolling back to non-existent snapshot."""
        manager = ConfigManager()
        result = manager.rollback(999)

        assert result['success'] is False
        assert 'not found' in result['error']

    def test_fetch_current_config(self, app_context, db_session, sample_node, mock_httpx):
        """Test fetching current config from node."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'paths': {'test': {}}}
        mock_httpx['get'].return_value = mock_response

        manager = ConfigManager()
        result = manager._fetch_current_config(sample_node)

        assert result is not None
        assert 'paths' in result

    def test_fetch_current_config_failure(self, app_context, db_session, sample_node, mock_httpx):
        """Test fetching config with failure."""
        mock_httpx['get'].side_effect = Exception('Connection refused')

        manager = ConfigManager()
        result = manager._fetch_current_config(sample_node)

        assert result is None

    def test_apply_to_node(self, app_context, db_session, sample_node, mock_httpx):
        """Test applying config to node."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx['patch'].return_value = mock_response

        config_yaml = "paths: {}"

        manager = ConfigManager()
        # Should not raise
        manager._apply_to_node(sample_node, config_yaml)

    def test_apply_to_node_failure(self, app_context, db_session, sample_node, mock_httpx):
        """Test applying config to node with failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_httpx['patch'].return_value = mock_response

        config_yaml = "paths: {}"

        manager = ConfigManager()
        with pytest.raises(RuntimeError):
            manager._apply_to_node(sample_node, config_yaml)

    def test_export_current_config(self, app_context, db_session, sample_node, mock_httpx):
        """Test exporting current config."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'paths': {'test': {}}}
        mock_httpx['get'].return_value = mock_response

        manager = ConfigManager()
        result = manager.export_current_config(sample_node)

        assert result['success'] is True
        assert 'config_yaml' in result
        assert 'config_hash' in result

    def test_export_current_config_failure(self, app_context, db_session, sample_node, mock_httpx):
        """Test exporting config with failure."""
        mock_httpx['get'].side_effect = Exception('Connection refused')

        manager = ConfigManager()
        result = manager.export_current_config(sample_node)

        assert result['success'] is False

    def test_get_environment_config_default(self, app_context):
        """Test getting environment config defaults."""
        manager = ConfigManager()
        result = manager.get_environment_config('development')

        assert result['logLevel'] == 'debug'

    def test_env_defaults(self, app_context):
        """Test environment defaults are set correctly."""
        manager = ConfigManager()

        assert manager.ENV_DEFAULTS['development']['logLevel'] == 'debug'
        assert manager.ENV_DEFAULTS['staging']['logLevel'] == 'info'
        assert manager.ENV_DEFAULTS['production']['logLevel'] == 'warn'

    def test_required_fields(self, app_context):
        """Test required fields constant."""
        manager = ConfigManager()

        assert 'paths' in manager.REQUIRED_FIELDS

    def test_validate_path_invalid_run_on_ready(self, app_context):
        """Test validating path with invalid runOnReady."""
        config_yaml = """
paths:
  test/stream:
    runOnReady:
      - command1
"""
        manager = ConfigManager()
        result = manager.validate(config_yaml)

        assert result['valid'] is False
        assert any('runOnReady must be a string' in error for error in result['errors'])

    def test_validate_path_config_not_dict(self, app_context):
        """Test validating path config that's not a dict."""
        config_yaml = """
paths:
  test/stream: "not a dict"
"""
        manager = ConfigManager()
        result = manager.validate(config_yaml)

        assert result['valid'] is False
        assert any('must be a mapping' in error for error in result['errors'])

    def test_apply_creates_backup(self, app_context, db_session, sample_node, mock_httpx):
        """Test that apply creates a backup snapshot."""
        # Mock fetch current config
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = {'paths': {'old': {}}}
        mock_httpx['get'].return_value = mock_get

        # Mock apply
        mock_patch = MagicMock()
        mock_patch.status_code = 200
        mock_httpx['patch'].return_value = mock_patch

        initial_count = ConfigSnapshot.query.count()

        new_config = """
paths:
  new: {}
"""
        manager = ConfigManager()
        result = manager.apply(sample_node.id, new_config)

        assert result['success'] is True
        # Should have created 2 snapshots (backup + new)
        assert ConfigSnapshot.query.count() >= initial_count + 2
