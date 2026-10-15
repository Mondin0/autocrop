"""Aceptación V2-10: puertas automáticas sin fotos reales ni Compose.

F2 y las pruebas con corpus real son bloqueos manuales descritos en
registro.md, sin test placeholder. El recorrido con Compose real +
Playwright MCP y el ZIP grande se registran en registro.md, no aquí.
"""

from __future__ import annotations

import io
import pathlib
import zipfile

import pytest

import app.archive as archive
import app.jobs as jobs_mod
from app.jobs import JobService, MemoryBlobStore, MemoryStateStore

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "v210_support", pathlib.Path(__file__).resolve().parent / "v210_support.py")
assert _spec is not None and _spec.loader is not None
sup = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(sup)

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _zip_bytes(payload: bytes = b"data") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.jpg", payload)
    return buf.getvalue()


def _ok_process(in_path, out_path, detector=None, ratio=None, margin=0.15,
                on_progress=None):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.jpg", b"crop")
        zf.writestr("review/", b"")
    return {"processed": 1, "saved": 1, "review": 0, "skipped": 0}


# T1 (puertas de contrato; la validación de entorno va en registro) --


# T2 ------------------------------------------------------------------


def test_v210_compose_publishes_only_loopback():
    import yaml
    doc = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    pubs = {n: s for n, s in doc["services"].items() if s.get("ports")}
    assert set(pubs) == {"api", "frontend"}
    for svc in pubs.values():
        for mapping in svc["ports"]:
            assert str(mapping).startswith("127.0.0.1:"), mapping


def test_v210_isolated_override_uses_free_loopback_ports(tmp_path):
    import socket
    # Ambos sockets abiertos a la vez: el SO no puede reutilizar el mismo
    # puerto al cerrar el primero antes de asignar el segundo.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s1, \
            socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
        s1.bind(("127.0.0.1", 0))
        s2.bind(("127.0.0.1", 0))
        api_port = int(s1.getsockname()[1])
        fe_port = int(s2.getsockname()[1])
    assert api_port != fe_port
    assert api_port not in (8000, 8080)
    assert fe_port not in (8000, 8080)
    out = sup.write_isolated_override(str(tmp_path / "override.yaml"),
                                      api_port, fe_port)
    text = pathlib.Path(out).read_text(encoding="utf-8")
    assert "!override" in text, "el override debe reemplazar, no fusionar puertos"
    for mapping in (f"127.0.0.1:{api_port}:8000",
                    f"127.0.0.1:{fe_port}:8080"):
        assert mapping in text, mapping
    assert "127.0.0.1:8000:" not in text and "127.0.0.1:8080:" not in text
    import socket
    for port in (api_port, fe_port):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass
        except OSError:
            continue  # libre: nadie escucha
        pytest.fail(f"puerto {port} ocupado; debe estar libre")


def test_v210_proxy_upload_timeout_supports_2gib(monkeypatch):
    """El proxy debe tolerar subidas de 2 GiB (medido: 113s solo API).

    Sin red ni ZIP gigante: se stubea HTTPConnection y se captura el
    timeout usado al proxear un POST con cuerpo.
    """
    import http.client
    import http.server
    import threading
    import urllib.request
    from app import frontend as fe_mod

    seen: dict = {}

    class _Resp:
        status = 202

        def getheader(self, name, default=None):
            return None

        def read(self, n=-1):
            return b""

    class _Conn:
        debuglevel = 0

        def __init__(self, host, port=None, timeout=None):
            seen["timeout"] = timeout

        def putrequest(self, *a, **k):
            pass

        def putheader(self, *a, **k):
            pass

        def endheaders(self):
            pass

        def send(self, data):
            pass

        def getresponse(self):
            return _Resp()

        def close(self):
            pass

    monkeypatch.setattr(http.client, "HTTPConnection", _Conn)
    handler = fe_mod.create_handler("http://127.0.0.1:9")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        import socket as _sock
        body = b"x" * 64
        with _sock.create_connection(("127.0.0.1", srv.server_port),
                                     timeout=30) as sock:
            sock.sendall(b"POST /api/jobs HTTP/1.1\r\nHost: x\r\n"
                         b"Content-Type: application/octet-stream\r\n"
                         b"Content-Length: " + str(len(body)).encode()
                         + b"\r\nConnection: close\r\n\r\n" + body)
            resp = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                resp += chunk
        assert resp.split(b"\r\n", 1)[0].endswith(b"202 Accepted"), resp[:60]
    finally:
        srv.shutdown()
    assert (seen.get("timeout") or 0) >= 300, seen


def test_v210_isolated_override_uniquifies_all_container_names(tmp_path):
    out = sup.write_isolated_override(
        str(tmp_path / "override.yaml"), 36063, 53619, prefix="autocrop-v210")
    text = pathlib.Path(out).read_text(encoding="utf-8")
    for svc in ("api", "worker", "frontend", "redis", "rustfs"):
        assert f"autocrop-v210-{svc}" in text, svc
    for default in ("autocrop-api", "autocrop-worker", "autocrop-frontend",
                    "autocrop-redis", "autocrop-rustfs"):
        assert default not in text.replace("autocrop-v210-", ""), default


