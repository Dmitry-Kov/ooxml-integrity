"""Coverage and doctor are user-facing honesty contracts, not diagnostics."""
from __future__ import annotations

import json
import re

import pytest

from conftest import read_part, repack, run_cli

from ooxml_integrity import coverage as coverage_module
from ooxml_integrity.cli import EXIT_FINDINGS, EXIT_OK, main
from ooxml_integrity.coverage import CoverageStatus, pptx_coverage
from ooxml_integrity.pptx_layout import layout_shape, read_deck


DOCX_COVERAGE_IDS = (
    "package.read",
    "package.xml",
    "package.content-types",
    "package.relationships",
    "docx.styles",
    "docx.numbering",
    "docx.footnotes",
    "docx.comments",
    "docx.revisions",
    "docx.tables",
    "docx.content-controls",
    "docx.text-whitespace",
    "docx.header-footer-semantics",
    "docx.media-content",
    "docx.strict-wordprocessingml",
    "docx.fidelity.main-story",
    "docx.fidelity.note-bodies",
    "docx.fidelity.headers-footers",
)

PPTX_COVERAGE_IDS = (
    "package.read",
    "pptx.package-integrity",
    "pptx.slide-order",
    "pptx.font-metrics",
    "pptx.text-overflow",
    "pptx.off-slide-geometry",
    "pptx.text-shape-overlap",
    "pptx.grouped-shapes",
    "pptx.tables",
    "pptx.smartart",
    "pptx.charts",
    "pptx.fields",
    "pptx.rotated-bounds",
    "pptx.vertical-text",
    "pptx.master-layout-objects",
    "pptx.fidelity.source",
)


def _coverage(result) -> dict:
    return json.loads(result.stdout)["files"][0]["coverage"]


def _by_id(report: dict) -> dict[str, dict]:
    return {item["id"]: item for item in report["items"]}


def test_docx_json_coverage_has_stable_schema_and_identifiers(base_docx):
    result = run_cli("check", str(base_docx), "--coverage", "--json")

    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    report = _coverage(result)
    assert report["schema_version"] == 1
    assert set(report["summary"]) == {
        "checked", "not-present", "estimated", "skipped", "unsupported",
    }
    assert tuple(item["id"] for item in report["items"]) == DOCX_COVERAGE_IDS
    assert len(_by_id(report)) == len(report["items"])
    assert all(item["reason"] for item in report["items"])

    items = _by_id(report)
    assert items["package.read"]["status"] == "checked"
    assert items["docx.header-footer-semantics"]["status"] == "unsupported"
    assert items["docx.fidelity.main-story"]["status"] == "skipped"


def test_human_coverage_is_qualified_concise_and_expandable(base_docx):
    concise = run_cli("check", str(base_docx), "--coverage")
    detailed = run_cli("check", str(base_docx), "--coverage-details")

    assert concise.returncode == detailed.returncode == EXIT_OK
    assert "no findings in checked surfaces" in concise.stdout
    assert "coverage:" in concise.stdout
    assert "[unsupported] docx.header-footer-semantics" in concise.stdout
    assert "[checked] package.read" not in concise.stdout
    assert "[checked] package.read" in detailed.stdout
    assert "[not-present] docx.strict-wordprocessingml" in detailed.stdout


def test_requested_docx_comparison_is_reflected_per_surface(base_docx):
    result = run_cli(
        "check", str(base_docx), "--against", str(base_docx),
        "--coverage", "--json",
    )

    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    items = _by_id(_coverage(result))
    assert items["docx.fidelity.main-story"]["status"] == "checked"
    assert items["docx.fidelity.note-bodies"]["status"] == "checked"
    assert items["docx.fidelity.headers-footers"]["status"] == "checked"


def test_orphan_note_definitions_still_count_as_a_checked_surface(
        tmp_docx, tmp_path):
    document_part = "word/document.xml"
    document = read_part(tmp_docx, document_part)
    without_refs = re.sub(
        r"<w:(?:commentRangeStart|commentRangeEnd|commentReference|"
        r"footnoteReference)\b[^>]*/>",
        "",
        document,
    )
    fixture = repack(
        tmp_docx, tmp_path / "orphan-notes.docx",
        {document_part: without_refs.encode()},
    )

    result = run_cli("check", str(fixture), "--coverage", "--json")
    items = _by_id(_coverage(result))

    assert items["docx.footnotes"]["status"] == "checked"
    assert items["docx.comments"]["status"] == "checked"


def test_unreadable_file_has_an_explicit_skipped_inventory(tmp_path):
    result = run_cli(
        "check", str(tmp_path / "missing.docx"), "--coverage", "--json",
    )

    assert result.returncode == EXIT_FINDINGS
    report = _coverage(result)
    assert report["items"] == [{
        "id": "package.read",
        "status": "skipped",
        "reason": report["items"][0]["reason"],
    }]
    assert "could not read" in report["items"][0]["reason"]


def test_pptx_coverage_has_stable_ids_and_explicit_font_confidence(root):
    deck = root / "corpus" / "deck.pptx"
    if not deck.exists():
        pytest.skip("corpus/deck.pptx missing")

    result = run_cli("check", str(deck), "--coverage", "--json")
    report = _coverage(result)

    assert tuple(item["id"] for item in report["items"]) == PPTX_COVERAGE_IDS
    items = _by_id(report)
    assert items["pptx.package-integrity"]["status"] == "unsupported"
    assert items["pptx.font-metrics"]["status"] in {"estimated", "skipped"}
    assert items["pptx.text-overflow"]["status"] == \
        items["pptx.font-metrics"]["status"]
    assert items["pptx.fidelity.source"]["status"] == "skipped"


