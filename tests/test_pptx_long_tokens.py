"""PowerPoint-observed long-word wrapping, plus font-independent boundaries."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from lxml import etree

from conftest import read_part, repack
from ooxml_integrity import Severity, check_pptx
from ooxml_integrity.coverage import CoverageItem, CoverageStatus, pptx_coverage
from ooxml_integrity.fonts import EMU_PER_POINT, Metrics, ResolvedFace
from ooxml_integrity.pptx_checks import check_text_overflow
from ooxml_integrity.pptx_layout import (
    A, Deck, Paragraph, Run, Shape, _build_lines, _split_runs, layout_shape, read_deck,
)


def shape(text="W" * 20, *, width=50, height=120, **kwargs):
    return Shape("test", 1, 0, 0, round(width * EMU_PER_POINT),
                 round(height * EMU_PER_POINT),
                 paragraphs=[Paragraph([Run(text, 20, "Test", False, False)])],
                 insets=(0, 0, 0, 0), **kwargs)


@pytest.fixture
def metrics(monkeypatch):
    # Ten points per character at 20pt. No host fonts or approximate geometry.
    m = Metrics(ResolvedFace("Test", Path("unused.ttf"), "Test", "exact"),
                1000, 800, 200, 0, {cp: 500 for cp in range(32, 127)}, 500, {})
    monkeypatch.setattr("ooxml_integrity.pptx_layout._metrics_for", lambda run: m)
    monkeypatch.setattr("ooxml_integrity.pptx_checks.measurement_available",
                        lambda: (True, "test metrics"))
    return m


def findings_for(s):
    return check_text_overflow(Deck(Path("test.pptx"), 9144000, 6858000, [s], {}))


def rendered_lines(s):
    notes = []
    para = s.paragraphs[0]
    pieces, _ = _split_runs(para, s.font_scale, notes)
    return ["".join(p.text for p in line) for line in _build_lines(
        pieces, s.usable_width_emu / EMU_PER_POINT, s.wrap, notes,
        latin_line_break=para.latin_line_break)]


def test_powerpoint_observations_are_pinned_and_match_the_model(root):
    manifest = json.loads((root / "docs/calibration/pptx-long-tokens/evidence.json").read_text())
    path = root / manifest["fixture"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["fixture_sha256"]
    deck = read_deck(path)
    findings = check_pptx(path)
    assert len(deck.shapes) == len(manifest["cases"]) == 12
    # These must be genuine old-model false negatives, not boxes so low that
    # even the erroneous one-line estimate would already report an error.
    for index in (1, 9):
        s = deck.shapes[index]
        one_line_height = max(r.size_pt for p in s.paragraphs for r in p.runs) * 1.2
        assert one_line_height < s.usable_height_emu / EMU_PER_POINT
        assert layout_shape(s).vertical_overflow_ratio > 1.05
    for s, case in zip(deck.shapes, manifest["cases"]):
        assert s.name == case["shape"]
        result = layout_shape(s)
        assert result.measured and result.confident
        assert result.lines == case["observed_line_count"]
        assert rendered_lines(s) == case["observed_lines"]
        actual = [(f.code, f.severity.name) for f in findings
                  if f.where == f"slide{s.slide}/{s.name}" and f.severity >= Severity.WARN]
        assert actual == [tuple(v) for v in case["expected_findings"]]
        image = root / case["render"]
        assert hashlib.sha256(image.read_bytes()).hexdigest() == case["render_sha256"]


def test_wrapped_word_clean_control_and_vertical_defect(metrics):
    clean = shape()
    defect = replace(clean, height=24 * EMU_PER_POINT)
    assert layout_shape(clean).lines == layout_shape(defect).lines == 4
    assert findings_for(clean) == []
    assert [(f.code, f.severity) for f in findings_for(defect)] == [("PPT001", Severity.ERROR)]


@pytest.mark.parametrize("width,lines,confident", [(50, 1, True), (49, 2, False), (34, 2, True)])
def test_exact_and_near_character_wrap_boundary(metrics, width, lines, confident):
    s = shape("WWWWW", width=width, height=24)
    r = layout_shape(s)
    assert r.lines == lines
    assert r.confident is confident
    found = findings_for(s)
    if width == 50:
        assert found == []
    elif not confident:
        assert found[0].severity is Severity.WARN
        assert "character-wrap boundary" in found[0].message
    else:
        assert found[0].severity is Severity.ERROR


@pytest.mark.parametrize("width,expected", [(10, []), (9.8, []), (9, ["PPT003"]), (0, ["PPT003"])])
def test_single_glyph_too_wide_and_horizontal_tolerance(metrics, width, expected):
    s = shape("W", width=width)
    assert layout_shape(s).lines == 1
    assert [f.code for f in findings_for(s)] == expected


def test_no_wrap_stays_a_single_horizontal_overrun(metrics):
    s = shape(wrap=False)
    assert layout_shape(s).lines == 1
    assert [f.code for f in findings_for(s)] == ["PPT003"]
    assert "wrap is off" in findings_for(s)[0].message


def test_insets_and_paragraph_indent_reduce_character_wrap_width(metrics):
    s = shape("W" * 12, width=70)
    s.insets = (10 * EMU_PER_POINT, 0, 10 * EMU_PER_POINT, 0)
    s.paragraphs[0].bullet_indent_emu = 10 * EMU_PER_POINT
    assert layout_shape(s).lines == 3  # 40pt available, four characters per line
    s.paragraphs[0].bullet_indent_emu = 45 * EMU_PER_POINT
    assert any(f.code == "PPT003" for f in findings_for(s))


def test_stored_scale_and_autofit_contracts_are_preserved(metrics):
    s = shape(height=24, autofit="normAutofit", font_scale=0.5)
    assert layout_shape(s).lines == 2
    assert findings_for(s) == []
    s.font_scale = 1.0
    assert [f.code for f in findings_for(s)] == ["PPT005"]
    s.autofit = "spAutoFit"
    assert findings_for(s) == []


def test_run_boundaries_do_not_create_word_boundaries(metrics):
    s = shape("Hi WWWW")
    s.paragraphs[0].runs = [Run(t, 20, "Test", False, False) for t in ("Hi WW", "WW")]
    assert rendered_lines(s) == ["Hi", "WWWW"]
    s.paragraphs[0].runs = [Run("W" * 3, 20, "Test", False, False) for _ in range(4)]
    assert rendered_lines(s) == ["WWWWW", "WWWWW", "WW"]


def test_each_character_keeps_its_run_size_and_style(metrics):
    s = shape()
    s.paragraphs[0].runs = [Run("W" * 5, 20, "Test", True, False),
                            Run("W" * 10, 10, "Test", False, True)]
    r = layout_shape(s)
    assert r.lines == 2
    assert r.text_height_pt == 36  # 24pt first line + 12pt second line


def test_legacy_kerning_is_reset_at_a_character_break(metrics):
    metrics.kerning[(ord("W"), ord("W"))] = -100
    s = shape("WWWW", width=26)
    assert rendered_lines(s) == ["WWW", "W"]
    assert layout_shape(s).widest_line_pt == 26


@pytest.mark.parametrize("text,expected", [
    ("WWWWWW\nX", ["WWWWW", "W", "X"]),
    ("WWWWW \nX", ["WWWWW", "X"]),
    ("WWWWWW\n", ["WWWWW", "W", ""]),
    ("WWWWW   ", ["WWWWW"]),
])
def test_explicit_breaks_and_trailing_whitespace(metrics, text, expected):
    assert rendered_lines(shape(text)) == expected


def test_latin_break_option_uses_remaining_line_space(metrics):
    s = shape("Hi " + "W" * 6)
    assert rendered_lines(s) == ["Hi", "WWWWW", "W"]
    s.paragraphs[0].latin_line_break = True
    assert rendered_lines(s) == ["Hi WW", "WWWW"]


@pytest.mark.parametrize("text", ["é" * 20, "a\u0301" * 20, "https://example.invalid/long-path"])
def test_unmodelled_character_breaking_cannot_be_a_confident_error(metrics, text):
    s = shape(text)
    r = layout_shape(s)
    assert not r.confident
    found = findings_for(s)
    assert found and all(f.severity is Severity.WARN for f in found)
    assert any("not modelled" in f.message for f in found)


def test_missing_and_fallback_metrics_fail_closed(metrics, monkeypatch):
    metrics.face = replace(metrics.face, match="fallback")
    assert all(f.severity is Severity.WARN for f in findings_for(shape(height=24)))
    monkeypatch.setattr("ooxml_integrity.pptx_layout._metrics_for", lambda run: None)
    assert [f.code for f in findings_for(shape())] == ["PPT000"]


def test_long_token_measurement_work_is_linear(metrics, monkeypatch):
    count = 0
    original = Metrics.advance

    def counted(self, cp):
        nonlocal count
        count += 1
        return original(self, cp)

    monkeypatch.setattr(Metrics, "advance", counted)
    s = shape("W" * 10000)
    assert layout_shape(s).lines == 2000
    assert count <= 3 * 10000


@pytest.mark.parametrize("source", ["paragraph", "shape-level", "shape-default", "presentation-level", "presentation-default"])
def test_latin_break_inheritance_and_direct_override(root, tmp_path, source):
    path = root / "corpus/pptx-long-tokens.pptx"
    slide_name = "ppt/slides/slide9.xml"
    slide = etree.fromstring(read_part(path, slide_name).encode())
    presentation = etree.fromstring(read_part(path, "ppt/presentation.xml").encode())
    a = lambda name: f"{{{A}}}{name}"
    ppr = slide.find(".//" + a("pPr"))
    if source == "paragraph":
        parent = ppr
    else:
        if source.startswith("shape"):
            styles = slide.find(".//" + a("lstStyle"))
        else:
            pns = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
            styles = presentation.find(pns + "defaultTextStyle")
            if styles is None:
                styles = etree.SubElement(presentation, pns + "defaultTextStyle")
        tag = a("defPPr" if source.endswith("default") else "lvl1pPr")
        parent = styles.find(tag)
        if parent is None:
            parent = etree.SubElement(styles, tag)
    parent.set("latinLnBrk", "1")

    def save():
        return repack(path, tmp_path / "inheritance.pptx", {
            slide_name: etree.tostring(slide),
            "ppt/presentation.xml": etree.tostring(presentation),
        })

    assert read_deck(save()).shapes[8].paragraphs[0].latin_line_break
    ppr.set("latinLnBrk", "0")
    assert not read_deck(save()).shapes[8].paragraphs[0].latin_line_break


def test_coverage_does_not_call_approximate_wrapping_checked(root, tmp_path):
    path = root / "corpus/pptx-long-tokens.pptx"
    part = "ppt/slides/slide1.xml"
    xml = read_part(path, part).replace("W" * 20, "é" * 20)
    changed = repack(path, tmp_path / "approximate.pptx", {part: xml.encode()})
    report = pptx_coverage(changed, check_pptx(changed))
    item = next(i for i in report.items if i.id == "pptx.text-overflow")
    assert item.status is CoverageStatus.ESTIMATED


def test_coverage_confidence_failure_is_skipped_not_a_crash(root, monkeypatch):
    monkeypatch.setattr("ooxml_integrity.coverage._font_coverage", lambda *args:
                        CoverageItem("pptx.font-metrics", CoverageStatus.CHECKED, "test"))

    def fail(shape):
        raise RuntimeError("measurement failed")

    monkeypatch.setattr("ooxml_integrity.coverage.layout_shape", fail)
    report = pptx_coverage(root / "corpus/pptx-long-tokens.pptx", [])
    item = next(i for i in report.items if i.id == "pptx.text-overflow")
    assert item.status is CoverageStatus.SKIPPED
