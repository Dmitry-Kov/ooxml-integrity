"""
pptx layout checks, tested against the corpus's declared intent.

Every shape in `corpus/deck.pptx` is named with the verdict it is designed to
produce. These tests assert the checker agrees with those names - so a fixture
whose label is wrong fails just as loudly as a checker that is wrong, and the
two are told apart by reading which.
"""
from __future__ import annotations

import pytest

from docx_integrity import Severity, check_pptx
from docx_integrity.fonts import (
    METRIC_SUBSTITUTES, SIMILAR_SUBSTITUTES, load_metrics, resolve_face,
)
from docx_integrity.pptx_layout import (
    DRAWINGML_LINE_SPACING, layout_shape, read_deck,
)


@pytest.fixture(scope="module")
def deck_path(root):
    p = root / "corpus" / "deck.pptx"
    if not p.exists():
        pytest.skip("corpus/deck.pptx missing; run research/build_pptx_corpus.py")
    return p


@pytest.fixture(scope="module")
def deck(deck_path):
    return read_deck(deck_path)


@pytest.fixture(scope="module")
def findings(deck_path):
    return check_pptx(deck_path)


def intent(name: str) -> str:
    return name.split("_", 1)[0]


def flagged(findings) -> set[str]:
    """Shape names with a finding at WARN or above."""
    out = set()
    for f in findings:
        if f.severity >= Severity.WARN and "/" in f.where:
            out.add(f.where.split("/", 1)[1])
    return out


# ----------------------------------------------------------------- the corpus
def test_every_shape_resolves_geometry_and_font(deck):
    assert deck.shapes, "no shapes were read"
    for s in deck.shapes:
        assert s.width > 0 and s.height > 0, f"{s.name} has no geometry"
        for p in s.paragraphs:
            for r in p.runs:
                assert r.size_pt > 0, f"{s.name}: run with no resolved size"
                assert r.font, f"{s.name}: run with no resolved font"


def test_shapes_designed_to_fit_are_not_flagged(deck, findings):
    bad = flagged(findings)
    fits = {s.name for s in deck.shapes if intent(s.name) == "FIT"}
    false_positives = fits & bad
    assert not false_positives, (
        f"shapes designed to fit were flagged: {sorted(false_positives)}"
    )


def test_shapes_designed_to_overflow_are_all_caught(deck, findings):
    bad = flagged(findings)
    overs = {s.name for s in deck.shapes if intent(s.name) == "OVER"}
    missed = overs - bad
    assert not missed, f"overflow not caught in: {sorted(missed)}"


def test_offcanvas_shapes_are_caught(deck, findings):
    codes = {f.where.split("/", 1)[1]: f.code for f in findings
             if f.code == "PPT004"}
    for s in deck.shapes:
        if intent(s.name) == "OFFCANVAS":
            assert s.name in codes, f"{s.name} was not reported as off-canvas"


def test_overlapping_shapes_are_caught(findings):
    overlaps = [f for f in findings if f.code == "PPT006"]
    assert overlaps, "the overlapping pair was not reported"
    assert any("OVERLAP" in f.where for f in overlaps)


def test_autofit_shrink_is_a_warning_not_an_error(findings):
    """A deck asking for shrink-to-fit with no stored scale is renderer-dependent."""
    ppt005 = [f for f in findings if f.code == "PPT005"]
    assert ppt005, "the autofit-without-scale case was not reported"
    assert all(f.severity is Severity.WARN for f in ppt005)


def test_grow_shape_autofit_is_not_reported(findings):
    """spAutoFit means the box grows to the text, so overflow is not a defect."""
    assert not any("AUTOFIT_grow_shape" in f.where for f in findings
                   if f.severity >= Severity.WARN)


def test_unavailable_font_downgrades_confidence(deck_path, findings):
    ppt007 = [f for f in findings if f.code == "PPT007"]
    assert ppt007, "the unavailable font was not reported"
    assert all(f.severity is Severity.INFO for f in ppt007)
    assert "estimate" in ppt007[0].message


