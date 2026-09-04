# Changelog

## Unreleased

### Breaking
- Baselines now use format version 2. Version 1 fingerprints could allow one
  accepted fidelity loss to hide a different new loss with the same rule code.
  Version 1 is therefore rejected with an instruction to regenerate it rather
  than being interpreted ambiguously.

### Security
- OOXML parts are parsed with DTD loading, entity expansion and network access
  disabled, and parts containing a `DOCTYPE` are rejected.
- Composite Action inputs are passed to the shell through environment variables
  instead of being interpolated into shell source.

### Fixed
- DOCX relationships are checked package-wide, including the root
  `officeDocument` entry point and relationships owned by headers, footers and
  other XML parts.
- An explicit `--against` now fails closed when the comparison cannot run or is
  requested for a PowerPoint file, where source comparison is not implemented.
- The composite Action installs the checker from its selected Action ref by
  default, so pinning the Action no longer silently installs the latest PyPI
  release. Explicit `source` and `version` inputs remain available as overrides.
- Directories, permission failures and other package I/O errors are reported as
  findings instead of escaping the CLI as a traceback.

### Documentation
- Added a support matrix that separates supported, partial and unchecked
  surfaces for DOCX self-consistency, DOCX fidelity and PPTX layout.

## 0.3.1

### Added
- `python -m ooxml_integrity` as an entry point. The console script lands in
  pip's scripts directory, which is not on PATH on plenty of machines - a
  `pip install --user` against a Python whose user base nobody added to PATH is
  the common case, and pip only warns about it. Hit on the first machine that
  installed 0.3.0, which is a good argument for it not being a corner case.

## 0.3.0

**Renamed from `docx-integrity` to `ooxml-integrity`.** Same project, same
author, same history. The old name described half of it: the deck checks are the
part that took the most work and the only part validated against four renderers,
and someone reading `docx-integrity` would never learn they exist. The new name
is scoped to what the code actually knows - OPC packaging, XML parts, DrawingML -
which covers `.docx`, `.pptx`, and `.xlsx` when it arrives, without a second
rename.

It deliberately does **not** stretch to PDF. PDF is not OOXML: no zip of XML
parts, no relationship graph, no comment anchors. A PDF checker would share the
`Finding` type and the CLI with this and nothing else, so naming for it now would
mean picking a vaguer name for a capability that may never arrive.

### Breaking
- The import is `ooxml_integrity`, not `docx_integrity`.
- The command is `ooxml-integrity`.
- `pip install docx-integrity` still resolves, but that name stops receiving
  updates at 0.2.0. PyPI names cannot be released, so it stays reserved.
- The default baseline file is `.ooxml-integrity-baseline.json`. Point
  `--baseline` at the old one if you have it, or regenerate.

### Not breaking, on purpose
- `.docx-integrity.toml` and `[tool.docx-integrity]` are still read. A rename on
  this side is not a reason for someone else's config to stop working. The new
  spellings win when both are present, and there are tests for both.

## 0.2.0

The first release aimed at somebody else's repository rather than at this
experiment. Everything before it answered "what is wrong with this file"; this
answers the question a person hits ten minutes after adding the check to a real
project - *how do I turn off the one rule that does not apply to us, without
turning off the tool?*

### Added
- **Config** in `.docx-integrity.toml`, or `[tool.docx-integrity]` in
  `pyproject.toml`, found by walking upwards from the working directory.
  `fail-on` sets the default threshold; `[severity]` re-grades a rule or turns
  it `off`.
- **Path-scoped ignores**, with a **required** `reason`. A suppression whose
  justification lives in someone's memory cannot be reviewed a year later, so a
  config without one is refused rather than accepted quietly. Globs use shell
  semantics - `*` stays inside a path segment, which `fnmatch` alone gets wrong.
- **Baseline**: `--write-baseline` records what a repository already reports,
  `--baseline` then fails only on what is new. Three deliberate properties:
  it is written from what the *checks* saw rather than from what config allowed,
  so changing the config later cannot resurrect old findings as fake
  regressions; it counts occurrences instead of storing a set, so a second
  overflow in a shape that had one is still new; and its fingerprints exclude
  the message, because messages carry measurements and a baseline keyed on
  those goes stale the first time anything moves by a point.
