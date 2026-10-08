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
The demo pins published `0.5.0` and reports its installed version in the footer.
[Real browser checks](tests/browser/README.md) gate changes before Pages deployment.
Version `0.5.0` is [available on PyPI](https://pypi.org/project/ooxml-integrity/0.5.0/).
The [upgrade notes](docs/releases/0.5.0.md) describe changed findings and compatibility.

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

## Tools and agents on a reviewed document

Eight runs could only suggest a pattern. The
[review-history benchmark](https://dmitry-kov.github.io/ooxml-integrity/benchmark/)
gave 30 ordinary requests (replace a phrase, reply to a comment, accept one
revision, fix a footnote) on two contracts with a live review history to six
document tools, python-docx on two code paths, and three coding agents in
sealed containers. An oracle that never imports the checker compared each
output with its source, and one output per kind of damage was opened in Word
for Mac.

- Claude Code (Opus 5.5) and Codex (gpt-6.1-sol) completed and preserved all
  150 attempts each, five captures apiece. In every capture Codex's reply to
  the first contract's comment had no anchor in the document, and Word for Mac
  does not show such a reply.
  OpenCode with a local Qwen3.8 27B once removed another reviewer's insertion
  wrapper, so that reviewer's pending sentence read as accepted text.
- Assigning `Paragraph.text` or `_Cell.text` in python-docx damaged 14 of 28
  outputs. docx-cli damaged 38 of 56: bullets turned into the literal text
  `&#8226;`, and new words were credited to another reviewer. Two tools edited
  the document title instead of the requested header.
- Of 69 damaged outputs, the frozen checker (0.4.6) reported 41, and it flagged
  145 of 537 correct outputs, mostly for the requested change itself. 0.4.9,
  with each task's requested change [declared as expected](docs/configuration.md#changes-the-edit-was-asked-to-make),
  reports 65 and flags 12, each a true report outside the benchmark's scope,
  such as a reply Word does not show.

Counts are attempts on two documents, not independent documents. The
[evidence](evidence/review-history-benchmark/README.md) has the frozen
protocol, its amendments and every capture.

## Applied to other projects

Findings from the corpus and the benchmark were filed upstream, each with a
self-contained reproduction. adeu fixed two; the others are open.

| Project | Finding | Status |
|---|---|---|
| [adeu](https://github.com/dealfluence/adeu/issues/137) | comment reference run carried `rStyle="CommentReference"` with no such style defined | fixed in 3.0.3; the reference document from this corpus was adopted as an upstream fixture |
| [python-docx](https://github.com/python-openxml/python-docx/issues/1604) | `paragraph.text` setter detaches comment anchors created through 1.2's comment API and existing footnote references | open; [PR #1605](https://github.com/python-openxml/python-docx/pull/1605) restores the comment anchors, footnotes and revisions remain |
| [python-docx](https://github.com/python-openxml/python-docx/issues/1609) | `add_comment()` references the `CommentReference` style without defining it | open |
| [anthropics/skills](https://github.com/anthropics/skills/issues/1733) | the docx skill's `validate.py` passes a file whose comment is present in `comments.xml` but anchored to nothing — it checks marker → comment, not the reverse | open; [PR #1734](https://github.com/anthropics/skills/pull/1734) awaits maintainer review |
| [sontanon/docx-mcp](https://github.com/sontanon/docx-mcp/issues/4) | offer of labelled pairs; question about the policy of rejecting inputs that already carry revisions | open |
| [docx-cli](https://github.com/kklimuk/docx-cli/issues/12) | any write turns numeric character references such as `&#8226;` into literal text; Word shows `&#8226;` instead of a bullet | open |
| [docx-cli](https://github.com/kklimuk/docx-cli/issues/13) | `replace --track` inside another author's pending insertion credits the new text to that author, and misses the target next to a nested deletion | open |
| [docxengine](https://github.com/ruwadgroup/docxengine/issues/1) | a new comment writes `w14:paraId` into a comments part that does not declare `w14`; Word reports unreadable content | open |
| [docxengine](https://github.com/ruwadgroup/docxengine/issues/2), [SecurityRonin/docx-mcp](https://github.com/SecurityRonin/docx-mcp/issues/21) | a reply has no anchor in the document, and Word does not display it | open |

Fixture contributions merged upstream: [adeu #138](https://github.com/dealfluence/adeu/pull/138)
(comment projection across LibreOffice, Word for Mac and Word for Windows) and
[adeu #140](https://github.com/dealfluence/adeu/pull/140) (revision projection and
accept/reject). Preparing them surfaced a Python/TypeScript namespace-serialization
mismatch in adeu's own consistency suite
([#139](https://github.com/dealfluence/adeu/issues/139), fixed in 3.0.4).

In use upstream: since [adeu #156](https://github.com/dealfluence/adeu/pull/156)
(merged 2026-09-29), adeu's test suite installs `ooxml-integrity`, pinned to
0.4.8 since [adeu #161](https://github.com/dealfluence/adeu/pull/161) (merged
2026-10-05). For each shared cross-platform scenario it applies the edits, runs
`check()` on the output and `compare()` against the input, and fails on
error-level findings. The two accept/reject scenarios declare the revision-count
changes they request as expectations with `expect()`.

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
- uses: Dmitry-Kov/ooxml-integrity@v0.5.0
  with:
    files: "out/**/*.docx"
    against: templates/master.docx   # optional, enables the fidelity check
    fail-on: error
```

Run the check after a generation script, agent edit or template merge, while
the source and edited files are still available for comparison.

The action writes a summary to the job page and can produce JSON and SARIF
reports. SARIF findings can appear as code-scanning annotations in a pull
request. The [configuration guide](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.5.0/docs/configuration.md)
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
These tables describe [0.5.0](docs/releases/0.5.0.md). Version `0.4.0` treated undefined character styles
as errors; use `--fail-on warn` to keep them failing after upgrading.

`.docx`:

| code | check |
|---|---|
| `PKG001-008` | OPC package integrity, content types, archive budgets, unsafe part names |
| `PKG009` | 0.4.4: Strict Open XML is not supported, so the Word checks were not run; reported as an error |
| `XML001` | well-formedness of every XML part |
| `REL001-003` | `r:id` / `r:embed` / `r:link` references resolve; targets exist; unreferenced relationships |
| `STY001` | undefined paragraph/table styles: error; undefined character styles: warning |
| `STY002` | undefined `basedOn` / `next` / `link` style references: warning; 0.4.5: `next` / `link` are info |
| `NUM001-004` | `numId` → `w:num` → `abstractNumId` → `w:abstractNum`; `ilvl` defined |
| `FTN001-002` | footnote references resolve; orphaned footnotes |
| `CMT001-006` | Comment ranges/references ↔ the related comments part; unresolved or unreadable comments parts |
| `REV001-003` | revision-ID collisions outside the verified paragraph-mark/content pair; `w:del` carries `w:delText`, respecting legal `w:ins > w:del` nesting |
| `TBL001-002` | `tblGrid` present; cells per row vs grid columns, accounting for `gridSpan` |
| `SDT001-002` | content-control integrity |
| `TXT001` | XML edge whitespace in runs without effective `xml:space="preserve"` |
| `TXT002` | WARN: literal numeric punctuation/symbol spellings after XML decoding, suggesting double escaping; [scope and intent ambiguity](docs/review-edit-warnings.md) |
| `FID000` | requested source comparison could not run |
| `FID001-003` | losses and additions relative to the source, by construct count; drop in text volume |
| `FID004-006` | comment, footnote or endnote text missing from the edited file, allowing for changed ids; 0.4.6: a tracked edit is not a loss |
| `FID007-008` | header/footer story missing or changed untracked (0.4.6); tracked constructs lost from headers/footers |
| `FID009` | 0.4.2: missing literal insertion/deletion text with equal wrapper counts in the supported main-document profile; [limits](evidence/docx-revision-text/README.md) |
| `FID010` | 0.4.2: fewer notes retain insertion/deletion markup in equally populated footnote/endnote text groups; [limits](evidence/docx-note-revisions/README.md) |
| `FID011` | WARN: preserved source insertion text plus additional characters under its old author/date context without a distinct new insertion context; [scope and intent ambiguity](docs/review-edit-warnings.md) |
| `FID012` | 0.4.9, INFO: the tracked changes an edit added, per story (body, header/footer slot, notes), kind and author, so an [expectation](docs/configuration.md#changes-the-edit-was-asked-to-make) can require a tracked edit in the right place |
| `FID013` | 0.5.1, WARN: a tracked replacement the edit added deletes and inserts again more unchanged words than it changes (at least four), so a reviewer sees unchanged text struck through and added again; [scope](docs/review-edit-warnings.md#fid013-a-tracked-replacement-wider-than-the-change) |
| `INT001` | a check raised and did not complete: error; other checks still run, and coverage reports that check's surface as `skipped` |
| `EXP001` | 0.4.8: a declared expectation (`--expect` or `[[expect]]`) matched no finding, so the requested change did not happen; [expected changes](docs/configuration.md#changes-the-edit-was-asked-to-make) |

`.pptx`:

| code | check |
|---|---|
| `PPT000` | text could not be measured; reported as an error |
| `PKG009` | 0.4.4: Strict Open XML is not supported, so the layout checks were not run; reported as an error |
| `PPT001` | text taller than its box, beyond the measurement tolerance |
| `PPT002` | predicted text height exceeds the box by up to 5% — borderline overflow |
| `PPT003` | line runs outside the usable width: wrap off, or a single overwide glyph |
| `PPT004` | shape extends past the slide edge, or sits entirely outside it |
| `PPT005` | shrink-to-fit requested but no `fontScale` stored — result depends on the renderer |
| `PPT006` | two text-bearing shapes overlap |
| `PPT007` | declared font unavailable; measurements for those shapes are estimates |
| `INT001` | a check raised and did not complete: error; other checks still run, and coverage reports that check's surface as `skipped` |

Use `--coverage` to see the scope of a result. It distinguishes
`checked`, `not-present`, `estimated`, `skipped` and
`unsupported` surfaces per file, and a result with a gap says
`no findings in checked surfaces`, not `clean`. `ooxml-integrity doctor`
reports which measurements are available on the current machine.
See the [support matrix](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.5.0/docs/support-matrix.md) and
[coverage and doctor](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.5.0/docs/coverage.md).

## Limitations

- The DOCX evidence corpus uses 50 synthetic sources and 220 labelled pairs
  across five producers (Word for Windows, Word for Mac, Word Online, LibreOffice,
  `python-docx`): 120 clean controls and 100 seeded-defect pairs. The
  [recorded result](evidence/docx-beta/RESULTS.md) has 111 error-level true
  positives, zero false positives and zero false negatives. The 100% precision
  and recall apply to that corpus and the 14 rules it labels; the other rules
  are not measured there. Accuracy on customer documents has not been measured.
- A separate [existing-revision tranche](evidence/docx-revisions/README.md)
  has 30 pairs: 15 controls preserving review content through adeu, Word Online
  and Word for Windows, nine seeded defects (historical checker revision: seven detected,
  two missed; 0.4.2 [FID009/FID010 follow-up](evidence/docx-note-revisions/README.md):
  nine detected), and six accept/reject characterizations excluded from
  preservation metrics. Producer groups are reported separately. The three
  Windows saves preserve revisions but change table widths; unchanged layout
  and broader Office review operations remain unmeasured.
- The review-history benchmark used two contracts written for it, one version
  of each tool and agent, and one build of Word for Mac to confirm each kind of
  damage. It compares review content, not formatting or layout.
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

The benchmark showed that tools and agents given the same request can
preserve or lose review information on the same document, and that a checker
told which change was requested separates the two. Its documents were written
for it. The next question is how the checker does on real reviewed documents
and the edits real pipelines make to them.

If your workflow includes automated DOCX edits followed by human review,
try a [30-minute pilot](docs/pilot.md) with one local before/after pair.
[Share feedback](https://github.com/Dmitry-Kov/ooxml-integrity/issues/new?template=checker-feedback.yml)
about a useful finding, false alarm, missed defect or setup problem. Include
the generator and checker versions, finding code and expected/actual behavior.
GitHub reports are public; attaching a document is optional.

To attach a confidential pair, anonymize it first. The copies keep the
structure and lose the text, authors, dates, properties and pictures, and the
command checks that every finding is still there:

```bash
ooxml-integrity anonymize original.docx edited.docx -o share/
```

[What it replaces, what a reader can still learn, and how it was measured](docs/anonymize.md).

## Contributing and compatibility

See [CONTRIBUTING.md](CONTRIBUTING.md) for reproducible reports, development
setup, evidence requirements and the checks relevant to a PR.
[Compatibility and upgrades](docs/compatibility.md) explains rule codes,
severity, JSON/coverage versions, baseline migration and changes that can
affect a CI gate even in a patch release. For sensitive vulnerability reports,
use the private channel in [SECURITY.md](SECURITY.md).

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
evidence/docx-revisions/  30 pairs with existing revisions and explicit known misses
evidence/review-history-benchmark/  frozen protocol, tool and agent captures, evaluation
runs/                  the first eight agent outputs, used as fixtures
action.yml             the GitHub Action
```

## License

MIT.
