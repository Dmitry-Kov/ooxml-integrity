# ooxml-integrity

[![CI](https://github.com/Dmitry-Kov/ooxml-integrity/actions/workflows/ci.yml/badge.svg)](https://github.com/Dmitry-Kov/ooxml-integrity/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ooxml-integrity)](https://pypi.org/project/ooxml-integrity/)
[![Python](https://img.shields.io/pypi/pyversions/ooxml-integrity)](https://pypi.org/project/ooxml-integrity/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/LICENSE)

Preflight for machine-edited `.docx` and `.pptx`. Catches what Word,
LibreOffice and every schema validator accept without complaint: a reviewer's
comment silently detached from its text, tracked changes lost, footnotes
orphaned, and deck text that does not fit its box.

No model calls, no rendering, no network. It reads the zip and the font files,
so it runs on documents you cannot send anywhere.

```bash
pip install ooxml-integrity
ooxml-integrity check edited.docx --against original.docx
```

```
edited.docx: 2 error(s), 0 warning(s), 0 info
  [ERROR] CMT005  comment id=1 is orphaned - present in comments.xml but
                  anchored to nothing - the reviewer's note is invisible in Word
  [ERROR] FID001  comment anchors: 2 -> 1 (1 lost)
```

Same word count, same page count, opens in Word without a warning. The only
thing missing is the note that said *"Confirm this figure against the source
table before circulation"* — which vanished at the moment the figure changed.

## Why this exists

The failure is not exotic. Assigning `paragraph.text` in `python-docx` — the
first thing most agents reach for — drops every run in the paragraph and
creates one new run. Comment anchors, footnote references, character styles and
tracked-change markup live between those runs, so they go too. The result is
schema-valid, renders correctly and opens without complaint.

Two agents were given the same contract and the same three-figure edit. The
careful one produced a correct multi-author redline in 23 tool calls; the fast
one used `python-docx` in 5:

| | fast agent | careful agent |
|---|---|---|
| Reviewer comment in margin | **absent** | present, anchored to the figure |
| Table edits | **untracked** (0 `w:ins`, 0 `w:del`) | tracked (9 `w:ins`, 2 `w:del`) |
| Word warning on open | **none** | none |
| Word count | 118 | 118 |

On the six defect classes tested, well-formedness checks, schema validation and
render-to-PDF-and-look each caught **0 of 6**. This checker caught 6 of 6 with
zero false positives across eight real agent runs.

Full experiment, agent transcripts, renderer calibration and every limitation:
**[docs/research.md](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/research.md)**.

## Two questions

A document stripped of every style, footnote and revision is perfectly
self-consistent. So the tool asks two things, and you usually want both:

**Did this file survive editing?** Internal references resolve — comments,
footnotes, styles, numbering, relationships, tracked changes.

```bash
ooxml-integrity check report.docx
```

**What did the edit lose?** Compared against the source, by construct count and
by text — catches the file that is stripped of everything but otherwise clean.

```bash
ooxml-integrity check edited.docx --against original.docx
```

Exit codes are the CI contract: `0` clean, `1` findings at or above `--fail-on`
(default `error`), `2` usage error. `--json` for machine-readable output,
`--quiet` to print only what fails.

## Decks: does the text fit the box?

```bash
ooxml-integrity check deck.pptx
```

```
deck.pptx: 6 error(s), 4 warning(s), 1 info
  [ERROR] PPT001  text needs 144pt in a 40pt box - 104pt too tall (260% over), 3 line(s)
            -> slide1/OVER_huge_type_tiny_box
  [ERROR] PPT003  word wrap is off and the longest line is 304pt in a 182pt box
                  - 122pt runs outside the shape
            -> slide2/OVER_nowrap_single_line
  [WARN ] PPT004  shape extends 142pt past the right edge - content will be cut off
            -> slide3/OFFCANVAS_right
  [WARN ] PPT006  overlaps 'OVERLAP_upper_right' over 23% of the smaller shape
            -> slide3/OVERLAP_lower_left
```

This is the part [python-pptx has declined for a decade](https://github.com/scanny/python-pptx/issues/973):
it needs text measurement, and text measurement needs the *effective* font size,
resolved through run, paragraph, list style, layout and master placeholders,
presentation defaults and theme. Widths come from the font's own `hmtx`/`cmap`
tables via `fontTools`; nothing is rasterised.

Validated against real PowerPoint: 21 of 21 shapes got the predicted verdict
with the line count exact on every one. Where renderers disagree with each
other (they do, at the margin), the finding is `PPT002 borderline`, not
overflow. When a font is missing, the tool says so (`PPT007`) instead of
guessing quietly. [How it was validated](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/powerpoint-validation.md).

## In CI

```yaml
- uses: Dmitry-Kov/ooxml-integrity@v0.4.0
  with:
    files: "out/**/*.docx"
    against: templates/master.docx   # optional, enables the fidelity check
    fail-on: error
```

Put it on the step *after* anything that edits documents programmatically — a
generation script, an agent, a template merge. That is where these defects
come from, and the only place they are still cheap to find.

The action writes a summary to the job page, can emit a JSON report and can
produce SARIF so findings land in the pull request as code-scanning
annotations. Severity overrides, path-scoped ignores with a required `reason`,
and counted baselines for adopting the checker in a repository that already has
findings: **[docs/configuration.md](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/configuration.md)**.

## From Python

```python
from ooxml_integrity import check, compare

for f in check("edited.docx"):
    print(f.code, f.severity.value, f.message, f.where)

for f in compare("original.docx", "edited.docx"):
    print(f.code, f.message)
```

Python 3.9+. Two dependencies: `lxml`, `fonttools` (plus `tomli` on 3.10 and
older, only to read the config file). If the console script is not on your
PATH, `python -m ooxml_integrity check report.docx` works anywhere.

## What it reports, and how much it covered

Every finding has a stable code, a severity, and a part, shape or XPath where
one can be identified. The rule: **losing something that makes content or an
audit trail invisible is an error**, because nothing downstream will report it.
Losing something that only changes how the document looks is a warning.

`.docx`:

| code | check |
|---|---|
| `PKG001-008` | OPC package integrity, content types, archive budgets, unsafe part names |
| `XML001` | well-formedness of every XML part |
| `REL001-003` | every `r:id` / `r:embed` resolves; targets exist; unreferenced relationships |
| `STY001-002` | paragraph, run and table styles resolve; `basedOn` / `next` / `link` resolve |
| `NUM001-004` | `numId` → `w:num` → `abstractNumId` → `w:abstractNum`; `ilvl` defined |
| `FTN001-002` | footnote references resolve; orphaned footnotes |
| `CMT001-005` | `commentRangeStart` ↔ `commentRangeEnd` ↔ `commentReference` ↔ `comments.xml` |
| `REV001-003` | revision-id uniqueness; `w:del` carries `w:delText`, respecting legal `w:ins > w:del` nesting |
| `TBL001-002` | `tblGrid` present; cells per row vs grid columns, accounting for `gridSpan` |
| `SDT001-002` | content-control integrity |
| `TXT001` | edge whitespace in runs without `xml:space="preserve"` |
| `FID001-003` | losses and additions relative to the source, by construct count; drop in text volume |
| `FID004-006` | a comment, footnote or endnote whose **text** survives but under no id at all |
| `FID007-008` | header/footer story missing or changed; tracked constructs lost from headers/footers |

`.pptx`:

| code | check |
|---|---|
| `PPT000` | text could not be measured at all — an error, never "clean" |
| `PPT001` | text taller than its box, beyond the measurement tolerance |
| `PPT002` | within tolerance of overflowing — borderline, renderers may disagree |
| `PPT003` | line runs outside the usable width: wrap off, or a single overwide glyph |
| `PPT004` | shape extends past the slide edge, or sits entirely outside it |
| `PPT005` | shrink-to-fit requested but no `fontScale` stored — result depends on the renderer |
| `PPT006` | two text-bearing shapes overlap |
| `PPT007` | declared font unavailable; measurements for those shapes are estimates |

A clean result is only as good as what was actually checked. `--coverage`
distinguishes `checked`, `not-present`, `estimated`, `skipped` and
`unsupported` surfaces per file, and a result with a gap says
`no findings in checked surfaces`, not `clean`. `ooxml-integrity doctor`
reports what the machine can and cannot measure before you run a deck through
it. Exact boundaries: [support matrix](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/support-matrix.md),
[coverage and doctor](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/coverage.md).

## Limitations

- Evidence is synthetic: 50 sources and 220 labelled pairs across five
  producers (Word for Windows, Word for Mac, Word Online, LibreOffice,
  `python-docx`). 100% error-level precision applies to the 14 measured rules
  on that corpus, not to your documents.
- Eight real agent runs is a small sample, on one document, on one day.
- PPTX layout is validated against PowerPoint for Mac in the editing view.
  Windows and Slide Show mode are untested. No GPOS kerning or shaping, so
  complex scripts and heavily-ligatured faces are estimates.
- Groups, rotations, tables, SmartArt and charts in decks are reported as
  unsupported, not silently approximated.
- Only the Carlito/Calibri metric-compatible pairing has been measured.

The full list, with the numbers behind each, is in
[docs/research.md](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/research.md#limitations).

## Where this is going

The agent runs reframed the problem. The variance between pipelines is total
and invisible: same task, same document, one produces a correct redline and the
other detaches the reviewer's warning. So the useful question is less "is this
file broken" than "which of my document pipelines is safe" — which argues for a
public benchmark across docx editing tools and agent harnesses, on a real
corpus.

That needs a corpus. If you have workflows where an agent edits Office files
that someone else then reviews, I would like to hear what breaks for you —
open an issue.

## Repository layout

```
src/ooxml_integrity/   inspector, fidelity, fonts, pptx layout and checks,
                       coverage, doctor, policy, sarif, cli
tests/                 labelled-corpus, story-fidelity and false-positive regressions
research/              corpus builders, mutators, calibration, renderer comparison
docs/                  research notes, configuration, support matrix, validation records
corpus/                reference .docx and .pptx, byte-reproducible
evidence/docx-beta/    50 producer sources and 220 labelled DOCX pairs
runs/                  eight real agent outputs, used as fixtures
action.yml             the GitHub Action
AUDIT_PLAN.md          readiness priorities and release gates
```

## License

MIT.
