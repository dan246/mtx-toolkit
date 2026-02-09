"""
MTX Toolkit - Stream Reliability Toolkit
Flask Application Factory
"""

import os

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
socketio = SocketIO()


def create_app(config_name: str = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load configuration
    config_name = config_name or os.getenv("FLASK_ENV", "development")
    app.config.from_object(f"app.config.{config_name.capitalize()}Config")

    # Initialize extensions
    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")

    # Register blueprints
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

    # Create database tables
    with app.app_context():
        db.create_all()

    return app
