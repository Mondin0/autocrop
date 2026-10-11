"""Local frontend server for V2-05.

Serves the static page from ``frontend/`` and proxies ``/api/*`` to the
API service over the Compose internal network. Stdlib only: no YOLO,
Redis, RustFS or external web dependencies.
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
API_BASE_DEFAULT = "http://api:8000"

_CHUNK = 64 * 1024


def _api_base(api_base: str | None = None) -> str:
    return (api_base or os.environ.get("FRONTEND_API_BASE")
            or API_BASE_DEFAULT).rstrip("/")


def create_handler(api_base: str | None = None) -> Any:
    base = _api_base(api_base)

    class Handler(BaseHTTPRequestHandler):
        _base = base

        def _serve_file(self) -> None:
            target = self.path.split("?", 1)[0]
            if target not in ("/", "/index.html"):
                self._send_text(404, "not found")
                return
            try:
                body = (FRONTEND_DIR / "index.html").read_bytes()
            except OSError:
                self._send_text(500, "frontend page missing")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _proxy_api(self) -> None:
            if not (self.path == "/api/" or
                    self.path.startswith("/api/")):
                self._send_text(404, "not found")
                return
            import http.client
            from urllib.parse import urlsplit

            sent = False
            conn = None
            try:
                parts = urlsplit(base)
                conn = http.client.HTTPConnection(
                    parts.hostname or "api", parts.port or 80, timeout=30)
                length = int(self.headers.get("Content-Length") or 0)
                conn.putrequest(self.command, self.path,
                                skip_accept_encoding=True)
                ctype = self.headers.get("Content-Type")
                if ctype:
                    conn.putheader("Content-Type", ctype)
                if length:
                    conn.putheader("Content-Length", str(length))
                conn.endheaders()
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(_CHUNK, remaining))
                    if not chunk:
                        break
                    conn.send(chunk)
                    remaining -= len(chunk)
                resp = conn.getresponse()
                self.send_response(resp.status)
                for name in ("Content-Type", "Content-Disposition"):
                    value = resp.getheader(name)
                    if value:
                        self.send_header(name, value)
                body_length = resp.getheader("Content-Length")
                if body_length:
                    self.send_header("Content-Length", body_length)
                self.end_headers()
                sent = True
                if self.command != "HEAD":
                    while True:
                        chunk = resp.read(_CHUNK)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except Exception:
                if not sent:
                    try:
                        self._send_text(502, "cannot reach api")
                    except (BrokenPipeError, ConnectionResetError):
                        pass
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        def _send_text(self, code: int, message: str) -> None:
            body = message.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/api" or not self.path.startswith("/api/"):
                self._serve_file() if self.path.split(
                    "?", 1)[0] in ("/", "/index.html") else \
                    self._send_text(404, "not found")
            else:
                self._proxy_api()

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_POST(self) -> None:
            self._proxy_api()

        def do_PUT(self) -> None:
            self._proxy_api()

        def do_DELETE(self) -> None:
            self._proxy_api()

        def do_PATCH(self) -> None:
            self._proxy_api()

        def do_OPTIONS(self) -> None:
            self._proxy_api()

        def log_message(self, *args: Any) -> None:
            pass

    return Handler


def build_server(host: str = "0.0.0.0", port: int = 8080,
                 api_base: str | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), create_handler(api_base))


def main() -> None:
    port = int(os.environ.get("AUTOCROP_FRONTEND_PORT")
               or os.environ.get("FRONTEND_PORT") or 8080)
    server = build_server("0.0.0.0", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
