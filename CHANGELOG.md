# Changelog

## Unreleased

- Fixed a DOCX false negative when `word/styles.xml` and its package declarations
  are removed but main-document style references remain. Self-check and
  `--against` now report `STY001` for those references, with the paragraph/table
  ERROR and character WARN severities below. Missing styles without references
  remain clean. Malformed or unsafe styles XML produces `XML001` and skipped
  style coverage without duplicate undefined-reference findings. Coverage now
  marks references to an absent styles part as checked. JSON/coverage schema,
  SARIF and baseline v2 formats are unchanged; an existing baseline may expose
  newly detected references at other locations. Regression:
  [missing styles](tests/test_missing_styles.py).
- Changed `STY001` for undefined character styles (`rStyle`) from ERROR to WARN,
  including comment reference marks. Undefined paragraph and table styles
  (`pStyle`/`tblStyle`) remain ERROR because they can carry numbering and
  structure. Character-style findings no longer fail the default
  `--fail-on error` threshold; use `--fail-on warn` to retain a failing result.
  The seven measured STY001 cases are paragraph styles, so the committed corpus
  labels and metrics are unchanged.
- Added a [browser demo](demo/README.md) served by GitHub Pages. A Pyodide worker
  runs the released package from PyPI for DOCX checks, DOCX source comparison,
  PPTX layout, coverage and Doctor. Selected files remain in browser memory;
  startup downloads the runtime, package and bundled metric-compatible fonts.
  Inputs are limited to 25 MiB each and checks to 60 seconds.
- Added three public examples, human and JSON reports, CLI adapter-parity tests,
  and [recorded smoke tests](demo/VALIDATION.md) in Chrome, Safari, Firefox and
  the in-app browser on macOS. The optional `run_integrity_example` WebMCP tool
  runs only those examples.
- Expanded the demo into the project's landing page, with the detached-comment
  example, research results, installation instructions and documented limits.
- Browser report headings and JSON paths now show the filename without the
  worker's internal `input/` directory. Input and source paths remain separate,
  including when the files have the same name.
- Excluded the local audit plan from version control and package distributions.

The missing-styles fix and STY001 severity change are unreleased; release `0.4.0`
still skips references when the styles part is missing and reports undefined
character styles as errors when it is present. The other changes above affect
the website, browser adapter and repository packaging.

## 0.4.0 — 2026-09-06

Upgrade notes: [baseline v2 migration and release scope](docs/releases/0.4.0.md).

### Added

- A versioned DOCX beta evidence tranche with 50 synthetic source documents and
  220 exactly labelled source/output pairs. Ten sources each were created or
  saved by `python-docx`, LibreOffice, Word for Mac, Word for Windows and Word
  Online. Twenty pairs retain actual Windows saves and observed web edits with
  sanitised provenance and independent XML audits. The
  evaluator publishes per-rule TP/FP/FN, verifies every source/output hash, and
  makes all 120 clean controls permanent false-positive regressions. External
  documents, other builds/web sessions, independently supplied generators and
  independent dual human review remain explicit evidence gaps. The original
  corpus records and bytes are preserved.
- `check --coverage` adds a versioned per-file coverage inventory to JSON and a
  concise human summary. `--coverage-details` expands it to every surface.
  Stable identifiers distinguish checks that ran, absent surfaces, estimates,
  skipped checks and recognised unsupported constructs.
- `doctor` reports parser/runtime versions, archive-limit enforcement,
  representative usable font faces with confidence classes, and checks that
  are unavailable in this release. `doctor --json` emits the versioned report.
- DOCX source comparison now follows effective `default`, `first`, and `even`
  header/footer section relationships. `FID007` detects a missing or changed
  normalised story (including meaningful empty stories), and `FID008` detects
  lost tracked constructs. Relationship ids and part names may be renumbered;
  shared parts may be split or merged without a false loss.
- A release workflow builds and checks wheel and sdist installations, verifies
  the pinned Action, publishes to PyPI through Trusted Publishing with
  attestations, and attaches the same artifacts and checksums to GitHub Releases.
  The procedure is documented in [releasing](docs/releasing.md).

### Changed

- Grouped PowerPoint shapes and vertical-text shapes are excluded from the
  ordinary ungrouped/horizontal layout model. Their transforms and text direction
  require checks outside that model.

### Breaking

- Baselines now use format version 2. Version 1 fingerprints could allow one
  accepted fidelity loss to hide a different new loss with the same rule code.
  Version 1 is therefore rejected with an instruction to regenerate it.

### Security

- OOXML parts are parsed with DTD loading, entity expansion and network access
  disabled, and parts containing a `DOCTYPE` are rejected.
