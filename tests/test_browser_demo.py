"""Keep the static Pyodide adapter faithful to the installed CLI contract."""
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
import runpy

import pytest

from ooxml_integrity.cli import main
from ooxml_integrity import fonts

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
pytestmark = pytest.mark.skipif(not DEMO.is_dir(), reason="static demo is not shipped in the PyPI sdist")


@pytest.fixture
def bridge():
    return runpy.run_path(str(DEMO / "bridge.py"))


@pytest.mark.parametrize("coverage", [False, True])
@pytest.mark.parametrize("example,source", [
    ("base.docx", None), ("deck.pptx", None), ("agreement.docx", "base.docx"),
])
def test_cli_parity(bridge, example, source, coverage):
    path = DEMO / "examples" / example
    original = DEMO / "examples" / source if source else None
    result = bridge["run_check"](path, original, coverage)
    args = ["check", str(path), "--no-config"]
    if original:
        args += ["--against", str(original)]
    if coverage:
        args += ["--coverage"]
    human, machine = StringIO(), StringIO()
    with redirect_stdout(human):
        code = main(args)
    with redirect_stdout(machine):
        json_code = main(args + ["--json"])
    assert code == json_code == result["exit_code"]
    assert human.getvalue() == result["human"]
    assert json.loads(machine.getvalue()) == result["json"]


def test_fidelity_example(bridge):
    result = bridge["run_check"](DEMO / "examples/agreement.docx", DEMO / "examples/base.docx")
    assert {"CMT005", "FID001"} <= {f["code"] for f in result["json"]["files"][0]["findings"]}
    assert result["exit_code"] == 1


@pytest.mark.parametrize("original,copy", [
    ("corpus/base.docx", "base.docx"), ("corpus/deck.pptx", "deck.pptx"),
    ("runs/t4_fast_fee/agreement.docx", "agreement.docx"),
])
def test_examples_are_identical(original, copy):
    assert (ROOT / original).read_bytes() == (DEMO / "examples" / copy).read_bytes()


@pytest.mark.parametrize("path,source", [("bad.pdf", None), ("deck.pptx", "base.docx"), ("base.docx", "bad.pdf")])
def test_invalid_extensions_are_not_silently_ignored(bridge, path, source):
    with pytest.raises(ValueError):
        bridge["run_check"](path, source)


def test_corrupt_docx_is_reported(bridge, tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a zip")
    result = bridge["run_check"](path)
    assert result["exit_code"] == 1
    assert result["json"]["files"][0]["summary"]["error"] > 0


def test_python_exception_is_not_swallowed(bridge, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("simulated parser failure")
    monkeypatch.setitem(bridge["run_check"].__globals__, "check", broken)
    with pytest.raises(RuntimeError, match="simulated parser failure"):
        bridge["run_check"]("file.docx")


def test_font_checksums_and_licenses():
    folder = DEMO / "fonts"
    lines = (folder / "SHA256SUMS").read_text().splitlines()
    names = set()
    for line in lines:
        digest, name = line.split(maxsplit=1)
        names.add(name)
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
    assert len([name for name in names if name.endswith(".ttf")]) == 20
    assert {p.name for p in folder.glob("*.ttf")} <= names
    for family in ("Carlito", "Caladea", "Liberation"):
        assert "SIL OPEN FONT LICENSE" in (folder / f"{family}-OFL.txt").read_text()


def test_browser_fonts_without_fontconfig(bridge, monkeypatch):
    # Emulate the browser: only bundled fonts, no system fonts or fc-match.
    cached = [fonts._index_font_dirs, fonts.resolve_face, fonts.load_metrics]
    for func in cached:
        func.cache_clear()
    monkeypatch.setattr(fonts, "FONT_DIRS", (DEMO / "fonts",))
    monkeypatch.setattr(fonts, "_fc_match", lambda *args: None)
    try:
        for family in ("Calibri", "Cambria", "Arial", "Times New Roman", "Courier New"):
            for bold, italic in ((False, False), (True, False), (False, True), (True, True)):
                face = fonts.resolve_face(family, bold, italic)
                assert face.match == "metric"
                style = ("Bold" if bold else "") + ("Italic" if italic else "") or "Regular"
                assert face.path.name.endswith(f"-{style}.ttf")
        result = bridge["run_doctor"]()
        assert result["exit_code"] == 0
        assert result["json"]["status"] == "ready"
        assert "doctor: ready" in result["human"]
    finally:
        for func in cached:
            func.cache_clear()
