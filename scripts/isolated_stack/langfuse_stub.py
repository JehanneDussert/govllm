# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
"""Langfuse stand-in for the isolated stack: answers 200 {} to every request, stores nothing.
The evaluation service creates a trace and pushes scores after each evaluation; on the
isolated network there is no Langfuse to receive them."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def _ok(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"data": [], "successes": [], "errors": []}')

    do_GET = do_POST = do_PUT = do_PATCH = _ok

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("0.0.0.0", 3000), Handler).serve_forever()