- DOCX, PPTX and source-comparison ZIPs now have configurable limits for entry
  count, archive bytes, total and per-entry expanded bytes, and compression
  ratio. Budgets are checked before member decompression and produce `PKG007`.
- Absolute, traversal-like, backslash-separated and duplicate normalised ZIP
  member names are rejected with `PKG008` before package parts are loaded.
- Composite Action inputs are passed to the shell through environment variables
  instead of being interpolated into shell source.

### Fixed

- PPTX major/minor Latin fonts now resolve through each slide's own layout,
  master and theme. Literal fonts retain precedence; unrelated themes and ZIP
  order cannot select another master's face. Missing required dependencies or
  faces and unsupported font-scheme overrides fail closed with `PKG002` and
  skipped coverage. Eight native PowerPoint exports document three fixed omissions
  and one false positive. The layout model adds per-slide theme diagnostics;
  the legacy `Deck.theme_fonts` summary now contains only common resolved faces.
  Font confidence and rule thresholds are unchanged. Also removed the stale
  `doctor` claim that main slide order is unavailable.
- PPTX layout now follows the main `p:sldIdLst` and its slide relationships,
  preserving presentation positions even with reordered, gapped or nonnumeric
  part names. Hidden slides retain their editor positions; unlisted parts are
  excluded from layout checks. Broken listed references/roots fail closed
  with `PKG002`. Slide-order coverage is now checked when resolved. Three
  native PowerPoint exports confirm the ordering and correct finding location.
  Existing baselines with old incorrect slide locations may need review and
  regeneration; the baseline format is unchanged.
- TTC/OTC discovery and metrics now retain the selected collection member,
  including substitutions and character-coverage caches. Lazy collection
  streams stay open through enumeration, and later Light/Heavy faces no longer
  overwrite canonical Regular styles. Fontconfig indices are retained;
  unsupported named variable instances are not silently measured as member
  zero. `doctor --json` includes `face_index`. Synthetic TrueType/CFF tests and
  six native PowerPoint exports document two fixed omissions and one false positive.
- PPTX long basic-Latin words now wrap by character when wider than a complete
  usable line, preserving run sizes, insets and stored font scaling. This closes
  vertical-overflow false negatives without flagging tall clean controls.
  `latinLnBrk` inheritance and run-spanning words are respected. `PPT003` also
  detects residual horizontal excess with wrap on, such as one overwide glyph.
  Near-boundary or unmodelled character breaking is explicitly estimated/WARN
  and reflected in coverage. Twelve pinned PowerPoint for Mac PNG exports and
  a synthetic PPTX record the observed line breaks and verdicts.
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

- `python -m ooxml_integrity` as an entry point for machines where pip's scripts
  directory is not on PATH. The issue appeared on the first machine that
  installed 0.3.0: `pip install --user` succeeded, but the console command could
  not be found. Module invocation uses the selected Python installation directly.

## 0.3.0

Renamed from `docx-integrity` to `ooxml-integrity`, keeping the same project,
author and history. The old name hid the presentation checks, which had taken
most of the development work and included comparisons with PowerPoint,
LibreOffice and ONLYOFFICE.
The new name covers the shared OPC packaging, XML parts and DrawingML used by
`.docx` and `.pptx`, and leaves room for possible `.xlsx` support.

PDF remains outside the scope. It has a different file structure, and a PDF
checker would share little beyond the `Finding` type and CLI.

### Breaking

- The import is `ooxml_integrity`, not `docx_integrity`.
- The command is `ooxml-integrity`.
- `pip install docx-integrity` still resolves, but that name stops receiving
  updates at 0.2.0. PyPI names cannot be released, so it stays reserved.
- The default baseline file is `.ooxml-integrity-baseline.json`. Point
  `--baseline` at the old one if you have it, or regenerate.

### Not breaking, on purpose

- `.docx-integrity.toml` and `[tool.docx-integrity]` remain supported, so existing
  configuration keeps working after the rename. The new spellings take
  precedence when both are present; tests cover both forms.

## 0.2.0

Added the configuration needed to use the checker in an existing repository:
rule overrides, path-specific exceptions, baselines and review annotations.

### Added

- **Config** in `.docx-integrity.toml`, or `[tool.docx-integrity]` in
  `pyproject.toml`, found by walking upwards from the working directory.
  `fail-on` sets the default threshold; `[severity]` re-grades a rule or turns
  it `off`.
- **Path-scoped ignores**, with a required `reason` so a later reviewer can
  understand the exception. A config without one is rejected. Globs use shell
  semantics: `*` stays inside a path segment, unlike plain `fnmatch` matching.
