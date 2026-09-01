# Changelog

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
