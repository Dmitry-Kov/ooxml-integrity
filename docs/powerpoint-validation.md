# The overflow model against real renderers

The `.pptx` layout model was first calibrated against LibreOffice using
`research/calibrate_pptx.py`. This check compares its predictions with PowerPoint
for Mac, then adds numerical measurements from LibreOffice and ONLYOFFICE.
The raw per-shape numbers are in [`docs/calibration/`](calibration/).

## Setup

| | |
|---|---|
| Renderer | PowerPoint for Mac, Microsoft 365, macOS on Apple Silicon |
| Deck | `corpus/deck_outlined.pptx`, built by `research/outline_deck.py` |
| Font | real Calibri, read from `/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts/Calibri.ttf` |
| Resolution | `resolve_face("Calibri") -> Calibri (exact)` |
| Predictions | `research/powerpoint_checklist.py`, generated before the deck was opened |

The checker and PowerPoint read the same `Calibri.ttf` from the application
bundle. This removes font substitution as a source of disagreement in this
comparison.

The checklist was generated before opening the deck. Its numbers come from the
tool's usual code path. On the first pass, two fixture labels turned out to be
wrong because they had been guessed; the checklist now derives every prediction.

`outline_deck.py --check` re-runs the checks on the outlined copy and compares
each finding with the committed deck. This verifies that adding the visible
outlines leaves the layout findings unchanged.

## Result

All 21 non-excluded shapes agreed with the predictions, including every line
count.

| shape | predicted | PowerPoint | lines predicted / drawn |
|---|---|---|---|
| `FIT_one_short_line` | inside | inside | 1 / 1 |
| `OVER_paragraph_in_small_box` | crosses bottom | crosses bottom | 7 / 7 |
| `OVER_huge_type_tiny_box` | crosses bottom | crosses bottom | 3 / 3 |
| `FIT_wrapped_paragraph` | inside | inside | 3 / 3 |
| `FIT_generous_box` | inside | inside | 3 / 3 |
| `OVER_nowrap_single_line` | crosses right | crosses right | 1 / 1 |
| `OVER_fat_insets` | crosses bottom | crosses bottom | 4 / 4 |
| `FIT_two_lines_of_four` | inside | inside | 2 / 2 |
| `FIT_zero_insets` | inside | inside | 3 / 3 |
| `FIT_nowrap_short` | inside | inside | 1 / 1 |
| `OVERLAP_lower_left` | inside, overlaps | inside, overlaps | 1 / 1 |
| `OVERLAP_upper_right` | inside, overlaps | inside, overlaps | 1 / 1 |
| `FIT_clear_of_others` | inside, clear | inside, clear | 1 / 1 |
| `OFFCANVAS_right` | inside, off canvas | inside, off canvas | 1 / 1 |
| `OFFCANVAS_bottom` | inside, off canvas | inside, off canvas | 1 / 1 |
| `OVER_no_autofit_same_text` | crosses bottom | crosses bottom | 6 / 6 |
| `FIT_middle_anchored` | inside | inside | 1 / 1 |
| `FIT_mixed_run_sizes` | inside | inside | 2 / 2 |
| `OVER_hard_breaks` | crosses bottom | crosses bottom | 5 / 5 |
| `FIT_hard_breaks_room` | inside | inside | 5 / 5 |
| `FIT_bold_narrow` | inside | inside | 1 / 1 |

Three shapes were excluded before the comparison, with the reasons recorded in
`powerpoint_checklist.py`: `AUTOFIT_shrink_text` and `AUTOFIT_grow_shape`, whose
layout depends on renderer behaviour, and `FIT_unknown_font`, whose font was
unavailable on every test machine.

### The line counts are the strong part

A FIT/OVER verdict alone says little about wrapping when the text exceeds the
box by a large margin. Matching all 21 line counts gives more useful evidence:
the model and PowerPoint made the same wrap decisions for these strings.

The closest case was `FIT_mixed_run_sizes`. Its widest line fills 99.2% of the
usable width, so a small difference could have moved a word to the next line.
PowerPoint broke it in the predicted place. The same held for
`FIT_generous_box` (97.7%), `FIT_zero_insets` (97.6%) and
`OVER_paragraph_in_small_box` (97.0%).

For this deck, the result supports the fixed `DRAWINGML_LINE_SPACING = 1.2`
constant and the inset calculation previously checked against LibreOffice.

### Substitution error, measured a third time

The same checklist generated on Linux with Carlito instead of Calibri produced
identical verdicts, identical line counts and identical needed heights on all 24
shapes. The only differences were in width fill:

