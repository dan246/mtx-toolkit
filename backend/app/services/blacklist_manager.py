"""
Blacklist Manager Service.
Manages IP blacklist for recording blocked viewers.
Note: This is for record-keeping only, does not prevent reconnection.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app import db
from app.models import IPBlacklist

logger = logging.getLogger(__name__)


class BlacklistManager:
    """
    IP Blacklist management for blocking viewers.

    Features:
    - Add/remove IPs from blacklist
    - Temporary and permanent blocking
    - Scope blocking by path or node
    - Check if IP is blocked
    """

    # Predefined block durations
    BLOCK_DURATIONS = {
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
        "permanent": None,
    }

    def block_ip(
        self,
        ip_address: str,
        reason: Optional[str] = None,
        blocked_by: Optional[str] = None,
        duration: str = "1h",
        path_pattern: Optional[str] = None,
        node_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Add an IP to the blacklist.

        Args:
            ip_address: The IP address to block
            reason: Reason for blocking
            blocked_by: Who is blocking this IP
            duration: Block duration ('5m', '15m', '30m', '1h', '6h', '24h', '7d', '30d', 'permanent')
            path_pattern: Optional path pattern to restrict block scope
            node_id: Optional node ID to restrict block to specific node

        Returns:
            Dict with success status and blocked entry info
        """
        # Check if already blocked
        existing = self._find_existing_block(ip_address, path_pattern, node_id)
        if existing:
            # Update existing block
            return self._update_block(existing, reason, blocked_by, duration)

        # Calculate expiration
        is_permanent = duration == "permanent"
        expires_at = None
        if not is_permanent:
            delta = self.BLOCK_DURATIONS.get(duration, timedelta(hours=1))
            expires_at = datetime.utcnow() + delta

        # Create new block entry
        entry = IPBlacklist(
            ip_address=ip_address,
            reason=reason,
            blocked_by=blocked_by,
            path_pattern=path_pattern,
            node_id=node_id,
            is_permanent=is_permanent,
            expires_at=expires_at,
            is_active=True,
        )

        db.session.add(entry)
        db.session.commit()

        return {
            "success": True,
            "message": f"IP {ip_address} blocked successfully",
            "entry": self._entry_to_dict(entry),
        }

    def _find_existing_block(
        self,
        ip_address: str,
        path_pattern: Optional[str],
        node_id: Optional[int],
    ) -> Optional[IPBlacklist]:
        """Find existing block for same IP and scope."""
        query = IPBlacklist.query.filter_by(
            ip_address=ip_address,
            is_active=True,
        )

        if path_pattern:
            query = query.filter_by(path_pattern=path_pattern)
        else:
            query = query.filter(IPBlacklist.path_pattern.is_(None))

        if node_id:
            query = query.filter_by(node_id=node_id)
        else:
            query = query.filter(IPBlacklist.node_id.is_(None))

        return query.first()

    def _update_block(
        self,
        entry: IPBlacklist,
        reason: Optional[str],
        blocked_by: Optional[str],
        duration: str,
    ) -> Dict[str, Any]:
        """Update existing block entry."""
        if reason:
            entry.reason = reason
        if blocked_by:
            entry.blocked_by = blocked_by

        is_permanent = duration == "permanent"
        entry.is_permanent = is_permanent

        if is_permanent:
            entry.expires_at = None
        else:
            delta = self.BLOCK_DURATIONS.get(duration, timedelta(hours=1))
            entry.expires_at = datetime.utcnow() + delta

        db.session.commit()

        return {
            "success": True,
            "message": f"Block for IP {entry.ip_address} updated",
            "entry": self._entry_to_dict(entry),
        }

    def unblock_ip(self, entry_id: int) -> Dict[str, Any]:
        """
        Remove an IP from the blacklist by entry ID.

        Args:
            entry_id: The blacklist entry ID

        Returns:
            Dict with success status
        """
        entry = IPBlacklist.query.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}

        ip_address = entry.ip_address
        entry.is_active = False
        db.session.commit()

        return {
            "success": True,
            "message": f"IP {ip_address} unblocked successfully",
        }

    def unblock_ip_by_address(
        self,
        ip_address: str,
        path_pattern: Optional[str] = None,
        node_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Remove an IP from the blacklist by IP address.

        Args:
            ip_address: The IP address to unblock
            path_pattern: Optional path pattern scope
            node_id: Optional node ID scope

        Returns:
            Dict with success status and count of unblocked entries
        """
        query = IPBlacklist.query.filter_by(
            ip_address=ip_address,
            is_active=True,
        )

        if path_pattern:
            query = query.filter_by(path_pattern=path_pattern)
        if node_id:
            query = query.filter_by(node_id=node_id)

        entries = query.all()
        count = len(entries)

        for entry in entries:
            entry.is_active = False

        db.session.commit()

        return {
            "success": True,
            "message": f"Unblocked {count} entries for IP {ip_address}",
            "count": count,
        }

    def is_ip_blocked(
        self,
        ip_address: str,
        path: Optional[str] = None,
        node_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Check if an IP is blocked.

        Args:
            ip_address: The IP address to check
            path: Optional path to check against path patterns
            node_id: Optional node ID to check against node scope

        Returns:
            Dict with blocked status and matching entry if blocked
        """
        # Clean up expired entries first
        self._cleanup_expired()

        # Check for blocks
        query = IPBlacklist.query.filter_by(
            ip_address=ip_address,
            is_active=True,
        )

        entries = query.all()

        for entry in entries:
            # Check if this entry applies
            if self._entry_applies(entry, path, node_id):
                return {
                    "blocked": True,
                    "entry": self._entry_to_dict(entry),
                }

        return {"blocked": False}

    def _entry_applies(
        self,
        entry: IPBlacklist,
        path: Optional[str],
        node_id: Optional[int],
    ) -> bool:
        """Check if a blacklist entry applies to the given path and node."""
        # Check node scope
        if entry.node_id is not None:
            if node_id is None or entry.node_id != node_id:
                return False

        # Check path pattern
        if entry.path_pattern is not None and path is not None:
            # Simple wildcard matching
            pattern = entry.path_pattern
            if pattern.endswith("*"):
                if not path.startswith(pattern[:-1]):
                    return False
            elif pattern != path:
                return False

        return True

    def list_blocked_ips(
        self,
        page: int = 1,
        per_page: int = 50,
        include_expired: bool = False,
    ) -> Dict[str, Any]:
        """
        List all blocked IPs.

        Args:
            page: Page number
            per_page: Items per page
            include_expired: Whether to include expired entries

        Returns:
            Dict with blocked IPs list and pagination info
        """
        if not include_expired:
            self._cleanup_expired()

        query = IPBlacklist.query.filter_by(is_active=True)
        query = query.order_by(IPBlacklist.created_at.desc())

        total = query.count()
        entries = query.offset((page - 1) * per_page).limit(per_page).all()

        return {
            "entries": [self._entry_to_dict(e) for e in entries],
            "total": total,
            "page": page,
            "pages": (total + per_page - 1) // per_page if total > 0 else 1,
        }

    def get_block_stats(self) -> Dict[str, Any]:
        """Get blacklist statistics."""
        self._cleanup_expired()

        total_active = IPBlacklist.query.filter_by(is_active=True).count()
        permanent = IPBlacklist.query.filter_by(
            is_active=True, is_permanent=True
        ).count()
        temporary = total_active - permanent

        return {
            "total_blocked": total_active,
            "permanent": permanent,
            "temporary": temporary,
        }

    def _cleanup_expired(self) -> int:
        """Remove expired temporary blocks."""
        now = datetime.utcnow()
        expired = IPBlacklist.query.filter(
            IPBlacklist.is_active == True,
            IPBlacklist.is_permanent == False,
            IPBlacklist.expires_at < now,
        ).all()

        count = len(expired)
        for entry in expired:
            entry.is_active = False

        if count > 0:
            db.session.commit()

        return count

    def _entry_to_dict(self, entry: IPBlacklist) -> Dict[str, Any]:
        """Convert blacklist entry to dictionary."""
        remaining_seconds = None
        if not entry.is_permanent and entry.expires_at:
            remaining = entry.expires_at - datetime.utcnow()
            remaining_seconds = max(0, int(remaining.total_seconds()))

        return {
            "id": entry.id,
            "ip_address": entry.ip_address,
            "reason": entry.reason,
            "blocked_by": entry.blocked_by,
            "path_pattern": entry.path_pattern,
            "node_id": entry.node_id,
            "node_name": entry.node.name if entry.node else None,
            "is_permanent": entry.is_permanent,
            "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
            "remaining_seconds": remaining_seconds,
            "is_active": entry.is_active,
            "created_at": entry.created_at.isoformat(),
        }
