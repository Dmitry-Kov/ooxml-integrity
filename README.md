# ooxml-integrity

[![CI](https://github.com/Dmitry-Kov/ooxml-integrity/actions/workflows/ci.yml/badge.svg)](https://github.com/Dmitry-Kov/ooxml-integrity/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/ooxml-integrity)](https://pypi.org/project/ooxml-integrity/) [![Python](https://img.shields.io/pypi/pyversions/ooxml-integrity)](https://pypi.org/project/ooxml-integrity/) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.10.0/LICENSE)

An edited Word file can open normally and still have lost a reviewer's comment,
another author's tracked change or a footnote. `ooxml-integrity` finds these
losses after a script, library or agent edits a `.docx`, and finds `.pptx` text
that overflows its box. It runs locally, with no rendering, model calls or network.

```bash
pip install ooxml-integrity
ooxml-integrity check edited.docx --against original.docx
```

```
edited.docx: 2 error(s), 0 warning(s), 1 info
  [ERROR] CMT005  comment id=1 is orphaned - present in comments.xml but anchored to nothing - the reviewer's note is invisible in Word
            -> word/comments.xml
  [ERROR] FID001  comment anchors: 2 -> 1 (1 lost)
  [INFO ] FID014  document: paragraph 15 changed: 'EUR 12,000' -> 'EUR 12,500'
            -> document/p15
```

python-docx changed the fee as asked, and dropped the anchor of the reviewer's
comment on that cell. Exit code `1` fails a CI job; `--json` gives machine-readable output.

**Benchmark.** Thirty ordinary edit requests on two reviewed contracts went to six
document tools and three coding agents. 69 of the 636 attempts that ran damaged
the review record: replies Word does not show, bullets turned into `&#8226;`,
another reviewer's pending insertion turned into accepted text. The frozen checker
(0.4.6) reported 41 of the 69. With each task's requested change declared, 0.4.9
reports 65 and 0.8.0 all 69, and both flag 12 of 537 correct outputs, each a true
report outside the benchmark's scope, such as a reply Word does not show. Those
rules came after the benchmark and were measured on the same captures. Counts are
attempts on two documents, not independent documents. [Results](https://dmitry-kov.github.io/ooxml-integrity/benchmark/) ·
[evidence](evidence/review-history-benchmark/README.md) ·
[fixed upstream](docs/upstream.md)

**Next:** [browser demo](https://dmitry-kov.github.io/ooxml-integrity/) ·
[CI action](#in-ci) · [MCP server for agents](docs/mcp.md) ·
[Python API](#from-python) · [`fix`](docs/fix.md) ·
[decks](#decks-does-the-text-fit-the-box) · [rules and coverage](docs/rules.md) ·
[how it started](docs/research.md#the-finding) ·
[limitations](docs/research.md#limitations)

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

When the original may already be broken, as with a document a user uploads to
an agent, add `--introduced` (0.10.0) to fail only on what the edit added. A
finding the original already has is listed as suppressed instead; lost content
always counts. [What counts as the same finding](docs/configuration.md#defects-the-source-already-had).

Exit codes are `0` for no findings at or above `--fail-on` (default `error`),
`1` when such findings exist, and `2` for a usage error. Use `--json` for
machine-readable output and `--quiet` to print only findings that fail the run.

## Three repairs, and no more

Most findings cannot be repaired from the file: putting back a lost comment,
style or tracked change means guessing what was there. `fix` makes only the
three repairs whose result is unique, and checks the copy again before writing
it.

```bash
ooxml-integrity fix edited.docx -o repaired.docx
```

- **anchor-replies** (`CMT005`): a reply whose parent comment is anchored is
  given its parent's range, in the order Word writes a thread. In Word for Mac,
  the reply appears in its thread only after the repair.
- **renumber-revisions** (`REV001`): every repeated revision id after the first
  gets a fresh id.
- **content-type** (`PKG010`): a related part's `Override` in
  `[Content_Types].xml` gets the content type its relationship type requires.
  Word for Mac refused all five Codex outputs that `fix` repairs this way, and
  opened the copy `fix` writes from one of them, with the reply in its thread.

Every other finding is listed as not repaired, with the reason. The input is
never changed. In the copy, only the repaired bytes differ, and every other ZIP
member is copied as stored. Exit `0` means a verified copy was written; `1`,
nothing to repair; `2`, a usage error or a package `fix` does not rewrite; `3`,
a failed re-check. [What it repairs, refuses and guarantees](docs/fix.md).

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
- uses: Dmitry-Kov/ooxml-integrity@v0.10.0
  with:
    files: "out/**/*.docx"
    against: templates/master.docx   # optional, enables the fidelity check
    fail-on: error
```

Run the check after a generation script, agent edit or template merge, while
the source and edited files are still available for comparison.

The action writes a summary to the job page and can produce JSON and SARIF
reports. SARIF findings can appear as code-scanning annotations in a pull
request. The [configuration guide](https://github.com/Dmitry-Kov/ooxml-integrity/blob/v0.10.0/docs/configuration.md)
covers severity overrides, path-scoped ignores with a required `reason`, and
counted baselines for repositories that already have findings.

## From an agent

```bash
claude mcp add ooxml-integrity -- ooxml-integrity mcp
```

An agent can run the same checks on a document it has just edited, before it
returns the file. `ooxml-integrity mcp` is a local MCP server with two tools,
`check` and `compare`; it talks over stdin and stdout and opens no socket. A
call returns the report of `check --json --coverage` and a one-line verdict.
The [MCP guide](docs/mcp.md) has the configuration for Claude Code, Codex and
OpenCode.

<!-- mcp-name: io.github.Dmitry-Kov/ooxml-integrity -->

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

## What it reports

Every finding has a stable code and severity. The full rule tables for `.docx`
and `.pptx`, and how `--coverage` reports what was checked, are in
[docs/rules.md](docs/rules.md); the exact scope of each rule is in the
[support matrix](docs/support-matrix.md).

## Limitations

- The DOCX evidence corpus is 50 synthetic sources and 220 labelled pairs across
  five producers: 120 clean controls and 100 seeded-defect pairs, with 111
  error-level true positives and zero false positives or negatives
  ([recorded result](evidence/docx-beta/RESULTS.md)). The 100% precision and
  recall apply to that corpus and the 14 rules it labels. **Accuracy on customer
  documents has not been measured.**
- The [review-history benchmark](evidence/review-history-benchmark/README.md)
  used two contracts written for it, one version of each tool and agent, and one
  build of Word for Mac. It compares review content, not formatting or layout.
- PPTX evidence comes from PowerPoint for Mac; Windows and Slide Show mode are
  untested. Grouped shapes, tables, SmartArt and charts are not modelled,
  rotated shapes are only partially checked, and complex scripts are estimates.
- A separate [existing-revision tranche](evidence/docx-revisions/README.md) has
  30 pairs. Of its nine seeded defects the checker of the time found seven;
  0.4.2 finds all nine.
- The full list, with the numbers behind each, is in
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
affect a CI gate even in a patch release; each release's
[upgrade notes](docs/releases/) describe changed findings. For sensitive vulnerability reports,
use the private channel in [SECURITY.md](SECURITY.md).

## Repository layout

```
src/ooxml_integrity/   inspector, fidelity, fonts, pptx layout and checks,
                       coverage, doctor, policy, sarif, cli, MCP server
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