"""Browser regressions for V2-09 (Chromium via the ``page`` fixture).

Consistent single-job UI against a controlled frontend/API double: stale
responses never replace the current job, no duplicate submits or
overlapping polls, readable errors for empty selection / HTTP /
connection / invalid JSON, UUID-bound downloads (410 expired, 404
absent), and static page/README hints. No Compose, no real photos, no
YOLO/Redis/RustFS.
"""

from __future__ import annotations

import http.server
import json
import pathlib
import threading
import time

import pytest


def _processing(job_id: str, n: int = 0) -> dict:
    return {"job_id": job_id, "status": "processing", "current": f"{job_id}-pic.jpg",
            "processed": n, "total": 5, "saved": n, "review": 0, "error": None}


def _completed(job_id: str) -> dict:
    return {"job_id": job_id, "status": "completed", "current": None,
            "processed": 5, "total": 5, "saved": 4, "review": 1, "error": None}


def _fresh_state() -> dict:
    return {"posts": 0, "polls": 0, "concurrent": 0, "max_concurrent": 0,
            "accepted": [], "job_ids": ["job-A", "job-B", "job-C"],
            "poll_scripts": {}, "poll_index": {}, "poll_delay": 0.0,
            "results": {}, "accept_mode": "ok", "accept_gate": None}


class _V9Api(http.server.BaseHTTPRequestHandler):
    """Scripted API double with per-job poll/download scripts."""

    state: dict = {}

    def _send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_raw(self, code: int, raw: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        st = type(self).state
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        st["posts"] += 1
        gate = st.get("accept_gate")
        if gate is not None:
            gate.wait(timeout=20)
        mode = st.get("accept_mode", "ok")
        if mode == "http500":
            self._send_json(500, {"detail": "boom"})
            return
        if mode == "too-large":
            self._send_json(413, {"detail": "upload exceeds 2 GiB"})
            return
        if mode == "badjson":
            self._send_raw(202, b'{"job_id": ', "application/json")
            return
        idx = len(st["accepted"])
        ids = st["job_ids"]
        jid = ids[idx] if idx < len(ids) else f"job-{idx}"
        st["accepted"].append(jid)
        self._send_json(202, {"job_id": jid, "status": "queued"})

    def do_GET(self) -> None:
        st = type(self).state
        if self.path.endswith("/result"):
            segs = self.path.split("/")
            jid = segs[3] if len(segs) > 3 else ""
            act = st["results"].get(jid, {"body": f"ZIP-{jid}".encode()})
            if act.get("delay"):
                time.sleep(act["delay"])
            status = act.get("status", 200)
            if status != 200:
                self._send_json(status, {"detail": act.get("detail", "x")})
                return
            body = act["body"]
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition",
                             f'attachment; filename="{jid}.zip"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if "/api/jobs/" in self.path:
            jid = self.path.split("/api/jobs/")[1].split("?")[0].split("/")[0]
            st["polls"] += 1
            st["concurrent"] += 1
            st["max_concurrent"] = max(st["max_concurrent"], st["concurrent"])
            try:
                if st.get("poll_delay"):
                    time.sleep(st["poll_delay"])
                script = st["poll_scripts"].get(jid, [])
                n = st["poll_index"].get(jid, 0)
                st["poll_index"][jid] = n + 1
                act = script[n] if n < len(script) else None
                if act is None:
                    self._send_json(200, _processing(jid, n))
                    return
                if act.get("headers_first"):
                    # Ventana tardía real: headers ya enviados (fetch
                    # resuelve) pero el body JSON aún no llega, de modo que
                    # `await res.json()` espera mientras otro trabajo avanza.
                    raw = act["raw"]
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.flush()
                    assert act["wait"].wait(timeout=20), "stale gate timeout"
                    self.wfile.write(raw)
                    self.wfile.flush()
                    if "done" in act:
                        act["done"].set()
                    return
                if act.get("wait") is not None:
                    assert act["wait"].wait(timeout=20), "stale gate timeout"
                if act.get("delay"):
                    time.sleep(act["delay"])
                if "raw" in act:
                    self._send_raw(200, act["raw"], "application/json")
                    if "done" in act:
                        act["done"].set()
                    return
                if act.get("status", 200) != 200:
                    self._send_json(act["status"], {"detail": "boom"})
                    return
                self._send_json(200, act["json"])
            finally:
                st["concurrent"] -= 1
            return
        self._send_json(404, {"detail": "unknown job"})

    def log_message(self, *args):  # silence test output
        pass


@pytest.fixture()
def live_v9():  # type: ignore[no-untyped-def]
    _V9Api.state = _fresh_state()
    up = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _V9Api)
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


