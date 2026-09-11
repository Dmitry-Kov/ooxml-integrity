# Browser validation

## Pinned runtime and browser gate — 2026-09-12

The B2 runtime changes were checked locally on macOS with Playwright 1.63.0 /
Chromium 153.0.8010.12. The checkout was based on
`ba7b66d687fbb9cc619be199d1b39791d35602b7`; these hashes identify the changed
runtime files exercised by the runs:

```text
3061d0c0ad44c00d6a6edae99d58706d572db20be8714c70e8e1300ff92e7899  demo/app.js
8502d46bd219e291c15bf80e15547440bc00d5433ebab280a1e22b7d47ca7f82  demo/worker.js
```

The HTML/CSS hashes are unchanged from the B1 record below. The public worker
pins `0.4.0` and verifies distribution/module versions before signalling ready.
All six [browser scenarios](../tests/browser/README.md) passed in both runs:

| Package source | Actual footer version | Result |
| --- | --- | --- |
| PyPI, exact public pin | ooxml-integrity 0.4.0 · Pyodide 314.0.6 | 6 passed, 0 skipped |
| Local candidate wheel in an isolated preview | ooxml-integrity 0.4.1 · Pyodide 314.0.6 | 6 passed, 0 skipped |

The candidate was built from a temporary source copy with only the project and
module version strings changed to `0.4.1`. Its wheel SHA-256 was
`2e2054f4e7ca496193efa0f47fcdd5400fef02469f0fe98319d5daa944a7b730`.
This proves the preview can install a different version without changing the
public site. It is not a published release or final R1 artifact: the tracked
package version is still `0.4.0`. CI builds the actual checkout version rather
than applying this temporary version stamp.

Both runs reported CPython 3.14.2 / Emscripten-5.0.3-wasm32-32bit, lxml 6.0.2.0,
libxml2 2.9.10 and fonttools 4.62.1. Actual network requests recorded the public
wheel from files.pythonhosted.org and the candidate wheel from the loopback
preview server. Checks used the three bundled metric font substitutes reported
by Doctor. The public examples returned the expected clean DOCX, CMT005/FID001
comparison and PPTX findings; JSON and coverage toggles agreed. Same-named
inputs, removal/reselection, corrupt files, invalid extensions and the invalid
PPTX/source combination all produced the expected outcome and recovered.

Blocked runtime and required-font downloads produced visible connection/reload
guidance with checks disabled. Removing each fault and reloading restored a
working check. A four-second delay on the runtime module request kept loading
progress visible and then completed; this was a latency injection, not a
bandwidth-throttling benchmark. For the timeout case, a test-only bridge made
real Python spin while the main-thread UI remained responsive. The production
60-second timer stopped the worker; the observations after asserting the stopped
state were 63.062s and 63.059s from clicking Check. Both runs recovered on reload.

At 1280×900 and 390×900, the document had no horizontal overflow, navigation
reached the intended sections and the narrow table exposed its final column
through internal scrolling. Its captured screenshot was inspected. These are
desktop Chromium viewports, not physical mobile-device tests. No Safari/Firefox
gate or exhaustive slow-network coverage is claimed.

Local Python verification returned **706 passed, 7 skipped**, including 20
adapter tests and six preview-generation checks. JavaScript syntax and actionlint
passed. The browser workflow uploads JSON receipts with the exact checkout,
page hashes, package/runtime/browser versions and observed results; failures also
retain screenshots and traces. Pages now depends on both browser jobs and
uploads only `demo/`. Publication of the final `0.4.1` package and the subsequent
public-PyPI pin change remain part of the release procedure.

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
