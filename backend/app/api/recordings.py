"""
Recording and retention management API endpoints.
"""

import os
import re
import subprocess
from datetime import datetime

from flask import Blueprint, Response, jsonify, request, send_file

from app import db
from app.models import Recording, Stream
from app.services.retention_manager import RetentionManager

recordings_bp = Blueprint("recordings", __name__)
retention_mgr = RetentionManager()


@recordings_bp.route("/", methods=["GET"])
def list_recordings():
    """List recordings with filtering and search."""
    stream_id = request.args.get("stream_id", type=int)
    segment_type = request.args.get("segment_type")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    search = request.args.get("search")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    query = Recording.query

    if stream_id:
        query = query.filter_by(stream_id=stream_id)
    if segment_type:
        query = query.filter_by(segment_type=segment_type)
    if start_date:
        query = query.filter(Recording.start_time >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.filter(Recording.end_time <= datetime.fromisoformat(end_date))
    if search:
        # Search in file_path and join with Stream to search stream path
        query = query.outerjoin(Stream).filter(
            db.or_(
                Recording.file_path.ilike(f"%{search}%"),
                Stream.path.ilike(f"%{search}%"),
                Stream.name.ilike(f"%{search}%"),
            )
        )

    pagination = query.order_by(Recording.start_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify(
        {
            "recordings": [
                {
                    "id": r.id,
                    "stream_id": r.stream_id,
                    "stream_path": r.stream.path if r.stream else None,
                    "stream_name": r.stream.name if r.stream else None,
                    "file_path": r.file_path,
                    "file_size": r.file_size,
                    "duration_seconds": r.duration_seconds,
                    "start_time": r.start_time.isoformat(),
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "segment_type": r.segment_type,
                    "is_archived": r.is_archived,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                }
                for r in pagination.items
            ],
            "total": pagination.total,
            "page": page,
            "pages": pagination.pages,
        }
    )


@recordings_bp.route("/<int:recording_id>", methods=["GET"])
def get_recording(recording_id: int):
    """Get recording details."""
    recording = Recording.query.get_or_404(recording_id)

    return jsonify(
        {
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
            "expires_at": (
                recording.expires_at.isoformat() if recording.expires_at else None
            ),
            "is_archived": recording.is_archived,
            "archive_path": recording.archive_path,
            "created_at": recording.created_at.isoformat(),
        }
    )


@recordings_bp.route("/<int:recording_id>/download", methods=["GET"])
def download_recording(recording_id: int):
    """Download a recording file."""
    recording = Recording.query.get_or_404(recording_id)
    return send_file(recording.file_path, as_attachment=True)


@recordings_bp.route("/<int:recording_id>/stream", methods=["GET"])
def stream_recording(recording_id: int):
    """
    Stream a recording file with Range request support for seeking.
    """
    recording = Recording.query.get_or_404(recording_id)
    file_path = recording.file_path

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    file_size = os.path.getsize(file_path)

    # Determine MIME type based on extension
    ext = os.path.splitext(file_path)[1].lower()
    mime_types = {
        ".ts": "video/mp2t",
        ".mp4": "video/mp4",
        ".mkv": "video/x-matroska",
        ".flv": "video/x-flv",
        ".webm": "video/webm",
    }
    mime_type = mime_types.get(ext, "video/mp4")

    # Handle Range requests for video seeking
    range_header = request.headers.get("Range")

    if range_header:
        # Parse Range header: bytes=start-end
        match = re.search(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1

            # Limit chunk size to 1MB for streaming
            chunk_size = 1024 * 1024
            if end - start + 1 > chunk_size:
                end = start + chunk_size - 1

            end = min(end, file_size - 1)
            length = end - start + 1

            def generate():
                with open(file_path, "rb") as f:
                    f.seek(start)
                    yield f.read(length)

            response = Response(
                generate(),
                status=206,
                mimetype=mime_type,
                direct_passthrough=True,
            )
            response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            response.headers["Accept-Ranges"] = "bytes"
            response.headers["Content-Length"] = length
            return response

    # No Range header - return full file
    def generate_full():
        chunk_size = 1024 * 1024  # 1MB chunks
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    response = Response(
        generate_full(),
        status=200,
        mimetype=mime_type,
        direct_passthrough=True,
    )
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Content-Length"] = file_size
    return response


@recordings_bp.route("/<int:recording_id>/transcode", methods=["GET"])
def transcode_recording(recording_id: int):
    """
    Transcode recording to MP4 on-the-fly using ffmpeg.
    This allows browsers to play .ts files that they can't natively handle.
    """
    import shutil
    import tempfile

    recording = Recording.query.get_or_404(recording_id)
    file_path = recording.file_path

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    # Create a temporary file for the transcoded output
    # This allows proper MP4 headers with duration metadata
    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(temp_fd)

    try:
        # Transcode to temp file with proper MP4 structure
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            file_path,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            temp_path,
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            os.unlink(temp_path)
            return jsonify({"error": "Transcode failed"}), 500

        # Stream the temp file
        def generate():
            try:
                with open(temp_path, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 256)
                        if not chunk:
                            break
                        yield chunk
            finally:
                # Clean up temp file after streaming
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        file_size = os.path.getsize(temp_path)

        return Response(
            generate(),
            mimetype="video/mp4",
            headers={
                "Content-Disposition": "inline",
                "Content-Length": file_size,
                "Accept-Ranges": "bytes",
            },
        )

    except subprocess.TimeoutExpired:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return jsonify({"error": "Transcode timeout"}), 504
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return jsonify({"error": str(e)}), 500


@recordings_bp.route("/<int:recording_id>/archive", methods=["POST"])
def archive_recording(recording_id: int):
    """Archive a recording to NAS."""
    recording = Recording.query.get_or_404(recording_id)
    result = retention_mgr.archive_recording(recording)
    return jsonify(result)


@recordings_bp.route("/retention/status", methods=["GET"])
def retention_status():
    """Get retention and disk usage status."""
    return jsonify(retention_mgr.get_status())


@recordings_bp.route("/retention/cleanup", methods=["POST"])
def trigger_cleanup():
    """Manually trigger retention cleanup."""
    dry_run = request.args.get("dry_run", "false").lower() == "true"
    result = retention_mgr.cleanup(dry_run=dry_run)
    return jsonify(result)


@recordings_bp.route("/retention/policy", methods=["GET"])
def get_retention_policy():
    """Get current retention policy."""
    return jsonify(retention_mgr.get_policy())


@recordings_bp.route("/retention/policy", methods=["PUT"])
def update_retention_policy():
    """Update retention policy."""
    data = request.get_json()
    result = retention_mgr.update_policy(data)
    return jsonify(result)


@recordings_bp.route("/search", methods=["GET"])
def search_recordings():
    """Search recordings by time range and stream."""
    stream_path = request.args.get("stream_path")
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    results = retention_mgr.search_recordings(
        stream_path=stream_path, start_time=start_time, end_time=end_time
    )

    return jsonify(results)


@recordings_bp.route("/playback/<int:recording_id>", methods=["GET"])
def get_playback_url(recording_id: int):
    """Get a playback URL for a recording."""
    recording = Recording.query.get_or_404(recording_id)
    result = retention_mgr.get_playback_url(recording)
    return jsonify(result)


@recordings_bp.route("/scan", methods=["POST"])
def scan_recordings():
    """
    Scan local recording directory and index files to database.

    Request body:
        node_id (optional): Filter by node ID
        force_rescan (optional): Re-scan and update existing records

    Returns:
        success: Whether scan completed successfully
        stats: Scan statistics (scanned, added, skipped, errors)
    """
    data = request.get_json() or {}
    node_id = data.get("node_id")
    force_rescan = data.get("force_rescan", False)

    result = retention_mgr.scan_recordings(node_id=node_id, force_rescan=force_rescan)
    return jsonify(result)