- **SARIF 2.1.0** via `--sarif`, so findings become annotations in a pull
  request instead of lines in a log nobody opens. Suppressed findings are
  emitted too, marked suppressed with their reason - a report that omits them
  cannot be audited, which would defeat the point of requiring a reason.
- `--show-suppressed` prints what was hidden and why; `--no-config` ignores any
  config that would be found.
- The GitHub Action gained `config`, `baseline` and `sarif` inputs, and a
  `sarif` output.
- `docs/example-config.toml` - a worked config that explains when to reach for
  an override, an ignore, or a baseline. They are kept separate on purpose:
  "this rule is wrong for us", "this rule is wrong here" and "we know, not
  today" are three different statements, and one switch for all three loses
  which was meant.
- CI gates the new layer end to end - default run fails, baseline makes it pass,
  the same content at a different path still fails, SARIF parses. A suppression
  bug is silent by nature: the run goes green and the finding is simply gone.

### Changed
- `tomli` is a dependency on Python 3.10 and older, only to read the config
  file. 3.11+ uses `tomllib` from the standard library.
- `Policy` is exported from the package, so an API user gets the same
  suppression semantics as the CLI rather than reimplementing them.

## 0.1.3

### Fixed
- **The fidelity check counted constructs, so a swapped comment was invisible.**
  Remove one comment and add another and every count matches; because the anchor
  and the `comments.xml` entry go together, nothing is orphaned either, so the
  self-consistency half is silent too. The tool reported such a file as
  `0 error(s), 0 warning(s), 0 info - clean` while the reviewer's note had been
  destroyed - the exact defect this project exists to catch, missed by its own
  check.

  `FID004` / `FID005` / `FID006` now compare the **body text** of every comment,
  footnote and endnote in the source against the edited file, as a multiset, so
  losing one of two identically worded items is still a loss. Matching is on
  normalised text rather than on id: ids get renumbered legitimately, and it is
  the reviewer's sentence that either survived or did not.

  Found by an outside review of the arithmetic, not by the 99 tests. The
  reproduction is now `tests/test_fidelity.py::
  test_a_swapped_comment_is_caught_even_though_counts_match`, which asserts up
  front that no count changes - so it cannot quietly stop testing what it
  claims to. Verified against all eight real agent runs, including the two that
  rewrote paragraphs wholesale: no false positives.

### Added
- `research/calibrate_pptx.py` takes `--renderer` (`soffice`, `x2t`, or a path),
  `--json`, and a `--build-probe` / `--from-pdf` pair for renderers with no
  usable command line: it writes one deck with a single shape per slide, so a
  PDF exported by hand from a GUI can be measured page by page with no
  attribution guesswork. The new path was cross-checked against the old one on
  the same renderer - identical numbers on all 24 shapes.
- `research/compare_renderers.py` and `docs/calibration/` - several renderers
  side by side from the same measurement code, and the raw numbers behind the
  claims. ONLYOFFICE matches the 1.2 line-spacing constant to 0.000026% median,
  which is floating-point noise, from an engine that had no part in establishing
  it.
- The borderline band has a better justification than it had. `FIT_mixed_run_sizes`
  fills 99.2% of its box: this model and PowerPoint put it on two lines,
  LibreOffice and ONLYOFFICE on three. Two engines on each side of one string, so
  the disagreement is a property of the string rather than a precision limit of
  the model - which is what a borderline band is for. The README said the
  opposite and has been corrected.

### Changed
- Prior work names `docx-mcp` as the closest overlap and says precisely where it
  overlaps and where it does not, and the README no longer describes the
  source-comparison question as one no other tool asks.

## 0.1.2

Both fixes in this release were found by the CI matrix on its first real run,
not by the 99 tests passing on Linux.

### Fixed
- **Dot-prefixed system faces were still reachable through the style key.** The
  `.aqua kana` guard in 0.1.1 covered the plain family key, but the composed
  key (`family:italic`) was written by a second line that skipped it. So
  `.sf ns mono` was correctly rejected while `.sf ns mono:italic` was indexed,
  and an internal macOS system face remained selectable for any italic run.
  `_index_font_dirs` now has exactly one writer, which owns both keys.

  Only the macOS runner could see this - no other platform ships dot-prefixed
  families - so `tests/test_pptx.py::test_styled_system_faces_are_excluded_too`
  manufactures such a face with fontTools, and the bug is now catchable
  everywhere.

