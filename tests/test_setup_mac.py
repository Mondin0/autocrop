"""Setup portable en Mac (etapa 07).

Verifica pins probados, ``setup-mac.sh`` de un comando (python3.12,
hash de pesos, --help y humo sintético en temporales) y la sección
Mac del README. Sin cambios en el pipeline de detección/crop.
"""

from __future__ import annotations

from collections.abc import Iterator
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "setup-mac.sh"
EXPECTED_HASH = (
    "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"
)
EXPECTED_PINS = {
    "ultralytics==8.4.174",
    "Pillow==12.3.0",
    "torch==2.14.1",
    "torchvision==0.29.1",
}
SetupCopy = tuple[pathlib.Path, dict[str, str]]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_bytes().decode("utf-8"))


def _script_text() -> str:
    assert SCRIPT.is_file(), "setup-mac.sh missing (etapa 07 pendiente)"
    return SCRIPT.read_text(encoding="utf-8")


def test_pyproject_pins_tested_dependencies() -> None:
    deps = _pyproject()["project"]["dependencies"]
    for pin in EXPECTED_PINS:
        assert pin in deps, f"pin ausente en pyproject: {pin}"
    assert not any("+" in d or ";" in d for d in deps), (
        "pins con sufijo de plataforma o marcador: cada OS resuelve su wheel"
    )


def test_setup_mac_exists_and_is_executable() -> None:
    assert SCRIPT.is_file(), "setup-mac.sh missing"
    assert SCRIPT.stat().st_mode & 0o111, "setup-mac.sh no es ejecutable"