@pytest.fixture()
def live_v9_ctrl():  # type: ignore[no-untyped-def]
    """URL más servidores expuestos: permite tumbar y revivir el frontend."""
    import types

    _V9Api.state = _fresh_state()
    up = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _V9Api)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    from app import frontend
    api_base = f"http://127.0.0.1:{up.server_port}"
    fe = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), frontend.create_handler(api_base))
    threading.Thread(target=fe.serve_forever, daemon=True).start()
    ns = types.SimpleNamespace(url=f"http://127.0.0.1:{fe.server_port}",
                               api=up, fe=fe, api_base=api_base,
                               fe_port=fe.server_port)
    try:
        yield ns
    finally:
        try:
            ns.fe.shutdown()
        except Exception:
            pass
        try:
            ns.fe.server_close()
        except Exception:
            pass
        up.shutdown()


def _revive_frontend(ns) -> None:  # type: ignore[no-untyped-def]
    """Levanta de nuevo el frontend en el mismo puerto tras tumbarlo."""
    import http.server

    from app import frontend

    ns.fe.server_close()
    ns.fe = http.server.ThreadingHTTPServer(
        ("127.0.0.1", ns.fe_port), frontend.create_handler(ns.api_base))
    threading.Thread(target=ns.fe.serve_forever, daemon=True).start()


def _kill_frontend(ns) -> None:  # type: ignore[no-untyped-def]
    ns.fe.shutdown()
    ns.fe.server_close()


