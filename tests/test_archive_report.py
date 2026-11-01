"""Contract tests for V2-13 originals and report inside the result ZIP."""

from __future__ import annotations

import html
import io
import re
import zipfile
from urllib.parse import unquote

import pytest
from PIL import Image

import app.archive as archive
from app.archive import process_archive


class Stub:
    """Detector stand-in keyed by image size: {(w, h): [boxes]}."""

    def __init__(self, by_size=None):
        self.by_size = dict(by_size or {})

    def detect_people(self, image):
        return list(self.by_size.get(tuple(image.size), []))


def make_jpg_bytes(width=800, height=600, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "JPEG")
    return buf.getvalue()


def write_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def zip_files(path):
    with zipfile.ZipFile(path) as zf:
        return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}


def report_cells(report, css_class):
    return re.findall(
        rf'<td class="{css_class}">(.*?)</td>', report, flags=re.DOTALL)


def report_hrefs(report):
    return [unquote(value) for value in re.findall(r'href="([^"]*)"', report)]


def build_mixed_zip(tmp_path):
    sizes = {
        'foto <b>&"sol" \'playa\'.jpg': (800, 600),
        "foto: rara <r> & 2.jpg": (500, 500),
        "originals.jpg": (640, 480),
        "reporte.html.jpg": (720, 540),
    }
    payloads = {
        name: make_jpg_bytes(*size, color=(idx * 30, 80, 160))
        for idx, (name, size) in enumerate(sizes.items())
    }
    payloads["nota.txt"] = b"ignored"
    stub = Stub({
        (800, 600): [(100, 100, 300, 300)],
        (500, 500): [],
        (640, 480): [(50, 50, 200, 250)],
        (720, 540): [],
    })
    saved = {'foto <b>&"sol" \'playa\'.jpg', "originals.jpg"}
    src = write_zip(tmp_path / "in.zip", payloads)
    return sizes, saved, payloads, stub, src


# --- F1: original bytes under originals/ -------------------------------------


def test_mixed_batch_keeps_originals_bytes_and_existing_outputs(tmp_path):
    sizes, _saved, payloads, stub, src = build_mixed_zip(tmp_path)
    before = src.read_bytes()
    out = tmp_path / "out.zip"
    summary = process_archive(src, out, stub, None, 0.15)

    assert summary == {"processed": 4, "saved": 2, "review": 2, "skipped": 0}
    assert src.read_bytes() == before
    with zipfile.ZipFile(out) as zf:
        listed = zf.namelist()
        files = {n: zf.read(n) for n in listed if not n.endswith("/")}
        assert {"reporte.html", "review.log", "review/",
                "originals.jpg", "review/reporte.html.jpg"} <= set(listed)
        for name in sizes:
            path = f"originals/{name}"
            assert listed.count(path) == 1
            assert files[path] == payloads[name]
        assert "review/originals.jpg" not in listed
        assert listed == sorted(listed)


# --- F2/F3: report rows, links and escaping ---------------------------------


def test_mixed_report_has_ordered_rows_links_and_reasons(tmp_path):
    sizes, saved, _payloads, stub, src = build_mixed_zip(tmp_path)
    out = tmp_path / "out.zip"
    process_archive(src, out, stub, None, 0.15)
    files = zip_files(out)
    report = files["reporte.html"].decode("utf-8")
    ordered = sorted(sizes)

    assert report.startswith("<!DOCTYPE html>")
    assert 'lang="es"' in report
    assert "<h1>Reporte de Autocrop</h1>" in report
    assert "Fotos procesadas: 4. Guardadas: 2. En revisión: 2." in report
    assert not re.search(r"https?://|url\(|<script|<link|<img|\ssrc=", report)

    assert report_cells(report, "foto") == [
        html.escape(name) for name in ordered]
    assert report_cells(report, "estado") == [
        "guardada" if name in saved else "en revisión" for name in ordered]
    assert report_cells(report, "motivo") == [
        "" if name in saved else "no_person" for name in ordered]

    expected = set()
    for name in ordered:
        expected.add(f"originals/{name}")
        if name in saved:
            expected.add(name)
        else:
            expected.add(f"review/{name}")
    hrefs = report_hrefs(report)
    assert set(hrefs) == expected
    assert len(hrefs) == len(expected)
    for href in hrefs:
        assert href in files

    assert html.escape('foto <b>&"sol" \'playa\'.jpg') in report
    assert "<b>" not in report


def test_all_saved_batch_links_every_crop_and_never_review(tmp_path):
    payloads = {
        "a.jpg": make_jpg_bytes(800, 600),
        "b.jpg": make_jpg_bytes(640, 480),
        "c.jpg": make_jpg_bytes(720, 540),
    }
    stub = Stub({
        (800, 600): [(100, 100, 300, 300)],
        (640, 480): [(50, 50, 200, 250)],
        (720, 540): [(60, 60, 300, 320)],
    })
    src = write_zip(tmp_path / "in.zip", payloads)
    out = tmp_path / "out.zip"
    summary = process_archive(src, out, stub, None, 0.15)

    assert summary == {"processed": 3, "saved": 3, "review": 0, "skipped": 0}
    files = zip_files(out)
    report = files["reporte.html"].decode("utf-8")
    hrefs = report_hrefs(report)
    expected = {f"originals/{name}" for name in payloads} | set(payloads)
    assert set(hrefs) == expected
    for href in hrefs:
        assert href in files
    assert not any(href.startswith("review/") for href in hrefs)
    assert "Guardadas: 3. En revisión: 0." in report
    assert report_cells(report, "motivo") == ["", "", ""]
    assert report_cells(report, "estado") == ["guardada"] * 3


