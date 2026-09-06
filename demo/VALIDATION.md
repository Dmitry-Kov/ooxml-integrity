# Browser smoke test — 2026-09-06

Served the exact `demo/` directory with `python -m http.server 8765 --bind
127.0.0.1`; no bundler or development-only application server. Every browser
installed **ooxml-integrity 0.4.0 from PyPI** in **Pyodide 314.0.6 / Python 3.14.2**.

| Browser on macOS | Observed initial ready time | Clean DOCX | Broken PPTX | Fidelity pair |
| --- | --- | --- | --- | --- |
| Chrome 152.0.7977.82 | 10.0 s | exit 0, no findings | exit 1, 6 errors / 4 warnings / 1 info | CMT005 + FID001, exit 1 |
| Safari 26.6.2 | 3.4 s | exit 0, no findings | exit 1, 6 errors / 4 warnings / 1 info | CMT005 + FID001, exit 1 |
| Firefox 153.0.3 | 3.8 s | exit 0, no findings | exit 1, 6 errors / 4 warnings / 1 info | CMT005 + FID001, exit 1 |
| In-app browser | 8.6 s (repeat 1.4 s) | exit 0, no findings | exit 1, 6 errors / 4 warnings / 1 info | CMT005 + FID001, exit 1 |

These are observed page startup timings, not a controlled cold-cache benchmark
or a performance guarantee. The shared network and OS caches were not reset.

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

Repository checks: **546 passed, 7 skipped**, including **17 demo tests** for
human/JSON parity with the CLI (all examples, coverage on/off), unchanged fixture
bytes, font checksums/licenses, all 20 metric-substitute styles without
fontconfig, corrupt files, invalid extensions and propagated Python exceptions.
JavaScript syntax and the Pages workflow passed their validators.

Not tested: mobile devices, slow-network throttling, browser memory exhaustion,
the 60-second worker-termination path, or a controlled offline/network trace.
The no-upload property was reviewed in source: document buffers only go through
FileReader → worker → memory filesystem; fetches only download runtime/assets
and public fixtures. No file or finding data is used in a request.
