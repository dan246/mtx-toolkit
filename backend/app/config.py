"""
Configuration settings for different environments.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


DEFAULT_DEV_SECRET = "dev-secret-key-change-in-production"


def _split_csv(value: str) -> list:
    """Parse a comma-separated env value into a clean list."""
    return [item.strip() for item in value.split(",") if item.strip()]


class BaseConfig:
    """Base configuration."""

    SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_DEV_SECRET)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # CORS — comma-separated allowlist. Defaults to the local Vite dev server.
    # Production MUST set CORS_ORIGINS explicitly (validated in create_app).
    CORS_ORIGINS = _split_csv(
        os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
    )

    # Auth / JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or os.getenv(
        "SECRET_KEY", DEFAULT_DEV_SECRET
    )
    JWT_ACCESS_TOKEN_EXPIRES_HOURS = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRES_HOURS", "12")
    )
    # Bootstrap admin created on first startup if no users exist.
    # `or "admin"` so an explicitly-empty env value still yields a usable
    # password rather than creating an account with an empty one.
    BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME") or "admin"
    BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or "admin"

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_JSON = os.getenv("LOG_JSON", "true").lower() in ("1", "true", "yes")

    # Require authentication on mutating/control endpoints. Disabled under tests.
    AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() in ("1", "true", "yes")

    # Connection pool settings to prevent connection exhaustion
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 5,  # 每個 worker 最多 5 個連線
        "max_overflow": 10,  # 額外允許 10 個臨時連線
        "pool_recycle": 300,  # 5 分鐘回收連線
        "pool_pre_ping": True,  # 使用前檢查連線是否有效
    }

    # MediaMTX defaults - 連接到主機上現有的 MediaMTX (api_mediamtx_secondary)
    MEDIAMTX_API_URL = os.getenv("MEDIAMTX_API_URL", "http://localhost:9998")
    MEDIAMTX_RTSP_URL = os.getenv("MEDIAMTX_RTSP_URL", "rtsp://localhost:8555")

    # Health check settings
    HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))
    HEALTH_CHECK_TIMEOUT = int(os.getenv("HEALTH_CHECK_TIMEOUT", "10"))

    # Auto-remediation settings
    RETRY_MAX_ATTEMPTS = int(os.getenv("RETRY_MAX_ATTEMPTS", "5"))
    RETRY_BASE_DELAY = float(os.getenv("RETRY_BASE_DELAY", "1.0"))
    RETRY_MAX_DELAY = float(os.getenv("RETRY_MAX_DELAY", "60.0"))

    # Recording settings
    RECORDING_BASE_PATH = os.getenv("RECORDING_BASE_PATH", "/recordings")
    DISK_USAGE_THRESHOLD = float(os.getenv("DISK_USAGE_THRESHOLD", "0.85"))

    # Redis (for Celery)
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL

    # Phase 1: Liveness Probe
    LIVENESS_PROBE_TIMEOUT = int(os.getenv("LIVENESS_PROBE_TIMEOUT", "5"))
    LIVENESS_PROBE_INTERVAL = int(os.getenv("LIVENESS_PROBE_INTERVAL", "30"))
    LIVENESS_PTS_STALE_MS = int(os.getenv("LIVENESS_PTS_STALE_MS", "2000"))
    LIVENESS_BLACK_THRESHOLD = float(os.getenv("LIVENESS_BLACK_THRESHOLD", "10.0"))
    LIVENESS_FREEZE_SHORT_SEC = int(os.getenv("LIVENESS_FREEZE_SHORT_SEC", "15"))
    LIVENESS_FREEZE_LONG_SEC = int(os.getenv("LIVENESS_FREEZE_LONG_SEC", "60"))

    # Phase 3: Fallback
    FALLBACK_ASSETS_PATH = os.getenv("FALLBACK_ASSETS_PATH", "/fallback-assets")
    FALLBACK_DEFAULT_TYPE = os.getenv("FALLBACK_DEFAULT_TYPE", "color_bars")

    # Phase 5: Recording Pipeline
    PIPELINE_WRITE_LATENCY_WARNING_MS = int(
        os.getenv("PIPELINE_WRITE_LATENCY_WARNING_MS", "500")
    )
    PIPELINE_WRITE_LATENCY_CRITICAL_MS = int(
        os.getenv("PIPELINE_WRITE_LATENCY_CRITICAL_MS", "2000")
    )
    PIPELINE_SEGMENT_GAP_WARNING_SEC = float(
        os.getenv("PIPELINE_SEGMENT_GAP_WARNING_SEC", "5.0")
    )


class DevelopmentConfig(BaseConfig):
    """Development configuration."""

    DEBUG = True
    LOG_JSON = os.getenv("LOG_JSON", "false").lower() in ("1", "true", "yes")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR}/mtx_toolkit.db"
    )


class StagingConfig(BaseConfig):
    """Staging configuration."""

    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")


class ProductionConfig(BaseConfig):
    """Production configuration."""

    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")

    # Stricter settings for production
    HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "15"))


class TestingConfig(BaseConfig):
    """Testing configuration."""

    TESTING = True
    AUTH_ENABLED = False  # auth decorators no-op so existing API tests keep passing
    LOG_JSON = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}  # SQLite 不支援連線池參數
