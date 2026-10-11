from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_hub_override_uses_required_image_without_builds():
    config = yaml.safe_load((ROOT / "compose.hub.yaml").read_text())
    services = config["services"]
    assert set(services) == {"autocrop", "api", "worker", "frontend"}
    for service in services.values():
        assert service["image"] == "${AUTOCROP_IMAGE:?Set AUTOCROP_IMAGE}"
        assert service["build"] is None


def test_dockerfile_pins_direct_dependencies_and_keeps_cpu_torch():
    dockerfile = (ROOT / "Dockerfile").read_text()
    for pin in (
        "torch==2.14.1", "torchvision==0.29.1", "ultralytics==8.4.174",
        "Pillow==12.3.0", "fastapi==0.143.0",
        "python-multipart==0.0.32", "uvicorn==0.54.0",
        "redis==8.1.0", "boto3==1.43.111",
    ):
        assert pin in dockerfile
    assert "--index-url https://download.pytorch.org/whl/cpu" in dockerfile


def test_compose_pins_rustfs_release():
    config = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert config["services"]["rustfs"]["image"] == "rustfs/rustfs:1.0.1-glibc"


def test_readme_documents_multiarch_tags_and_hub_compose():
    readme = (ROOT / "README.md").read_text()
    assert "linux/amd64,linux/arm64" in readme
    assert "tu-usuario/autocrop:0.1.0" in readme
    assert "tu-usuario/autocrop:latest" in readme
    assert "-f compose.hub.yaml" in readme
