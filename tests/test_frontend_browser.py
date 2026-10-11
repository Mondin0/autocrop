"""Browser tests for V2-05 (Chromium via the ``page`` fixture).

Real interaction with the page against controlled frontend/API doubles:
submit a file, watch state/progress/terminal states, download the
result, and recover from a visible error with a retry. No Compose,
no real photos, no YOLO/Redis/RustFS.
"""

from __future__ import annotations

import http.server
import json
import pathlib
import threading

import pytest

RESULT_BYTES = b"RESULT-ZIP-BYTES"


class _Api(http.server.BaseHTTPRequestHandler):
    """Scripted API double: progress, failed or query-error modes."""

    state: dict = {}

    def _send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length) if length else b""
        st = type(self).state
        st["posts"] += 1
        st["post_ct"] = self.headers.get("Content-Type") or ""
        st["post_file"] = b'name="file"' in data
        self._send_json(202, {"job_id": "job-1", "status": "queued"})

    def do_GET(self) -> None:
        st = type(self).state
        if self.path.endswith("/result"):
            body = st["result"]
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition",
                             'attachment; filename="job-1.zip"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if "/api/jobs/" in self.path:
            if st["mode"] == "boom":
                self._send_json(500, {"detail": "boom"})
                return
            n = st["polls"]
            st["polls"] += 1
            payload = {"job_id": "job-1", "current": None, "processed": 0,
                       "total": 2, "saved": 0, "review": 0, "error": None,
                       "status": "queued"}
            if st["mode"] == "failed":
                payload.update(status="failed", error="motor roto")
            elif n == 1:
                payload.update(status="processing", current="a.jpg",
                               processed=1, saved=1)
            elif n >= 2:
                payload.update(status="completed", processed=2, saved=1,
                               review=1)
            self._send_json(200, payload)
            return
        self._send_json(404, {"detail": "unknown job"})

    def log_message(self, *args):  # silence test output
        pass


@pytest.fixture()
def live_url():  # type: ignore[no-untyped-def]
    _Api.state = {"mode": "progress", "polls": 0, "posts": 0,
                  "post_ct": "", "post_file": False,
                  "result": RESULT_BYTES}
    up = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Api)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    from app import frontend
    fe = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        frontend.create_handler(f"http://127.0.0.1:{up.server_port}"))
    threading.Thread(target=fe.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{fe.server_port}"
    finally:
        fe.shutdown()
        up.shutdown()


def _wait_until(cond, timeout: float = 10.0) -> None:  # type: ignore[no-untyped-def]
    import time

    deadline = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < deadline, "timeout esperando al stub"
        time.sleep(0.05)


def _submit(page, url: str, tmp_path: pathlib.Path) -> None:  # type: ignore[no-untyped-def]
    page.goto(url + "/")
    zipp = tmp_path / "in.zip"
    zipp.write_bytes(b"PK-fake-zip")
    page.set_input_files("#file", str(zipp))
    page.click("#send")


# F2 ---------------------------------------------------------------------

def test_browser_submit_accepts_job_and_polls(page, live_url, tmp_path):  # type: ignore[no-untyped-def]
    _submit(page, live_url, tmp_path)
    page.wait_for_function(
        "() => /trabajo aceptado|estado:/.test("
        "document.getElementById('status').textContent)")
    _wait_until(lambda: _Api.state["polls"] >= 1)
    assert _Api.state["posts"] == 1
    assert "multipart/form-data" in _Api.state["post_ct"]
    assert _Api.state["post_file"] is True


# F3 + F4 ----------------------------------------------------------------

def test_browser_progress_completed_and_download(page, live_url, tmp_path):  # type: ignore[no-untyped-def]
    _submit(page, live_url, tmp_path)
    page.wait_for_function(
        "() => document.getElementById('current').textContent"
        ".includes('a.jpg')")
    page.wait_for_function(
        "() => document.getElementById('counters').textContent"
        ".includes('1/2')")
    page.locator("#download").wait_for(state="visible")
    assert page.locator("#download").get_attribute("href").endswith(
        "/api/jobs/job-1/result")
    with page.expect_download() as dl_info:
        page.click("#download")
    download = dl_info.value
    assert download.suggested_filename == "job-1.zip"
    assert pathlib.Path(str(download.path())).read_bytes() == RESULT_BYTES
    before = _Api.state["polls"]
    page.wait_for_timeout(1600)
    assert _Api.state["polls"] == before


# F4 (failed) --------------------------------------------------------------

def test_browser_failed_shows_error_without_download(page, live_url, tmp_path):  # type: ignore[no-untyped-def]
    _Api.state["mode"] = "failed"
    _submit(page, live_url, tmp_path)
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".includes('motor roto')")
    assert not page.locator("#download").is_visible()


# F5 ---------------------------------------------------------------------

def test_browser_query_error_visible_then_retry(page, live_url, tmp_path):  # type: ignore[no-untyped-def]
    _Api.state["mode"] = "boom"
    _submit(page, live_url, tmp_path)
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".includes('consulta falló')")
    before = _Api.state["polls"]
    page.wait_for_timeout(1300)
    assert _Api.state["polls"] == before
    _Api.state["mode"] = "progress"
    _submit(page, live_url, tmp_path)
    page.locator("#download").wait_for(state="visible", timeout=15000)