- **Baseline**: `--write-baseline` records what a repository already reports,
  `--baseline` then fails only on new findings. Entries are recorded before
  configuration is applied, so a config change does not make old findings
  appear as regressions. Occurrences are counted: a second overflow in a shape
  that already had one is still new. Fingerprints exclude message text, whose
  measurements may change after a small layout adjustment.
- **SARIF 2.1.0** via `--sarif`, for findings in pull request reviews.
  Suppressed findings are included with their reasons, so reviewers can inspect
  the exceptions as well.
- `--show-suppressed` prints what was hidden and why; `--no-config` ignores any
  config that would be found.
- The GitHub Action gained `config`, `baseline` and `sarif` inputs, and a
  `sarif` output.
- `docs/example-config.toml`, a worked config explaining when to use an
  override, a path-specific ignore, or a baseline of existing findings.
- CI tests policy handling end to end: the default run fails, the baseline
  makes it pass, the same content at a different path still fails, and the
  SARIF output parses. These checks catch suppressions that would otherwise
  hide a finding while leaving CI green.

### Changed

- `tomli` is a dependency on Python 3.10 and older, only to read the config
  file. 3.11+ uses `tomllib` from the standard library.
- `Policy` is exported from the package, so an API user gets the same
  suppression semantics as the CLI rather than reimplementing them.

## 0.1.3

### Fixed

- Replacing one comment with another escaped the fidelity check because the
  construct counts stayed equal. When the anchor and `comments.xml` entry were
  replaced together, self-consistency checks also found no orphaned item. The
  tool reported `0 error(s), 0 warning(s), 0 info - clean` even though the
  original reviewer's note was gone.

  `FID004` / `FID005` / `FID006` now compare the body text of every comment,
  footnote and endnote in the source against the edited file, as a multiset, so
  losing one of two identically worded items is still a loss. Matching is on
  normalised text, allowing legitimate id renumbering.

  An outside review found the gap while the 99 tests were passing. The
  reproduction is now `tests/test_fidelity.py::
  test_a_swapped_comment_is_caught_even_though_counts_match`, which asserts up
  front that no count changes. All eight real agent runs were checked for
  false positives, including the two that rewrote paragraphs wholesale; none
  were found.

### Added

- `research/calibrate_pptx.py` takes `--renderer` (`soffice`, `x2t`, or a path),
  `--json`, and a `--build-probe` / `--from-pdf` pair for renderers with no
  usable command line: it writes one deck with a single shape per slide, so a
  PDF exported by hand from a GUI can be measured page by page with each result
  attributed to its source shape. The new path was cross-checked against the
  old one on the same renderer, with identical numbers on all 24 shapes.
- `research/compare_renderers.py` and `docs/calibration/` - several renderers
  side by side from the same measurement code, and the raw numbers behind the
  results. ONLYOFFICE matches the 1.2 line-spacing constant to 0.000026% median,
  a difference at the level of floating-point noise. It was not used to
  establish that constant.
- Renderer comparison clarified the borderline band. `FIT_mixed_run_sizes`
  fills 99.2% of its box: this model and PowerPoint put it on two lines,
  LibreOffice and ONLYOFFICE on three. The same text therefore has different
  valid layouts across engines. The README was corrected to describe this
  renderer dependence; the earlier explanation had attributed the band to the
  model's measurement precision.

### Changed

- Prior work now describes the overlap with `docx-mcp`. The README's claim that
  no other tool addresses source comparison was removed.

## 0.1.2

The first CI matrix run found both fixes below after the 99 tests had passed
on Linux.

### Fixed

- Dot-prefixed system faces were still reachable through the style key. The
  `.aqua kana` guard in 0.1.1 covered the plain family key, but the composed
  key (`family:italic`) was written by a second line that skipped it. So
  `.sf ns mono` was correctly rejected while `.sf ns mono:italic` was indexed,
  and an internal macOS system face remained selectable for any italic run.
  `_index_font_dirs` now has exactly one writer, which owns both keys.

  The failure appeared on the macOS runner, where these system families were
  present. `tests/test_pptx.py::test_styled_system_faces_are_excluded_too` now
  creates such a face with fontTools so the regression can run on every platform.

- `research/build_corpus.py` produced different bytes on Windows.
  `ZipInfo.__init__` defaults `create_system` to 0 on Windows and 3 elsewhere,
  and the value is written into the central directory - so identical content
  produced a different file there. The value is now fixed. `build_pptx_corpus.py` gained
  the same treatment plus a timestamp pass: `python-pptx` stamps entries with
  the current time, so the deck had never been byte-reproducible.

### Added

- `research/assert_deck.py` - asserts the reference deck reports its exact set
  of finding codes, and that text measurement was available at all. The
  previous CI step tested only the exit code. A runner with no fonts could pass
  it while reducing layout errors to warnings.
