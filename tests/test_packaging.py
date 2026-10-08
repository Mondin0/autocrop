"""Packaging tests (stage 06).

Verify the ``autocrop`` console script is declared, installed, and
reuses ``app.cli:main`` without duplicating parsing/processing logic.
Docker artefacts are validated with real ``docker build``/``exec``
runs (see registro.md), not by repeating their text here.
"""

from __future__ import annotations

import importlib.metadata
import pathlib
import subprocess
import sys
import tomllib

import pytest

import app.cli


def _declared_script() -> str | None:
    text = pathlib.Path("pyproject.toml").read_bytes()
    data = tomllib.loads(text.decode("utf-8"))
    return data.get("project", {}).get("scripts", {}).get("autocrop")


def test_pyproject_declares_console_script_reusing_cli_main() -> None:
    assert _declared_script() == "app.cli:main"


def test_installed_entry_point_loads_cli_main() -> None:
    matches = [
        ep for ep in importlib.metadata.entry_points(group="console_scripts")
        if ep.name == "autocrop"
    ]
    assert matches, "console script 'autocrop' is not installed"
    assert matches[0].load() is app.cli.main


def test_console_script_binary_help_matches_module() -> None:
    binary = pathlib.Path(sys.executable).parent / "autocrop"
    assert binary.is_file(), f"console script binary missing: {binary}"
    script = subprocess.run(
        [str(binary), "--help"], capture_output=True, text=True, timeout=60)
    module = subprocess.run(
        [sys.executable, "-m", "app.cli", "--help"],
        capture_output=True, text=True, timeout=60)
    assert script.returncode == 0
    assert module.returncode == 0
    for flag in ("--input", "--output", "--ratio", "--margin", "0.15",
                 "Crop sports photos around the main subject."):
        assert flag in script.stdout
        assert flag in module.stdout


def test_console_script_rejects_missing_args_like_module() -> None:
    binary = pathlib.Path(sys.executable).parent / "autocrop"
    script = subprocess.run(
        [str(binary)], capture_output=True, text=True, timeout=60)
    module = subprocess.run(
        [sys.executable, "-m", "app.cli"],
        capture_output=True, text=True, timeout=60)
    assert script.returncode != 0
    assert script.returncode == module.returncode
    for flag in ("--input", "--output"):
        assert flag in script.stderr
        assert flag in module.stderr


def test_cli_main_accepts_argv_list() -> None:
    with pytest.raises(SystemExit) as exc:
        app.cli.main(["--help"])
    assert exc.value.code == 0
