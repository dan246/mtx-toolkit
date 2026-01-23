#!/usr/bin/env python3
"""
MTX Toolkit - Stream Reliability Toolkit
Main entry point.
"""

import os
from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    debug = os.getenv("FLASK_ENV", "development") == "development"
    port = int(os.getenv("PORT", 5000))

    socketio.run(app, host="0.0.0.0", port=port, debug=debug)
