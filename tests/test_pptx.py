"""
pptx layout checks, tested against the corpus's declared intent.

Every shape in `corpus/deck.pptx` is named with the verdict it is designed to
produce. These tests assert the checker agrees with those names - so a fixture
whose label is wrong fails just as loudly as a checker that is wrong, and the
two are told apart by reading which.
"""
from __future__ import annotations

import shutil

import pytest

from ooxml_integrity import Severity, check_pptx
from ooxml_integrity.fonts import (
    METRIC_SUBSTITUTES, SIMILAR_SUBSTITUTES, load_metrics, resolve_face,
)
from ooxml_integrity.pptx_layout import (
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


# ------------------------------------------------- the macOS silent-failure bug
class TestMeasurementUnavailable:
    """Regression for the worst bug this project has had.

    The first version looked for fonts only through `fc-match`. macOS ships no
    fontconfig, so on a Mac it found nothing, `layout_shape` skipped every
    paragraph, and a deck with seven overflowing shapes came back as `0
    error(s), 3 warning(s)` - the three geometry findings, and a clean bill of
    health on all the text. The checker had checked nothing and said so to
    nobody.

    Two things had to change: find fonts without fontconfig, and fail loudly
    when they cannot be found at all.
    """

    def test_fonts_are_found_without_fontconfig(self, monkeypatch):
        """The directory scan has to stand on its own."""
        import ooxml_integrity.fonts as fonts

        monkeypatch.setattr(fonts, "_fc_match", lambda pattern: None)
        fonts.resolve_face.cache_clear()
        fonts.load_metrics.cache_clear()
        try:
            face = fonts.resolve_face("Calibri")
            assert face.path.exists(), "no font file found without fontconfig"
            m = fonts.load_metrics("Calibri")
            assert m.text_width_pt("The quick brown fox", 18) > 0
        finally:
            fonts.resolve_face.cache_clear()
            fonts.load_metrics.cache_clear()

    def test_overflow_is_still_caught_without_fontconfig(
            self, monkeypatch, deck_path):
        """The exact scenario that failed on macOS."""
        import ooxml_integrity.fonts as fonts

        monkeypatch.setattr(fonts, "_fc_match", lambda pattern: None)
        fonts.resolve_face.cache_clear()
        fonts.load_metrics.cache_clear()
        try:
            found = check_pptx(deck_path)
            codes = {f.code for f in found}
            assert "PPT001" in codes, (
                "text overflow was not reported without fontconfig - this is the "
                "macOS bug returning"
            )
            assert "PPT000" not in codes, (
                "measurement should have worked via the directory scan"
            )
        finally:
            fonts.resolve_face.cache_clear()
            fonts.load_metrics.cache_clear()

    def test_no_fonts_at_all_reports_loudly(self, monkeypatch, deck_path):
        """With no fonts anywhere, the answer must be 'could not check'."""
        import ooxml_integrity.fonts as fonts

        monkeypatch.setattr(fonts, "_fc_match", lambda pattern: None)
        monkeypatch.setattr(fonts, "_index_font_dirs", lambda: {})
        fonts.resolve_face.cache_clear()
        fonts.load_metrics.cache_clear()
        try:
            found = check_pptx(deck_path)
            codes = {f.code for f in found}
            assert "PPT000" in codes, (
                "a checker that cannot measure must say so, not report clean"
            )
            ppt000 = [f for f in found if f.code == "PPT000"]
            assert any(f.severity is Severity.ERROR for f in ppt000)
            assert any("NOT checked" in f.message or "not measured" in f.message
                       for f in ppt000)
            # geometry does not need fonts, so it must still work
            assert "PPT004" in codes and "PPT006" in codes
        finally:
            fonts.resolve_face.cache_clear()
            fonts.load_metrics.cache_clear()

    def test_measurement_available_reports_what_it_uses(self):
        from ooxml_integrity.fonts import measurement_available

        ok, detail = measurement_available()
        assert ok
        assert "measuring with" in detail


def test_fallback_never_picks_a_non_latin_system_face(monkeypatch):
    """Regression: `.aqua kana` was chosen to measure English text on macOS.

    The last-resort branch sorted the font index alphabetically and took the
    first entry. A dot-prefixed macOS internal Japanese face sorts before
    everything, so English text was measured with a CJK font. Two guards now:
    dot-prefixed families never enter the index, and the pick requires basic
    Latin coverage.
    """
    import ooxml_integrity.fonts as fonts

    monkeypatch.setattr(fonts, "_fc_match", lambda pattern: None)
    fonts.resolve_face.cache_clear()
    fonts.load_metrics.cache_clear()
    fonts._index_font_dirs.cache_clear()
    try:
        index = fonts._index_font_dirs()
        assert not [k for k in index if k.startswith(".")], (
            "dot-prefixed system faces must not be indexed"
        )
        face = fonts.resolve_face("Some Font Nobody Has 98765")
        assert not face.family.startswith(".")
        m = fonts.load_metrics("Some Font Nobody Has 98765")
        # a face used to measure Latin text must actually have Latin glyphs
        for ch in "AaEeOo 0123456789.,":
            assert ord(ch) in m.widths, (
                f"fallback face {face.family!r} has no glyph for {ch!r}"
            )
    finally:
        fonts.resolve_face.cache_clear()
        fonts.load_metrics.cache_clear()
        fonts._index_font_dirs.cache_clear()


def test_styled_system_faces_are_excluded_too(tmp_path, monkeypatch):
    """A dot-prefixed face must not reach the index under its *style* key either.

    The guard lived in the index writer, but the composed key (`family:italic`)
    was written by a second line that skipped it. So `.sf ns mono` was rejected
    while `.sf ns mono:italic` was indexed, and an internal macOS system face
    stayed reachable for any italic run - the `.aqua kana` bug with one extra
    step.

    Only the macOS runner could see that, because no other platform ships
    dot-prefixed families. This test manufactures one, so the bug is catchable
    everywhere.
    """
    from fontTools.ttLib import TTFont
    import ooxml_integrity.fonts as fonts

    donor = fonts.resolve_face("Arial")
    if not donor.path or not donor.path.exists():
        pytest.skip("no font available to rename")

    font = TTFont(str(donor.path), fontNumber=0)
    for rec in font["name"].names:
        if rec.nameID == 1:
            rec.string = ".Fake System Face"
        elif rec.nameID in (2, 17):
            rec.string = "Italic"
        elif rec.nameID == 4:
            rec.string = ".Fake System Face Italic"
        elif rec.nameID == 6:
            rec.string = ".FakeSystemFace-Italic"
    font.save(str(tmp_path / "FakeSystemFace-Italic.ttf"))
    font.close()

    # A second, ordinary face, so a non-empty index proves the scan ran. Without
    # it an empty index would satisfy the assertion below for the wrong reason.
    shutil.copy(donor.path, tmp_path / "ordinary.ttf")

    monkeypatch.setattr(fonts, "FONT_DIRS", (str(tmp_path),))
    fonts._index_font_dirs.cache_clear()
    try:
        index = fonts._index_font_dirs()
        assert index, "the scan read nothing, so this proves nothing"
        assert not [k for k in index if k.startswith(".")], (
            f"dot-prefixed face reached the index: "
            f"{[k for k in index if k.startswith('.')]}"
        )
    finally:
        fonts._index_font_dirs.cache_clear()


def test_office_font_locations_are_searched():
    """Real Calibri beats any substitute, and Microsoft 365 hides it."""
    from ooxml_integrity.fonts import FONT_DIRS

    joined = " ".join(FONT_DIRS)
    assert "UBF8T346G9.Office" in joined, (
        "Microsoft 365 on macOS keeps its fonts in a group container, not in a "
        "font directory; without this path the real Calibri is never found"
    )
    assert "Windows/Fonts" in joined


def test_reading_fonts_is_quiet(capfd):
    """fontTools chatter about system fonts must not reach the user.

    macOS system faces have irregular `post` tables and fontTools reports
    lines like "144733 extra bytes in post.stringData array" on stderr. They
    are harmless for advance widths and pure noise in a check report.
    """
    import ooxml_integrity.fonts as fonts

    fonts.resolve_face.cache_clear()
    fonts.load_metrics.cache_clear()
    fonts._index_font_dirs.cache_clear()
    try:
        fonts._index_font_dirs()
        fonts.load_metrics("Calibri")
        out, err = capfd.readouterr()
        assert "extra bytes" not in err, f"fontTools noise leaked: {err[:200]}"
        assert "extra bytes" not in out
    finally:
        fonts.resolve_face.cache_clear()
        fonts.load_metrics.cache_clear()
        fonts._index_font_dirs.cache_clear()
