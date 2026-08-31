# Changelog

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
