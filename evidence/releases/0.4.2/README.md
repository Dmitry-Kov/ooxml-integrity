# 0.4.2 candidate validation

Local validation on 2026-09-15 (Asia/Tashkent), from `main` at `559a9cd` plus
the release-preparation changes. This is a candidate, not a published release.
Only the package version changes in production Python code; the checker fixes
were already merged. [Upgrade notes](../../../docs/releases/0.4.2.md) describe
their CI effects, compatibility and known gaps.

## Recorded checks

| Check | Local result |
| --- | --- |
| Full Python suite, Python 3.9.6 | 982 passed, 7 skipped: seven missing-font cases skip because those fonts are installed. |
| Historical checker replay | 16 passed, with archived checker source/hash validation; old receipts unchanged. |
| Original producer corpus | [220 pairs / 50 sources](docx-beta.json), zero label mismatches. Of these, 120 clean controls and 100 seeded-defect pairs; 111 ERROR findings TP, 0 FP/FN in this fixed set. |
| Existing revision corpus | [30 pairs](revisions.json): 9/9 seeded defects detected; 15 adeu/Word review-content controls without ERROR/WARN; 6 accept/reject characterizations remain 5 correct, 1 incorrect and are excluded from preservation metrics. |
| Saved benchmark/Word outputs | All 168 retain their previous finding multisets. The 45 recorded attempts without an output remain unevaluated. |
| Reference PPTX | Exactly the 11 expected findings, using installed Calibri for measurement. |
| Distribution metadata and fresh installations | Both wheel and sdist pass strict Twine validation and the installed-package smoke. The wheel is built from the sdist. Installed Python file inventories and bytes match the checkout. |
| Real Chromium/Pyodide wheel preview | All 7 scenarios passed, including startup failures, voluntary feedback, delayed loading and actual 60-second worker termination/recovery. |
| Historical file preservation | All 1565 pre-existing tracked evidence/corpus files and the public demo worker retain their SHA-256 hashes. |

[validation.json](validation.json) records tool/dependency versions, commands,
local archive hashes, source provenance and the real browser results. Full local
logs and browser attachments are under ignored `tmp/release-0.4.2/`. These local
development archives precede the completed validation write-up; the PR's
Distributions workflow rebuilds the final tree and records its own artifact
hashes. Local and CI archive hashes must not be conflated.

The original corpus, revision labels and historical metrics are immutable.
The published-metrics equality test now replays the archived checker; all other
corpus semantic/hash/label tests still evaluate the current checker. The new
`evaluate --output` option records a fresh result and refuses to overwrite an
existing file. No oracle, detection rule or expected defect was changed to
make this candidate pass.

## Reproduce

Run from the repository root with the documented editable dev installation
and the fonts in [CONTRIBUTING](../../../CONTRIBUTING.md). Use a fresh destination
for receipts; no Office application or model run is needed:

```sh
mkdir -p tmp/recheck-0.4.2
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/recheck-0.4.2/docx-beta.json
python research/review_revision_text.py --evidence-dir evidence/docx-note-revisions --saved-outputs --output tmp/recheck-0.4.2/revisions.json
python research/replay_frozen_docx.py
python research/assert_deck.py corpus/deck.pptx
```

For the distributions, these commands match the local method (Python 3.12.13).
`build` 1.6.1, Hatchling 1.32.0 and the remaining observed versions are in the
validation receipt. `python -m build` without `--wheel` first builds the sdist,
then builds the wheel from it:

```sh
python3.12 -m venv tmp/recheck-0.4.2/build-env
tmp/recheck-0.4.2/build-env/bin/python -m pip install build twine
tmp/recheck-0.4.2/build-env/bin/python -m build --outdir tmp/recheck-0.4.2/dist
tmp/recheck-0.4.2/build-env/bin/python -m twine check --strict tmp/recheck-0.4.2/dist/*
python3.12 -m venv tmp/recheck-0.4.2/wheel-env
tmp/recheck-0.4.2/wheel-env/bin/python -m pip install tmp/recheck-0.4.2/dist/ooxml_integrity-0.4.2-py3-none-any.whl
tmp/recheck-0.4.2/wheel-env/bin/python research/release_smoke.py --version 0.4.2
python3.12 -m venv tmp/recheck-0.4.2/sdist-env
tmp/recheck-0.4.2/sdist-env/bin/python -m pip install tmp/recheck-0.4.2/dist/ooxml_integrity-0.4.2.tar.gz
tmp/recheck-0.4.2/sdist-env/bin/python research/release_smoke.py --version 0.4.2
```

The smoke checks both entry points, 0/1/2 exits, JSON/coverage, FID009/FID010,
baseline v2 and v1 rejection, new-file regression, SARIF, TOML policy and archive
limits. It must run from this release checkout with the installed environment's
Python. Version equality alone is insufficient: all installed Python sources
must match.

For Chromium/Pyodide, first preserve any previous `tmp/browser-results/wheel/`
directory; the suite replaces that mode's results. Install the browser suite
using its lockfile and follow its [runtime requirements](../../../tests/browser/README.md):

```sh
npm ci --prefix tests/browser
npm exec --prefix tests/browser -- playwright install chromium
python research/prepare_browser_preview.py --wheel tmp/recheck-0.4.2/dist/ooxml_integrity-0.4.2-py3-none-any.whl --output tmp/recheck-0.4.2/browser-preview
OOXML_DEMO_DIR="$PWD/tmp/recheck-0.4.2/browser-preview" npm test --prefix tests/browser
```

## Limits and remaining release gates

The corpus checks are evaluations of saved files, not new editor comparisons.
The 9/9 number covers nine injected defects, not general recall or an editor
ranking. Denominators partly overlap and must not be added. No new agent,
Ollama, Word or adeu execution, document upload, or paid API call occurred.
Browser runtime/font failures and the 60-second deadline are injected test
conditions, not measured real-world failure rates. Visual Office fidelity and
the documented FID009/FID010 identity/presence gaps remain unverified here.

PR checks must pass, then CI must pass on the exact merged `main` commit before
tagging. The still-uncreated public Action tag, PyPI publication, fresh public
PyPI installation/hash verification and a later demo-pin update are separate
steps under the [release procedure](../../../docs/releasing.md). This candidate
does not perform or claim those steps. Public consumer/demo pins remain 0.4.1.
