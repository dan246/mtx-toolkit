"""
Recording and retention management API endpoints.
"""
from flask import Blueprint, jsonify, request, send_file
from app import db
from app.models import Recording, Stream
from app.services.retention_manager import RetentionManager
from datetime import datetime

recordings_bp = Blueprint('recordings', __name__)
retention_mgr = RetentionManager()


@recordings_bp.route('/', methods=['GET'])
def list_recordings():
    """List recordings with filtering."""
    stream_id = request.args.get('stream_id', type=int)
    segment_type = request.args.get('segment_type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = Recording.query

    if stream_id:
        query = query.filter_by(stream_id=stream_id)
    if segment_type:
        query = query.filter_by(segment_type=segment_type)
    if start_date:
        query = query.filter(Recording.start_time >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.filter(Recording.end_time <= datetime.fromisoformat(end_date))

    pagination = query.order_by(Recording.start_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "recordings": [{
            "id": r.id,
            "stream_id": r.stream_id,
            "file_path": r.file_path,
            "file_size": r.file_size,
            "duration_seconds": r.duration_seconds,
            "start_time": r.start_time.isoformat(),
            "end_time": r.end_time.isoformat() if r.end_time else None,
            "segment_type": r.segment_type,
            "is_archived": r.is_archived,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None
        } for r in pagination.items],
        "total": pagination.total,
        "page": page,
        "pages": pagination.pages
    })


@recordings_bp.route('/<int:recording_id>', methods=['GET'])
def get_recording(recording_id: int):
    """Get recording details."""
    recording = Recording.query.get_or_404(recording_id)

    return jsonify({
        "id": recording.id,
        "stream_id": recording.stream_id,
        "stream_path": recording.stream.path if recording.stream else None,
        "file_path": recording.file_path,
        "file_size": recording.file_size,
        "duration_seconds": recording.duration_seconds,
        "start_time": recording.start_time.isoformat(),
        "end_time": recording.end_time.isoformat() if recording.end_time else None,
        "segment_type": recording.segment_type,
        "triggered_by_event_id": recording.triggered_by_event_id,
        "retention_days": recording.retention_days,
        "expires_at": recording.expires_at.isoformat() if recording.expires_at else None,
        "is_archived": recording.is_archived,
        "archive_path": recording.archive_path,
        "created_at": recording.created_at.isoformat()
    })


@recordings_bp.route('/<int:recording_id>/download', methods=['GET'])
def download_recording(recording_id: int):
    """Download a recording file."""
    recording = Recording.query.get_or_404(recording_id)
    return send_file(recording.file_path, as_attachment=True)


@recordings_bp.route('/<int:recording_id>/archive', methods=['POST'])
def archive_recording(recording_id: int):
    """Archive a recording to NAS."""
    recording = Recording.query.get_or_404(recording_id)
    result = retention_mgr.archive_recording(recording)
    return jsonify(result)


@recordings_bp.route('/retention/status', methods=['GET'])
def retention_status():
    """Get retention and disk usage status."""
    return jsonify(retention_mgr.get_status())


@recordings_bp.route('/retention/cleanup', methods=['POST'])
def trigger_cleanup():
    """Manually trigger retention cleanup."""
    dry_run = request.args.get('dry_run', 'false').lower() == 'true'
    result = retention_mgr.cleanup(dry_run=dry_run)
    return jsonify(result)


@recordings_bp.route('/retention/policy', methods=['GET'])
def get_retention_policy():
    """Get current retention policy."""
    return jsonify(retention_mgr.get_policy())


@recordings_bp.route('/retention/policy', methods=['PUT'])
def update_retention_policy():
    """Update retention policy."""
    data = request.get_json()
    result = retention_mgr.update_policy(data)
    return jsonify(result)


@recordings_bp.route('/search', methods=['GET'])
def search_recordings():
    """Search recordings by time range and stream."""
    stream_path = request.args.get('stream_path')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')

    results = retention_mgr.search_recordings(
        stream_path=stream_path,
        start_time=start_time,
        end_time=end_time
    )

    return jsonify(results)


@recordings_bp.route('/playback/<int:recording_id>', methods=['GET'])
def get_playback_url(recording_id: int):
    """Get a playback URL for a recording."""
    recording = Recording.query.get_or_404(recording_id)
    result = retention_mgr.get_playback_url(recording)
    return jsonify(result)
