# Browser validation

## Landing evidence and layout — 2026-09-12

The B1 page was served from `demo/` on `http://127.0.0.1:8765/` in the
in-app browser on macOS. The checkout was based on
`848fb24c7e1f829b3ad7f12924da7d71da39c7bc`, with the B1 changes in this revision.
These SHA-256 hashes identify the exact page files inspected:

```text
abe3f76ec02965d64757aec4e260ee8ab5a7cdeb041b52c1b5ec464693a59cdb  demo/index.html
0799fcf1b0e68e5edfc3bd75e40642ce803a20f171da19133942fbab6ef6bcee  demo/style.css
```

Visual inspection covered the hero illustration, comparison table, measurement
cards, installation examples and limitations at **1280 × 900** and **390 × 844**.
The final page was reloaded after the HTML/CSS changes. At 1280px, document
width was 1280px and the full five-column comparison table fit its 1016px
container. At 390px, document width was 390px; the table scrolled inside a
354px region with 640px of content. Scrolling it to `scrollLeft = 286` exposed
the final findings column. Its visible hint explains the sideways scroll.
The narrow header retained all four navigation links. Long installation code
stayed inside its scrollable blocks instead of widening the page. Try it and
Install navigation reached their corresponding sections.

The runtime footer reported **ooxml-integrity 0.4.0 · Pyodide 314.0.6**.
Doctor reported CPython 3.14.2, lxml 6.0.2.0 / libxml2 2.9.10 and fonttools
4.62.1. The three public examples were run through the page's
`run_integrity_example` tool and updated the visible report:

| Example | Observed result |
| --- | --- |
| Clean DOCX | Exit 0; no findings |
| Detached comment with source | Exit 1; CMT005 + FID001 errors, FID002 informational addition |
| Broken PPTX | Exit 1; 6 errors, 4 warnings, 1 info |

The fidelity JSON tab contained the same findings and a coverage block.
Turning coverage off and rechecking the PPTX removed that block while retaining
the same finding counts. Doctor returned `ready`, XML/archive capabilities
available and 3/3 representative font families usable through substitutes;
fontconfig was not installed. Browser console inspection returned no warnings
or errors. Startup on the observed reload took 1.5 seconds; caches were not
reset, so this is not a cold-start benchmark.

The evidence review distinguishes the following measurements:

- [Six controlled mutations and two controls](../docs/research.md#what-each-verification-approach-catches):
  XML parsing, Word namespace/root/body checks and PDF creation, with no full
  XSD validation or scored visual-review detection rate.
- [Eight agent runs](../runs/README.md): separate observations with varied tasks
  and prompts, not a controlled comparison of tool choice or a damage-frequency estimate.
- [PowerPoint fit](../docs/powerpoint-validation.md#result): 21 non-excluded
  reference shapes in Mac editing view with the same Calibri file; three exclusions.
- [Font measurements](../docs/research.md#how-accurate-is-the-deck-model): a
  six-face LibreOffice line-pitch probe at 12pt/20pt and six Calibri/Carlito
  width samples at 18pt, not general renderer or substitution guarantees.
- [DOCX corpus](../evidence/docx-beta/RESULTS.md): 50 synthetic sources,
  220 pairs (120 clean / 100 seeded), 111 error-level TP, zero FP/FN;
  14 measured rules and 30 unmeasured rules, without customer-document accuracy.

The controlled mutation comparison was also rerun against this checkout using
LibreOfficeDev 26.8.0.0.alpha0 (`2c87e51eeaa2b413ff4ae097b2705eea1995d8e5`).
All eight inputs parsed, passed the root/body check and produced PDFs larger
than 1000 bytes. All six defect cases had ERROR/WARN checker findings; both
controls had none. The research table records the current counts, distinguishing
INFO additions from losses. Local Python 3.9.6 verification returned **662 passed,
7 skipped**, including **20 demo adapter tests**. The 50-source / 220-pair DOCX
evaluation had zero label mismatches; JavaScript syntax and page evidence links
passed their checks.

This is a desktop-browser viewport check, not a test on physical mobile devices
or a repeat of the cross-browser matrix below. The worker and its unpinned PyPI
installation are unchanged. Pinning the package and gating publication on a
broader real-browser suite, including startup failure, slow networking and
timeout recovery, remain separate work. No new Office render observations or
package release are claimed by this page revision.

## Initial browser smoke test — 2026-09-06

The test served `demo/` with `python -m http.server 8765 --bind 127.0.0.1`.
Every browser installed ooxml-integrity 0.4.0 from PyPI in
Pyodide 314.0.6 / Python 3.14.2.

This record covers the initial demo. The landing-page redesign followed in
commits `d77c797`, `19e81df` and `4747ea0`, which changed `index.html` and
`style.css`. The worker and adapter were unchanged, but the browser observations
below do not constitute a visual check of that later layout.

| Browser on macOS | Observed initial ready time | Clean DOCX | Broken PPTX | Fidelity pair |
| --- | --- | --- | --- | --- |
| Chrome 152.0.7977.82 | 10.0 s | exit 0, no findings | exit 1, 6 errors / 4 warnings / 1 info | CMT005 + FID001, exit 1 |
| Safari 26.6.2 | 3.4 s | exit 0, no findings | exit 1, 6 errors / 4 warnings / 1 info | CMT005 + FID001, exit 1 |
| Firefox 153.0.3 | 3.8 s | exit 0, no findings | exit 1, 6 errors / 4 warnings / 1 info | CMT005 + FID001, exit 1 |
| In-app browser | 8.6 s (repeat 1.4 s) | exit 0, no findings | exit 1, 6 errors / 4 warnings / 1 info | CMT005 + FID001, exit 1 |

These timings record the observed page startup. Shared network and OS caches
were not reset, so the numbers cannot be used as a controlled cold-cache
benchmark or a performance guarantee.

Additional UI checks in the in-app browser:

- Doctor: `ready`, XML/archive checks available, all three representative font
  probes usable through metric substitutes, `fontconfig not installed`.
- JSON has version, fail_on, config, baseline, files, findings, summary, worst,
  suppressed and coverage in the CLI shape. Turning coverage off removes its
  block and its human output; findings remain unchanged.
- Selecting a real local PPTX through the file chooser works. PPTX + a DOCX
  source produces an explicit comparison error; removing the source and
  rechecking succeeds with the expected PPTX findings.
- Selecting a Markdown file produces the visible unsupported-file error and
  clears the invalid selection. A subsequent valid selection works.
- The optional WebMCP `run_integrity_example` registered with the advertised
  schema, ran the fidelity example into the visible report and returned CMT005,
  FID001 and FID002. An invalid example was rejected without changing the report.
- Chrome console inspection reported no warnings or errors.

At the time of this smoke test, repository checks returned 546 passed and
7 skipped, including 17 demo tests for
human/JSON parity with the CLI (all examples, coverage on/off), unchanged fixture
bytes, font checksums/licenses, all 20 metric-substitute styles without
fontconfig, corrupt files, invalid extensions and propagated Python exceptions.
JavaScript syntax and the Pages workflow passed their validators.

The test did not cover mobile devices, slow-network throttling, browser memory
exhaustion, the 60-second worker-termination path or a controlled offline/network
trace. Source review confirmed that document buffers pass from FileReader to the
worker and its memory filesystem. Fetches download the runtime, assets and
public fixtures; no request contains file or finding data.