def _wait_until(cond, timeout: float = 10.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < deadline, "timeout esperando a la página"
        time.sleep(0.05)


def _text(page, sel: str) -> str:  # type: ignore[no-untyped-def]
    return page.locator(sel).text_content() or ""


def _goto_submit(page, url: str, tmp_path: pathlib.Path,  # type: ignore[no-untyped-def]
                 name: str = "in.zip") -> None:
    page.goto(url + "/")
    zipp = tmp_path / name
    zipp.write_bytes(b"PK-fake-zip")
    page.set_input_files("#file", str(zipp))
    page.click("#send")


def _resubmit(page, tmp_path: pathlib.Path,  # type: ignore[no-untyped-def]
              name: str = "in2.zip") -> None:
    zipp = tmp_path / name
    zipp.write_bytes(b"PK-fake-zip-2")
    page.set_input_files("#file", str(zipp))
    page.click("#send")


def _wait_accepted(page, job: str) -> None:  # type: ignore[no-untyped-def]
    # La aceptación puede ser transitoria: la página consulta inmediatamente
    # al aceptar (V2-09) y el primer sondeo reemplaza el texto "trabajo
    # aceptado". Basta con aceptación registrada en el doble y actividad
    # visible; cada test espera además su contenido específico.
    _wait_until(lambda: job in _V9Api.state["accepted"])
    _wait_until(lambda: (_text(page, "#status") or "") != "")


# F1 ---------------------------------------------------------------------

def test_stale_poll_from_previous_job_is_ignored(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    release_a = threading.Event()
    _V9Api.state["poll_scripts"] = {
        "job-A": [{"wait": release_a, "json": dict(
            _completed("job-A"), processed=99, saved=99)}],
        "job-B": [{"json": _processing("job-B", 3)}] * 10,
    }
    _goto_submit(page, live_v9, tmp_path)
    _wait_accepted(page, "job-A")
    _resubmit(page, tmp_path)
    _wait_accepted(page, "job-B")
    _wait_until(lambda: "job-B-pic" in _text(page, "#current"))
    release_a.set()  # stale completed A arrives now
    page.wait_for_timeout(1200)
    assert "processing" in _text(page, "#status")
    assert "3/5" in _text(page, "#counters")
    assert not page.locator("#download").is_visible()
    assert _text(page, "#error") == ""


def test_stale_failed_poll_does_not_overwrite_current(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    release_a = threading.Event()
    _V9Api.state["poll_scripts"] = {
        "job-A": [{"wait": release_a, "json": {
            "job_id": "job-A", "status": "failed", "current": None,
            "processed": 0, "total": 5, "saved": 0, "review": 0,
            "error": "viejo roto"}}],
        "job-B": [{"json": _processing("job-B", 1)}],
    }
    _goto_submit(page, live_v9, tmp_path)
    _wait_accepted(page, "job-A")
    _resubmit(page, tmp_path)
    _wait_accepted(page, "job-B")
    release_a.set()
    page.wait_for_timeout(1200)
    assert "viejo roto" not in _text(page, "#error")
    assert "processing" in _text(page, "#status")


def test_stale_invalid_json_poll_does_not_stop_current(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    release_a = threading.Event()
    done_a = threading.Event()
    _V9Api.state["poll_scripts"] = {
        "job-A": [{"headers_first": True, "wait": release_a,
                     "raw": b"{no-json", "done": done_a}],
        # B sondea libre: su vista ya es visible cuando A resuelve el body.
        "job-B": [{"json": _processing("job-B", 2)}] * 10,
    }
    _goto_submit(page, live_v9, tmp_path)
    _wait_accepted(page, "job-A")
    _resubmit(page, tmp_path)
    _wait_accepted(page, "job-B")
    _wait_until(lambda: "job-B-pic" in _text(page, "#current"))
    # Baseline: B visible y sin error antes de liberar el body de A.
    assert _text(page, "#error") == ""
    release_a.set()  # el body inválido de A llega ahora, con B en curso
    assert done_a.wait(timeout=20), "A nunca respondió"
    page.wait_for_timeout(800)  # deja que la página procese la respuesta A
    assert _text(page, "#error") == ""
    _wait_until(lambda: "job-B-pic" in _text(page, "#current"))


# F2 ---------------------------------------------------------------------

def test_double_click_sends_once_then_resend_allowed(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    gate = threading.Event()
    _V9Api.state["accept_gate"] = gate
    page.goto(live_v9 + "/")
    zipp = tmp_path / "in.zip"
    zipp.write_bytes(b"PK-fake-zip")
    page.set_input_files("#file", str(zipp))
    page.evaluate("document.getElementById('send').click();"
                  "document.getElementById('send').click();")
    page.wait_for_timeout(600)
    assert _V9Api.state["posts"] == 1
    assert not page.locator("#send").is_enabled()
    gate.set()
    _wait_accepted(page, "job-A")
    assert page.locator("#send").is_enabled()
    _resubmit(page, tmp_path)
    _wait_accepted(page, "job-B")
    assert _V9Api.state["posts"] == 2


def test_polls_never_overlap(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    _V9Api.state["poll_delay"] = 1.4
    _goto_submit(page, live_v9, tmp_path)
    _wait_accepted(page, "job-A")
    page.wait_for_timeout(4500)
    assert _V9Api.state["max_concurrent"] == 1
    assert _V9Api.state["polls"] >= 2


# F3 ---------------------------------------------------------------------

def test_empty_selection_visible_without_request(page, live_v9):  # type: ignore[no-untyped-def]
    page.goto(live_v9 + "/")
    page.click("#send")
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".toLowerCase().includes('seleccion')", timeout=8000)
    assert _V9Api.state["posts"] == 0


def test_invalid_json_poll_readable_and_stops(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    _V9Api.state["poll_scripts"] = {"job-A": [{"raw": b"{no-json"}]}
    _goto_submit(page, live_v9, tmp_path)
    _wait_accepted(page, "job-A")
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".includes('consultar')", timeout=8000)
    before = _V9Api.state["polls"]
    page.wait_for_timeout(1500)
    assert _V9Api.state["polls"] == before
    assert page.locator("#send").is_enabled()


def test_poll_http_error_visible_stops_and_allows_retry(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    _V9Api.state["poll_scripts"] = {"job-A": [{"status": 500}]}
    _goto_submit(page, live_v9, tmp_path)
    _wait_accepted(page, "job-A")
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".includes('consulta falló: 500')", timeout=8000)
    before = _V9Api.state["polls"]
    page.wait_for_timeout(1500)
    assert _V9Api.state["polls"] == before
    _resubmit(page, tmp_path)
    _wait_accepted(page, "job-B")


def test_poll_connection_error_visible_and_stops(page, live_v9_ctrl, tmp_path):  # type: ignore[no-untyped-def]
    ns = live_v9_ctrl
    _goto_submit(page, ns.url, tmp_path)
    _wait_accepted(page, "job-A")
    _kill_frontend(ns)  # el próximo sondeo falla en el navegador
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".toLowerCase().includes('conexión')", timeout=8000)
    assert "consultar" in _text(page, "#error").lower()
    before = _V9Api.state["polls"]
    page.wait_for_timeout(1500)
    assert _V9Api.state["polls"] == before
    assert page.locator("#send").is_enabled()
    _revive_frontend(ns)
    _resubmit(page, tmp_path)
    _wait_accepted(page, "job-B")


def test_upload_errors_readable_and_allow_retry(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    _V9Api.state["accept_mode"] = "too-large"
    _goto_submit(page, live_v9, tmp_path)
    page.wait_for_function(
        "() => document.getElementById('error').textContent.includes('2 GiB')", timeout=8000)
    assert page.locator("#send").is_enabled()
    _V9Api.state["accept_mode"] = "http500"
    _resubmit(page, tmp_path, "in3.zip")
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".includes('envío falló: 500')", timeout=8000)
    _V9Api.state["accept_mode"] = "badjson"
    _resubmit(page, tmp_path, "in4.zip")
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".includes('aceptar')", timeout=8000)
    _V9Api.state["accept_mode"] = "ok"
    _resubmit(page, tmp_path, "in5.zip")
    _wait_accepted(page, "job-A")


def test_upload_connection_error_visible(page, live_v9_ctrl, tmp_path):  # type: ignore[no-untyped-def]
    ns = live_v9_ctrl
    page.goto(ns.url + "/")
    _kill_frontend(ns)  # el envío falla en el navegador
    zipp = tmp_path / "in.zip"
    zipp.write_bytes(b"PK-fake-zip")
    page.set_input_files("#file", str(zipp))
    page.click("#send")
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".toLowerCase().includes('conexión')", timeout=8000)
    assert "enviar" in _text(page, "#error").lower()
    assert page.locator("#send").is_enabled()
    assert _V9Api.state["posts"] == 0
    _revive_frontend(ns)
    _resubmit(page, tmp_path, "in2.zip")
    _wait_accepted(page, "job-A")


# F4 ---------------------------------------------------------------------

def test_download_keeps_original_uuid_after_switch(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    _V9Api.state["poll_scripts"] = {
        "job-A": [{"json": _completed("job-A")}],
        "job-B": [{"json": _processing("job-B", 2)}],
    }
    _V9Api.state["results"] = {"job-A": {"delay": 2.0, "body": b"BYTES-A"}}
    _goto_submit(page, live_v9, tmp_path)
    _wait_accepted(page, "job-A")
    page.locator("#download").wait_for(state="visible")
    with page.expect_download(timeout=15000) as dl_info:
        page.click("#download")
        _resubmit(page, tmp_path)  # switch visible job while A downloads
        _wait_accepted(page, "job-B")
    download = dl_info.value
    assert download.suggested_filename == "job-A.zip"
    assert pathlib.Path(str(download.path())).read_bytes() == b"BYTES-A"
    assert "processing" in _text(page, "#status")


def test_download_410_expired_and_404_absent_without_new_tab(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    _V9Api.state["poll_scripts"] = {
        "job-A": [{"json": _completed("job-A")}],
        "job-B": [{"json": _completed("job-B")}],
    }
    _V9Api.state["results"] = {"job-A": {"status": 410},
                               "job-B": {"status": 404}}
    _goto_submit(page, live_v9, tmp_path)
    _wait_accepted(page, "job-A")
    page.locator("#download").wait_for(state="visible")
    before_pages = len(page.context.pages)
    page.click("#download")
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".includes('vencido')", timeout=8000)
    assert len(page.context.pages) == before_pages
    _resubmit(page, tmp_path)
    _wait_accepted(page, "job-B")
    page.locator("#download").wait_for(state="visible")
    page.click("#download")
    page.wait_for_function(
        "() => /ausente|limpiado/.test("
        "document.getElementById('error').textContent)", timeout=8000)
    assert len(page.context.pages) == before_pages
    assert page.locator("#send").is_enabled()


def test_no_download_for_queued_processing_failed(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    _goto_submit(page, live_v9, tmp_path)
    _wait_accepted(page, "job-A")
    assert not page.locator("#download").is_visible()
    _wait_until(lambda: "processing" in _text(page, "#status"))
    assert not page.locator("#download").is_visible()
    _V9Api.state["poll_scripts"] = {"job-B": [{"json": {
        "job_id": "job-B", "status": "failed", "current": None,
        "processed": 1, "total": 5, "saved": 0, "review": 0,
        "error": "motor roto"}}]}
    _resubmit(page, tmp_path)
    _wait_accepted(page, "job-B")
    page.wait_for_function(
        "() => document.getElementById('error').textContent"
        ".includes('motor roto')", timeout=8000)
    assert not page.locator("#download").is_visible()


def test_html_in_names_and_errors_is_inert_text(page, live_v9, tmp_path):  # type: ignore[no-untyped-def]
    evil_current = "<img src=x onerror=alert(1)>"
    evil_error = "<script>alert(1)</script>"
    _V9Api.state["poll_scripts"] = {"job-A": [
        {"json": dict(_processing("job-A", 1), current=evil_current)},
        {"json": {"job_id": "job-A", "status": "failed", "current": None,
                  "processed": 1, "total": 5, "saved": 0, "review": 0,
                  "error": evil_error}},
    ]}
    _goto_submit(page, live_v9, tmp_path)
    _wait_accepted(page, "job-A")
    page.wait_for_function(
        "() => document.getElementById('current').textContent.includes('<img')", timeout=8000)
    assert page.locator("#current img").count() == 0
    page.wait_for_function(
        "() => document.getElementById('error').textContent.includes('<script>')", timeout=8000)
    assert page.locator("#error script").count() == 0
    assert page.locator("#error img").count() == 0


# Página y README (sin navegador) ------------------------------------------

def test_page_hints_single_job_and_safe_rendering():
    text = (pathlib.Path(__file__).resolve().parent.parent
            / "frontend" / "index.html").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "jpeg" in lowered and "raíz" in lowered
    assert "2 GiB" in text
    assert "tres horas" in lowered or "3 h" in lowered
    assert "textContent" in text
    assert "disabled" in text


def test_readme_covers_profiles_recovery_and_limits():
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    text = (root / "README.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "--profile v1" in text
    assert "docker compose --profile v1 up" in text
    assert "blob()" in text
    assert "8080" in text
    for token in ("interrump", "vencid", "fallid", "logs", "limpi"):
        assert token in lowered, token
    blocks = re.findall(r"```bash(.*?)```", text, re.S)
    hub = [b for b in blocks
           if "compose.hub.yaml" in b and "buildx" not in b]
    assert hub, "bloque Docker Hub V2 ausente"
    assert all("--profile" not in b for b in hub), \
        "el stack Hub V2 no debe activar el perfil v1"
    v1_ups = [b for b in blocks
              if "up -d --build" in b and "compose.hub.yaml" not in b
              and "autocrop --input" in b]
    assert v1_ups, "bloques de arranque V1 ausentes"
    assert all("--profile v1" in b for b in v1_ups), \
        "el arranque V1 debe usar su perfil explícito"


def test_wrapper_starts_v1_service_before_exec():
    root = pathlib.Path(__file__).resolve().parent.parent
    wrapper = (root / "autocrop-run").read_text(encoding="utf-8")
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    assert 'profiles: ["v1"]' in compose or "profiles: ['v1']" in compose
    up_lines = [ln for ln in wrapper.splitlines()
                if "docker compose" in ln and " up" in ln]
    assert up_lines, "el wrapper no levanta Compose"
    assert all("--profile v1" in ln for ln in up_lines), \
        "el wrapper debe arrancar el perfil v1 antes de docker exec autocrop"
    assert "docker exec" in wrapper and "autocrop autocrop" in wrapper
