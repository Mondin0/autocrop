"""Tests for V2-06: default Compose boot without host data folders.

Covers F1-F4/T1 of .plans/v2/06-compose-sin-datos-host/plan.md.
No YOLO, no network, no real photos: static config + docs assertions.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
V2_DEFAULT = {"api", "worker", "frontend", "redis", "rustfs"}


def compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def default_services(doc: dict) -> set[str]:
    return {n for n, s in doc["services"].items() if not s.get("profiles")}


def volume_entries(svc: dict) -> list:
    return svc.get("volumes") or []


def test_f1_default_services_are_v2_only():
    assert default_services(compose()) == V2_DEFAULT


def test_f1_default_config_lists_only_v2():
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available")
    proc = subprocess.run(["docker", "compose", "config", "--services"],
                          cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert set(proc.stdout.split()) == V2_DEFAULT


def test_f1_v2_services_have_no_host_data_bind_mounts():
    doc = compose()
    for name in V2_DEFAULT:
        for vol in volume_entries(doc["services"][name]):
            text = str(vol).lower()
            assert "fotos" not in text and "output" not in text, (name, vol)
            if isinstance(vol, dict):
                assert vol.get("type", "volume") != "bind" or (
                    "fotos" not in str(vol.get("source", "")).lower()
                    and "output" not in str(vol.get("source", "")).lower()
                ), (name, vol)


def test_f2_v1_service_behind_v1_profile_keeps_mounts():
    svc = compose()["services"]["autocrop"]
    assert svc.get("profiles") == ["v1"]
    targets = {v["target"]: v for v in volume_entries(svc)}
    assert targets["/input"].get("read_only") is True
    assert "/output" in targets


def test_f2_v1_profile_enables_v1_service():
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available")
    proc = subprocess.run(["docker", "compose", "--profile", "v1",
                           "config", "--services"],
                          cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert set(proc.stdout.split()) == (V2_DEFAULT | {"autocrop"})


def test_f3_weights_from_checkout_without_download_or_dep_change():
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY yolo11n.pt" in docker
    assert not re.search(r"curl.*\.pt|wget.*\.pt", docker)


def test_f4_named_volumes_and_readme_down_semantics():
    doc = compose()
    assert {"redis-data", "rustfs-data"} <= set(doc.get("volumes", {}))
    mounts = {n: volume_entries(doc["services"][n]) for n in ("redis", "rustfs")}
    assert any("redis-data" in str(m) for m in mounts["redis"])
    assert any("rustfs-data" in str(m) for m in mounts["rustfs"])
    text = readme()
    assert "docker compose down" in text and "docker compose down -v" in text
    assert "redis-data" in text and "rustfs-data" in text


def test_f5_readme_v2_needs_no_env_nor_host_dirs():
    text = readme()
    v2 = text.split("Demo local V2", 1)[1]
    assert "docker compose up -d --build" in v2
    assert "http://localhost:8080" in v2
    prep = v2.split("### Levantar", 1)[0]
    assert "mkdir -p fotos output" not in prep
    assert "cp .env.example .env" not in prep
    lowered = prep.lower()
    assert "no necesita" in lowered and ".env" in prep
    assert "fotos/" in prep and "output/" in prep  # mentioned as not required
    assert "--profile v1" in v2  # V1 stays available explicitly


def test_t1_loopback_ports_and_no_host_network():
    services = compose()["services"]
    publishers = {n: s for n, s in services.items() if s.get("ports")}
    assert set(publishers) == {"api", "frontend"}
    for mapping in publishers["api"]["ports"] + publishers["frontend"]["ports"]:
        assert str(mapping).startswith("127.0.0.1:"), mapping
    for svc in services.values():
        assert svc.get("network_mode") != "host"
