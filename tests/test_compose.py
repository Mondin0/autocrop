"""Tests for V2-04 local Docker Compose architecture (contract first)."""

from __future__ import annotations

import ast
import io
import pathlib
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile

import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image

import app.archive as archive
from app import runtime, serve, worker
from app.jobs import JobService, MemoryBlobStore, MemoryStateStore

ROOT = pathlib.Path(__file__).resolve().parent.parent


def compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def env_example() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def compose_referenced_vars(text: str) -> set[str]:
    return set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-.*?)?\}", text))


def make_jpg_bytes(width=800, height=600, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "JPEG")
    return buf.getvalue()


def two_photo_zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("b.jpg", make_jpg_bytes(500, 500, color=(10, 200, 10)))
        zf.writestr("a.jpg", make_jpg_bytes(800, 600))
    return buf.getvalue()


def fake_process(in_path, out_path, detector=None, ratio=None, margin=0.15,
                 on_progress=None):
    if on_progress is not None:
        on_progress({"current": None, "processed": 0, "total": 2,
                     "saved": 0, "review": 0})
        on_progress({"current": None, "processed": 2, "total": 2,
                     "saved": 1, "review": 1})
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.jpg", b"crop-a")
        zf.writestr("review/", b"")
    return {"processed": 2, "saved": 1, "review": 1, "skipped": 0}


class StubDetector:
    def detect_people(self, image):
        return []


# F1 ---------------------------------------------------------------------

