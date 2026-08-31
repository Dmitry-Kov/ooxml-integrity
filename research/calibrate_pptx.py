#!/usr/bin/env python3
"""
Calibrate the text measurement against a real renderer.

The question: when the checker says a paragraph wraps to 7 lines with a line
pitch of 17.1pt, how close is that to what a renderer actually does? Without
this number every overflow verdict is an assertion.

Method, and why it is shaped this way:

* **One shape per rendered deck.** An earlier version tried to attribute text
  lines to shapes by geometry on a full slide, and got it wrong wherever two
  shapes shared a horizontal band - producing nonsense like a 767pt "measured"
  height for a one-line label. Rendering each shape alone removes the
  attribution problem entirely.
* **Compare line count and line pitch, not total height.** pdfplumber reports a
  character's height from the font matrix, so a single rendered line comes back
  as the font size rather than the line box. Comparing that against a computed
  line height produced a constant +22% error that was an artefact of comparing
  two different quantities. Line count and baseline-to-baseline pitch are both
  unambiguous, and together they determine the height.
* **Autofit off, box made huge.** The point is to measure how text lays out, not
  how a renderer clips it. Each probe puts the shape's text in a box wide enough
  to preserve the original wrapping and tall enough that nothing is dropped.

Caveat that limits what any of this proves: LibreOffice is not PowerPoint.
Agreement here shows the measurement is sane, not that it matches what Word or
PowerPoint would do. That comparison needs a machine with PowerPoint on it.
"""
from __future__ import annotations

import os
import shutil
import statistics
import subprocess
import sys
from collections import defaultdict

import pdfplumber
from pptx import Presentation
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Emu, Pt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from docx_integrity.fonts import EMU_PER_POINT  # noqa: E402
from docx_integrity.pptx_layout import (  # noqa: E402
    DRAWINGML_LINE_SPACING, layout_shape, read_deck,
)

DECK = os.environ.get("DI_PPTX", "../corpus/deck.pptx")
WORK = "/tmp/pptx-calib"


def probe_deck(shape, out_path: str) -> None:
    """One slide, one text box: same text, same width, same font, room to spare."""
    prs = Presentation()
    prs.slide_width = Emu(12192000)
    prs.slide_height = Emu(6858000)
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    box = slide.shapes.add_textbox(
        Emu(200000), Emu(200000),
        Emu(shape.width), Emu(6000000),      # original width, generous height
    )
    tf = box.text_frame
    tf.word_wrap = shape.wrap
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left, tf.margin_right = Emu(shape.insets[0]), Emu(shape.insets[2])
    tf.margin_top, tf.margin_bottom = Emu(shape.insets[1]), Emu(shape.insets[3])

    for i, para in enumerate(shape.paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        for run in para.runs:
            if run.text == "\n":
                continue
            r = p.add_run()
            r.text = run.text
            r.font.size = Pt(run.size_pt)
            r.font.bold = run.bold
            r.font.italic = run.italic
            r.font.name = run.font
    prs.save(out_path)


def render(path: str) -> str:
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf",
         "--outdir", os.path.dirname(path), path],
        capture_output=True, timeout=300, check=False,
    )
    pdf = path.rsplit(".", 1)[0] + ".pdf"
    return pdf if os.path.exists(pdf) else ""


def measure_pdf(pdf: str, tol: float = 1.5) -> tuple[int, float | None]:
    """Rendered line count, and median baseline-to-baseline pitch in points."""
    with pdfplumber.open(pdf) as doc:
        if not doc.pages:
            return 0, None
        rows: dict[float, list] = defaultdict(list)
        for ch in doc.pages[0].chars:
            rows[round(ch["top"] / tol) * tol].append(ch)
        if not rows:
            return 0, None
        tops = sorted(min(c["top"] for c in v) for v in rows.values())
    pitches = [b - a for a, b in zip(tops, tops[1:]) if b - a > 1.0]
    return len(tops), (statistics.median(pitches) if pitches else None)


def main() -> int:
    deck = read_deck(DECK)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)

    hdr = (f'{"shape":32}{"lines":13}{"pitch pred":12}{"pitch real":12}'
           f'{"pitch delta":13}')
    print(f"deck: {DECK}   probes rendered one shape at a time\n")
    print(hdr)
    print("-" * len(hdr))

    line_exact = line_total = 0
    line_off_by_one = 0
    pitch_deltas: list[float] = []
    untrusted: list[str] = []

    for shape in deck.shapes:
        pred = layout_shape(shape)
        if pred is None:
            continue
        if not pred.confident:
            untrusted.append(shape.name)

        probe = os.path.join(WORK, f"{shape.name}.pptx")
        probe_deck(shape, probe)
        pdf = render(probe)
        if not pdf:
            print(f'{shape.name[:31]:32}{"render failed":13}')
            continue

        real_lines, real_pitch = measure_pdf(pdf)

        # Predicted pitch comes from the library's own model, never from a
        # formula copied into this script - a calibration that re-derives the
        # thing it is testing proves nothing. An earlier version of this file
        # did exactly that and kept reporting a stale +1.7% after the model was
        # already fixed.
        sizes = {r.size_pt for p in shape.paragraphs for r in p.runs
                 if r.text.strip()}
        uniform = len(sizes) == 1
        pred_pitch = (max(sizes) * DRAWINGML_LINE_SPACING) if sizes else None

        line_total += 1
        if real_lines == pred.lines:
            line_exact += 1
        elif abs(real_lines - pred.lines) == 1:
            line_off_by_one += 1

        if pred_pitch and real_pitch and uniform:
            d = (pred_pitch - real_pitch) / real_pitch
            pitch_deltas.append(abs(d))
            pitch_s, delta_s = f"{real_pitch:.2f}", f"{d * 100:+.1f}%"
        elif pred_pitch and real_pitch:
            # Mixed run sizes: each line takes its height from its own tallest
            # run, so "the pitch" is not one number and a single delta would be
            # meaningless. Line count is still comparable.
            pitch_s, delta_s = f"{real_pitch:.2f}", "mixed sizes"
        else:
            pitch_s = "-" if not real_pitch else f"{real_pitch:.2f}"
            delta_s = "single line"

        flag = "" if real_lines == pred.lines else "  <-"
        print(f'{shape.name[:31]:32}'
              f'{f"{pred.lines} / {real_lines}":13}'
              f'{f"{pred_pitch:.2f}" if pred_pitch else "-":12}'
              f'{pitch_s:12}{delta_s:13}{flag}')

    print()
    print(f"line count      exact {line_exact}/{line_total}, "
          f"off by one {line_off_by_one}/{line_total}")
    if pitch_deltas:
        pitch_deltas.sort()
        print(f"line pitch      uniform-size shapes only, n={len(pitch_deltas)}  "
              f"median {statistics.median(pitch_deltas) * 100:.2f}%  "
              f"worst {max(pitch_deltas) * 100:.2f}%")
    if untrusted:
        print(f"not confident   {len(untrusted)}: {', '.join(untrusted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
