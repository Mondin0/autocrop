"""Secure ZIP wrapper around the crop engine (stage V2-01)."""

from __future__ import annotations

import html
import math
import os
import pathlib
import tempfile
import zipfile
from collections.abc import Callable
from urllib.parse import quote

from app.processor import process_folder

MAX_INPUT_BYTES = 5 * 1024 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 5 * 1024 * 1024 * 1024
MAX_ENTRIES = 10_000

_JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})
_CHUNK = 1024 * 1024
_REPORT_NAME = "reporte.html"


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


def _review_reasons(
    log_path: pathlib.Path, review_names: list[str]
) -> dict[str, str]:
    """Map reviewed photo name to the reason already recorded in review.log.

    ``process_folder()`` writes one ``name: reason`` record per reviewed photo
    in sorted name order and reasons contain no newline. Walking that known
    order keeps names containing newlines intact instead of splitting lines.
    """
    if not log_path.is_file():
        return {}
    text = log_path.read_text(encoding="utf-8")
    reasons: dict[str, str] = {}
    position = 0
    for name in review_names:
        prefix = f"{name}: "
        if not text.startswith(prefix, position):
            continue
        end = text.find("\n", position + len(prefix))
        if end < 0:
            end = len(text)
        reasons[name] = text[position + len(prefix):end]
        position = end + 1
    return reasons


def _href(path: str) -> str:
    return html.escape(quote(path), quote=True)


def _build_report(
    names: list[str],
    reasons: dict[str, str],
) -> bytes:
    """Render only failures from the processor's recorded review reasons."""
    rows: list[str] = []
    for name in names:
        rows.append(
            f'<tr><td class="foto">{html.escape(name)}</td>'
            f'<td class="motivo">{html.escape(reasons.get(name, ""))}</td>'
            f'<td class="archivos"><a href="{_href(name)}">original</a>'
            "</td></tr>")
    document = (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n<head>\n<meta charset="utf-8">\n'
        "<title>Reporte de Autocrop</title>\n"
        "<style>\n"
        "body { font-family: sans-serif; margin: 2rem; }\n"
        "table { border-collapse: collapse; }\n"
        "th, td { border: 1px solid #888; padding: 0.35rem 0.6rem; "
        "text-align: left; }\n"
        "section { max-width: 60rem; margin: 1rem 0 1.5rem; }\n"
        "</style>\n</head>\n<body>\n"
        "<h1>Reporte de Autocrop</h1>\n"
        f"<p>Fotos con fallas o en revisión: {len(names)}.</p>\n"
        "<section><h2>Referencia de motivos</h2><ul>"
        "<li><code>unreadable</code>: no se pudo abrir o leer la foto; "
        "revisar que el archivo no esté dañado.</li>"
        "<li><code>no_person</code>: no se detectó ninguna persona.</li>"
        "<li><code>ambiguous_subject</code>: no se pudo elegir con seguridad "
        "a quién encuadrar.</li>"
        "<li><code>no_valid_crop</code>: no se pudo generar un recorte válido.</li>"
        "</ul><p>Las fotos en revisión conservan su original sin modificar.</p>"
        "</section>\n"
        "<table>\n<thead>\n<tr><th>Foto</th><th>Motivo</th>"
        "<th>Archivos</th></tr>\n</thead>\n<tbody>\n"
        + "\n".join(rows)
        + "\n</tbody>\n</table>\n</body>\n</html>\n"
    )
    return document.encode("utf-8")


def process_archive(
    input_zip: pathlib.Path,
    output_zip: pathlib.Path,
    detector: object,
    ratio: tuple[int, int] | None = None,
    margin: float = 0.15,
    on_progress: Callable[[dict[str, int | str | None]], None] | None = None,
) -> dict[str, int]:
    """Process a ZIP of JPEGs into a ZIP of ``process_folder()`` output."""
    if on_progress is not None and not callable(on_progress):
        raise ValueError(f"on_progress must be callable: {on_progress!r}")
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
        raise _fail(f"input zip exceeds 5 GiB: {input_zip}")

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
            raise _fail("uncompressed size exceeds 5 GiB")
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
            written = 0
            for info in sorted(candidates, key=lambda i: i.filename):
                try:
                    with zf.open(info) as src:
                        dest = in_dir / info.filename
                        with open(dest, "wb") as fh:
                            while True:
                                chunk = src.read(_CHUNK)
                                if not chunk:
                                    break
                                written += len(chunk)
                                if written > MAX_TOTAL_UNCOMPRESSED:
                                    raise _fail(
                                        "uncompressed size exceeds 5 GiB")
                                fh.write(chunk)
                except ValueError:
                    raise
                except Exception as exc:
                    raise _fail(
                        f"cannot read entry: {info.filename!r} ({exc})"
                    ) from exc
            total = len(candidates)
            if on_progress is not None:
                on_progress({"current": None, "processed": 0, "total": total,
                             "saved": 0, "review": 0})
            summary = process_folder(
                in_dir, out_dir, detector, ratio, margin, on_progress)

            photo_names = sorted(info.filename for info in candidates)
            entries: dict[str, pathlib.Path | bytes] = {}
            for name in photo_names:
                entries[name] = (out_dir / name if (out_dir / name).is_file()
                                 else in_dir / name)
            reviewed = [name for name in photo_names
                        if not (out_dir / name).is_file()]
            entries[_REPORT_NAME] = _build_report(
                reviewed,
                _review_reasons(out_dir / "review.log", reviewed))
            arcs = sorted(entries)
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
                            source = entries[arc]
                            if isinstance(source, bytes):
                                out_zf.writestr(arc, source)
                            else:
                                out_zf.write(source, arc)
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
            if on_progress is not None:
                on_progress({"current": None, "processed": total,
                             "total": total, "saved": summary["saved"],
                             "review": summary["review"]})
            return summary
