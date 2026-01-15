"""
Fleet management API endpoints.
Multi-node MediaMTX management.
"""
from flask import Blueprint, jsonify, request
from app import db
from app.models import MediaMTXNode, Stream
from datetime import datetime

fleet_bp = Blueprint('fleet', __name__)


@fleet_bp.route('/nodes', methods=['GET'])
def list_nodes():
    """List all MediaMTX nodes in the fleet."""
    environment = request.args.get('environment')
    active_only = request.args.get('active_only', 'true').lower() == 'true'

    query = MediaMTXNode.query
    if environment:
        query = query.filter_by(environment=environment)
    if active_only:
        query = query.filter_by(is_active=True)

    nodes = query.all()

    return jsonify({
        "nodes": [{
            "id": n.id,
            "name": n.name,
            "api_url": n.api_url,
            "environment": n.environment,
            "is_active": n.is_active,
            "last_seen": n.last_seen.isoformat() if n.last_seen else None,
            "stream_count": n.streams.count(),
            "healthy_streams": n.streams.filter_by(status='healthy').count(),
            "unhealthy_streams": n.streams.filter_by(status='unhealthy').count()
        } for n in nodes],
        "total": len(nodes)
    })


@fleet_bp.route('/nodes/<int:node_id>', methods=['GET'])
def get_node(node_id: int):
    """Get node details."""
    node = MediaMTXNode.query.get_or_404(node_id)

    return jsonify({
        "id": node.id,
        "name": node.name,
        "api_url": node.api_url,
        "environment": node.environment,
        "is_active": node.is_active,
        "last_seen": node.last_seen.isoformat() if node.last_seen else None,
        "metadata": node.metadata_json,
        "stream_count": node.streams.count(),
        "streams_by_status": {
            "healthy": node.streams.filter_by(status='healthy').count(),
            "degraded": node.streams.filter_by(status='degraded').count(),
            "unhealthy": node.streams.filter_by(status='unhealthy').count(),
            "unknown": node.streams.filter_by(status='unknown').count()
        },
        "created_at": node.created_at.isoformat(),
        "updated_at": node.updated_at.isoformat()
    })


@fleet_bp.route('/nodes', methods=['POST'])
def create_node():
    """Add a new MediaMTX node to the fleet."""
    data = request.get_json()

    node = MediaMTXNode(
        name=data['name'],
        api_url=data['api_url'],
        environment=data.get('environment', 'production'),
        is_active=data.get('is_active', True),
        metadata_json=data.get('metadata')
    )

    db.session.add(node)
    db.session.commit()

    return jsonify({"id": node.id, "message": "Node added to fleet"}), 201


@fleet_bp.route('/nodes/<int:node_id>', methods=['PUT'])
def update_node(node_id: int):
    """Update node configuration."""
    node = MediaMTXNode.query.get_or_404(node_id)
    data = request.get_json()

    for field in ['name', 'api_url', 'environment', 'is_active', 'metadata_json']:
        if field in data:
            setattr(node, field, data[field])

    db.session.commit()
    return jsonify({"message": "Node updated"})


@fleet_bp.route('/nodes/<int:node_id>', methods=['DELETE'])
def delete_node(node_id: int):
    """Remove a node from the fleet."""
    node = MediaMTXNode.query.get_or_404(node_id)
    db.session.delete(node)
    db.session.commit()
    return jsonify({"message": "Node removed from fleet"})


@fleet_bp.route('/nodes/<int:node_id>/sync', methods=['POST'])
def sync_node(node_id: int):
    """Sync streams from a MediaMTX node."""
    from app.services.fleet_manager import FleetManager

    node = MediaMTXNode.query.get_or_404(node_id)
    manager = FleetManager()
    result = manager.sync_node_streams(node)

    return jsonify(result)


@fleet_bp.route('/sync-all', methods=['POST'])
def sync_all_nodes():
    """Sync streams from all active nodes."""
    from app.services.fleet_manager import FleetManager

    manager = FleetManager()
    results = manager.sync_all_nodes()

    return jsonify(results)


@fleet_bp.route('/rolling-update', methods=['POST'])
def rolling_update():
    """Perform a rolling config update across fleet."""
    from app.services.fleet_manager import FleetManager

    data = request.get_json()
    environment = data.get('environment')
    config_snapshot_id = data.get('config_snapshot_id')

    manager = FleetManager()
    result = manager.rolling_update(
        environment=environment,
        config_snapshot_id=config_snapshot_id
    )

    return jsonify(result)


@fleet_bp.route('/overview', methods=['GET'])
def fleet_overview():
    """Get fleet-wide overview statistics."""
    nodes = MediaMTXNode.query.filter_by(is_active=True).all()

    total_streams = 0
    healthy_streams = 0
    unhealthy_streams = 0
    total_events_today = 0

    for node in nodes:
        total_streams += node.streams.count()
        healthy_streams += node.streams.filter_by(status='healthy').count()
        unhealthy_streams += node.streams.filter_by(status='unhealthy').count()

    return jsonify({
        "nodes": {
            "total": len(nodes),
            "by_environment": {
                "production": sum(1 for n in nodes if n.environment == 'production'),
                "staging": sum(1 for n in nodes if n.environment == 'staging'),
                "development": sum(1 for n in nodes if n.environment == 'development')
            }
        },
        "streams": {
            "total": total_streams,
            "healthy": healthy_streams,
            "unhealthy": unhealthy_streams,
            "health_percentage": round(healthy_streams / total_streams * 100, 1) if total_streams > 0 else 0
        }
    })