- **`research/build_corpus.py` was not reproducible on Windows.**
  `ZipInfo.__init__` defaults `create_system` to 0 on Windows and 3 elsewhere,
  and the value is written into the central directory - so identical content
  produced a different file there. Now pinned. `build_pptx_corpus.py` gained
  the same treatment plus a timestamp pass: `python-pptx` stamps entries with
  the current time, so the deck had never been byte-reproducible.

### Added
- `research/assert_deck.py` - asserts the reference deck reports its exact set
  of finding codes, and that text measurement was available at all. The
  previous CI step tested the exit code, which a runner with no fonts passes by
  reporting every layout error as a warning: the tool's own failure mode,
  inside the tool's own pipeline.
- `research/outline_deck.py` and `research/powerpoint_checklist.py` - draw a
  visible outline on every text box and print the per-shape predictions, so the
  overflow model can be checked against a real renderer by eye rather than by
  trusting the arithmetic.
- CI installs metric-compatible fonts on Linux and macOS, and fails if Calibri
  or Cambria resolve to anything but an exact or metric-compatible face.
- `docs/powerpoint-validation.md` - the overflow model checked against real
  PowerPoint for the first time. 21 of 21 checkable shapes agreed, with the line
  count exact on all of them, reading the same `Calibri.ttf` PowerPoint renders
  with. It also found that PowerPoint recomputes neither autofit mode on open,
  which puts two current severity choices in question.

## 0.1.1 - unreleased

### Fixed
- **The checker was silently not checking on macOS and Windows.** Fonts were
  located only through `fc-match`, which neither ships. On a Mac nothing was
  found, `layout_shape` skipped every paragraph, and a deck with seven
  overflowing shapes came back as `0 error(s), 3 warning(s)` - the three
  geometry findings, and a clean bill of health on all the text.

  This is the same silent-failure class the project exists to catch, in the
  project's own code, and it was caught by running the built wheel on a real
  Mac rather than by any test.

  Two changes, because either alone would have been insufficient:

  - `fonts.FONT_DIRS` and `_index_font_dirs()`: when there is no fontconfig,
    the standard font directories for macOS, Windows and Linux are scanned and
    indexed by the family names in each face's `name` table. Filenames are not
    family names - `Times New Roman` lives in `Times.ttc` - so the `name` table
    is read, and `.ttc`/`.otc` collections are expanded. The scan is deferred
    until fontconfig has already failed and cached for the process.
  - `PPT000` and `fonts.measurement_available()`: when text cannot be measured
    at all, the report says so as an **error**, rather than returning no
    findings. A tool that cannot run its own check must not report success.

  Regression tests in `tests/test_pptx.py::TestMeasurementUnavailable` cover
  all three states: fontconfig present, fontconfig absent but fonts present,
  and no fonts at all.

- **The macOS fallback picked a Japanese system font to measure English.** With
  the directory scan working but no substitute installed, the last-resort branch
  sorted the index alphabetically and took the first entry - `.aqua kana`, a
  dot-prefixed internal macOS face. Two guards: dot-prefixed families are never
  indexed, and a fallback must have basic Latin coverage. `LAST_RESORT` also
  gained the faces that actually exist on macOS and Windows, since it previously
  listed only Linux ones and therefore never matched on either.

- **Metric compatibility is measured, not asserted.** The docstring on
  `METRIC_SUBSTITUTES` claimed "IDENTICAL advance widths". Measuring Carlito
  against real Calibri - which needs two machines, since the two fonts are
  almost never installed together - shows digits match exactly and letters do
  not: Carlito is 0.26-0.58% wider. The claim is now the measurement, with the
  numbers in the source. The error is the same order as the GPOS-kerning gap and
  points toward false positives rather than misses, so `BORDERLINE` needs no
  change.

