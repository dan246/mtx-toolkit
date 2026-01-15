"""
Config-as-Code API endpoints.
Terraform-like plan/apply workflow.
"""
from flask import Blueprint, jsonify, request
from app import db
from app.models import ConfigSnapshot, MediaMTXNode
from app.services.config_manager import ConfigManager

config_bp = Blueprint('config', __name__)
manager = ConfigManager()


@config_bp.route('/snapshots', methods=['GET'])
def list_snapshots():
    """List config snapshots."""
    node_id = request.args.get('node_id', type=int)
    environment = request.args.get('environment')
    limit = request.args.get('limit', 20, type=int)

    query = ConfigSnapshot.query
    if node_id:
        query = query.filter_by(node_id=node_id)
    if environment:
        query = query.filter_by(environment=environment)

    snapshots = query.order_by(ConfigSnapshot.created_at.desc()).limit(limit).all()

    return jsonify({
        "snapshots": [{
            "id": s.id,
            "node_id": s.node_id,
            "config_hash": s.config_hash,
            "environment": s.environment,
            "applied": s.applied,
            "applied_at": s.applied_at.isoformat() if s.applied_at else None,
            "applied_by": s.applied_by,
            "notes": s.notes,
            "created_at": s.created_at.isoformat()
        } for s in snapshots]
    })


@config_bp.route('/snapshots/<int:snapshot_id>', methods=['GET'])
def get_snapshot(snapshot_id: int):
    """Get a specific config snapshot."""
    snapshot = ConfigSnapshot.query.get_or_404(snapshot_id)

    return jsonify({
        "id": snapshot.id,
        "node_id": snapshot.node_id,
        "config_hash": snapshot.config_hash,
        "config_yaml": snapshot.config_yaml,
        "environment": snapshot.environment,
        "applied": snapshot.applied,
        "applied_at": snapshot.applied_at.isoformat() if snapshot.applied_at else None,
        "applied_by": snapshot.applied_by,
        "rollback_of": snapshot.rollback_of,
        "notes": snapshot.notes,
        "created_at": snapshot.created_at.isoformat()
    })


@config_bp.route('/plan', methods=['POST'])
def plan_config():
    """
    Plan a config change (like terraform plan).
    Shows diff without applying.
    """
    data = request.get_json()
    node_id = data.get('node_id')
    new_config_yaml = data.get('config_yaml')
    environment = data.get('environment')

    result = manager.plan(
        node_id=node_id,
        new_config_yaml=new_config_yaml,
        environment=environment
    )

    return jsonify(result)


@config_bp.route('/apply', methods=['POST'])
def apply_config():
    """
    Apply a planned config change.
    Creates backup, validates, applies, and rolls back on failure.
    """
    data = request.get_json()
    node_id = data.get('node_id')
    new_config_yaml = data.get('config_yaml')
    environment = data.get('environment')
    notes = data.get('notes')
    applied_by = data.get('applied_by', 'api')

    result = manager.apply(
        node_id=node_id,
        new_config_yaml=new_config_yaml,
        environment=environment,
        notes=notes,
        applied_by=applied_by
    )

    return jsonify(result)


@config_bp.route('/rollback', methods=['POST'])
def rollback_config():
    """Rollback to a previous config snapshot."""
    data = request.get_json()
    snapshot_id = data.get('snapshot_id')
    applied_by = data.get('applied_by', 'api')

    result = manager.rollback(
        snapshot_id=snapshot_id,
        applied_by=applied_by
    )

    return jsonify(result)


@config_bp.route('/validate', methods=['POST'])
def validate_config():
    """Validate a config without planning or applying."""
    data = request.get_json()
    config_yaml = data.get('config_yaml')

    result = manager.validate(config_yaml)
    return jsonify(result)


@config_bp.route('/diff', methods=['POST'])
def diff_configs():
    """Show diff between two configs."""
    data = request.get_json()
    old_config = data.get('old_config')
    new_config = data.get('new_config')

    result = manager.diff(old_config, new_config)
    return jsonify(result)


@config_bp.route('/export/<int:node_id>', methods=['GET'])
def export_config(node_id: int):
    """Export current config from a node."""
    node = MediaMTXNode.query.get_or_404(node_id)
    result = manager.export_current_config(node)
    return jsonify(result)


@config_bp.route('/environments', methods=['GET'])
def list_environments():
    """List available environments and their configs."""
    return jsonify({
        "environments": ["development", "staging", "production"],
        "configs": {
            "development": manager.get_environment_config("development"),
            "staging": manager.get_environment_config("staging"),
            "production": manager.get_environment_config("production")
        }
    })
