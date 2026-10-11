"""Tests for V2-05 local web interface (contract first).

Uses controlled stub upstreams and the static page text; no YOLO,
no real Redis/RustFS and no real photos.
"""

from __future__ import annotations

import http.client
import http.server
import io
import pathlib
import threading
import urllib.request
import urllib.error
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


def page() -> str:
    return (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


class _StubUpstream(http.server.BaseHTTPRequestHandler):
    """Canned API double; records the last proxied request."""

    last: dict = {}
    mode: str = "ok"

    def _send(self, code: int, body: bytes, ctype: str = "application/json",
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _record(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length) if length else b""
        type(self).last = {"method": self.command, "path": self.path,
                           "content_type": self.headers.get("Content-Type"),
                           "body": data}
        return data

    def _route(self) -> None:
        data = self._record()
        mode = type(self).mode
        if mode == "boom":
            self._send(500, b'{"detail":"boom"}')
        elif self.path.startswith("/api/jobs") and self.command == "POST":
            assert b"multipart/form-data" in (
                self.headers.get("Content-Type") or "").encode()
            assert b'name="file"' in data or b'name=file' in data
            self._send(202, b'{"job_id":"j1","status":"queued"}')
        elif self.path.startswith("/api/jobs/j1/result"):
            self._send(200, b"ZIPBYTES", "application/zip",
                        {"Content-Disposition": 'attachment; filename="j1.zip"'})
        elif self.path.startswith("/api/jobs/j1"):
            q = "?echo=1" in self.path
            body = ('{"job_id":"j1","status":"processing","current":"a.jpg",'
                    '"processed":1,"total":2,"saved":1,"review":0,'
                    '"error":null}') if not q else '{"echoed":true}'
            self._send(200, body.encode())
        elif self.path.startswith("/api/"):
            self._send(404, b'{"detail":"unknown job"}')
        else:
            self._send(404, b"nope", "text/plain")

    do_GET = _route
    do_POST = _route
    do_PUT = _route
    do_DELETE = _route
    do_PATCH = _route

    def log_message(self, *args):  # silence test output
        pass


def _serve(handler, port: int = 0):  # type: ignore[no-untyped-def]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv


def _frontend_server(api_base: str):  # type: ignore[no-untyped-def]
    from app import frontend
    handler = frontend.create_handler(api_base)
    return _serve(handler)


def _get(port: int, path: str) -> tuple[int, bytes, http.client.HTTPMessage]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path)
    resp = conn.getresponse()
    return resp.status, resp.read(), resp.headers


# F1 ---------------------------------------------------------------------

def test_f1_root_serves_upload_page():
    import app.frontend as frontend

    srv = _frontend_server("http://127.0.0.1:1")
    try:
        status, body, headers = _get(srv.server_port, "/")
        assert status == 200
        assert "text/html" in (headers.get("Content-Type") or "")
        text = body.decode()
        assert 'type="file"' in text
        assert "/api/jobs" in text
    finally:
        srv.shutdown()


def test_f1_api_proxy_preserves_status_headers_body_query():
    srv_up = _serve(_StubUpstream)
    try:
        srv = _frontend_server(
            f"http://127.0.0.1:{srv_up.server_port}")
        try:
            status, body, headers = _get(
                srv.server_port, "/api/jobs/j1?echo=1")
            assert status == 200
            assert body == b'{"echoed":true}'
            assert _StubUpstream.last["method"] == "GET"
            assert _StubUpstream.last["path"] == "/api/jobs/j1?echo=1"

            status, body, headers = _get(
                srv.server_port, "/api/jobs/j1/result")
            assert status == 200
            assert body == b"ZIPBYTES"
            assert "application/zip" in (
                headers.get("Content-Type") or "")
            assert "j1.zip" in (headers.get("Content-Disposition") or "")

            status, body, _ = _get(srv.server_port, "/api/jobs/missing")
            assert status == 404
            assert body == b'{"detail":"unknown job"}'
        finally:
            srv.shutdown()
    finally:
        srv_up.shutdown()


def test_f1_proxy_forwards_method_and_multipart_body():
    srv_up = _serve(_StubUpstream)
    try:
        srv = _frontend_server(
            f"http://127.0.0.1:{srv_up.server_port}")
        try:
            boundary = "TESTBOUND"
            payload = ("\r\n".join([
                f"--{boundary}",
                'Content-Disposition: form-data; name="file"; filename="in.zip"',
                "Content-Type: application/zip", "",
                "ZIPDATA",
                f"--{boundary}--", ""]).encode())
            req = urllib.request.Request(
                f"http://127.0.0.1:{srv.server_port}/api/jobs",
                data=payload, method="POST",
                headers={"Content-Type":
                         f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status == 202
                assert b"j1" in resp.read()
            assert _StubUpstream.last["method"] == "POST"
            assert b"ZIPDATA" in _StubUpstream.last["body"]
        finally:
            srv.shutdown()
    finally:
        srv_up.shutdown()


def test_f1_uncontracted_paths_are_404_on_frontend():
    srv = _frontend_server("http://127.0.0.1:1")
    try:
        for path in ("/health", "/api"):
            assert _get(srv.server_port, path)[0] == 404, path
    finally:
        srv.shutdown()


# F2 ---------------------------------------------------------------------

def test_f2_page_posts_multipart_file_and_polls_each_second():
    text = page()
    assert 'name="file"' in text or "name='file'" in text
    assert "multipart" in text or "FormData" in text
    assert "202" in text
    assert "1000" in text
    assert "setInterval" in text or "setTimeout" in text


# F3 ---------------------------------------------------------------------

def test_f3_page_shows_status_current_and_counters():
    text = page()
    for token in ("status", "current", "processed", "total", "saved",
                  "review"):
        assert token in text
    assert "queued" in text and "processing" in text


# F4 ---------------------------------------------------------------------

def test_f4_page_stops_polling_and_downloads_only_when_completed():
    text = page()
    assert "completed" in text and "failed" in text
    assert "clearInterval" in text or "clearTimeout" in text
    assert "/result" in text
    assert "error" in text


# F5 ---------------------------------------------------------------------

def test_f5_page_shows_errors_and_allows_retry():
    text = page()
    lowered = text.lower()
    assert "error" in lowered
    assert "catch" in text or "onerror" in lowered or "failed to" in lowered
    assert "clearInterval" in text or "clearTimeout" in text


def test_f5_proxy_failure_is_visible_502_not_hang():
    srv = _frontend_server("http://127.0.0.1:1")  # nothing listens there
    try:
        conn = http.client.HTTPConnection(
            "127.0.0.1", srv.server_port, timeout=10)
        conn.request("GET", "/api/jobs/j1")
        resp = conn.getresponse()
        assert resp.status in (502, 504)
        assert resp.read()
    finally:
        srv.shutdown()


# T1 ---------------------------------------------------------------------

def test_t1_compose_runs_frontend_and_api_separately_on_loopback():
    services = compose()["services"]
    assert {"api", "frontend"} <= set(services)
    api, front = services["api"], services["frontend"]
    assert front.get("build") == api.get("build")
    publishers = {n: s for n, s in services.items() if s.get("ports")}
    assert set(publishers) == {"api", "frontend"}
    api_map = str(publishers["api"]["ports"][0])
    front_map = str(publishers["frontend"]["ports"][0])
    assert api_map.startswith("127.0.0.1:") and api_map.endswith(":8000")
    assert "8000" in (str(publishers["api"]["ports"][0]))
    assert front_map.startswith("127.0.0.1:") and front_map.endswith(":8080")
    assert "8080" in front_map
    for name in ("redis", "rustfs", "worker"):
        assert not services[name].get("ports"), name


def test_t1_frontend_reaches_api_internally_without_external_deps():
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "api:8000" in text
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "AUTOCROP_FRONTEND_PORT" in example
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "frontend" in docker
    html = page().lower()
    assert "cdn" not in html and "http://api" not in html
    assert "/api/" in page()


# H2 (revisión del director) ------------------------------------------------
# `docker compose up --build` fallaba en COPY frontend ./frontend porque
# la allowlist de .dockerignore no incluía frontend/ en el contexto.

def _ignore_patterns() -> list[str]:
    out = []
    for line in (ROOT / ".dockerignore").read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _ignore_excludes(rel: str, patterns: list[str]) -> bool:
    """Último patrón que casa decide (suficiente para esta allowlist)."""
    import fnmatch

    excluded = False
    for pat in patterns:
        negated = pat.startswith("!")
        body = (pat[1:] if negated else pat).rstrip("/")
        hit = (rel == body or rel.startswith(body + "/")
               or fnmatch.fnmatchcase(rel, body))
        if hit:
            excluded = not negated
    return excluded


def test_h2_docker_context_includes_frontend_page():
    patterns = _ignore_patterns()
    assert not _ignore_excludes("frontend/index.html", patterns)
    assert "COPY frontend" in (ROOT / "Dockerfile").read_text(
        encoding="utf-8")
    assert not _ignore_excludes("app/frontend.py", patterns)
    assert _ignore_excludes(".env", patterns)
    assert _ignore_excludes("fotos/a.jpg", patterns)


# T2 ---------------------------------------------------------------------

def test_t2_frontend_needs_no_heavy_services():
    src = (ROOT / "app" / "frontend.py").read_text(encoding="utf-8")
    imports = [ln for ln in src.splitlines()
               if ln.lstrip().startswith(("import ", "from "))]
    for heavy in ("ultralytics", "torch", "redis", "boto3"):
        assert all(heavy not in ln for ln in imports), heavy
    assert "http.server" in src or "BaseHTTPRequestHandler" in src


# H1 (revisión del director) ------------------------------------------------
# El proxy materializaba cuerpo completo (rfile.read(length) y resp.read()
# + wfile.write(body)); V2-03 admite ZIP de hasta 500 MiB y exige bloques.

_MAX_BLOCK = 64 * 1024


def _instrument(handler_cls):  # type: ignore[no-untyped-def]
    """Envuelve rfile/wfile del handler y registra picos por operación."""
    peak = {"read": 0, "write": 0}
    orig_setup = handler_cls.setup

    def setup(self):
        orig_setup(self)
        raw_r, raw_w = self.rfile, self.wfile
        state = peak

        class _R:
            def __init__(self, f):
                self._f = f

            def read(self, n=-1):
                data = self._f.read(n)
                if n is None or (isinstance(n, int) and n < 0):
                    state["read"] = max(state["read"], len(data))
                else:
                    state["read"] = max(
                        state["read"], int(n), len(data))
                return data

            def __getattr__(self, name):
                return getattr(self._f, name)

        class _W:
            def __init__(self, f):
                self._f = f

            def write(self, data):
                state["write"] = max(state["write"], len(data))
                return self._f.write(data)

            def __getattr__(self, name):
                return getattr(self._f, name)

        self.rfile, self.wfile = _R(raw_r), _W(raw_w)

    handler_cls.setup = setup
    return peak


def test_h1_proxy_streams_request_body_in_bounded_blocks():
    import hashlib

    from app import frontend

    body = bytes(range(256)) * 1024  # 256 KiB > _MAX_BLOCK
    assert len(body) > _MAX_BLOCK
    seen = {}

    class _Echo(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(length)
            seen["digest"] = hashlib.sha256(data).hexdigest()
            seen["length"] = len(data)
            out = b"{}"
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args):
            pass

    srv_up = _serve(_Echo)
    try:
        handler = frontend.create_handler(
            f"http://127.0.0.1:{srv_up.server_port}")
        peak = _instrument(handler)
        srv = _serve(handler)
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{srv.server_port}/api/jobs",
                data=body, method="POST",
                headers={"Content-Type": "application/octet-stream"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                assert resp.status == 202
            assert seen["length"] == len(body)
            assert seen["digest"] == hashlib.sha256(body).hexdigest()
            assert peak["read"] <= _MAX_BLOCK, peak
        finally:
            srv.shutdown()
    finally:
        srv_up.shutdown()


def test_h1_proxy_streams_response_body_in_bounded_blocks():
    from app import frontend

    payload = bytes(range(256)) * 1280  # 320 KiB > _MAX_BLOCK
    assert len(payload) > _MAX_BLOCK

    class _Big(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    srv_up = _serve(_Big)
    try:
        handler = frontend.create_handler(
            f"http://127.0.0.1:{srv_up.server_port}")
        peak = _instrument(handler)
        srv = _serve(handler)
        try:
            status, data, _ = _get(srv.server_port, "/api/jobs/big/result")
            assert status == 200
            assert data == payload
            assert peak["write"] <= _MAX_BLOCK, peak
        finally:
            srv.shutdown()
    finally:
        srv_up.shutdown()


def test_h1a_page_accepts_only_202_on_submit():
    text = page()
    assert "res.status === 202" in text
    assert "!res.ok && res.status" not in text
    assert "envío falló" in text


def test_h1b_page_labels_input_and_announces_status():
    text = page()
    assert '<label for="file"' in text or "<label for='file'" in text
    assert "aria-live" in text
    assert 'role="status"' in text or "role='status'" in text


def test_t2_full_job_flow_through_proxy_with_controlled_double():
    import io as _io
    import zipfile as _zip

    from fastapi.testclient import TestClient

    from app.jobs import JobService, MemoryBlobStore, MemoryStateStore
    from app.jobs import create_app as create_api_app

    def fake_process(in_path, out_path, detector=None, ratio=None,
                     margin=0.15, on_progress=None):
        if on_progress is not None:
            on_progress({"current": "a.jpg", "processed": 0, "total": 1,
                         "saved": 0, "review": 0})
            on_progress({"current": None, "processed": 1, "total": 1,
                         "saved": 1, "review": 0})
        with _zip.ZipFile(out_path, "w") as zf:
            zf.writestr("a.jpg", b"crop-a")

    svc = JobService(MemoryStateStore(), MemoryBlobStore(),
                     process_fn=fake_process)
    api = TestClient(create_api_app(svc))

    class _ApiOnly(http.server.BaseHTTPRequestHandler):
        def _proxy(self):
            length = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(length) if length else b""
            path = self.path
            if self.command == "POST" and path == "/api/jobs":
                resp = api.post("/api/jobs", files={"file": (
                    "in.zip", _io.BytesIO(data), "application/zip")})
            elif self.command == "GET" and path.endswith("/result"):
                job = path.split("/")[3]
                resp = api.get(f"/api/jobs/{job}/result")
            elif self.command == "GET":
                job = path.split("/")[3].split("?")[0]
                resp = api.get(f"/api/jobs/{job}")
            else:
                self.send_response(404)
                self.end_headers()
                return
            body = resp.content
            self.send_response(resp.status_code)
            ctype = resp.headers.get("content-type", "application/json")
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _proxy
        do_POST = _proxy

        def log_message(self, *args):
            pass

    srv_up = _serve(_ApiOnly)
    try:
        srv = _frontend_server(
            f"http://127.0.0.1:{srv_up.server_port}")
        try:
            buf = _io.BytesIO()
            with _zip.ZipFile(buf, "w") as zf:
                zf.writestr("a.jpg", b"fake-jpeg")
            boundary = "B2"
            payload = (f"--{boundary}\r\nContent-Disposition: form-data; "
                       f'name="file"; filename="in.zip"\r\n\r\n').encode() + \
                buf.getvalue() + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{srv.server_port}/api/jobs",
                data=payload, method="POST",
                headers={"Content-Type":
                         f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status == 202
            job_id = svc.state.ids()[0]
            done = svc.run_next()
            assert done["status"] == "completed"
            status, body, _ = _get(srv.server_port,
                                   f"/api/jobs/{job_id}")
            assert status == 200 and b"completed" in body
            status, body, _ = _get(srv.server_port,
                                   f"/api/jobs/{job_id}/result")
            assert status == 200 and len(body) > 0
        finally:
            srv.shutdown()
    finally:
        srv_up.shutdown()
