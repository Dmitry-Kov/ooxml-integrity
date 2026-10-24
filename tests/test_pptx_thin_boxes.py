"""A text box no taller than its insets has no room for text.

Through 0.8.3 its overflow ratio was taken as 0, so text in it was never
reported; a box 0.8pt taller was. The fixture's renders are in
docs/calibration/pptx-thin-boxes/evidence.json.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from conftest import ROOT, needs_zlib_bytes
from ooxml_integrity import Severity, check_pptx
from ooxml_integrity.fonts import EMU_PER_POINT, Metrics, ResolvedFace
from ooxml_integrity.pptx_checks import check_text_overflow
from ooxml_integrity.pptx_layout import (
    Deck, LayoutResult, Paragraph, Run, Shape, read_deck,
)
from research.pptx_thin_boxes import PROBES, build

EVIDENCE = json.loads((ROOT / "docs/calibration/pptx-thin-boxes/evidence.json").read_text())
FIXTURE = ROOT / EVIDENCE["fixture"]
INSETS = (91440, 45720, 91440, 45720)            # 7.2pt left/right, 3.6pt top/bottom


@pytest.fixture
def metrics(monkeypatch):
    m = Metrics(ResolvedFace("Test", Path("unused.ttf"), "Test", "exact"),
                1000, 800, 200, 0, {cp: 100 for cp in range(32, 127)}, 100, {})
    monkeypatch.setattr("ooxml_integrity.pptx_layout._metrics_for", lambda run: m)
    monkeypatch.setattr("ooxml_integrity.pptx_checks.measurement_available",
                        lambda: (True, "test metrics"))
    return m


def box(height, size=18, insets=INSETS, **kwargs):
    return Shape("box", 1, 0, 0, round(500 * EMU_PER_POINT), round(height * EMU_PER_POINT),
                 paragraphs=[Paragraph([Run("Label", size, "Test", False, False)])],
                 insets=insets, **kwargs)


def findings(s):
    return [(f.code, f.severity, f.message) for f in
            check_text_overflow(Deck(Path("t.pptx"), 9144000, 6858000, [s], {}))]


def test_a_box_without_room_has_an_infinite_ratio_not_zero():
    room = LayoutResult(1, 21.6, 0.0, 10.0, 100.0, True)
    empty = LayoutResult(0, 0.0, 0.0, 0.0, 100.0, True)
    assert room.vertical_overflow_ratio == math.inf
    assert empty.vertical_overflow_ratio == 0.0


@pytest.mark.parametrize("height", [0, 4, 7.2])
def test_text_taller_than_a_box_without_room_is_an_error(metrics, height):
    [(code, severity, message)] = findings(box(height))
    assert (code, severity) == ("PPT001", Severity.ERROR)
    assert message == (f"text needs 22pt in a box with no room for text: it is {height:.1f}pt "
                       "tall and its top and bottom insets take 7.2pt - 1 line(s)")


def test_text_no_taller_than_the_shape_is_a_warning(metrics):
    # A 2cm shape with 1cm insets on each side, as in LibreOffice's
    # TextDistancesInsets decks: the renderer decides where the text goes.
    cm = 360000
    shape = box(2 * cm / EMU_PER_POINT, size=12, insets=(91440, cm, 91440, cm))
    assert shape.height == 2 * cm
    [(code, severity, message)] = findings(shape)
    assert (code, severity) == ("PPT001", Severity.WARN)
    assert "no taller than the shape" in message


def test_a_box_with_a_little_room_is_reported_as_before(metrics):
    [(code, severity, message)] = findings(box(8))
    assert (code, severity) == ("PPT001", Severity.ERROR)
    assert message.startswith("text needs 22pt in a 1pt box - 21pt too tall")


def test_shrink_without_a_stored_scale_stays_ppt005(metrics):
    [(code, severity, _)] = findings(box(4, autofit="normAutofit"))
    assert (code, severity) == ("PPT005", Severity.WARN)


def test_a_box_that_fits_is_clean(metrics):
    assert findings(box(40)) == []


@needs_zlib_bytes
def test_the_fixture_rebuilds_byte_for_byte(tmp_path):
    out = tmp_path / "deck.pptx"
    build(out)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == EVIDENCE["fixture_sha256"]
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == EVIDENCE["fixture_sha256"]


@pytest.mark.parametrize("renderer", sorted(EVIDENCE["renderers"]))
def test_verdicts_match_what_each_renderer_drew(renderer):
    probes = EVIDENCE["renderers"][renderer]["probes"]
    flagged = {f.where.split("/", 1)[1]: f.severity for f in check_pptx(FIXTURE)
               if f.code == "PPT001"}
    assert {s.name for s in read_deck(FIXTURE).shapes} == set(PROBES)
    for name, (_, height, _) in PROBES.items():
        drawn = probes[name]
        outside = drawn["a_top_pt"] < -0.5 or drawn["x_bottom_pt"] > height + 0.5
        assert (name in flagged) == outside, (renderer, name)
        if outside:
            assert flagged[name] is Severity.ERROR, (renderer, name)
