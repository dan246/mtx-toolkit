"""
Structured logging configuration built on structlog.

Call :func:`configure_logging` once during app/worker startup, then obtain a
bound logger anywhere with :func:`get_logger`. Output is JSON in production and
human-friendly key/value pairs in development.
"""

import logging
import sys

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """Configure stdlib logging + structlog. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str = "mtx"):
    """Return a structlog bound logger. Safe to call before configuration."""
    if not _CONFIGURED:
        # Fall back to sane defaults so module-level loggers never crash.
        configure_logging()
    return structlog.get_logger(name)
