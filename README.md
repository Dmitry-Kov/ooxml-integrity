# ooxml-integrity

[![CI](https://github.com/Dmitry-Kov/ooxml-integrity/actions/workflows/ci.yml/badge.svg)](https://github.com/Dmitry-Kov/ooxml-integrity/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ooxml-integrity)](https://pypi.org/project/ooxml-integrity/)
[![Python](https://img.shields.io/pypi/pyversions/ooxml-integrity)](https://pypi.org/project/ooxml-integrity/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/LICENSE)

`ooxml-integrity` checks `.docx` and `.pptx` files after automated editing.
It finds broken comment anchors, lost tracked changes, orphaned footnotes,
and presentation text that is likely to overflow its box.

The checker reads the document package and local font files. It runs locally,
without rendering, model calls or network access, so documents can stay on
your machine.

The [browser demo](https://dmitry-kov.github.io/ooxml-integrity/) runs without
installation. Files stay in your tab; Python downloads once at startup.
The browser footer reports its installed package version. The published package
tested here is `0.4.0`; this repository also contains
[unreleased fixes](CHANGELOG.md#unreleased), so checkout behaviour can differ.

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

In this example, the edited file opens in Word without a warning and keeps the
same word and page counts. The reviewer's note, *"Confirm this figure against
the source table before circulation"*, is still inside the package, but its
anchor is gone and Word no longer shows it beside the figure.

## Why this exists

I started with a small experiment: ask agents to edit a contract that already
contains reviewer comments and tracked changes. In two runs, the task was to
update three figures in the same table. The run labelled `careful` preserved
the comment and recorded the edits under a separate author. The `fast` run
used `python-docx` and lost the comment anchor:

| | fast agent | careful agent |
|---|---|---|
| Reviewer comment in margin | **absent** | present, anchored to the figure |
| Table edits | **untracked** (0 `w:ins`, 0 `w:del`) | tracked (9 `w:ins`, 2 `w:del`) |
| Word warning on open | **none** | none |
| Word count | 118 | 118 |

The cause is a paragraph replacement. Assigning `paragraph.text` in
`python-docx` replaces the paragraph's contents with a new run. That also
removes comment anchors, footnote references, run formatting and tracked-change
markup stored there. The file can still open normally after those losses.

In a separate test with six deliberately introduced defect cases, the checker
found all six. XML parsing, a namespace/root-element check and successful
LibreOffice PDF conversion did not distinguish those cases from the controls.
The experiment did not run a full XSD validator or a systematic visual review.
Across the eight real agent runs, the checker reported no false positives.

The [research notes](docs/research.md)
describe the experiments, saved outputs, renderer measurements and limitations.

## Applied to other projects

The method was run against four third-party tools that edit or validate DOCX.
Each finding was filed with a self-contained reproduction; two are fixed upstream, and a third has a proposed fix in an open pull request.

| Project | Finding | Status |
|---|---|---|
| [adeu](https://github.com/dealfluence/adeu/issues/137) | comment reference run carried `rStyle="CommentReference"` with no such style defined | fixed in 3.0.3; the reference document from this corpus was adopted as an upstream fixture |
| [python-docx](https://github.com/python-openxml/python-docx/issues/1604) | `paragraph.text` setter detaches comment anchors created through 1.2's comment API and existing footnote references | open; [PR #1605](https://github.com/python-openxml/python-docx/pull/1605) restores the comment anchors, footnotes and revisions remain |
| [python-docx](https://github.com/python-openxml/python-docx/issues/1609) | `add_comment()` references the `CommentReference` style without defining it | open |
| [anthropics/skills](https://github.com/anthropics/skills/issues/1733) | the docx skill's `validate.py` passes a file whose comment is present in `comments.xml` but anchored to nothing — it checks marker → comment, not the reverse | open; [PR #1734](https://github.com/anthropics/skills/pull/1734) awaits maintainer review |
| [docx-mcp](https://github.com/sontanon/docx-mcp/issues/4) | offer of labelled pairs; question about the policy of rejecting inputs that already carry revisions | open |

Fixture contributions merged upstream: [adeu #138](https://github.com/dealfluence/adeu/pull/138)
(comment projection across LibreOffice, Word for Mac and Word for Windows) and
[adeu #140](https://github.com/dealfluence/adeu/pull/140) (revision projection and
accept/reject). Preparing them surfaced a Python/TypeScript namespace-serialization
mismatch in adeu's own consistency suite
([#139](https://github.com/dealfluence/adeu/issues/139), fixed in 3.0.4).

## Two questions

A document can lose all its styles, footnotes and revisions and still be
internally consistent. The checker therefore supports two kinds of inspection.

**Are the internal references intact?** Check comments, footnotes, styles,
numbering, relationships and tracked changes within one file.

```bash
ooxml-integrity check report.docx
```

**What did the edit lose?** Compare construct counts and text with the source.
This can find losses even when the edited file has no broken references.

```bash
ooxml-integrity check edited.docx --against original.docx
```

Exit codes are `0` for no findings at or above `--fail-on` (default `error`),
`1` when such findings exist, and `2` for a usage error. Use `--json` for
machine-readable output and `--quiet` to print only findings that fail the run.

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

Text fitting requires the effective font and size, which may be inherited
through runs, paragraphs, list styles, layout and master placeholders,
presentation defaults and themes. The checker resolves these values and reads
widths from the font's `hmtx`/`cmap` tables through `fontTools`. The related
[python-pptx discussion](https://github.com/scanny/python-pptx/issues/973)
describes the need for text measurement when fitting text.

In the reference-deck check against PowerPoint for Mac, all 21 checkable shapes
matched the predicted verdict and line count. Other renderers disagreed on a
shape close to its width limit. The checker reports predicted vertical
overflow of up to 5% as `PPT002 borderline`, and missing fonts as `PPT007`.
The [validation record](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/powerpoint-validation.md)
gives the method and the limits of that comparison.

Later checks in `0.4.0` cover long basic-Latin words, TTC/OTC font members,
presentation slide order and each slide master's Latin theme fonts. Their
four dedicated decks add 29 recorded PowerPoint slide observations. The
[long-token](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/pptx-long-tokens.md),
[font-collection](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/font-collections.md),
[slide-order](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/pptx-slide-order.md)
and [theme](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/pptx-master-themes.md)
notes record the cases and their remaining limits.

## In CI

```yaml
- uses: Dmitry-Kov/ooxml-integrity@v0.4.0
  with:
    files: "out/**/*.docx"
    against: templates/master.docx   # optional, enables the fidelity check
    fail-on: error
```

Run the check after a generation script, agent edit or template merge, while
the source and edited files are still available for comparison.

The action writes a summary to the job page and can produce JSON and SARIF
reports. SARIF findings can appear as code-scanning annotations in a pull
request. The [configuration guide](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/configuration.md)
covers severity overrides, path-scoped ignores with a required `reason`, and
counted baselines for repositories that already have findings.

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

Every finding has a stable code and severity, plus a part, shape or XPath
where one can be identified. Losses that hide content or its audit trail are
errors. Losses that affect only appearance are warnings.
Undefined paragraph and table styles remain errors because they can carry
numbering and structure; undefined character styles are warnings.
These tables describe the current checkout. Published `0.4.0` still treats
undefined character styles as errors; that severity fix is unreleased.

`.docx`:

| code | check |
|---|---|
| `PKG001-008` | OPC package integrity, content types, archive budgets, unsafe part names |
| `XML001` | well-formedness of every XML part |
| `REL001-003` | `r:id` / `r:embed` / `r:link` references resolve; targets exist; unreferenced relationships |
| `STY001` | undefined paragraph/table styles: error; undefined character styles: warning |
| `STY002` | undefined `basedOn` / `next` / `link` style references: warning |
| `NUM001-004` | `numId` → `w:num` → `abstractNumId` → `w:abstractNum`; `ilvl` defined |
| `FTN001-002` | footnote references resolve; orphaned footnotes |
| `CMT001-005` | `commentRangeStart` ↔ `commentRangeEnd` ↔ `commentReference` ↔ `comments.xml` |
| `REV001-003` | revision-id uniqueness; `w:del` carries `w:delText`, respecting legal `w:ins > w:del` nesting |
| `TBL001-002` | `tblGrid` present; cells per row vs grid columns, accounting for `gridSpan` |
| `SDT001-002` | content-control integrity |
| `TXT001` | edge whitespace in runs without `xml:space="preserve"` |
| `FID000` | requested source comparison could not run |
| `FID001-003` | losses and additions relative to the source, by construct count; drop in text volume |
| `FID004-006` | comment, footnote or endnote text missing from the edited file, allowing for changed ids |
| `FID007-008` | header/footer story missing or changed; tracked constructs lost from headers/footers |

`.pptx`:

| code | check |
|---|---|
| `PPT000` | text could not be measured; reported as an error |
| `PPT001` | text taller than its box, beyond the measurement tolerance |
| `PPT002` | predicted text height exceeds the box by up to 5% — borderline overflow |
| `PPT003` | line runs outside the usable width: wrap off, or a single overwide glyph |
| `PPT004` | shape extends past the slide edge, or sits entirely outside it |
| `PPT005` | shrink-to-fit requested but no `fontScale` stored — result depends on the renderer |
| `PPT006` | two text-bearing shapes overlap |
| `PPT007` | declared font unavailable; measurements for those shapes are estimates |

Use `--coverage` to see the scope of a result. It distinguishes
`checked`, `not-present`, `estimated`, `skipped` and
`unsupported` surfaces per file, and a result with a gap says
`no findings in checked surfaces`, not `clean`. `ooxml-integrity doctor`
reports which measurements are available on the current machine.
See the [support matrix](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/support-matrix.md) and
[coverage and doctor](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.4.0/docs/coverage.md).

## Limitations

- The DOCX evidence corpus uses 50 synthetic sources and 220 labelled pairs
  across five producers (Word for Windows, Word for Mac, Word Online, LibreOffice,
  `python-docx`): 120 clean controls and 100 seeded-defect pairs. The
  [recorded result](evidence/docx-beta/RESULTS.md) has 111 error-level true
  positives, zero false positives and zero false negatives. The 100% precision
  and recall apply to that corpus; 14 rules are measured and 30 are unmeasured.
  Accuracy on customer documents has not been measured.
- Eight real agent runs is a small sample, on one document, on one day.
- PPTX evidence comes from PowerPoint for Mac editing-view checks and native
  exports of the later regression decks. Windows and Slide Show mode are
  untested. GPOS kerning and shaping are not applied, so complex scripts and
  heavily-ligatured faces are estimates.
- Grouped shapes, tables, SmartArt and charts in decks are not modelled.
  Rotated-shape geometry is only partially checked.
- Only the Carlito/Calibri metric-compatible pairing has been measured.

The full list, with the numbers behind each, is in
[docs/research.md](docs/research.md#limitations).

## Where this is going

The eight agent runs showed that different editing approaches can preserve or
lose review information on the same document. I would like to compare more
DOCX editing tools and agent setups on a shared corpus, with enough real
documents to make the results useful outside this experiment.

If your workflow includes automated Office edits followed by human review,
open an issue with a description of what breaks. Reproducible examples would
help decide which checks and document types to work on next.

## Repository layout

```
src/ooxml_integrity/   inspector, fidelity, fonts, pptx layout and checks,
                       coverage, doctor, policy, sarif, cli
tests/                 labelled-corpus, story-fidelity and false-positive regressions
research/              corpus builders, mutators, calibration, renderer comparison
docs/                  research notes, configuration, support matrix, validation records
demo/                  browser checker, landing page, bundled fonts and examples
corpus/                reference .docx and .pptx, byte-reproducible
evidence/docx-beta/    50 producer sources and 220 labelled DOCX pairs
runs/                  eight real agent outputs, used as fixtures
action.yml             the GitHub Action
```

## License

MIT.
