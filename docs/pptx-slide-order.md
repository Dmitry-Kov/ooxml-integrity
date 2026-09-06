# Presentation slide order

P1 item 3 is closed for the **main Transitional PresentationML slide list**.
Layout findings now use one-based positions in `p:sldIdLst`, including hidden
slides. ZIP order, relationship order, numeric slide IDs and filenames do not
determine a slide's position.

The reader follows each entry's `r:id` through
`ppt/_rels/presentation.xml.rels` to its internal slide part. This is the same
lookup sequence used in Microsoft's [Open XML SDK slide-index example](https://learn.microsoft.com/en-us/office/open-xml/presentation/how-to-get-all-the-text-in-a-slide-in-a-presentation).
The [slide-list definition](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.slideidlist?view=openxml-3.0.1)
also separates slide identifiers from their relationship identifiers. Sorting
either identifier is not a substitute for following the list.

## Failure and Office evidence

Previously the reader scanned only `ppt/slides/slideN.xml`, sorted by N and
renumbered the result. A reordered presentation could therefore get the wrong
finding locations, and a valid nonnumeric slide filename was skipped entirely.

- Renderer: **Microsoft PowerPoint for Mac 16.112.3**, macOS Apple Silicon,
  observed locally on 2026-09-06.
- Input: [`corpus/pptx-slide-order.pptx`](../corpus/pptx-slide-order.pptx),
  SHA-256 `ec13236a43f1b0f3b8cb7c29dbf759e48be3d711015585ce63365564ab72a04c`.
- Opened without repair, editing or resaving. The navigation pane showed
  “First: clean”, “Second: clean”, “Third: overflow”, in that order.
- Native **File → Export → PNG → Save Every Slide**, 960 × 540. All three
  exported slides were inspected individually at full size. These are actual
  PowerPoint exports, not the fixture author's or checker's renders.
- [Provenance and pinned fixture/image hashes](calibration/slide-order/evidence.json).
  Fixture and images are synthetic project MIT material; no font binaries or
  third-party document content are redistributed.

The input was authored with `@oai/artifact-tool`, then the main slide list was
reordered and slide filenames/references renamed. Structural, geometry,
font-policy and import checks passed on the exact final bytes. The native blue
outline is the tested text box. All boxes contain 20 W characters in Calibri
24pt, with wrap/autofit off, zero insets and 60pt height. Two boxes are 600pt
wide; the defect is 120pt wide. Labels sit separately above them.

| Main position / render | Internal part | Office result | New finding |
|---|---|---|---|
| [1](calibration/slide-order/Slide1.png) | `ppt/slides/intro.xml` | First: clean | none |
| [2](calibration/slide-order/Slide2.png) | `ppt/slides/slide1.xml` | Second: clean | none |
| [3](calibration/slide-order/Slide3.png) | `ppt/slides/slide10.xml` | Third: overflow | `PPT003` ERROR at `slide3/OVER_third` |

The ZIP stores these slide parts in the order second, third, first. Running
the preceding checker, commit `97c302e`, against this exact input reads only
two slides and reports `slide2/OVER_third`. The new result reads all three and
locates the same real overflow on the third slide. The two clean controls
remain free of findings. The checker's measured line advance is 427.03pt on
the evidence host; this is not a pixel-derived Office measurement.

## Reader, confidence and reporting contract

- Only slides in the main list participate in layout. Unlisted relationships
  or orphan slide parts cannot create phantom layout findings. Their package
  validity is a separate, unimplemented complete-OPC-graph check.
- Hidden slides keep their editor-list positions and are checked. Custom-show
  sequences, playback skipping and `firstSlideNum`/footer fields do not redefine
  the one-based `slideN` location in this API.
- An absent or empty optional slide list means zero main slides, never a
  filename-based fallback. Coverage reports `pptx.slide-order: not-present`.
- A nonempty list is fully resolved before any layout checks run. Missing,
  ambiguous, external or wrong-type slide relationships, repeated IDs/parts,
  invalid internal targets, or unreadable/unsupported listed roots produce
  `PKG002` ERROR. No partial deck is silently renumbered. Coverage reports the
  read as skipped, not as successfully checked.
- Valid order is deterministic and reports `pptx.slide-order: checked`.
  Font substitution and layout confidence still govern the separate overflow
  coverage and existing `PPT001`–`PPT007` severities. No thresholds change and
  no new finding code is introduced.
- Human output, JSON, SARIF and baseline fingerprints share the corrected
  location. Baselines made with wrong old locations may stop matching: review
  the corrected findings and regenerate with `--write-baseline` when appropriate.
  The baseline format itself remains version 2.

Tests cover every permutation of the three slides, inherited geometry/styles,
ZIP/relationship/ID order independence, relative and package-absolute targets,
URI-encoded and nonnumeric names, comments, hidden slides, empty lists,
unlisted-defect false positives and fail-closed errors at every slide position.
These variants are synthetic regressions, not additional Office observations.

## Limits and remediation

This is one Office-for-Mac observation set, not Windows/web rendering or
independent review. The reader still expects `ppt/presentation.xml` with the
Transitional namespace. A differently located presentation root, Strict
PresentationML, full content-type/relationship validation and custom-show
playback remain outside this change.

For `PKG002`, repair the listed relationship/part in the producer or inspect
the file in PowerPoint before creating a new verified copy. Do not bypass a
broken manifest by sorting ZIP filenames. For the control fixture's `PPT003`,
widen the third text box or reduce its text/font size; the checker does not
edit it. The original reference DOCX/PPTX corpus is unchanged.
