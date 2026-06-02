"""
MTX Toolkit - Stream Reliability Toolkit
Flask Application Factory
"""

import os

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
socketio = SocketIO()

# Endpoints reachable without authentication (login + public client telemetry +
# the container health probe). Everything else under /api requires a token when
# AUTH_ENABLED is on.
PUBLIC_ENDPOINTS = {
    "auth.login",
    "auth.logout",
    "health.get_health_status",
    "health.submit_playback_report",
}


def create_app(config_name: str = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load configuration
    config_name = config_name or os.getenv("FLASK_ENV", "development")
    app.config.from_object(f"app.config.{config_name.capitalize()}Config")

    _validate_config(app, config_name)

    # Logging (structlog) — configure once per process.
    from app.utils.logging import configure_logging, get_logger

    configure_logging(
        level=app.config.get("LOG_LEVEL", "INFO"),
        json_logs=app.config.get("LOG_JSON", True),
    )
    logger = get_logger("mtx.app")

    # Initialize extensions
    db.init_app(app)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", [])}},
        supports_credentials=True,
    )
    socketio.init_app(
        app,
        cors_allowed_origins=app.config.get("CORS_ORIGINS", []),
        async_mode="eventlet",
    )

    # Register blueprints
    from app.api.auth import auth_bp
    from app.api.blacklist import blacklist_bp
    from app.api.config import config_bp
    from app.api.dashboard import dashboard_bp
    from app.api.fallback import fallback_bp
    from app.api.fleet import fleet_bp
    from app.api.health import health_bp
    from app.api.liveness import liveness_bp
    from app.api.pipeline import pipeline_bp
    from app.api.recordings import recordings_bp
    from app.api.sessions import sessions_bp
    from app.api.streams import streams_bp
    from app.api.testing import testing_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(health_bp, url_prefix="/api/health")
    app.register_blueprint(streams_bp, url_prefix="/api/streams")
    app.register_blueprint(fleet_bp, url_prefix="/api/fleet")
    app.register_blueprint(config_bp, url_prefix="/api/config")
    app.register_blueprint(recordings_bp, url_prefix="/api/recordings")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.register_blueprint(sessions_bp, url_prefix="/api/sessions")
    app.register_blueprint(blacklist_bp, url_prefix="/api/blacklist")
    app.register_blueprint(liveness_bp, url_prefix="/api/liveness")
    app.register_blueprint(fallback_bp, url_prefix="/api/fallback")
    app.register_blueprint(pipeline_bp, url_prefix="/api/pipeline")
    app.register_blueprint(testing_bp, url_prefix="/api/testing")

    _register_auth_guard(app)

    # Create database tables + bootstrap admin
    with app.app_context():
        db.create_all()
        _bootstrap_admin(app, logger)

    logger.info("app_created", env=config_name, auth_enabled=app.config["AUTH_ENABLED"])
    return app


def _validate_config(app: Flask, config_name: str) -> None:
    """Fail fast on insecure production configuration."""
    from app.config import DEFAULT_DEV_SECRET

    if config_name in ("production", "staging"):
        if app.config.get("SECRET_KEY") in (None, "", DEFAULT_DEV_SECRET):
            raise RuntimeError(
                "SECRET_KEY must be set to a strong value in production/staging "
                "(the built-in dev default is not allowed)."
            )
        if not app.config.get("SQLALCHEMY_DATABASE_URI"):
            raise RuntimeError("DATABASE_URL must be set in production/staging.")
        if app.config.get("AUTH_ENABLED") and not app.config.get("CORS_ORIGINS"):
            raise RuntimeError(
                "CORS_ORIGINS must be set explicitly in production/staging."
            )


def _register_auth_guard(app: Flask) -> None:
    """Enforce authentication on all /api endpoints except the public allowlist."""

    @app.before_request
    def _enforce_auth():
        if not app.config.get("AUTH_ENABLED", True):
            return None
        if request.method == "OPTIONS":  # CORS preflight
            return None
        if not request.path.startswith("/api/"):
            return None
        if (request.endpoint or "") in PUBLIC_ENDPOINTS:
            return None

        from app.utils.auth import load_current_user

        user = load_current_user()
        if user is None:
            return jsonify({"error": "authentication required"}), 401
        g.current_user = user
        return None


def _bootstrap_admin(app: Flask, logger) -> None:
    """Create an initial admin account if no users exist yet."""
    from app.models import User

    if User.query.first() is not None:
        return
    username = app.config.get("BOOTSTRAP_ADMIN_USERNAME", "admin")
    password = app.config.get("BOOTSTRAP_ADMIN_PASSWORD", "admin")
    admin = User(username=username, role="admin", is_active=True)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    logger.warning(
        "bootstrap_admin_created",
        username=username,
        note="change this password immediately via /api/auth/change-password",
    )