def test_no_wrap_overrun_is_horizontal_not_vertical(deck, findings):
    """With wrap off the text runs out the side, however tall the box is."""
    ppt003 = [f for f in findings if f.code == "PPT003"]
    assert ppt003, "the no-wrap overrun was not reported"
    assert "wrap is off" in ppt003[0].message
    shape = next(s for s in deck.shapes if s.name == "OVER_nowrap_single_line")
    result = layout_shape(shape)
    assert result.vertical_overflow_ratio < 1.0, (
        "this shape's box is tall enough; only the width is the problem"
    )


def test_insets_reduce_the_usable_box(deck):
    fat = next(s for s in deck.shapes if s.name == "OVER_fat_insets")
    zero = next(s for s in deck.shapes if s.name == "FIT_zero_insets")
    assert fat.usable_height_emu < zero.usable_height_emu
    assert layout_shape(fat).vertical_overflow_ratio > 1.0
    assert layout_shape(zero).vertical_overflow_ratio < 1.0


def test_mixed_run_sizes_take_line_height_from_the_tallest_run(deck):
    shape = next(s for s in deck.shapes if s.name == "FIT_mixed_run_sizes")
    sizes = {r.size_pt for p in shape.paragraphs for r in p.runs if r.text.strip()}
    assert len(sizes) > 1, "fixture no longer has mixed sizes"
    result = layout_shape(shape)
    # First line carries the 32pt run, the rest are 12pt. A model using one
    # size for the whole paragraph would give 2 x 38.4 = 76.8pt and call it
    # overflow; per-line heights give a smaller, correct total.
    naive = result.lines * max(sizes) * DRAWINGML_LINE_SPACING
    assert result.text_height_pt < naive


# ------------------------------------------------------------------- metrics
def test_line_spacing_is_the_measured_constant():
    """1.2 was established by rendering, and is not a font-derived value."""
    assert DRAWINGML_LINE_SPACING == 1.2
    m = load_metrics("Calibri")
    font_derived = m.line_height_pt(18) / 18
    assert abs(font_derived - DRAWINGML_LINE_SPACING) > 0.01, (
        "if these ever coincide, this test no longer proves the distinction"
    )


@pytest.mark.parametrize("declared", sorted(METRIC_SUBSTITUTES))
def test_metric_substitutes_resolve_to_something_trustworthy(declared):
    face = resolve_face(declared)
    if face.match == "fallback":
        pytest.skip(f"no substitute for {declared} installed here")
    assert face.trustworthy, (
        f"{declared} resolved to {face.family} graded {face.match!r}; a face in "
        "METRIC_SUBSTITUTES must never be graded below 'metric'"
    )


@pytest.mark.parametrize("declared", sorted(SIMILAR_SUBSTITUTES))
def test_similar_substitutes_are_never_called_trustworthy(declared):
    """The bug this guards: DejaVu Sans was graded metric-compatible with Segoe UI."""
    face = resolve_face(declared)
    if face.match == "exact":
        pytest.skip(f"{declared} is actually installed here")
    assert not face.trustworthy, (
        f"{declared} resolved to {face.family} graded {face.match!r}, which "
        "claims width accuracy the pairing does not have"
    )


def test_unknown_family_degrades_rather_than_raising():
    face = resolve_face("Definitely Not A Real Font 12345")
    assert face.match == "fallback"
    assert not face.trustworthy
    assert "guess" in face.note


def test_missing_file_is_reported_not_raised(tmp_path):
    findings = check_pptx(tmp_path / "nope.pptx")
    assert [f.code for f in findings] == ["PKG000"]


def test_not_a_package_is_reported_not_raised(tmp_path):
    p = tmp_path / "junk.pptx"
    p.write_bytes(b"not a zip")
    findings = check_pptx(p)
    assert [f.code for f in findings] == ["PKG002"]