# F5 (puerta unitaria; la medición real va a registro.md) --------------


def test_v210_upload_limit_constants():
    assert jobs_mod.MAX_UPLOAD_BYTES == 2 * 1024 * 1024 * 1024 == 2147483648
    assert archive.MAX_INPUT_BYTES == 2 * 1024 * 1024 * 1024 == 2147483648
    assert jobs_mod.RESULT_TTL_SECONDS == 3 * 3600


def test_v210_limit_boundary_exact_accepts_plus_one_rejects():
    now = [1000.0]
    svc = JobService(MemoryStateStore(), MemoryBlobStore(),
                     now=lambda: now[0], process_fn=_ok_process,
                     max_upload_bytes=32)
    assert svc.submit(b"x" * 32)["status"] == "queued"
    with pytest.raises(jobs_mod.TooLargeError):
        svc.submit(b"x" * 33)
    from fastapi.testclient import TestClient
    from app.jobs import create_app
    client = TestClient(create_app(svc), raise_server_exceptions=False)
    assert client.post("/api/jobs", files={"file": ("a.zip", b"x" * 32,
                                                    "application/zip")}
                       ).status_code == 202
    assert client.post("/api/jobs", files={"file": ("b.zip", b"x" * 33,
                                                    "application/zip")}
                       ).status_code == 413
    assert len(svc.state.ids()) == 2  # solo los dos exactos aceptados


def test_v210_frontend_states_2gib_limit():
    text = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "2 GiB" in text
    assert "500 MiB" not in text


def test_v210_sized_zip_root_jpegs_and_hash(tmp_path):
    dest = str(tmp_path / "sized.zip")
    info = sup.build_sized_zip(dest, 2 * 1024 * 1024)
    assert info["size"] >= 2 * 1024 * 1024
    assert info["entries"] >= 2
    with zipfile.ZipFile(dest) as zf:
        assert zf.testzip() is None
        for name in zf.namelist():
            assert "/" not in name and "\\" not in name, name
            assert name.lower().endswith((".jpg", ".jpeg")), name
    import hashlib
    assert (hashlib.sha256(pathlib.Path(dest).read_bytes()).hexdigest()
            == info["sha256"])


# F3 ------------------------------------------------------------------


def test_v210_invalid_and_nested_rejected(tmp_path):
    class _Det:
        def detect_people(self, image):
            return []

    def _jpeg(color=(10, 20, 30)):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (16, 16), color).save(buf, "JPEG")
        return buf.getvalue()

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("a.txt", b"no jpeg here")
    with pytest.raises(ValueError):
        archive.process_archive(bad, tmp_path / "o1.zip", _Det())
    nested = tmp_path / "nested.zip"
    with zipfile.ZipFile(nested, "w") as zf:
        zf.writestr("b.jpg", _jpeg((10, 20, 30)))
        zf.writestr("sub/nested.jpg", _jpeg((200, 10, 10)))
    out = tmp_path / "o3.zip"
    with pytest.raises(ValueError, match="unsafe entry name"):
        archive.process_archive(nested, out, _Det())
    assert not out.exists()


def test_v210_api_rejects_oversize_before_accepting():
    now = [1000.0]
    svc = JobService(MemoryStateStore(), MemoryBlobStore(),
                     now=lambda: now[0], process_fn=_ok_process,
                     max_upload_bytes=32)
    with pytest.raises(jobs_mod.TooLargeError):
        svc.submit(b"x" * 33)
    assert svc.state.ids() == []
    from fastapi.testclient import TestClient
    from app.jobs import create_app
    client = TestClient(create_app(svc), raise_server_exceptions=False)
    r = client.post("/api/jobs", files={"file": ("in.zip", b"x" * 33,
                                                 "application/zip")})
    assert r.status_code == 413
    assert svc.state.ids() == []
    assert svc.blobs.keys() == []


# F4 ------------------------------------------------------------------


def test_v210_ttl_410_then_404_with_clock():
    from fastapi.testclient import TestClient
    from app.jobs import create_app
    now = [2000.0]
    svc = JobService(MemoryStateStore(),
                     MemoryBlobStore(now=lambda: now[0]),
                     now=lambda: now[0], process_fn=_ok_process)
    jid = svc.submit(_zip_bytes())["job_id"]
    svc.run_next()
    client = TestClient(create_app(svc))
    assert client.get(f"/api/jobs/{jid}/result").status_code == 200
    now[0] += jobs_mod.RESULT_TTL_SECONDS + 1
    assert client.get(f"/api/jobs/{jid}/result").status_code == 410
    assert svc.cleanup() == 1
    assert client.get(f"/api/jobs/{jid}/result").status_code == 404


# F1/F6 ---------------------------------------------------------------


def test_v210_readme_documents_flow():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for needle in ("docker compose up", "--build", "localhost:8080",
                   "Response.blob()", "curl", "docker compose down"):
        assert needle in text, needle
