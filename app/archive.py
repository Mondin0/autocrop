"""Secure ZIP wrapper around the crop engine (stage V2-01)."""

from __future__ import annotations

import math
import os
import pathlib
import tempfile
import zipfile

from app.processor import process_folder

MAX_INPUT_BYTES = 500 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
MAX_ENTRIES = 10_000

_JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})
_CHUNK = 1024 * 1024


def _fail(message: str) -> ValueError:
    return ValueError(message)


def _check_options(detector: object, ratio, margin: float) -> None:
    if not callable(getattr(detector, "detect_people", None)):
        raise ValueError(f"detector has no detect_people method: {detector!r}")
    if ratio is not None:
        if not isinstance(ratio, tuple) or len(ratio) != 2:
            raise ValueError(f"invalid ratio: {ratio!r}")
        w, h = ratio
        if isinstance(w, bool) or isinstance(h, bool):
            raise ValueError(f"invalid ratio: {ratio!r}")
        if not isinstance(w, int) or not isinstance(h, int):
            raise ValueError(f"invalid ratio: {ratio!r}")
        if w <= 0 or h <= 0:
            raise ValueError(f"invalid ratio: {ratio!r}")
    if isinstance(margin, bool) or not isinstance(margin, (int, float)):
        raise ValueError(f"invalid margin: {margin!r}")
    if margin < 0:
        raise ValueError(f"invalid margin: {margin!r}")
    if isinstance(margin, float) and not math.isfinite(margin):
        raise ValueError(f"invalid margin: {margin!r}")


def _is_jpeg_name(name: str) -> bool:
    return pathlib.PurePosixPath(name).suffix.lower() in _JPEG_SUFFIXES


def _check_jpeg_name(name: str) -> None:
    if not name or name in (".", ".."):
        raise _fail(f"unsafe entry name: {name!r}")
    if "/" in name or "\\" in name:
        raise _fail(f"unsafe entry name: {name!r}")
    if pathlib.PurePath(name).name != name:
        raise _fail(f"unsafe entry name: {name!r}")


def process_archive(
    input_zip: pathlib.Path,
    output_zip: pathlib.Path,
    detector: object,
    ratio: tuple[int, int] | None = None,
    margin: float = 0.15,
) -> dict[str, int]:
    """Process a ZIP of JPEGs into a ZIP of ``process_folder()`` output."""
    if not isinstance(input_zip, pathlib.Path):
        raise ValueError(f"input_zip must be a pathlib.Path: {input_zip!r}")
    if not isinstance(output_zip, pathlib.Path):
        raise ValueError(f"output_zip must be a pathlib.Path: {output_zip!r}")
    _check_options(detector, ratio, margin)
    if os.path.lexists(output_zip):
        raise FileExistsError(f"output already exists: {output_zip}")
    if not input_zip.exists():
        raise FileNotFoundError(f"input zip not found: {input_zip}")
    if not input_zip.is_file():
        raise ValueError(f"input is not a file: {input_zip}")
    if input_zip.stat().st_size > MAX_INPUT_BYTES:
        raise _fail(f"input zip exceeds 500 MiB: {input_zip}")

    try:
        zf = zipfile.ZipFile(input_zip)
    except zipfile.BadZipFile as exc:
        raise _fail(f"invalid zip file: {input_zip} ({exc})") from exc
    with zf:
        try:
            infos = zf.infolist()
        except zipfile.BadZipFile as exc:
            raise _fail(f"invalid zip file: {input_zip} ({exc})") from exc
        if len(infos) > MAX_ENTRIES:
            raise _fail(f"too many entries: {len(infos)}")
        declared = sum(max(0, i.file_size) for i in infos)
        if declared > MAX_TOTAL_UNCOMPRESSED:
            raise _fail("uncompressed size exceeds 2 GiB")
        candidates = []
        for info in infos:
            if info.is_dir():
                continue
            if not _is_jpeg_name(info.filename):
                continue
            if info.flag_bits & 0x1:
                raise _fail(f"encrypted entry: {info.filename!r}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise _fail(f"symlink entry: {info.filename!r}")
            _check_jpeg_name(info.filename)
            candidates.append(info)
        if not candidates:
            raise _fail("zip contains no JPEG in its root")
        seen: dict[str, str] = {}
        for info in candidates:
            key = info.filename.lower()
            if key in seen:
                raise _fail(f"duplicate name: {info.filename!r}")
            seen[key] = info.filename

        with tempfile.TemporaryDirectory() as in_tmp, \
                tempfile.TemporaryDirectory() as out_tmp:
            in_dir = pathlib.Path(in_tmp)
            out_dir = pathlib.Path(out_tmp)
            total = 0
            for info in sorted(candidates, key=lambda i: i.filename):
                try:
                    with zf.open(info) as src:
                        dest = in_dir / info.filename
                        with open(dest, "wb") as fh:
                            while True:
                                chunk = src.read(_CHUNK)
                                if not chunk:
                                    break
                                total += len(chunk)
                                if total > MAX_TOTAL_UNCOMPRESSED:
                                    raise _fail(
                                        "uncompressed size exceeds 2 GiB")
                                fh.write(chunk)
                except ValueError:
                    raise
                except Exception as exc:
                    raise _fail(
                        f"cannot read entry: {info.filename!r} ({exc})"
                    ) from exc
            summary = process_folder(in_dir, out_dir, detector, ratio, margin)

            files = sorted(
                p.relative_to(out_dir).as_posix()
                for p in out_dir.rglob("*") if p.is_file())
            arcs = sorted(set(files) | {"review/"})
            tmp_out = None
            try:
                fd, tmp_name = tempfile.mkstemp(
                    dir=str(output_zip.parent) if str(output_zip.parent) else ".",
                    suffix=".tmp")
                tmp_out = pathlib.Path(tmp_name)
                with os.fdopen(fd, "wb") as fh:
                    with zipfile.ZipFile(
                            fh, "w", zipfile.ZIP_DEFLATED) as out_zf:
                        for arc in arcs:
                            if arc == "review/":
                                info = zipfile.ZipInfo("review/")
                                info.external_attr = (0o40775 << 16)
                                out_zf.writestr(info, b"")
                            else:
                                out_zf.write(out_dir / arc, arc)
                try:
                    os.link(tmp_out, output_zip)
                except FileExistsError as exc:
                    raise FileExistsError(
                        f"output already exists: {output_zip}") from exc
                os.unlink(tmp_out)
                tmp_out = None
            finally:
                if tmp_out is not None:
                    try:
                        os.unlink(tmp_out)
                    except OSError:
                        pass
            return summary
