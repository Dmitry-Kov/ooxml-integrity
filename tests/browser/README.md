# Real browser checks

This suite runs the static demo in Chromium with actual Pyodide, Python,
fonts and package installation. It serves only the selected demo directory on
loopback port 8766. The server stops when Playwright finishes; an existing
server on that port is an error, so a run cannot accidentally test a stale site.

From the repository root, with Node 24+ and the Python development environment:

```sh
npm ci --prefix tests/browser
npm exec --prefix tests/browser -- playwright install chromium
npm test --prefix tests/browser
```

On Linux, use `playwright install --with-deps chromium` to install system
dependencies too. The npm lockfile pins Playwright and its Chromium build.
Startup needs network access to the pinned Pyodide CDN and PyPI. The release
suite serves `demo/` directly and verifies a download from files.pythonhosted.org.

To test a wheel built from the checkout:

```sh
python -m pip install build
python -m build --wheel
python research/prepare_browser_preview.py --wheel dist/ooxml_integrity-0.4.1-py3-none-any.whl
OOXML_DEMO_DIR="$PWD/tmp/browser-preview" npm test --prefix tests/browser
```

Use the actual wheel filename when its version changes. The generator reads
the wheel metadata, hashes the wheel and rewrites the install/version declarations
only in `tmp/browser-preview/worker.js`. Its `_preview.json` identifies the wheel.
It refuses to replace the public site, its parents or an unrelated directory.
The preview suite requires an actual local wheel download; it cannot silently
fall back to the installed release. The same procedure accepts the `0.4.1`
candidate during release preparation. It does not publish a package or change
the repository version.

Six scenarios run for both release and wheel:

- Clean DOCX, detached-comment/source pair and defective PPTX through the UI;
  human and JSON output, coverage off/on, Doctor, actual package/runtime
  versions, metric font substitutes, navigation and widths 1280px/390px.
- Same source/output filenames, removing and reselecting both inputs, corrupt
  DOCX, rejected extension, rejected PPTX/source pairing and successful recovery.
- Blocked runtime download, with a visible startup error and reload recovery.
- Blocked required font, with disabled checks and reload recovery.
- A runtime download delayed by four seconds. This models added latency on one
  startup dependency, not a whole-connection bandwidth profile or a benchmark.
- A busy interpreter terminated at the production 60-second deadline. A
  test-only intercepted bridge response spins in Python for `stalled.docx`.
  The UI must stay responsive, the real Worker must close, and checks must
  recover after reloading the unmodified bridge. No virtual clock, shortened
  timer or mocked Worker/checker results are used.

Reports live in `tmp/browser-results/release/` or `tmp/browser-results/wheel/`.
`browser-results.json` includes the Git commit, modified tracked files (for a
local run), page-file SHA-256 hashes, package source/version and preview wheel
hash. Attachments record the actual browser build, runtime footer, Doctor JSON,
package download URL, narrow-table screenshot and fault-injection timings.
Failures retain screenshots and Playwright traces. Only synthetic public inputs
are used. Save the results directory elsewhere before another run of that mode
if both records are needed.

The reusable [browser workflow](../../.github/workflows/browser.yml) runs on
relevant PRs and can be started manually. It checks the pinned release and a
newly built checkout wheel in separate jobs. The [Pages workflow](../../.github/workflows/pages.yml)
calls that same workflow and declares it as a dependency of deployment. It
uploads only `demo/`, never the preview directory. Both jobs are read-only;
Pages write permission and the environment are confined to the deployment job.
Receipts are uploaded as `browser-release-<sha>` and `browser-wheel-<sha>`.

This gate covers Chromium on Linux CI and the recorded local desktop runs.
It does not claim a Safari/Firefox gate, physical mobile-device coverage,
an exhaustive adverse-network test, visual Office rendering or malware scanning.
Final candidate artifacts and the public PyPI installation after a release
still need the checks in the [release procedure](../../docs/releasing.md).
