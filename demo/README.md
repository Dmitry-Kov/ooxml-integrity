# Browser demo

[Open the demo](https://dmitry-kov.github.io/ooxml-integrity/).

The demo is also the project's landing page. It opens with the contract example,
then lets visitors check a file or run a bundled example. Further down are the
DOCX comparison results, PPTX measurement notes, installation examples and
limitations. The landing layout was added after the first browser smoke test in
commits `d77c797`, `19e81df` and `4747ea0`; those changes affected HTML and CSS.
The B1 revision separates the controlled mutation comparison from the eight
agent-run observations, qualifies the renderer/font measurements and links each
numerical comparison to its evidence. The side-by-side contract is an
illustration, not a Word screenshot. [The validation record](VALIDATION.md)
records the inspected HTML/CSS and desktop/narrow viewports.

The page uses plain CSS, JavaScript and a small Python adapter, with no framework
or build step. Document processing runs in the browser. GitHub Pages serves the
committed `demo/` directory. On relevant pushes to `main` or a manual run,
`.github/workflows/pages.yml` first requires both real-browser suites: the
pinned release and a separate preview of the checkout's wheel. Only then can
its deployment job run. A newer Pages run cancels a superseded run.

## What runs where

- A module Web Worker loads [Pyodide 314.0.6](https://pyodide.org/en/stable/usage/quickstart.html)
  from its official jsDelivr URL (latest stable verified 2026-09-06), then loads
  the built-in `lxml`, `fonttools` and `micropip` packages. `fonttools` is a pure
  Python wheel. Python 3.14 already includes `tomllib`, so it does not need `tomli`.
- `CHECKER_VERSION = "0.4.1"` in `worker.js` supplies the exact
  `ooxml-integrity==0.4.1` requirement to micropip. Startup verifies distribution
  and module versions before enabling checks; the footer shows the installed
  version. A new PyPI release does not change this demo automatically. Updating
  the pin requires the browser suites to pass with that version.
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
  JSON formatter. Report headings and JSON `files[].path` show only the filename,
  not the internal `input/` directory. Tests compare both representations with
  the CLI invoked using that filename; checking still uses separate input/source
  paths, including when both files have the same name.
  Doctor calls `cli.main(["doctor"])` and its JSON variant.

The page has no analytics, cookies, service worker or persistent document
storage. Startup requests go to **cdn.jsdelivr.net**, **pypi.org** and
**files.pythonhosted.org**. Page assets, fonts and example files download from
the same origin as the page; example buttons fetch their fixtures on demand.
External documentation is loaded only when a link is followed.

Checks themselves need no network. Loading the application does: the host and
CDNs receive ordinary web requests, and the tab executes Python code downloaded
from PyPI and the CDN.

## Font caveat

Calibri is measured with Carlito, Cambria with Caladea, Arial with Liberation
Sans, Times New Roman with Liberation Serif, and Courier New with Liberation
Mono. Regular, Bold, Italic and BoldItalic are bundled for each family. These
fonts provide metric-compatible substitutes; they do not reproduce Microsoft's
fonts or Office rendering. Coverage labels substituted measurements `estimated`,
and unknown fonts use a lower-confidence fallback. Doctor reports which checks
the environment can run. See [font sources and licenses](fonts/README.md) and the
[project's limitations](https://github.com/Dmitry-Kov/ooxml-integrity#limitations).

## Examples

| Button | Committed copy | Expected result |
| --- | --- | --- |
| A clean document | `corpus/base.docx` → `examples/base.docx` | No findings; coverage states its limits |
| A deck with text that does not fit | `corpus/deck.pptx` → `examples/deck.pptx` | Overflow, off-canvas and overlap findings |
| A detached comment, with its original | `runs/t4_fast_fee/agreement.docx` → `examples/agreement.docx`, with `base.docx` | **CMT005** orphaned comment and **FID001** lost anchor |

All three are synthetic public fixtures, copied byte-for-byte. Comparison is
DOCX-only, and selecting a PPTX with a source produces an error. Unsupported
extensions, unreadable packages and Python exceptions appear in the output
panel. These errors use JSON of the form `{ "error": "…" }`. Completed checks
retain the normal CLI result format and exit codes (0/1).
The interactive fidelity example uses the fee-edit output. The recorded Word
comparison behind the hero illustration uses the separate table-edit pair,
`t2_pres` / `t4_fast_table`, identified in [the run notes](../runs/README.md).

Files are capped at 25 MiB each and checks at 60 seconds to keep the browser
responsive. A timed-out worker is terminated; reload the page to restart it.
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
elapsed time are visible. The startup target is about 20 seconds on broadband;
the actual time depends on the connection and device. Fonts download while the
runtime initializes, and browser caching speeds up repeat visits.

From the repository's development environment:

```sh
python -m pytest tests/test_browser_demo.py
node --check demo/app.js
node --check demo/worker.js
```

The [browser suite](../tests/browser/README.md) runs real Pyodide in Chromium,
installs the exact public package, and tests the examples, uploads, JSON/coverage,
Doctor, startup failures, delayed downloads and the real 60-second termination
path. It also runs against a built wheel using an isolated generated preview.
The public worker has no URL, local-storage or message override for its package.
The preview generator changes only a copy under `tmp/`; Pages always uploads
the committed `demo/` directory.

The static demo and browser test dependencies are not included in the PyPI
distribution. Adapter and preview tests skip when run from an sdist without
`demo/`. See [the validation record](VALIDATION.md) for the browser runs,
versions, exact page hashes and test limits.
