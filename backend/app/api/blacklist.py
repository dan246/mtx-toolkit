"""
Blacklist API endpoints.
IP blacklist management for blocking viewers.
"""

from flask import Blueprint, jsonify, request

from app.utils.auth import current_username

blacklist_bp = Blueprint("blacklist", __name__)


@blacklist_bp.route("/", methods=["GET"])
def list_blocked_ips():
    """
    List all blocked IPs.

    Query Parameters:
        page: Page number (default: 1)
        per_page: Items per page (default: 50)

    Returns:
        JSON with blocked IPs list and pagination info
    """
    from app.services.blacklist_manager import BlacklistManager

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    manager = BlacklistManager()
    result = manager.list_blocked_ips(page=page, per_page=per_page)

    return jsonify(result)


@blacklist_bp.route("/stats", methods=["GET"])
def get_stats():
    """
    Get blacklist statistics.

    Returns:
        JSON with total blocked, permanent, and temporary counts
    """
    from app.services.blacklist_manager import BlacklistManager

    manager = BlacklistManager()
    result = manager.get_block_stats()

    return jsonify(result)


@blacklist_bp.route("/block", methods=["POST"])
def block_ip():
    """
    Add an IP to the blacklist.

    Request Body:
        ip_address: The IP address to block (required)
        reason: Reason for blocking
        duration: Block duration ('5m', '15m', '30m', '1h', '6h', '24h', '7d', '30d', 'permanent')
        path_pattern: Optional path pattern to restrict block scope
        node_id: Optional node ID to restrict block to specific node

    Returns:
        JSON with success status and blocked entry info
    """
    from app.services.blacklist_manager import BlacklistManager

    data = request.get_json()
    ip_address = data.get("ip_address")

    if not ip_address:
        return jsonify({"success": False, "error": "ip_address is required"}), 400

    manager = BlacklistManager()
    result = manager.block_ip(
        ip_address=ip_address,
        reason=data.get("reason"),
        blocked_by=data.get("blocked_by") or current_username("manual"),
        duration=data.get("duration", "1h"),
        path_pattern=data.get("path_pattern"),
        node_id=data.get("node_id"),
    )

    return jsonify(result)


@blacklist_bp.route("/unblock/<int:entry_id>", methods=["POST"])
def unblock_by_id(entry_id: int):
    """
    Remove an IP from the blacklist by entry ID.

    Args:
        entry_id: The blacklist entry ID

    Returns:
        JSON with success status
    """
    from app.services.blacklist_manager import BlacklistManager

    manager = BlacklistManager()
    result = manager.unblock_ip(entry_id)

    return jsonify(result)


@blacklist_bp.route("/unblock", methods=["POST"])
def unblock_by_ip():
    """
    Remove an IP from the blacklist by IP address.

    Request Body:
        ip_address: The IP address to unblock (required)
        path_pattern: Optional path pattern scope
        node_id: Optional node ID scope

    Returns:
        JSON with success status
    """
    from app.services.blacklist_manager import BlacklistManager

    data = request.get_json()
    ip_address = data.get("ip_address")

    if not ip_address:
        return jsonify({"success": False, "error": "ip_address is required"}), 400

    manager = BlacklistManager()
    result = manager.unblock_ip_by_address(
        ip_address=ip_address,
        path_pattern=data.get("path_pattern"),
        node_id=data.get("node_id"),
    )

    return jsonify(result)


@blacklist_bp.route("/check", methods=["POST"])
def check_ip():
    """
    Check if an IP is blocked.

    Request Body:
        ip_address: The IP address to check (required)
        path: Optional path to check against path patterns
        node_id: Optional node ID to check against node scope

    Returns:
        JSON with blocked status and matching entry if blocked
    """
    from app.services.blacklist_manager import BlacklistManager

    data = request.get_json()
    ip_address = data.get("ip_address")

    if not ip_address:
        return jsonify({"success": False, "error": "ip_address is required"}), 400

    manager = BlacklistManager()
    result = manager.is_ip_blocked(
        ip_address=ip_address,
        path=data.get("path"),
        node_id=data.get("node_id"),
    )

    return jsonify(result)
