# The overflow model against real renderers

The `.pptx` layout model was calibrated against LibreOffice
(`research/calibrate_pptx.py`) and, until this check, never against the renderer
the documents are actually made for. This is that check, and then two more
engines measured numerically alongside it. The raw per-shape numbers are in
[`docs/calibration/`](calibration/).

## Setup

| | |
|---|---|
| Renderer | PowerPoint for Mac, Microsoft 365, macOS on Apple Silicon |
| Deck | `corpus/deck_outlined.pptx`, built by `research/outline_deck.py` |
| Font | real Calibri, read from `/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts/Calibri.ttf` |
| Resolution | `resolve_face("Calibri") -> Calibri (exact)` |
| Predictions | `research/powerpoint_checklist.py`, generated before the deck was opened |

Two things make this a fair test rather than a demonstration.

**The checker and the renderer read the same font file.** Not a metric-compatible
clone - the actual `Calibri.ttf` inside the PowerPoint app bundle. So the result
says something about the layout model rather than about font substitution.

**The predictions were fixed in advance and are machine-generated.** Every number
in the checklist comes from the same code path the tool uses; nothing was typed
by hand. Two fixture labels in this corpus were wrong on the first pass precisely
because they had been guessed, which is why the checklist derives everything.

The outlined copy is asserted to be equivalent to the committed deck:
`outline_deck.py --check` re-runs the checks on it and compares finding-by-finding,
so the outline is decoration and not a layout change.

## Result

**21 of 21 non-excluded shapes agreed, and every predicted line count matched
exactly.**

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

Excluded in advance, for reasons named in `powerpoint_checklist.py` rather than
after seeing the result: `AUTOFIT_shrink_text`, `AUTOFIT_grow_shape` (the
renderer decides, not the file) and `FIT_unknown_font` (no machine has the face).

### The line counts are the strong part

A FIT/OVER verdict can be right for the wrong reason - a shape can overflow by so
much that any model catches it. Matching the *line count* on all 21 is a tighter
claim: it means the wrap decisions agree, string by string.

`FIT_mixed_run_sizes` is the case worth naming. Its widest line fills **99.2%** of
the usable width - one wrap decision from a different line count, and the place a
disagreement was most expected. PowerPoint broke it in the same place. The same
holds for `FIT_generous_box` (97.7%), `FIT_zero_insets` (97.6%) and
`OVER_paragraph_in_small_box` (97.0%).

So the flat `DRAWINGML_LINE_SPACING = 1.2` constant and the inset arithmetic hold
against PowerPoint, not only against LibreOffice.

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

All in the direction the README predicts - Carlito is wider, so it leans toward
reporting an overflow that is not there rather than missing one - and never large
enough to move a wrap, even at 99.2% fill.

## What the check turned up: PowerPoint does not recompute autofit on open

Not the thing being tested, and the more interesting result.

Both autofit shapes rendered **identically to `OVER_no_autofit_same_text`**: same
font size, same six lines, same overflow past the same outline.

- `AUTOFIT_shrink_text` (`normAutofit` with no stored `fontScale`) was not shrunk.
- `AUTOFIT_grow_shape` (`spAutoFit`) did not grow its box.

PowerPoint drew the stored state and recomputed nothing. Both were excluded from
the comparison on the grounds that the renderer decides - and it turns out that on
open the renderer decides to do nothing, which raises two questions the tool
currently answers differently:

1. `PPT005` (shrink-to-fit requested, no `fontScale` stored) is a **warning**, on
   the grounds that the outcome is renderer-dependent. Evidence now says the
   deck displays broken text in PowerPoint until someone edits the shape. That
   is an argument for **error**.
2. `spAutoFit` produces **no finding at all**, on the grounds that the box grows
   to the text. Evidence now says it does not grow on open, so a deck with
   `spAutoFit` and a stored height that is too small also displays broken.

Neither is changed yet, because one platform on open is not enough to move a
severity. What would settle it: the same deck in Slide Show mode (does an
audience see the overflow?), and PowerPoint for Windows.

## A third and fourth engine, measured numerically

`research/calibrate_pptx.py --build-probe` writes one deck with a single shape
per slide; exporting that to PDF and measuring it page by page gives per-shape
numbers with no attribution guesswork, from any renderer that can export a PDF.
The new path was cross-checked against the old shape-by-shape one on the same
renderer: identical numbers on all 24 shapes, so a difference between columns is
a difference between engines.

| | line count | line pitch vs the 1.2 constant |
|---|---|---|
| LibreOffice | 23/24 exact | median 0.05%, worst 0.06% |
| ONLYOFFICE Desktop Editors | 23/24 exact | median **0.000026%**, worst **0.00012%** |

ONLYOFFICE implements single line spacing as exactly 1.2 x the font size. The
agreement is floating-point noise in the PDF - the tightest confirmation of
`DRAWINGML_LINE_SPACING` there is, and it comes from an engine that had no part
in establishing it. LibreOffice's 0.05% is its own; whether that is rounding on
export or a marginally different pitch cannot be told from a PDF.

### The one shape that divides them

Both engines miss the same shape, and it is the same one PowerPoint got right:

| | `FIT_mixed_run_sizes` | method |
|---|---|---|
| this model | 2 lines | `layout_shape` |
| PowerPoint for Mac | 2 lines | rendered, read from the outlined deck (above) |
| LibreOffice | 3 lines | glyph positions from an exported PDF |
| ONLYOFFICE | 3 lines | same |

Its widest line fills 99.2% of the usable width. Two engines on each side of one
string, so the disagreement is not a precision limit of this model - it is a
property of the string. Nothing measurable decides it, which is the case for
having a borderline band rather than a threshold.

Stated plainly because the columns were not obtained the same way: the
PowerPoint number is read from a rendering of the outlined deck, the other two
are measured from exported PDFs by the same script. Getting PowerPoint through
the same script needs a working AppleScript export, which is not done - three
attempts produced `-2763` from its `save` verb. It would tighten the method, not
change the count: the shape renders on two lines in PowerPoint and that is
legible without measuring.

## Limits of this check

- One PowerPoint build, one platform, macOS on Apple Silicon. Windows is
  untested; so is Slide Show mode, as opposed to the editing view.
- Read from screenshots of the editing view. Line counts and inside/outside were
  unambiguous at that resolution; sub-point differences were not measured and are
  not claimed.
- `deck_outlined.pptx` is generated, not committed: rebuild it with
  `python research/outline_deck.py --check` to repeat this.