def test_all_review_batch_links_review_copy_and_reason(tmp_path):
    payloads = {
        "x.jpg": make_jpg_bytes(800, 600),
        "y.jpg": make_jpg_bytes(640, 480),
        "z.jpg": make_jpg_bytes(720, 540),
    }
    src = write_zip(tmp_path / "in.zip", payloads)
    out = tmp_path / "out.zip"
    summary = process_archive(src, out, Stub(), None, 0.15)

    assert summary == {"processed": 3, "saved": 0, "review": 3, "skipped": 0}
    files = zip_files(out)
    report = files["reporte.html"].decode("utf-8")
    hrefs = report_hrefs(report)
    expected = {f"originals/{name}" for name in payloads} | {
        f"review/{name}" for name in payloads}
    assert set(hrefs) == expected
    for href in hrefs:
        assert href in files
    assert not any(href in payloads for href in hrefs)
    assert "Guardadas: 0. En revisión: 3." in report
    assert report_cells(report, "motivo") == ["no_person"] * 3
    assert report_cells(report, "estado") == ["en revisión"] * 3
    for name in payloads:
        assert files[f"review/{name}"] == payloads[name]


def test_report_escapes_hostile_review_reason(tmp_path, monkeypatch):
    payload = make_jpg_bytes(800, 600)
    name = 'foto: <x> & "y".jpg'
    src = write_zip(tmp_path / "in.zip", {name: payload})
    real_process_folder = archive.process_folder

    def hostile_log(input_dir, output_dir, *args, **kwargs):
        summary = real_process_folder(input_dir, output_dir, *args, **kwargs)
        (output_dir / "review.log").write_text(
            f'{name}: motivo <script>&"raro"</script>\n', encoding="utf-8")
        return summary

    monkeypatch.setattr(archive, "process_folder", hostile_log)
    out = tmp_path / "out.zip"
    process_archive(src, out, Stub(), None, 0.15)
    report = zip_files(out)["reporte.html"].decode("utf-8")

    assert "<script>" not in report
    assert "&lt;script&gt;&amp;&quot;raro&quot;&lt;/script&gt;" in report
    assert html.escape(name) in report
    assert ('href="originals/foto%3A%20%3Cx%3E%20%26%20%22y%22.jpg"'
            in report)
    assert ('href="review/foto%3A%20%3Cx%3E%20%26%20%22y%22.jpg"'
            in report)


def test_review_name_with_newline_keeps_reason(tmp_path):
    name = "foto\ncon salto.jpg"
    payload = make_jpg_bytes(800, 600)
    src = write_zip(tmp_path / "in.zip", {name: payload})
    out = tmp_path / "out.zip"
    summary = process_archive(src, out, Stub(), None, 0.15)

    assert summary == {"processed": 1, "saved": 0, "review": 1, "skipped": 0}
    files = zip_files(out)
    assert files["review.log"].decode("utf-8") == f"{name}: no_person\n"
    report = files["reporte.html"].decode("utf-8")
    assert report_cells(report, "foto") == [html.escape(name)]
    assert report_cells(report, "motivo") == ["no_person"]
    hrefs = report_hrefs(report)
    assert set(hrefs) == {f"originals/{name}", f"review/{name}"}
    for href in hrefs:
        assert href in files


def test_names_that_resemble_reserved_outputs_do_not_collide(tmp_path):
    names = ["originals.jpg", "reporte.html.jpg", "review.log.jpg",
             "review.jpg"]
    sizes = [(800, 600), (640, 480), (720, 540), (500, 500)]
    payloads = {name: make_jpg_bytes(*size)
                for name, size in zip(names, sizes)}
    stub = Stub({
        (800, 600): [(100, 100, 300, 300)],
        (640, 480): [(50, 50, 200, 250)],
        (720, 540): [],
        (500, 500): [],
    })
    src = write_zip(tmp_path / "in.zip", payloads)
    out = tmp_path / "out.zip"
    process_archive(src, out, stub, None, 0.15)

    with zipfile.ZipFile(out) as zf:
        listed = zf.namelist()
        files = {n: zf.read(n) for n in listed if not n.endswith("/")}
    assert len(listed) == len(set(listed))
    for name in names:
        assert files[f"originals/{name}"] == payloads[name]
    assert files["reporte.html"].startswith(b"<!DOCTYPE html>")
    report = files["reporte.html"].decode("utf-8")
    for href in report_hrefs(report):
        assert href in files
    assert report_cells(report, "foto") == [
        html.escape(name) for name in sorted(names)]


# --- F4: no partial ZIP when packaging fails --------------------------------


def test_packaging_failure_leaves_no_partial_zip(tmp_path, monkeypatch):
    payloads = {"a.jpg": make_jpg_bytes(800, 600),
                "b.jpg": make_jpg_bytes(640, 480)}
    stub = Stub({
        (800, 600): [(100, 100, 300, 300)],
        (640, 480): [(50, 50, 200, 250)],
    })
    src = write_zip(tmp_path / "in.zip", payloads)
    out = tmp_path / "out.zip"
    real_process_folder = archive.process_folder

    def vanish_original(input_dir, output_dir, *args, **kwargs):
        summary = real_process_folder(input_dir, output_dir, *args, **kwargs)
        (input_dir / "a.jpg").unlink()
        return summary

    monkeypatch.setattr(archive, "process_folder", vanish_original)
    with pytest.raises(FileNotFoundError):
        process_archive(src, out, stub, None, 0.15)
    assert not out.exists()
    assert list(tmp_path.glob("*.tmp")) == []
