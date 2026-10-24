# Empty paragraphs and empty lines: renderer evidence and rule contract

Through 0.8.2 an empty paragraph added no height to a text box, an empty line
between two breaks or after a trailing break was always 18pt, and blank rows
below the last line of text counted wherever the text was anchored. So text
pushed out of its box by empty paragraphs between bullets was reported as
fitting, while a top-anchored title followed by a few breaks was reported as
overflowing when nothing was drawn outside it. 0.8.3 fixes both.

## What the model does

- **An empty line is as tall as the mark that ends it.** An empty paragraph
  is one line at the size of its `a:endParaRPr`, inherited like a run's size
  when absent (paragraph defaults, list styles, placeholder and master styles,
  presentation defaults). An empty line ended by a break has that break's
  `a:rPr` size; an empty last line after a trailing break has the paragraph
  mark's. The flat 1.2 line pitch, line spacing, stored shrink (`fontScale`)
  and line-space reduction apply as to any line. A paragraph mark's size does
  not change the height of a line that has text.
- **Spacing.** An empty paragraph keeps its `spcBef` and `spcAft`. There is no
  space above the first paragraph and none below the last.
- **The anchor decides whether blank rows show.** Blank rows above the first
  line of text (`lead`) and below the last one (`trail`) move glyphs only
  through the anchor: top-anchored text starts at the top whatever follows
  it, bottom-anchored text ends at the bottom whatever precedes it, and
  centred text moves by half the difference. The height compared with the box
  is the text's own extent plus `lead` for `t` (and for `just` and `dist`,
  which are treated as `t`), `trail` for `b`, and `|lead - trail|` for `ctr`.
  Blank rows between lines of text always count.
- **The anchor is inherited.** A placeholder without `anchor` takes it from
  its layout placeholder (the one with its `idx`, else the first of its
  type), then from the master's; a master has one title and one body
  placeholder, so `ctrTitle` reads the title's and `subTitle` and `obj` read
  the body's.

## Evidence

[`corpus/pptx-empty-lines.pptx`](../corpus/pptx-empty-lines.pptx) is built by
`python research/pptx_empty_lines.py build`, byte for byte. Each of its 33
slides holds one text box with zero insets and no autofit; its lines of text
start with `Abc` and `Xyz`, so a PDF render gives their positions, and an
empty line is measured by how far it pushes `Xyz`.
`research/pptx_empty_lines.py measure` reads a render;
[`evidence.json`](calibration/pptx-empty-lines/evidence.json) holds each
renderer's numbers, and `tests/test_pptx_empty_lines.py` checks the model
against every renderer recorded there.

Two renderers, 24 October 2026, on macOS 27.0.1: **PowerPoint for Mac
16.114.1**, saving a copy of the fixture as PDF through AppleScript, nothing
edited (real Calibri from its bundle); and **LibreOffice 25.8.4.2**, headless
PDF export (Calibri drawn as its metric-compatible Carlito). How far each probe
pushes `Xyz`, in points:

| Probe | PowerPoint | LibreOffice | Model |
| --- | ---: | ---: | ---: |
| empty paragraph, mark 18 / 36 / 10pt | 22.08 / 44.16 / 12.00 | 21.60 / 43.20 / 12.02 | 21.60 / 43.20 / 12.00 |
| empty paragraph, size inherited (18pt) | 22.08 | 21.60 | 21.60 |
| empty 18pt paragraph with 12pt before and 6pt after | 40.08 | 39.60 | 39.60 |
| two empty 36pt paragraphs | 87.12 | 86.40 | 86.40 |
| empty line between breaks of 36 / 10pt | 44.16 / 12.00 | 43.20 / 12.02 | 43.20 / 12.00 |
| empty line after a trailing break, mark 36 / 10pt | 44.16 / 12.00 | 43.20 / 12.02 | 43.20 / 12.00 |
| empty 36pt paragraph above one line | 42.96 | 43.20 | 43.20 |
| 36pt mark on a line of text | 0.00 | 0.00 | 0.00 |

Through 0.8.2 the model said 0 for each empty paragraph and 21.60 for each
empty line ended by a break or a trailing break. PowerPoint draws a line of text
that follows an empty line up to 0.96pt lower than the flat 1.2 line pitch
predicts, and a leading empty line 0.24pt shorter; the heights of whole blocks,
read from the bottom- and centre-anchored probes, match 1.2 × size within
0.16pt. The tests allow PowerPoint 1pt and LibreOffice 0.05pt.

In 100pt boxes, two 36pt empty paragraphs below two lines of text left the
text in place under `t`, moved it up by 43.2pt under `ctr` and by 86.4pt under
`b`, out of the top of the box, in both renderers. Above the text, they pushed
it out of the bottom under `t` and `ctr` and left it in place under `b`
(PowerPoint 0.72pt lower). A first paragraph's 36pt `spcBef` and a last
paragraph's 36pt `spcAft` moved nothing under any anchor. In both renderers
each of the 18 anchor slides is reported as `PPT001` exactly when its text was
drawn outside the box.

LibreOffice's own record of PowerPoint agrees: its commit `425b55efaf1f`
(tdf#164622) positions the text of every imported PPTX by its trailing empty
lines, which can move bottom-aligned text, while noting that PowerPoint's
shrink-to-fit leaves those lines out.

## On public decks

Over the 605 PPTX files of the [real-world corpora](real-world-corpora.md),
findings change in 8 decks. Four more findings keep their code, severity and
place with other numbers in the message (an empty line's height, or empty
lines now counted among the lines); every other finding is identical.

| Change | Findings | Cause |
| --- | ---: | --- |
| `PPT001` gone | 5 | Apache POI `aascu.org_…`: top-anchored titles of three lines, then breaks |
| `PPT001` gone | 8 | Apache POI `customGeo.pptx`: centred titles with one empty line above and one below |
| `PPT001` gone, `PPT002` gone | 1, 1 | LibreOffice `tdf103477`, `TextFittingComparisonWithMSO_3`: the last paragraph's `spcAft` |
| `PPT001` new, `PPT002` new | 3, 1 | Apache POI `60810.pptx`, slides 17, 19, 20 and 5: empty paragraphs between bullets in top-anchored body placeholders |
| `PPT002` → `PPT001` | 1 | `60810.pptx`, slide 6: a centred title with two trailing breaks |
| `PPT001` new | 4 | LibreOffice `TextFittingComparisonWithMSO_TopBottomMiddleAlignment` (2) and `tdf149961-autofitIndentation`, saved by PowerPoint at its limits (`fontScale` 25%, `lnSpcReduction` 20%) with empty paragraphs around or between the text; `trailing-paragraphs.pptx`, the tdf#164622 test, bottom-anchored with two empty paragraphs below |

## Limits

- One PowerPoint build, on one Mac, with one font. PowerPoint for Windows,
  PowerPoint on the web and other faces were not rendered. PowerPoint quit when
  the presentation was closed after the export; the PDF had been written.
- A paragraph mark's size is never taken into a line that has text, and an
  empty line made by wrapping leading spaces takes the paragraph mark's size.
- Grow-to-fit (`spAutoFit`) stays outside the model, as before.
- Only `anchor` is inherited from layout and master placeholders here; their
  insets, wrapping and autofit are not.