| shape | Carlito | real Calibri |
|---|---|---|
| `FIT_mixed_run_sizes` | 99.4% | 99.2% |
| `OVER_no_autofit_same_text` | 98.6% | 98.4% |
| `FIT_generous_box` | 98.0% | 97.7% |
| `FIT_zero_insets` | 97.8% | 97.6% |
| `OVER_paragraph_in_small_box` | 97.2% | 97.0% |

Carlito was slightly wider in each case, as described in the README. That
difference would favour an extra overflow report over a missed overflow. It
was too small to change any wrap, including the line at 99.2% fill with Calibri.

## What the check turned up: PowerPoint does not recompute autofit on open

The check also exposed an autofit behaviour that was outside the original
comparison. Both autofit shapes rendered like `OVER_no_autofit_same_text`, with
the same font size, six lines and overflow past the outline.

- `AUTOFIT_shrink_text` (`normAutofit` with no stored `fontScale`) was not shrunk.
- `AUTOFIT_grow_shape` (`spAutoFit`) did not grow its box.

On opening this deck, PowerPoint displayed the stored state without recomputing
autofit. The two shapes had been excluded because their layout was expected to
depend on the renderer. The observed behaviour raises questions about two
current rules:

1. `PPT005` (shrink-to-fit requested, no `fontScale` stored) is a warning because
   the outcome is renderer-dependent. In this check, the text overflowed in
   PowerPoint until the shape was edited. That gives a reason to consider an
   error severity.
2. `spAutoFit` produces no finding because the model assumes the box grows to
   the text. Here it did not grow on open, and the stored height was too small.

Both rules remain unchanged. Before changing severity, the same deck needs a
check in Slide Show mode and in PowerPoint for Windows. The current observation
covers only opening the deck in the Mac editing view.

## A third and fourth engine, measured numerically

`research/calibrate_pptx.py --build-probe` writes a deck with one shape per slide.
An export to PDF can then be measured page by page, with each measurement tied
to a known shape. This works with any renderer that exports PDF. On the same
renderer, the probe method and the previous shape-by-shape method gave identical
numbers for all 24 shapes. The comparisons below therefore use a common
measurement method.

| | line count | line pitch vs the 1.2 constant |
|---|---|---|
| LibreOffice | 23/24 exact | median 0.05%, worst 0.06% |
| ONLYOFFICE Desktop Editors | 23/24 exact | median **0.000026%**, worst **0.00012%** |

ONLYOFFICE's measured single line spacing agrees with 1.2 x the font size to
within floating-point noise in the PDF. This provides another check of
`DRAWINGML_LINE_SPACING` using an engine that was not involved in the original
calibration. LibreOffice differs by about 0.05%; the PDF alone cannot distinguish
export rounding from a slightly different line pitch.

### The one shape that divides them

Both engines differ from the model on `FIT_mixed_run_sizes`, where PowerPoint
agreed with it:

| | `FIT_mixed_run_sizes` | method |
|---|---|---|
| this model | 2 lines | `layout_shape` |
| PowerPoint for Mac | 2 lines | rendered, read from the outlined deck (above) |
| LibreOffice | 3 lines | glyph positions from an exported PDF |
| ONLYOFFICE | 3 lines | same |

The predicted widest line fills 99.2% of the usable width. At this margin,
renderers disagree on where the string wraps. The comparison supports keeping a
borderline band around the fit threshold: a single width estimate cannot settle
how every renderer will display this case.

The PowerPoint count was read from a rendering of the outlined deck; the other
two counts were measured from PDFs by the same script. PowerPoint has not yet
been measured through that script. Three AppleScript export attempts returned
`-2763` from the `save` verb. A working export would make the methods more
consistent, although the two lines in the PowerPoint editing view were clearly
visible.

## Limits of this check

- One PowerPoint build, one platform, macOS on Apple Silicon. Windows is
  untested; so is Slide Show mode, as opposed to the editing view.
- Read from screenshots of the editing view. Line counts and inside/outside were
  unambiguous at that resolution; sub-point differences were not measured and are
  not claimed.
- `deck_outlined.pptx` is generated, not committed: rebuild it with
  `python research/outline_deck.py --check` to repeat this.

The later 0.4.0 work adds 29 PowerPoint for Mac slide observations in four
separate reports: [long-token wrapping](pptx-long-tokens.md),
[font collections](font-collections.md), [slide order](pptx-slide-order.md) and
[master theme fonts](pptx-master-themes.md). Those checks extend the evidence
beyond this reference deck. They still use the Mac editing view and do not
resolve the Windows, Slide Show or autofit questions above.
