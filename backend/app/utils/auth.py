"""
Authentication helpers.

Tokens are signed with :mod:`itsdangerous` (ships with Flask, no extra
dependency) and carry the user id + role. They are opaque bearer tokens to the
frontend, which simply stores the string and replays it in the
``Authorization: Bearer <token>`` header.
"""

from functools import wraps

from flask import current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import db
from app.utils.logging import get_logger

logger = get_logger(__name__)

_SALT = "mtx-auth-token"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["JWT_SECRET_KEY"], salt=_SALT)


def generate_token(user) -> str:
    """Create a signed bearer token for a user."""
    return _serializer().dumps(
        {"uid": user.id, "username": user.username, "role": user.role}
    )


def _decode_token(token: str):
    max_age = current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES_HOURS", 12) * 3600
    return _serializer().loads(token, max_age=max_age)


def _token_from_request():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def load_current_user():
    """Return the authenticated user or ``None``. Caches on ``flask.g``."""
    if "current_user" in g:
        return g.current_user

    token = _token_from_request()
    if not token:
        return None
    try:
        data = _decode_token(token)
    except SignatureExpired:
        logger.info("token_expired")
        return None
    except BadSignature:
        logger.warning("token_invalid")
        return None

    from app.models import User

    user = db.session.get(User, data.get("uid"))
    if user and user.is_active:
        g.current_user = user
        return user
    return None


def current_username(default: str = "system") -> str:
    """Best-effort username for audit fields (applied_by / blocked_by)."""
    user = g.get("current_user") or load_current_user()
    return user.username if user else default


def require_auth(fn):
    """Decorator enforcing authentication on a single view."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_app.config.get("AUTH_ENABLED", True):
            return fn(*args, **kwargs)
        if load_current_user() is None:
            return jsonify({"error": "authentication required"}), 401
        return fn(*args, **kwargs)

    return wrapper