def test_f1_compose_config_validates():
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available")
    proc = subprocess.run(["docker", "compose", "config"], cwd=ROOT,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr


def test_f1_expected_services_present():
    services = compose()["services"]
    assert {"api", "worker", "redis", "rustfs"} <= set(services)
    assert "autocrop" in services  # V1 config still available (F6)


def test_f1_v1_service_unchanged():
    svc = compose()["services"]["autocrop"]
    assert svc["image"] == "autocrop:latest"
    assert svc["command"] == ["sleep", "infinity"]
    targets = {v["target"]: v for v in svc["volumes"]}
    assert targets["/input"].get("read_only") is True
    assert "/output" in targets


# T1 ---------------------------------------------------------------------

def test_t1_api_worker_share_app_version():
    services = compose()["services"]
    api, worker_svc = services["api"], services["worker"]
    assert api["build"] == worker_svc["build"]
    assert api["image"] == worker_svc["image"]


def test_t1_healthchecks_and_ready_dependencies():
    services = compose()["services"]
    for name in ("redis", "rustfs"):
        check = services[name].get("healthcheck", {})
        assert "test" in check and check["test"], f"{name} needs a healthcheck"
    for name in ("api", "worker"):
        deps = services[name].get("depends_on", {})
        assert deps.get("redis", {}).get("condition") == "service_healthy"
        assert deps.get("rustfs", {}).get("condition") == "service_healthy"


# F2 ---------------------------------------------------------------------

def test_f2_only_api_publishes_loopback_port():
    services = compose()["services"]
    publishers = {n: s for n, s in services.items() if s.get("ports")}
    assert set(publishers) == {"api"}
    for mapping in publishers["api"]["ports"]:
        assert str(mapping).startswith("127.0.0.1:"), mapping
    for svc in services.values():
        assert svc.get("network_mode") != "host"


# F3 ---------------------------------------------------------------------

def test_f3_wiring_reuses_engine_and_runs_cycle():
    svc = runtime.build_service(
        state=MemoryStateStore(), blobs=MemoryBlobStore(),
        process_fn=fake_process)
    assert svc.process_fn is fake_process
    default_svc = runtime.build_service(
        state=MemoryStateStore(), blobs=MemoryBlobStore())
    assert default_svc.process_fn is archive.process_archive
    app = serve.create_local_app(
        state=svc.state, blobs=svc.blobs)
    client = TestClient(app)
    r = client.post("/api/jobs",
                    files={"file": ("in.zip", two_photo_zip_bytes(),
                                     "application/zip")})
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert worker.pump_once(svc, StubDetector()) is True
    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == "completed"
    assert (body["processed"], body["total"]) == (2, 2)
    dl = client.get(f"/api/jobs/{job_id}/result")
    assert dl.status_code == 200
    assert dl.content == svc.blobs.get(f"jobs/{job_id}/output.zip")


def test_f3_serve_routes_with_rejected_and_unknown_ids():
    svc = runtime.build_service(
        state=MemoryStateStore(), blobs=MemoryBlobStore(),
        process_fn=fake_process)
    client = TestClient(serve.create_local_app(
        state=svc.state, blobs=svc.blobs))
    r = client.post("/api/jobs", files={"upload": ("in.zip", b"data")})
    assert r.status_code == 422
    import uuid as _uuid
    assert client.get(f"/api/jobs/{_uuid.uuid4()}").status_code == 404


class _DownRedis:
    def ping(self):
        raise ConnectionError("redis-down")


class _UpRedis:
    def ping(self):
        return True


class _MissingBucketS3:
    def __init__(self):
        self.created: list[str] = []

    def head_bucket(self, Bucket):
        raise RuntimeError("404 Not Found")

    def create_bucket(self, Bucket):
        self.created.append(Bucket)
        return {}


class _DownS3:
    def head_bucket(self, Bucket):
        raise ConnectionError("rustfs-down")


def test_f3_wait_ready_ok_and_timeout_names_service():
    runtime.wait_for_ready(_UpRedis(), None, "autocrop", sleep=lambda s: None)
    with pytest.raises(TimeoutError, match="(?i)redis"):
        runtime.wait_for_ready(_DownRedis(), None, "autocrop",
                               timeout=0, sleep=lambda s: None)
    with pytest.raises(TimeoutError, match="(?i)rustfs"):
        runtime.wait_for_ready(None, _DownS3(), "autocrop",
                               timeout=0, sleep=lambda s: None)


def test_f3_ensure_bucket_creates_missing_only():
    s3 = _MissingBucketS3()
    runtime.ensure_bucket(s3, "autocrop")
    assert s3.created == ["autocrop"]

    class _Present(_MissingBucketS3):
        def head_bucket(self, Bucket):
            return {}

    present = _Present()
    runtime.ensure_bucket(present, "autocrop")
    assert present.created == []
    with pytest.raises(ConnectionError):
        runtime.ensure_bucket(_DownS3(), "autocrop")


# F4 ---------------------------------------------------------------------

def test_f4_named_volumes_mounted_for_state_and_objects():
    doc = compose()
    assert {"redis-data", "rustfs-data"} <= set(doc.get("volumes", {}))
    mounts = {"redis": doc["services"]["redis"].get("volumes", []),
              "rustfs": doc["services"]["rustfs"].get("volumes", [])}
    assert any(str(m).startswith("redis-data:") for m in mounts["redis"])
    assert any(str(m).startswith("rustfs-data:") for m in mounts["rustfs"])


def test_f4_idle_pump_runs_expiration_cleanup():
    cleaned: list[str] = []

    class _Svc(JobService):
        def cleanup(self):
            cleaned.append("ran")
            return 0

    svc = _Svc(MemoryStateStore(), MemoryBlobStore(), process_fn=fake_process)
    assert worker.pump_once(svc, StubDetector()) is False
    assert cleaned == ["ran"]


# F5 ---------------------------------------------------------------------

def test_f5_env_documented_without_real_secrets():
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    example = env_example()
    missing = compose_referenced_vars(text) - set(example)
    assert not missing, f"undocumented vars: {sorted(missing)}"
    secret = example.get("AUTOCROP_S3_SECRET_KEY", "")
    assert len(secret) >= 8
    assert "local" in secret.lower() or "change" in secret.lower()
    assert example.get("AUTOCROP_S3_ACCESS_KEY", "")
    assert example.get("AUTOCROP_API_PORT", "").isdigit()


def test_f5_settings_defaults_and_overrides():
    defaults = runtime.Settings.from_env({})
    assert defaults.redis_url.startswith("redis://")
    assert defaults.s3_endpoint.startswith("http://")
    assert defaults.s3_bucket
    custom = runtime.Settings.from_env({
        "AUTOCROP_REDIS_URL": "redis://other:6380/2",
        "AUTOCROP_S3_ENDPOINT": "http://other:9000",
        "AUTOCROP_S3_BUCKET": "other",
        "AUTOCROP_S3_ACCESS_KEY": "key",
        "AUTOCROP_S3_SECRET_KEY": "secret-value",
    })
    assert custom.redis_url == "redis://other:6380/2"
    assert custom.s3_bucket == "other"


# F6 ---------------------------------------------------------------------

def test_f6_readme_documents_demo_and_keeps_v1():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docker compose up" in text and "--build" in text
    assert "localhost" in text
    assert "docker compose logs" in text
    assert "docker compose down" in text
    assert "docker exec" in text and "autocrop --input /input" in text


# Image ------------------------------------------------------------------

def test_image_installs_v2_deps_and_keeps_cpu_entry():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for dep in ("uvicorn", "redis", "boto3"):
        assert dep in text
    assert 'CMD ["sleep", "infinity"]' in text
    assert "yolo11n.pt" in text
    assert not re.search(r"curl.*\.pt|wget.*\.pt", text)


def test_entrypoints_serve_and_pump_without_startup_processing():
    services = compose()["services"]
    api_cmd = " ".join(services["api"]["command"])
    worker_cmd = " ".join(services["worker"]["command"])
    assert "app.serve" in api_cmd
    assert "app.worker" in worker_cmd
    assert "process_archive" not in api_cmd + worker_cmd


# Packaging (director correction round) -----------------------------------

_MODULE_TO_DISTRO = {
    "yaml": "pyyaml",
    "PIL": "Pillow",
    "multipart": "python-multipart",
    "botocore": "boto3",
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _third_party_imports(directory: pathlib.Path) -> set[str]:
    found: set[str] = set()
    for path in sorted(directory.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif (isinstance(node, ast.ImportFrom) and node.level == 0
                    and node.module):
                found.add(node.module.split(".")[0])
    found -= set(sys.stdlib_module_names) | {"app"}
    return {_norm(_MODULE_TO_DISTRO.get(m, m)) for m in found}


def _declared() -> tuple[set[str], set[str]]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(
        encoding="utf-8"))

    def names(reqs: list[str]) -> set[str]:
        return {_norm(re.split(r"[ ;\[=<>!~]", r, 1)[0]) for r in reqs}

    project = data["project"]
    return (names(project["dependencies"]),
            names(project["optional-dependencies"]["dev"]))


def test_packaging_runtime_deps_declared():
    deps, _ = _declared()
    assert _third_party_imports(ROOT / "app") <= deps


def test_packaging_test_deps_declared():
    deps, dev = _declared()
    assert _third_party_imports(ROOT / "tests") <= (deps | dev)


def _dockerfile_installs() -> set[str]:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    found = {_norm(m) for m in re.findall(r'"([A-Za-z0-9_.-]+)', text)}
    if "download.pytorch.org" in text:
        found |= {"torch", "torchvision"}
    return found


def test_packaging_dockerfile_installs_declared_deps():
    deps, _ = _declared()
    assert deps <= _dockerfile_installs()


def test_packaging_dev_includes_test_transport():
    _, dev = _declared()
    assert "httpx" in dev  # starlette TestClient needs it at test runtime


# API log clarification (director correction round) ------------------------

def test_api_uncontracted_paths_are_404():
    svc = runtime.build_service(
        state=MemoryStateStore(), blobs=MemoryBlobStore(),
        process_fn=fake_process)
    client = TestClient(serve.create_local_app(
        state=svc.state, blobs=svc.blobs))
    for path in ("/health", "/", "/api"):
        assert client.get(path).status_code == 404, path
