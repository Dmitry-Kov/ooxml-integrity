"""DOCX-first packaging contract: lxml-only core, optional [pptx] extra, slim sdist."""
from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO

import pytest

from conftest import ROOT, read_part, repack

from ooxml_integrity import (
    CoverageStatus,
    ERROR,
    check,
    check_pptx,
    compare,
    coverage_for,
)
from ooxml_integrity import doctor as doctor_module
from ooxml_integrity import fonts as fonts_module
from ooxml_integrity.cli import EXIT_OK, main
from ooxml_integrity.fix import EXIT_REPAIRED, fix
from ooxml_integrity.mcp_server import Server


def _load_pyproject() -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python 3.9/3.10
        import tomli as tomllib  # type: ignore[no-redef]
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _clear_font_caches() -> None:
    fonts_module._index_font_dirs.cache_clear()
    fonts_module._has_latin_coverage.cache_clear()
    fonts_module.resolve_face.cache_clear()
    fonts_module.load_metrics.cache_clear()


@pytest.fixture
def without_fonttools(monkeypatch):
    """Simulate a core `pip install ooxml-integrity` without the [pptx] extra."""
    _clear_font_caches()
    monkeypatch.setattr(fonts_module, "fonttools_available", lambda: False)
    monkeypatch.setattr(doctor_module, "fonttools_available", lambda: False)
    try:
        yield
    finally:
        _clear_font_caches()


def test_pyproject_core_is_docx_first_with_optional_pptx_and_slim_sdist():
    data = _load_pyproject()
    deps = data["project"]["dependencies"]
    assert any(d.startswith("lxml") for d in deps)
    assert not any(d.lower().startswith("fonttools") for d in deps)

    extras = data["project"]["optional-dependencies"]
    assert any(d.lower().startswith("fonttools") for d in extras["pptx"])

    sdist_include = set(data["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])
    assert "/evidence/" not in sdist_include
    assert "/research/" not in sdist_include
    assert {"/src/", "/tests/", "/corpus/"} <= sdist_include


def test_docx_workflows_succeed_without_fonttools(tmp_docx, tmp_path, without_fonttools):
    assert check(tmp_docx) == []
    assert compare(tmp_docx, tmp_docx) == []

    cov = coverage_for(tmp_docx, [], source=tmp_docx)
    items = {item.id: item for item in cov.items}
    assert items["docx.comments"].status is CoverageStatus.CHECKED
    assert items["docx.fidelity.main-story"].status is CoverageStatus.CHECKED

    server = Server(no_config=True)
    res = server.call({"name": "compare", "arguments": {
        "source": str(tmp_docx), "edited": str(tmp_docx),
    }})
    assert res["isError"] is False
    assert "0 error(s)" in res["content"][0]["text"]


def test_doctor_is_ready_for_docx_without_fonttools(without_fonttools):
    report = doctor_module.build_report()
    assert report["schema_version"] == 1
    assert report["status"] == "ready"
    cap = next(c for c in report["capabilities"] if c["id"] == "pptx.font-metrics")
    assert cap["status"] == "optional-missing"
    assert "ooxml-integrity[pptx]" in cap["detail"]
    assert report["fonts"]["probes"] == []
    assert report["fonts"]["failures"]

    buf = StringIO()
    with redirect_stdout(buf):
        code = main(["doctor", "--json"])
    assert code == EXIT_OK
    cli_report = json.loads(buf.getvalue())
    assert cli_report["status"] == "ready"


def test_pptx_fails_closed_cleanly_without_fonttools(root, without_fonttools):
    deck = root / "corpus" / "deck.pptx"
    if not deck.is_file():
        pytest.skip("corpus/deck.pptx missing")

    findings = check_pptx(deck)
    codes = {f.code for f in findings}
    assert "INT001" not in codes
    ppt000 = [f for f in findings if f.code == "PPT000"]
    assert len(ppt000) == 1
    assert ppt000[0].severity is ERROR
    assert "ooxml-integrity[pptx]" in ppt000[0].message
    # Geometry checks still ran alongside the fail-closed PPT000.
    assert "PPT004" in codes or "PPT006" in codes

    cov = coverage_for(deck, findings)
    items = {item.id: item for item in cov.items}
    assert items["pptx.font-metrics"].status is CoverageStatus.SKIPPED
    assert items["pptx.text-overflow"].status is CoverageStatus.SKIPPED
    assert "ooxml-integrity[pptx]" in items["pptx.font-metrics"].reason


def test_fix_renumber_revisions_works_without_evidence_or_fonttools(
    tmp_docx, tmp_path, without_fonttools
):
    doc = read_part(tmp_docx, "word/document.xml")
    dup = (
        '<w:p><w:ins w:id="501" w:author="Reviewer" w:date="2026-10-01T00:00:00Z">'
        '<w:r><w:t>First</w:t></w:r></w:ins>'
        '<w:ins w:id="501" w:author="Reviewer" w:date="2026-10-01T00:00:00Z">'
        '<w:r><w:t>Second</w:t></w:r></w:ins></w:p>'
    )
    broken = repack(
        tmp_docx, tmp_path / "dup-rev.docx",
        {"word/document.xml": doc.replace("</w:body>", dup + "</w:body>").encode()},
    )
    assert any(f.code == "REV001" for f in check(broken))

    out = tmp_path / "fixed.docx"
    report = fix(broken, out, against=tmp_docx)
    assert report.exit_code == EXIT_REPAIRED
    assert report.verification is not None and report.verification.passed
    assert not any(f.code == "REV001" for f in check(out))