def test_setup_mac_bash_syntax_clean() -> None:
    proc = subprocess.run(["bash", "-n", str(SCRIPT)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"bash -n falla: {proc.stderr}"


# Solo los límites externos son dobles: pip/venv/CLI/hash. Bash, temporales,
# limpieza y generación del JPEG con Pillow se ejecutan realmente, sin red.
STUB = r'''
import json, os, pathlib, shutil, subprocess, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["CALLS"], "a") as log:
    log.write(json.dumps([name, *args]) + "\n")
if args[:1] == ["-B"]:
    args = args[1:]
if name in ("brew", "curl", "wget"):
    sys.exit(99)
if name in ("shasum", "sha256sum"):
    print(os.environ["WEIGHT_HASH"] + "  yolo11n.pt")
elif name == "autocrop":
    if args == ["--help"]:
        sys.exit(int(os.environ.get("HELP_EXIT", "0")))
    source = pathlib.Path(args[args.index("--input") + 1]) / "blank.jpg"
    output = pathlib.Path(args[args.index("--output") + 1])
    from PIL import Image
    with Image.open(source) as image:
        assert image.format == "JPEG" and image.size == (640, 480)
        assert image.getextrema() == ((255, 255),) * 3
    mode = os.environ.get("SMOKE_MODE", "ok")
    if mode == "exit":
        sys.exit(7)
    if mode != "no-review":
        (output / "review").mkdir()
        shutil.copyfile(source, output / "review" / "blank.jpg")
    print("Done: " + ("0 processed" if mode == "no-processed" else "1 processed")
          + ", " + ("0 review" if mode == "no-count" else "1 review"))
elif args[0] == "-c":
    version = os.environ.get("HOST_VERSION" if name == "python3.12" else "VENV_VERSION", "3.12")
    sys.version_info = tuple(map(int, version.split("."))) + (0, "final", 0)
    exec(args[1])
elif args[:2] == ["-m", "venv"]:
    target = pathlib.Path(args[2])
    (target / "bin").mkdir(parents=True)
    (target / "pyvenv.cfg").write_text("version = 3.12.0\n")
    for command in ("python", "autocrop"):
        shutil.copyfile(sys.argv[0], target / "bin" / command)
        (target / "bin" / command).chmod(0o755)
elif args[:2] == ["-m", "pip"]:
    if os.environ.get("NO_PIP") == "1":
        sys.exit(1)
elif args[0] == "-":
    sys.exit(subprocess.run([sys.executable, *args], input=sys.stdin.read(), text=True).returncode)
else:
    raise AssertionError(args)
'''


@pytest.fixture
def setup_copy(tmp_path: pathlib.Path) -> Iterator[SetupCopy]:
    root = tmp_path / "project with spaces"
    root.mkdir()
    shutil.copy2(SCRIPT, root / SCRIPT.name)
    (root / "yolo11n.pt").write_bytes(b"local weights, never downloaded")
    (root / "fotos").mkdir()
    original = root / "fotos" / "original.jpg"
    original.write_bytes(b"original must remain unchanged")
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("bash", "dirname", "awk", "mkdir", "mktemp", "rm", "grep"):
        (tools / name).symlink_to(shutil.which(name))
    for name in ("python3.12", "shasum", "sha256sum", "brew", "curl", "wget"):
        executable = tools / name
        executable.write_text(f"#!{sys.executable}\n" + STUB)
        executable.chmod(0o755)
    smoke = tmp_path / "smoke"
    smoke.mkdir()
    calls = tmp_path / "calls.jsonl"
    env = {**os.environ, "PATH": str(tools), "TMPDIR": str(smoke),
           "CALLS": str(calls), "WEIGHT_HASH": EXPECTED_HASH}
    yield root, env
    assert original.read_bytes() == b"original must remain unchanged"
    assert sorted(p.name for p in original.parent.iterdir()) == ["original.jpg"]
    assert not list(smoke.iterdir()), "el temporal del humo debe limpiarse incluso al fallar"
    if (root / "yolo11n.pt").exists():
        assert (root / "yolo11n.pt").read_bytes() == b"local weights, never downloaded"
    assert not any(call[0] in ("brew", "curl", "wget") for call in _calls(env))


def _calls(env: dict[str, str]) -> list[list[str]]:
    path = pathlib.Path(env["CALLS"])
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _run(root: pathlib.Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(root / SCRIPT.name), *args], env=env,
                          capture_output=True, text=True, timeout=30)


def test_setup_mac_requires_python312_with_install_hint(setup_copy: SetupCopy) -> None:
    root, env = setup_copy
    (pathlib.Path(env["PATH"]) / "python3.12").unlink()
    proc = _run(root, env)
    assert proc.returncode != 0
    assert "python3.12 no encontrado" in proc.stderr
    assert "brew install python@3.12" in proc.stderr or "python.org" in proc.stderr
    assert _calls(env) == []
    assert not (root / ".venv").exists()


@pytest.mark.parametrize("missing", [True, False])
def test_setup_mac_rejects_missing_or_invalid_weights(setup_copy: SetupCopy, missing: bool) -> None:
    root, env = setup_copy
    if missing:
        (root / "yolo11n.pt").unlink()
    else:
        env["WEIGHT_HASH"] = "0" * 64
    proc = _run(root, env)
    assert proc.returncode != 0
    assert ("yolo11n.pt no encontrado" if missing else "hash de yolo11n.pt difiere") in proc.stderr
    assert not any(call[1:3] in (["-m", "venv"], ["-m", "pip"]) for call in _calls(env))
    assert not (root / ".venv").exists()


@pytest.mark.parametrize("args,install", [((), ["."]), (("--dev",), ["-e", ".[dev]"])])
@pytest.mark.parametrize("fallback", [False, True])
def test_setup_mac_success_runtime_dev_and_hash_fallback(
    setup_copy: SetupCopy, args: tuple[str, ...], install: list[str], fallback: bool,
) -> None:
    root, env = setup_copy
    if fallback:
        (pathlib.Path(env["PATH"]) / "shasum").unlink()
    proc = _run(root, env, *args)
    assert proc.returncode == 0, proc.stderr
    assert "setup-mac OK" in proc.stdout
    calls = _calls(env)
    assert ["python3.12", "-m", "venv", ".venv"] in calls
    assert [call for call in calls if call[1:4] == ["-m", "pip", "install"]] == [
        ["python", "-m", "pip", "install", *install]
    ]
    hash_call = ["sha256sum", "yolo11n.pt"] if fallback else ["shasum", "-a", "256", "yolo11n.pt"]
    assert hash_call in calls
    assert calls.index(["python", "-B", "-m", "pip", "--version"]) < calls.index(
        ["python", "-m", "pip", "install", *install]
    )
    help_index = calls.index(["autocrop", "--help"])
    smoke_index = next(i for i, call in enumerate(calls) if call[:2] == ["autocrop", "--input"])
    assert help_index < smoke_index
    smoke_call = calls[smoke_index]
    assert pathlib.Path(smoke_call[2]).parent.parent == pathlib.Path(env["TMPDIR"])
    assert smoke_call[3] == "--output"
    assert pathlib.Path(smoke_call[4]).parent == pathlib.Path(smoke_call[2]).parent
    assert not pathlib.Path(smoke_call[2]).exists()


def test_setup_help_has_no_effects(setup_copy: SetupCopy) -> None:
    root, env = setup_copy
    proc = _run(root, env, "--help")
    assert proc.returncode == 0 and "Usage:" in proc.stdout
    assert _calls(env) == []
    assert not (root / ".venv").exists()


def test_cli_help_failure_stops_before_smoke(setup_copy: SetupCopy) -> None:
    root, env = setup_copy
    env["HELP_EXIT"] = "9"
    proc = _run(root, env)
    assert proc.returncode != 0
    assert ["autocrop", "--help"] in _calls(env)
    assert not any(call[:2] == ["autocrop", "--input"] for call in _calls(env))
    assert "setup-mac OK" not in proc.stdout


@pytest.mark.parametrize("mode,message", [("exit", ""), ("no-processed", "1 processed"),
                                         ("no-count", "1 review"), ("no-review", "review/blank.jpg")])
def test_smoke_failures_are_rejected_and_cleaned(
    setup_copy: SetupCopy, mode: str, message: str,
) -> None:
    root, env = setup_copy
    env["SMOKE_MODE"] = mode
    proc = _run(root, env)
    assert proc.returncode != 0
    if mode == "exit":
        assert proc.returncode == 7
    assert message in proc.stderr
    assert any(call[:2] == ["autocrop", "--input"] for call in _calls(env))
    assert "setup-mac OK" not in proc.stdout


@pytest.mark.parametrize("version", ["3.11", "3.13"])
def test_named_python312_with_wrong_version_is_rejected(setup_copy: SetupCopy, version: str) -> None:
    root, env = setup_copy
    env["HOST_VERSION"] = version
    proc = _run(root, env)
    assert proc.returncode != 0
    assert "Python 3.12" in proc.stderr
    assert "brew install python@3.12" in proc.stderr or "python.org" in proc.stderr
    assert not (root / ".venv").exists()


@pytest.mark.parametrize("problem", ["wrong-version", "no-python", "not-executable", "no-config", "no-pip", "file"])
def test_existing_invalid_venv_is_preserved(setup_copy: SetupCopy, problem: str) -> None:
    root, env = setup_copy
    venv = root / ".venv"
    subprocess.run([str(pathlib.Path(env["PATH"]) / "python3.12"), "-m", "venv", str(venv)],
                   env=env, check=True)
    if problem == "wrong-version":
        env["VENV_VERSION"] = "3.11"
    elif problem == "no-python":
        (venv / "bin/python").unlink()
    elif problem == "not-executable":
        (venv / "bin/python").chmod(0o644)
    elif problem == "no-config":
        (venv / "pyvenv.cfg").unlink()
    elif problem == "no-pip":
        env["NO_PIP"] = "1"
    else:
        shutil.rmtree(venv)
        venv.write_bytes(b"not a directory; preserve me")
    files = [venv] if venv.is_file() else [p for p in venv.rglob("*") if p.is_file()]
    before = {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in files}
    pathlib.Path(env["CALLS"]).unlink()
    proc = _run(root, env)
    assert proc.returncode != 0
    assert ".venv" in proc.stderr and "error:" in proc.stderr
    assert before == {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in files}
    after_files = [venv] if venv.is_file() else [p for p in venv.rglob("*") if p.is_file()]
    assert set(files) == set(after_files)
    assert not any(call[1:3] == ["-m", "venv"] or call[1:4] == ["-m", "pip", "install"]
                   for call in _calls(env))


def test_existing_valid_venv_is_reused(setup_copy: SetupCopy) -> None:
    root, env = setup_copy
    subprocess.run([str(pathlib.Path(env["PATH"]) / "python3.12"), "-m", "venv", str(root / ".venv")],
                   env=env, check=True)
    sentinel = root / ".venv" / "keep.txt"
    sentinel.write_text("keep existing environment")
    pathlib.Path(env["CALLS"]).unlink()
    proc = _run(root, env)
    assert proc.returncode == 0, proc.stderr
    assert sentinel.read_text() == "keep existing environment"
    assert not any(call[1:3] == ["-m", "venv"] for call in _calls(env))
    assert ["python", "-m", "pip", "install", "."] in _calls(env)


def test_pipeline_untouched_cpu_kept() -> None:
    detector = (ROOT / "app" / "detector.py").read_text(encoding="utf-8")
    assert 'device="cpu"' in detector, "no tocar device=cpu en esta etapa"
    script = _script_text()
    assert "mps" not in script.lower(), "MPS es mejora futura, no implementada"


def test_readme_mac_section() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "setup-mac.sh" in readme
    assert "3.12" in readme
    lowered = readme.lower()
    assert "si falla" in lowered or "falla" in lowered
    assert "borde" in lowered or "píxel" in lowered or "pixel" in lowered, (
        "nota de que ARM vs Linux puede diferir en píxeles de borde"
    )
