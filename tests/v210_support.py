"""Soporte mínimo de validación V2-10 (etapa de aceptación).

Helpers puros para el aislamiento Docker y la construcción de fixtures
en temporales. Sin YOLO, red ni fotos reales.
"""

from __future__ import annotations

import hashlib
import io
import socket
import zipfile


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_isolated_override(path: str, api_port: int, frontend_port: int,
                            prefix: str = "autocrop-v210") -> str:
    # ``!override`` replaces the productive port list instead of merging
    # with it, so the isolated stack never binds 8000/8080. Unique
    # container names avoid reusing productive ``autocrop-*`` names.
    names = {svc: f"{prefix}-{svc}" for svc in
             ("api", "worker", "frontend", "redis", "rustfs")}
    text = (
        "services:\n"
        f"  api:\n    container_name: {names['api']}\n"
        f"    ports: !override [\"127.0.0.1:{api_port}:8000\"]\n"
        f"  worker:\n    container_name: {names['worker']}\n"
        f"  frontend:\n    container_name: {names['frontend']}\n"
        f"    ports: !override [\"127.0.0.1:{frontend_port}:8080\"]\n"
        f"  redis:\n    container_name: {names['redis']}\n"
        f"  rustfs:\n    container_name: {names['rustfs']}\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def build_sized_zip(dest: str, target_bytes: int) -> dict:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (512, 512), (180, 40, 40)).save(buf, "JPEG", quality=95)
    blob = buf.getvalue()
    digest = hashlib.sha256()
    entries = 0
    with open(dest, "wb") as fh:
        with zipfile.ZipFile(fh, "w", zipfile.ZIP_STORED) as zf:
            size = 0
            idx = 0
            while size < target_bytes:
                name = f"foto-{idx:05d}.jpg"
                zf.writestr(name, blob)
                size += len(blob)
                idx += 1
            entries = idx
    with open(dest, "rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    import os
    return {"size": os.path.getsize(dest), "entries": entries,
            "sha256": digest.hexdigest()}
