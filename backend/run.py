#!/usr/bin/env python3
"""
MTX Toolkit - Stream Reliability Toolkit
Main entry point.

IMPORTANT: eventlet.monkey_patch() must run before any other import so that
the stdlib (socket, time, threading, ...) is cooperatively patched. Without
this, a blocking call such as ``time.sleep`` inside a request handler — e.g. a
synchronous remediation — would freeze the entire SocketIO/eventlet hub and
stall every other connected client.
"""

import eventlet

eventlet.monkey_patch()

import os  # noqa: E402

from app import create_app, socketio  # noqa: E402
from app.utils.logging import get_logger  # noqa: E402

app = create_app()
logger = get_logger("mtx.run")

if __name__ == "__main__":
    debug = os.getenv("FLASK_ENV", "development") == "development"
    port = int(os.getenv("PORT", 5000))

    logger.info("server_starting", port=port, debug=debug)
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)
