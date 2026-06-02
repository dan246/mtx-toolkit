"""
Authentication API.

Endpoints:
    POST /api/auth/login            -> { token, user }
    GET  /api/auth/me               -> { user }            (requires auth)
    POST /api/auth/change-password  -> { message }         (requires auth)
    POST /api/auth/logout           -> { message }         (stateless / client discards token)
"""

from datetime import datetime

from flask import Blueprint, g, jsonify, request

from app import db
from app.models import User
from app.utils.auth import generate_token, load_current_user, require_auth
from app.utils.logging import get_logger

auth_bp = Blueprint("auth", __name__)
logger = get_logger(__name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.is_active or not user.check_password(password):
        logger.warning("login_failed", username=username)
        return jsonify({"error": "invalid credentials"}), 401

    user.last_login = datetime.utcnow()
    db.session.commit()

    token = generate_token(user)
    logger.info("login_success", username=username, user_id=user.id)
    return jsonify({"token": token, "user": user.to_dict()})


@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    user = g.get("current_user") or load_current_user()
    return jsonify({"user": user.to_dict()})


@auth_bp.route("/change-password", methods=["POST"])
@require_auth
def change_password():
    user = g.get("current_user") or load_current_user()
    data = request.get_json(silent=True) or {}
    current = data.get("current_password") or ""
    new = data.get("new_password") or ""

    if not user.check_password(current):
        return jsonify({"error": "current password is incorrect"}), 400
    if len(new) < 6:
        return jsonify({"error": "new password must be at least 6 characters"}), 400

    user.set_password(new)
    db.session.commit()
    logger.info("password_changed", user_id=user.id)
    return jsonify({"message": "password updated"})


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # Tokens are stateless; the client discards it. Endpoint exists for symmetry.
    return jsonify({"message": "logged out"})
