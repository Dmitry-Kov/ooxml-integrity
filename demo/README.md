# Browser demo

[Open the demo](https://dmitry-kov.github.io/ooxml-integrity/).

One static page with plain CSS, JavaScript and a small Python adapter. There is
no framework, server-side document processing or build step. GitHub Pages serves
the committed `demo/` directory; `.github/workflows/pages.yml` deploys it on pushes
to `main` affecting the demo and can also be started manually.

## What runs where

- A module Web Worker loads [Pyodide 314.0.6](https://pyodide.org/en/stable/usage/quickstart.html)
  from its official jsDelivr URL (latest stable verified 2026-09-06), then loads
  the built-in `lxml`, `fonttools` and `micropip` packages. `fonttools` is a pure
  Python wheel. Python 3.14 already includes `tomllib`, so it does not need `tomli`.
- `micropip.install("ooxml-integrity")` installs the released package from PyPI,
  not this checkout. The footer shows the installed version; the adapter is
  tested with **0.4.0**. Updating this repository does not update the PyPI package.
- Twenty bundled OFL font faces download in parallel with Python and are written
  to `/usr/share/fonts/` in the worker's memory-only filesystem before any checks
  or font-directory caching. Startup finishes with a Doctor capability check.
- `FileReader` reads selected files into memory. Transferable buffers go to the
  worker, which writes `input/<name>` and `source/<name>`, calls public `check`,
  `check_pptx` and `compare`, and unlinks both files after every run, including
  errors. No files, filenames or findings are uploaded. Selected `File` objects
  remain until removed; the visible report remains until the next run or the tab
  is closed.
- Human output calls the package's `_print_human` and `_print_coverage` helpers.
  JSON follows `check --no-config --json [--coverage]`; the CLI has no reusable
  JSON formatter. Tests compare both representations directly with the CLI.
  Doctor calls `cli.main(["doctor"])` and its JSON variant.

No analytics, cookies, service worker, persistent document storage or external
fonts. External requests are limited to **cdn.jsdelivr.net**, **pypi.org** and
**files.pythonhosted.org** for startup. Page assets, fonts and example files are
same-origin downloads. Checks themselves require no network; public example
buttons fetch their same-origin fixtures on demand. External documentation links
are ordinary links, not startup requests. This is not an air-gapped application:
the host/CDNs still receive normal web requests, and Python code from PyPI/CDN is
trusted code executing in the tab.

## Font caveat

Calibri is measured with **Carlito**, Cambria with **Caladea**, Arial with
**Liberation Sans**, Times New Roman with **Liberation Serif**, and Courier New
with **Liberation Mono**. Regular, Bold, Italic and BoldItalic are bundled for
each family. These are metric-compatible substitutions, not Microsoft's fonts
or an Office renderer. Coverage labels substituted measurements **estimated**;
unknown fonts fall back with lower confidence. Doctor reports capability, not
document correctness. See [font sources and licenses](fonts/README.md) and the
[project's limitations](https://github.com/Dmitry-Kov/ooxml-integrity#limitations).

## Examples

| Button | Committed copy | Expected result |
| --- | --- | --- |
| Clean DOCX | `corpus/base.docx` → `examples/base.docx` | No findings; coverage states its limits |
| Broken PPTX | `corpus/deck.pptx` → `examples/deck.pptx` | Overflow, off-canvas and overlap findings |
| Lost comments + source | `runs/t4_fast_fee/agreement.docx` → `examples/agreement.docx`, with `base.docx` | **CMT005** orphaned comment and **FID001** lost anchor |

All three are synthetic public fixtures, copied byte-for-byte. Comparison is
DOCX-only: the UI reports an error for PPTX plus a source instead of quietly
skipping comparison. Unsupported extensions, unreadable packages and Python
exceptions appear in the output panel. Error-panel JSON is `{ "error": "…" }`,
not a successful CLI result. Findings retain normal CLI exit codes (0/1).

To protect browser responsiveness, files are capped at **25 MiB each** and each
check at **60 seconds**. A timed-out worker is terminated; reload to restart it.
The package's default expanded-archive limits still apply. Use the CLI for large
documents. Current Chrome, Firefox and Safari support the required module
workers, WebAssembly, FileReader and transferable buffers; no cross-origin
isolation, SharedArrayBuffer or browser-specific API is required.

Browsers that expose `document.modelContext` also get one optional WebMCP tool,
`run_integrity_example`, using the same three public examples and UI actions.
It replaces the current selection and returns only fixture finding codes and
counts; it cannot inspect a user's previously selected file or report. Browsers
without that optional API keep the full visible interface.

## Run and verify locally

```sh
cd demo
python -m http.server 8765 --bind 127.0.0.1
# Open http://127.0.0.1:8765/ (file:// does not support this module-worker setup).
```

Click all three example buttons, verify CMT005 and FID001 in the fidelity report,
inspect JSON with coverage both on and off, and run Doctor. Startup progress and
elapsed time are visible; aim for about 20 seconds on a normal broadband
connection, not a guarantee for every network/device. Font downloads overlap
runtime initialization and ordinary browser caching speeds repeat visits.

From the repository's development environment:

```sh
python -m pytest tests/test_browser_demo.py
node --check demo/app.js
node --check demo/worker.js
```

The static demo is deliberately not included in the PyPI distribution. Its
adapter-parity tests skip when run from an sdist without `demo/`. Browser smoke
tests must exercise the actual PyPI installation as well as local adapter tests.
See [the recorded browser smoke test](VALIDATION.md).
