"""V2-11: despliegue simple desde el Compose principal (sin overlay).

F1/F2/F3/T1/T2: api/worker/frontend usan AUTOCROP_IMAGE con default
mondin0/autocrop:latest; .env/.env.example declaran latest; no existe
compose.hub.yaml; README documenta los dos comandos exactos sin overlay
y conserva el arranque V1 con perfil. Sin red ni Docker Hub.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLISHED = "mondin0/autocrop:latest"
IMAGE_REF = "${AUTOCROP_IMAGE:-mondin0/autocrop:latest}"
V2_SERVICES = ("api", "worker", "frontend")


def _compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def _env_file(name: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def test_v2_services_use_published_image_default():
    services = _compose()["services"]
    for name in V2_SERVICES:
        assert services[name]["image"] == IMAGE_REF, name
    # build local conservado para desarrollo
    for name in V2_SERVICES:
        assert services[name].get("build"), name


def test_env_and_example_default_latest():
    for name in (".env", ".env.example"):
        assert _env_file(name)["AUTOCROP_IMAGE"] == PUBLISHED, name


def test_v1_and_infra_unchanged():
    services = _compose()["services"]
    v1 = services["autocrop"]
    assert v1["image"] == "autocrop:latest"
    assert v1["command"] == ["sleep", "infinity"]
    assert "v1" in v1.get("profiles", [])
    assert v1.get("build")
    assert services["redis"]["image"] == "redis:7-alpine"
    assert services["rustfs"]["image"] == "rustfs/rustfs:1.0.1-glibc"
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    for name in ("redis", "rustfs", "autocrop"):
        block = str(services[name])
        assert "AUTOCROP_IMAGE" not in block, name
    assert "AUTOCROP_IMAGE" in text  # solo los tres servicios V2


def test_no_hub_overlay_and_readme_commands():
    assert not (ROOT / "compose.hub.yaml").exists()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "compose.hub.yaml" not in readme
    assert "docker compose up -d --pull always" in readme
    assert "docker compose up -d --build" in readme
    assert "AUTOCROP_IMAGE=tu-usuario" not in readme
    assert "export AUTOCROP_IMAGE" not in readme
    assert "docker compose --profile v1 up -d --build" in readme


def _compose_config(extra_env: dict[str, str] | None = None) -> dict:
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["docker", "compose", "--profile", "v1", "config"], cwd=ROOT,
        capture_output=True, text=True, timeout=120, env=env)
    assert proc.returncode == 0, proc.stderr
    return yaml.safe_load(proc.stdout)


def test_compose_config_resolves_published_default():
    config = _compose_config()
    services = config["services"]
    for name in V2_SERVICES:
        assert services[name]["image"] == PUBLISHED, name
    assert services["autocrop"]["image"] == "autocrop:latest"


def test_compose_config_override_propagates_to_v2():
    override = "example/autocrop:override-1"
    config = _compose_config({"AUTOCROP_IMAGE": override})
    services = config["services"]
    for name in V2_SERVICES:
        assert services[name]["image"] == override, name
    assert services["autocrop"]["image"] == "autocrop:latest"


def test_readme_hub_section_without_overlay_or_push():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "-f compose" not in readme
    assert "compose.hub.yaml" not in readme.lower()
    for token in ("--push", "docker push", "buildx"):
        assert token not in readme, token


def test_dockerfile_pins_kept():
    dockerfile = (ROOT / "Dockerfile").read_text()
    for pin in (
        "torch==2.14.1", "torchvision==0.29.1", "ultralytics==8.4.174",
        "Pillow==12.3.0", "fastapi==0.143.0",
        "python-multipart==0.0.32", "uvicorn==0.54.0",
        "redis==8.1.0", "boto3==1.43.111",
    ):
        assert pin in dockerfile
    assert "--index-url https://download.pytorch.org/whl/cpu" in dockerfile
    assert "rustfs/rustfs:1.0.1-glibc" in (ROOT / "compose.yaml").read_text()
