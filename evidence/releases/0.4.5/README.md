# 0.4.5 candidate validation

Candidate preparation for the corrections merged in #30–#33 and the Python 3.14
CI addition, on `5efc8a1` (main `92924a3` plus that commit). This record
precedes publication; it does not identify the later release archive hashes.
[Upgrade notes](../../../docs/releases/0.4.5.md) describe gate changes and
limits. Historical evidence/labels and current published demo bytes are unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 1102 passed, 7 skipped: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. Python 3.14.7 gives the same result. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match, including the STY002 `next`/`basedOn`, XML001 depth-limit and FID003 tracked-deletion smoke cases. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel. Public worker stays pinned to 0.4.4. |

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. The offline checks
ran with network access denied by `sandbox-exec`, as for 0.4.4. Private logs and
browser attachments remain under ignored tmp/release-0.4.5/ and tmp/browser-results/.

The completed PR and Release workflows rebuild the final tree and verify their
own exact archive hashes; do not equate local candidate hashes with published
files. The adeu scenario outputs belong to the FID003 correction (#33), not to
these packaging runs. This is not a new benchmark, general recall estimate or
Windows native review. Published pins change only after public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.4.5-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.4.5-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python -m build --outdir tmp/new-0.4.5-dist
python -m twine check --strict tmp/new-0.4.5-dist/*
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.4.5` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
