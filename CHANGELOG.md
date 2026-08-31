# Changelog

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
