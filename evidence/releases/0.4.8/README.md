# 0.4.8 candidate validation

Candidate preparation for #51 (declared expected changes and `EXP001`) and #52
(the benchmark results page), on main `366b471`. This record precedes
publication; it does not identify the later release archive hashes.
[Upgrade notes](../../../docs/releases/0.4.8.md) describe the addition and its
limits. Historical evidence/labels and current published demo bytes are unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 2172 passed, 7 skipped: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. Python 3.14.7 gives the same result. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches; identical to the 0.4.7 candidate apart from the version. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. Output identical to the 0.4.7 candidate. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match; the 0.4.8 controls pass: a requested accept/reject fails without expectations and passes with them from the command line, a config file and the Python API, and a wrong expectation fails with `EXP001`. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel, on the second run. The first run passed 6: one scenario's Pyodide startup could not fetch the Python standard library from the CDN. Public worker stays pinned to 0.4.7. |

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. The offline checks
ran with network access denied by `sandbox-exec`, as for 0.4.7. Private logs and
browser attachments remain under ignored tmp/release-0.4.8/ and tmp/browser-results/.

The completed PR and Release workflows rebuild the final tree and verify their
own exact archive hashes; do not equate local candidate hashes with published
files. The benchmark re-reading with expectations belongs to the change (#51),
not to these packaging runs. This is not a new benchmark, general recall
estimate or Windows native review. Published pins change only after public
PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.4.8-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.4.8-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python -m build --outdir tmp/new-0.4.8-dist
python -m twine check --strict tmp/new-0.4.8-dist/*
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.4.8` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