- **fontTools chatter no longer reaches the user.** Reading macOS system faces
  printed lines like `144733 extra bytes in post.stringData array` to stderr,
  in the middle of a check report. Harmless for advance widths, pure noise in
  output someone is meant to read. The first attempt silenced only the file
  open; TTFont is lazy, so the `kern` table's "subtable longer than defined"
  warning still escaped when that table was read further down. The whole read
  is inside the quiet block now.

- **Microsoft Office fonts are now found.** Microsoft 365 on macOS keeps Calibri,
  Cambria and Segoe UI in `~/Library/Group Containers/UBF8T346G9.Office/
  FontCache` rather than in a font directory, so a machine with Word installed
  was still measuring with a substitute. With this, a Mac that has Office
  measures with the real fonts - which also makes the metric-compatibility
  pairings verifiable for the first time.

## 0.1.0 — unreleased

First packaged release. The finding and the harness predate it; this is the
point at which it became installable.

### Added
- **`.pptx` layout checks.** `check_pptx()` and the CLI on a `.pptx` answer
  whether each shape's text fits its box, whether shapes overlap, and whether
  any hangs off the slide. This needs the effective font size, which is resolved
  through the full DrawingML inheritance chain: run, paragraph, the shape's list
  style, the layout and master placeholders, the master's text styles, the
  presentation defaults, and the theme font scheme.
- Text measurement (`fonts.py`) from the font's own `hmtx`/`cmap` tables, with
  graded font substitution: a metric-compatible clone counts as accurate, a
  merely similar face is reported as an estimate, and the report says which was
  used.
- `research/calibrate_pptx.py`: renders each shape alone with LibreOffice and
  compares against extracted glyph positions. Line pitch agrees to a median of
  0.05%; line count is exact on 23 of 24 shapes.
- `pip install docx-integrity`, Python 3.9+, `lxml` and `fonttools` the runtime
  dependencies.
- `docx-integrity check` CLI with `--against`, `--fail-on`, `--json`, `--quiet`
  and CI-shaped exit codes (0 clean, 1 findings, 2 usage error).
- Python API: `check()`, `compare()`, `Finding`, `Severity`.
- GitHub Action (`action.yml`) with job-summary output and a JSON report.
- 62 tests, including regressions for the three false positives that real agent
  runs exposed.
- `research/add_settings.py`: injects `word/settings.xml` into an existing
  package while asserting every other part stays byte-identical.
- The reference corpus is now byte-reproducible — a fixture you cannot rebuild
  identically is not a fixture.

### Changed
- Severity model, stated as a rule rather than case by case: losing something
  that makes content or an audit trail **invisible** is an error; losing
  something that only changes how the document **looks** is a warning. This
  promoted orphaned comments (`CMT005`), unreferenced footnotes (`FTN002`) and
  comment ranges with no reference (`CMT003`) from warning to error, so the
  defect this project exists for now fails CI at the default threshold.
- Fidelity losses carry a per-construct severity instead of one blanket rule.
- A glob matching nothing is a usage error; a *named* path that does not exist
  is a finding about that file. Previously both produced "file not found:
  *.docx", which is a nonsense message.

### Fixed
- **Line spacing for decks is a flat 1.2 x font size, not the font's vertical
  metrics.** Established by rendering six faces at two sizes: the pitch is
  exactly 1.2000 x size every time, while the faces' own metrics range from 0.80
  to 1.22. The font-metrics approach - right for Word body text - was giving a
  consistent +1.7% error.
- Line layout is run-aware: each line takes its height from the tallest run
  *on that line*. Measuring a mixed-size paragraph at one size overstated the
  height of a 32pt-plus-12pt paragraph by 45%.
- `SIMILAR_SUBSTITUTES` split out from `METRIC_SUBSTITUTES`. DejaVu Sans was
  being graded metric-compatible with Segoe UI, which claims width accuracy the
  pairing does not have.
- `REV003` no longer flags `w:ins > w:del` nesting, which is legal OOXML meaning
  "inserted by one author, deleted by another before acceptance".
- `PKG005` no longer flags zip directory entries, which are not OPC parts.
- `FID002` (a construct count going up) is informational, not a warning — an
  agent may legitimately add a clause. Real duplication is caught by colliding
  revision ids (`REV001`).