def test_pptx_source_comparison_is_unsupported_in_coverage(root, base_docx):
    deck = root / "corpus" / "deck.pptx"
    if not deck.exists():
        pytest.skip("corpus/deck.pptx missing")

    result = run_cli(
        "check", str(deck), "--against", str(base_docx),
        "--coverage", "--json",
    )

    assert result.returncode == EXIT_FINDINGS
    items = _by_id(_coverage(result))
    assert items["pptx.fidelity.source"]["status"] == "unsupported"
    assert any(
        finding["code"] == "FID000"
        for finding in json.loads(result.stdout)["files"][0]["findings"]
    )


def test_groups_tables_and_smartart_are_recognised_as_unsupported(
        root, tmp_path):
    deck = root / "corpus" / "deck.pptx"
    if not deck.exists():
        pytest.skip("corpus/deck.pptx missing")
    slide_part = "ppt/slides/slide1.xml"
    slide = read_part(deck, slide_part)
    constructs = """
      <p:grpSp/>
      <p:graphicFrame>
        <a:graphic><a:graphicData uri="urn:test:diagram"><a:tbl/></a:graphicData></a:graphic>
      </p:graphicFrame>
    """
    changed = slide.replace("</p:spTree>", constructs + "</p:spTree>")
    fixture = repack(
        deck, tmp_path / "unsupported.pptx", {slide_part: changed.encode()},
    )

    report = pptx_coverage(fixture, [])
    items = {item.id: item for item in report.items}

    assert items["pptx.grouped-shapes"].status is CoverageStatus.UNSUPPORTED
    assert items["pptx.tables"].status is CoverageStatus.UNSUPPORTED
    assert items["pptx.smartart"].status is CoverageStatus.UNSUPPORTED


def test_vertical_text_is_not_silently_measured(root, tmp_path):
    deck = root / "corpus" / "deck.pptx"
    if not deck.exists():
        pytest.skip("corpus/deck.pptx missing")
    slide_part = "ppt/slides/slide1.xml"
    slide = read_part(deck, slide_part)
    changed = slide.replace("<a:bodyPr", '<a:bodyPr vert="vert"', 1)
    fixture = repack(deck, tmp_path / "vertical.pptx", {
        slide_part: changed.encode(),
    })

    parsed = read_deck(fixture)
    vertical = [shape for shape in parsed.shapes if shape.vertical_text]
    assert len(vertical) == 1
    assert layout_shape(vertical[0]) is None
    items = {item.id: item for item in pptx_coverage(fixture, []).items}
    assert items["pptx.vertical-text"].status is CoverageStatus.UNSUPPORTED


def test_missing_font_metrics_mark_overflow_as_skipped(root, monkeypatch):
    deck = root / "corpus" / "deck.pptx"
    if not deck.exists():
        pytest.skip("corpus/deck.pptx missing")

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("test font resolver unavailable")

    monkeypatch.setattr(coverage_module, "resolve_face", unavailable)
    items = {item.id: item for item in pptx_coverage(deck, []).items}

    assert items["pptx.font-metrics"].status is CoverageStatus.SKIPPED
    assert items["pptx.text-overflow"].status is CoverageStatus.SKIPPED
    assert "resolver unavailable" in items["pptx.font-metrics"].reason


def test_doctor_reports_runtime_fonts_and_unavailable_checks():
    result = run_cli("doctor", "--json")

    assert result.returncode in (EXIT_OK, EXIT_FINDINGS), result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == 1
    assert report["runtime"]["python"]
    assert report["runtime"]["lxml"]
    assert report["runtime"]["libxml2"]
    assert report["runtime"]["fonttools"]
    assert set(report["fonts"]) == {"probes", "failures"}
    assert report["fonts"]["probes"] or report["fonts"]["failures"]
    assert all(font["confidence"] for font in report["fonts"]["probes"])
    assert {item["id"] for item in report["unavailable_checks"]} >= {
        "pptx.grouped-shapes",
        "pptx.tables",
        "pptx.smartart",
        "pptx.fidelity.source",
    }
    assert "docx.fidelity.headers-footers" not in {
        item["id"] for item in report["unavailable_checks"]
    }


def test_human_doctor_output_names_capability_confidence():
    result = run_cli("doctor")

    assert result.returncode in (EXIT_OK, EXIT_FINDINGS), result.stderr
    assert "runtime:" in result.stdout
    assert "pptx.font-metrics" in result.stdout
    assert "unavailable checks in this release:" in result.stdout


def test_doctor_fails_when_a_capability_is_unavailable(monkeypatch, capsys):
    report = {
        "schema_version": 1,
        "capabilities": [{
            "id": "pptx.font-metrics",
            "status": "unavailable",
            "confidence": "unavailable",
            "detail": "no usable font files",
        }],
    }
    monkeypatch.setattr(
        "ooxml_integrity.cli.build_doctor_report", lambda: report,
    )

    assert main(["doctor", "--json"]) == EXIT_FINDINGS
    assert json.loads(capsys.readouterr().out) == report
