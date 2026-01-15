"""
Config-as-Code Manager.
Terraform-like plan/apply workflow with validation, backup, and rollback.
"""
import yaml
import hashlib
import difflib
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import httpx

from flask import current_app
from app import db
from app.models import ConfigSnapshot, MediaMTXNode


class ConfigValidationError(Exception):
    """Raised when config validation fails."""
    pass


class ConfigManager:
    """
    Config-as-Code manager for MediaMTX configurations.

    Features:
    - Plan: Show diff before applying
    - Validate: Check config syntax and semantics
    - Apply: Apply config with automatic backup
    - Rollback: Revert to previous config
    """

    # Required fields in MediaMTX config
    REQUIRED_FIELDS = ['paths']

    # Environment-specific config overrides
    ENV_DEFAULTS = {
        'development': {
            'logLevel': 'debug',
            'metrics': True,
            'metricsAddress': ':9998'
        },
        'staging': {
            'logLevel': 'info',
            'metrics': True,
            'metricsAddress': ':9998'
        },
        'production': {
            'logLevel': 'warn',
            'metrics': True,
            'metricsAddress': ':9998'
        }
    }

    def __init__(self):
        self.configs_path = Path(current_app.config.get('CONFIGS_PATH', '/configs')) if current_app else Path('/configs')

    def validate(self, config_yaml: str) -> Dict[str, Any]:
        """
        Validate a MediaMTX configuration.
        Returns validation result with any errors/warnings.
        """
        errors = []
        warnings = []

        try:
            config = yaml.safe_load(config_yaml)
        except yaml.YAMLError as e:
            return {
                "valid": False,
                "errors": [f"YAML parse error: {str(e)}"],
                "warnings": []
            }

        if not isinstance(config, dict):
            return {
                "valid": False,
                "errors": ["Config must be a YAML mapping"],
                "warnings": []
            }

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in config:
                errors.append(f"Missing required field: {field}")

        # Validate paths
        if 'paths' in config:
            paths = config['paths']
            if not isinstance(paths, dict):
                errors.append("'paths' must be a mapping")
            else:
                for path_name, path_config in paths.items():
                    path_errors = self._validate_path(path_name, path_config)
                    errors.extend(path_errors)

        # Check for common issues
        if config.get('readTimeout') and config.get('readTimeout') < 5:
            warnings.append("readTimeout is very low, may cause connection issues")

        if config.get('writeTimeout') and config.get('writeTimeout') < 5:
            warnings.append("writeTimeout is very low, may cause connection issues")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "config_hash": self._hash_config(config_yaml)
        }

    def _validate_path(self, path_name: str, path_config: Dict) -> List[str]:
        """Validate a single path configuration."""
        errors = []

        if not path_config:
            return errors  # Empty path config is valid (uses defaults)

        if not isinstance(path_config, dict):
            errors.append(f"Path '{path_name}' config must be a mapping")
            return errors

        # Validate source URL if present
        source = path_config.get('source')
        if source and not isinstance(source, str):
            errors.append(f"Path '{path_name}': source must be a string")

        # Validate runOnReady if present
        run_on_ready = path_config.get('runOnReady')
        if run_on_ready and not isinstance(run_on_ready, str):
            errors.append(f"Path '{path_name}': runOnReady must be a string")

        return errors

    def _hash_config(self, config_yaml: str) -> str:
        """Generate a hash of the config for comparison."""
        # Normalize YAML to ensure consistent hashing
        config = yaml.safe_load(config_yaml)
        normalized = yaml.dump(config, sort_keys=True)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def diff(self, old_config: str, new_config: str) -> Dict[str, Any]:
        """
        Generate a diff between two configs.
        Returns unified diff and structured changes.
        """
        try:
            old_yaml = yaml.safe_load(old_config) if old_config else {}
            new_yaml = yaml.safe_load(new_config)
        except yaml.YAMLError as e:
            return {"error": f"YAML parse error: {str(e)}"}

        # Generate unified diff
        old_lines = yaml.dump(old_yaml, sort_keys=True).splitlines(keepends=True)
        new_lines = yaml.dump(new_yaml, sort_keys=True).splitlines(keepends=True)

        unified_diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile='current', tofile='proposed',
            lineterm=''
        ))

        # Analyze structural changes
        changes = self._analyze_changes(old_yaml, new_yaml)

        return {
            "has_changes": len(unified_diff) > 0,
            "unified_diff": ''.join(unified_diff),
            "changes": changes,
            "old_hash": self._hash_config(old_config) if old_config else None,
            "new_hash": self._hash_config(new_config)
        }

    def _analyze_changes(self, old: Dict, new: Dict, path: str = "") -> List[Dict]:
        """Analyze structural changes between two configs."""
        changes = []

        all_keys = set(old.keys()) | set(new.keys())

        for key in all_keys:
            current_path = f"{path}.{key}" if path else key
            old_val = old.get(key)
            new_val = new.get(key)

            if key not in old:
                changes.append({
                    "type": "added",
                    "path": current_path,
                    "value": new_val
                })
            elif key not in new:
                changes.append({
                    "type": "removed",
                    "path": current_path,
                    "value": old_val
                })
            elif old_val != new_val:
                if isinstance(old_val, dict) and isinstance(new_val, dict):
                    changes.extend(self._analyze_changes(old_val, new_val, current_path))
                else:
                    changes.append({
                        "type": "modified",
                        "path": current_path,
                        "old_value": old_val,
                        "new_value": new_val
                    })

        return changes

    def plan(
        self,
        node_id: Optional[int],
        new_config_yaml: str,
        environment: str = None
    ) -> Dict[str, Any]:
        """
        Plan a config change without applying.
        Shows what would change.
        """
        # Validate new config
        validation = self.validate(new_config_yaml)
        if not validation['valid']:
            return {
                "can_apply": False,
                "validation": validation,
                "error": "Config validation failed"
            }

        # Get current config
        current_config = None
        if node_id:
            node = MediaMTXNode.query.get(node_id)
            if node:
                current_config = self._fetch_current_config(node)

        # Generate diff
        diff_result = self.diff(current_config, new_config_yaml)

        return {
            "can_apply": True,
            "validation": validation,
            "diff": diff_result,
            "environment": environment,
            "summary": f"{len(diff_result['changes'])} change(s) to apply"
        }

    def apply(
        self,
        node_id: Optional[int],
        new_config_yaml: str,
        environment: str = None,
        notes: str = None,
        applied_by: str = "api"
    ) -> Dict[str, Any]:
        """
        Apply a config change with backup and rollback capability.
        """
        # First, plan to validate
        plan_result = self.plan(node_id, new_config_yaml, environment)
        if not plan_result['can_apply']:
            return {
                "success": False,
                "error": "Validation failed",
                "details": plan_result
            }

        # Get current config for backup
        current_config = None
        node = None
        if node_id:
            node = MediaMTXNode.query.get(node_id)
            if node:
                current_config = self._fetch_current_config(node)

        # Create backup snapshot
        if current_config:
            backup = ConfigSnapshot(
                node_id=node_id,
                config_hash=self._hash_config(current_config),
                config_yaml=current_config,
                environment=environment,
                applied=True,
                applied_at=datetime.utcnow(),
                notes="Auto-backup before apply"
            )
            db.session.add(backup)
            db.session.flush()

        # Try to apply
        try:
            if node:
                self._apply_to_node(node, new_config_yaml)

            # Create new snapshot
            snapshot = ConfigSnapshot(
                node_id=node_id,
                config_hash=plan_result['validation']['config_hash'],
                config_yaml=new_config_yaml,
                environment=environment,
                applied=True,
                applied_at=datetime.utcnow(),
                applied_by=applied_by,
                notes=notes
            )
            db.session.add(snapshot)
            db.session.commit()

            return {
                "success": True,
                "snapshot_id": snapshot.id,
                "changes_applied": len(plan_result['diff']['changes']),
                "backup_id": backup.id if current_config else None
            }

        except Exception as e:
            # Rollback on failure
            db.session.rollback()

            if current_config and node:
                try:
                    self._apply_to_node(node, current_config)
                except Exception:
                    pass  # Best effort rollback

            return {
                "success": False,
                "error": str(e),
                "rolled_back": True if current_config else False
            }

    def rollback(self, snapshot_id: int, applied_by: str = "api") -> Dict[str, Any]:
        """Rollback to a previous config snapshot."""
        snapshot = ConfigSnapshot.query.get(snapshot_id)
        if not snapshot:
            return {"success": False, "error": "Snapshot not found"}

        return self.apply(
            node_id=snapshot.node_id,
            new_config_yaml=snapshot.config_yaml,
            environment=snapshot.environment,
            notes=f"Rollback to snapshot {snapshot_id}",
            applied_by=applied_by
        )

    def _fetch_current_config(self, node: MediaMTXNode) -> Optional[str]:
        """Fetch current config from a MediaMTX node."""
        try:
            response = httpx.get(f"{node.api_url}/v3/config/global/get", timeout=10)
            if response.status_code == 200:
                return yaml.dump(response.json())
        except Exception:
            pass
        return None

    def _apply_to_node(self, node: MediaMTXNode, config_yaml: str):
        """Apply config to a MediaMTX node."""
        config = yaml.safe_load(config_yaml)

        # Apply global config
        response = httpx.patch(
            f"{node.api_url}/v3/config/global/patch",
            json=config,
            timeout=30
        )

        if response.status_code not in [200, 204]:
            raise RuntimeError(f"Failed to apply config: HTTP {response.status_code}")

    def export_current_config(self, node: MediaMTXNode) -> Dict[str, Any]:
        """Export current config from a node."""
        config = self._fetch_current_config(node)
        if config:
            return {
                "success": True,
                "config_yaml": config,
                "config_hash": self._hash_config(config),
                "exported_at": datetime.utcnow().isoformat()
            }
        return {"success": False, "error": "Failed to fetch config"}

    def get_environment_config(self, environment: str) -> Dict[str, Any]:
        """Get config template for an environment."""
        config_file = self.configs_path / environment / 'mediamtx.yml'
        if config_file.exists():
            with open(config_file) as f:
                return yaml.safe_load(f)
        return self.ENV_DEFAULTS.get(environment, {})