- `research/outline_deck.py` and `research/powerpoint_checklist.py` - draw a
  visible outline on every text box and print the per-shape predictions, so the
  overflow predictions can be compared visually with a renderer.
- CI installs metric-compatible fonts on Linux and macOS, and fails if Calibri
  or Cambria resolve to anything but an exact or metric-compatible face.
- `docs/powerpoint-validation.md` - the overflow model checked against real
  PowerPoint for the first time. 21 of 21 checkable shapes agreed, with the line
  count exact on all of them, reading the same `Calibri.ttf` PowerPoint renders
  with. It also found that PowerPoint recomputes neither autofit mode on open,
  which puts two current severity choices in question.

## 0.1.1 - unreleased

### Fixed

- Text measurement could be skipped on macOS and Windows because font discovery
  relied on `fc-match`, which neither ships. On a Mac nothing was
  found, `layout_shape` skipped every paragraph, and a deck with seven
  overflowing shapes came back as `0 error(s), 3 warning(s)` - the three
  geometry findings. The report did not say that the text had gone unchecked.
  Running the built wheel on a Mac exposed the problem; the tests had missed it.

  The fix adds font discovery and an explicit measurement failure:

  - `fonts.FONT_DIRS` and `_index_font_dirs()`: when there is no fontconfig,
    the standard font directories for macOS, Windows and Linux are scanned and
    indexed by the family names in each face's `name` table. Filenames are not
    family names: `Times New Roman` lives in `Times.ttc`, so the `name` table
    is read, and `.ttc`/`.otc` collections are expanded. The scan is deferred
    until fontconfig has already failed and cached for the process.
  - `PPT000` and `fonts.measurement_available()`: when text cannot be measured
    at all, the report returns an error explaining that measurement was unavailable.

  Regression tests in `tests/test_pptx.py::TestMeasurementUnavailable` cover
  all three states: fontconfig present, fontconfig absent but fonts present,
  and no fonts at all.

- The macOS fallback picked a Japanese system font to measure English. With
  the directory scan working but no substitute installed, the last-resort branch
  sorted the index alphabetically and took the first entry - `.aqua kana`, a
  dot-prefixed internal macOS face. Two checks now prevent this: dot-prefixed families are never
  indexed, and a fallback must have basic Latin coverage. `LAST_RESORT` also
  gained the faces that actually exist on macOS and Windows, since it previously
  listed only Linux ones and therefore never matched on either.

- Corrected the `METRIC_SUBSTITUTES` docstring, which claimed "IDENTICAL advance
  widths". Measurements of Carlito and real Calibri on two machines showed
  exact digit widths, while Carlito's letters were 0.26-0.58% wider. The source
  now records these measurements. The difference is of the same order as the
  GPOS-kerning gap and tends toward false positives, so `BORDERLINE` is unchanged.

- Suppressed fontTools diagnostics during metric loading. Reading macOS system faces
  printed lines like `144733 extra bytes in post.stringData array` to stderr,
  in the middle of a check report. These messages did not affect advance widths.
  The first attempt silenced only the file
  open; TTFont is lazy, so the `kern` table's "subtable longer than defined"
  warning still escaped when that table was read further down. The whole read
  is inside the quiet block now.

- Font discovery now includes Microsoft Office's cache. Microsoft 365 on macOS keeps Calibri,
  Cambria and Segoe UI in `~/Library/Group Containers/UBF8T346G9.Office/
  FontCache` rather than in a font directory, so a machine with Word installed
  was still measuring with a substitute. With this, a Mac that has Office
  can measure with the real fonts, allowing direct verification of the
  metric-compatibility pairings.

## 0.1.0 — unreleased

First installable package. The original finding and experimental harness predate it.

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
- The reference corpus can now be rebuilt byte-for-byte.

### Changed

- Defined the severity model: losing something that makes content or an audit
  trail invisible is an error; a loss affecting only appearance is a warning. This
  promoted orphaned comments (`CMT005`), unreferenced footnotes (`FTN002`) and
  comment ranges with no reference (`CMT003`) from warning to error, so
  these losses now fail CI at the default threshold.
- Fidelity losses carry a per-construct severity instead of one blanket rule.
- A glob matching nothing is a usage error; a *named* path that does not exist
  is a finding about that file. Previously both produced "file not found:
  *.docx", leaving the cause unclear.

### Fixed

- DrawingML line spacing is modelled as 1.2 x font size. Rendering six faces at
  two sizes gave a pitch of exactly 1.2000 x size every time, while the faces'
  own metrics range from 0.80
  to 1.22. Using vertical font metrics, as for Word body text, was giving a
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
- `FID002` (a construct count going up) is informational because an
  agent may legitimately add a clause. Duplication is caught by colliding
  revision ids (`REV001`).
