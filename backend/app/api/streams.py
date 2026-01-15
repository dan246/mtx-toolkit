"""
Streams management API endpoints.
"""
from flask import Blueprint, jsonify, request
from app import db
from app.models import Stream, MediaMTXNode, StreamStatus

streams_bp = Blueprint('streams', __name__)


@streams_bp.route('/', methods=['GET'])
def list_streams():
    """List all monitored streams."""
    node_id = request.args.get('node_id', type=int)
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = Stream.query
    if node_id:
        query = query.filter_by(node_id=node_id)
    if status:
        query = query.filter_by(status=status)

    pagination = query.order_by(Stream.path).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "streams": [{
            "id": s.id,
            "node_id": s.node_id,
            "path": s.path,
            "name": s.name,
            "source_url": s.source_url,
            "protocol": s.protocol,
            "status": s.status,
            "fps": s.fps,
            "bitrate": s.bitrate,
            "latency_ms": s.latency_ms,
            "auto_remediate": s.auto_remediate,
            "recording_enabled": s.recording_enabled,
            "last_check": s.last_check.isoformat() if s.last_check else None
        } for s in pagination.items],
        "total": pagination.total,
        "page": page,
        "pages": pagination.pages
    })


@streams_bp.route('/<int:stream_id>', methods=['GET'])
def get_stream(stream_id: int):
    """Get stream details."""
    stream = Stream.query.get_or_404(stream_id)
    return jsonify({
        "id": stream.id,
        "node_id": stream.node_id,
        "path": stream.path,
        "name": stream.name,
        "source_url": stream.source_url,
        "protocol": stream.protocol,
        "status": stream.status,
        "fps": stream.fps,
        "bitrate": stream.bitrate,
        "latency_ms": stream.latency_ms,
        "keyframe_interval": stream.keyframe_interval,
        "auto_remediate": stream.auto_remediate,
        "remediation_count": stream.remediation_count,
        "last_remediation": stream.last_remediation.isoformat() if stream.last_remediation else None,
        "recording_enabled": stream.recording_enabled,
        "last_check": stream.last_check.isoformat() if stream.last_check else None,
        "created_at": stream.created_at.isoformat(),
        "updated_at": stream.updated_at.isoformat()
    })


@streams_bp.route('/', methods=['POST'])
def create_stream():
    """Create a new stream to monitor."""
    data = request.get_json()

    # Validate node exists
    node = MediaMTXNode.query.get(data.get('node_id'))
    if not node:
        return jsonify({"error": "Node not found"}), 404

    stream = Stream(
        node_id=data['node_id'],
        path=data['path'],
        name=data.get('name'),
        source_url=data.get('source_url'),
        protocol=data.get('protocol', 'rtsp'),
        auto_remediate=data.get('auto_remediate', True),
        recording_enabled=data.get('recording_enabled', False)
    )

    db.session.add(stream)
    db.session.commit()

    return jsonify({"id": stream.id, "message": "Stream created"}), 201


@streams_bp.route('/<int:stream_id>', methods=['PUT'])
def update_stream(stream_id: int):
    """Update stream configuration."""
    stream = Stream.query.get_or_404(stream_id)
    data = request.get_json()

    for field in ['name', 'source_url', 'protocol', 'auto_remediate', 'recording_enabled']:
        if field in data:
            setattr(stream, field, data[field])

    db.session.commit()
    return jsonify({"message": "Stream updated"})


@streams_bp.route('/<int:stream_id>', methods=['DELETE'])
def delete_stream(stream_id: int):
    """Delete a stream from monitoring."""
    stream = Stream.query.get_or_404(stream_id)
    db.session.delete(stream)
    db.session.commit()
    return jsonify({"message": "Stream deleted"})


@streams_bp.route('/<int:stream_id>/remediate', methods=['POST'])
def trigger_remediation(stream_id: int):
    """Manually trigger remediation for a stream."""
    from app.services.auto_remediation import AutoRemediation

    stream = Stream.query.get_or_404(stream_id)
    remediation = AutoRemediation()
    result = remediation.remediate_stream(stream)

    return jsonify(result)
