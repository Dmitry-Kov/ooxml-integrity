# 0.4.7 candidate validation

Candidate preparation for #40 (tracked edits next to pending revisions), #43
(`TXT002`, `FID011`) and #46 (`INT001` as an ERROR), on main `6f5ca8d`. This
record precedes publication; it does not identify the later release archive
hashes. [Upgrade notes](../../../docs/releases/0.4.7.md) describe gate changes and
limits. Historical evidence/labels and current published demo bytes are unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 2147 passed, 7 skipped: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. Python 3.14.7 gives the same result. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches; identical to the 0.4.6 candidate apart from the version. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. Output identical to the 0.4.6 candidate. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match; the 0.4.7 controls pass: a tracked header edit next to a pending revision, an escaped bullet label (`TXT002`), words added inside another author's insertion (`FID011`) and a check that raises (`INT001`). |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel. Public worker stays pinned to 0.4.6. |

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. The offline checks
ran with network access denied by `sandbox-exec`, as for 0.4.6. Private logs and
browser attachments remain under ignored tmp/release-0.4.7/ and tmp/browser-results/.

The completed PR and Release workflows rebuild the final tree and verify their
own exact archive hashes; do not equate local candidate hashes with published
files. The benchmark captures and the Word for Mac check belong to the changes
(#40, #43), not to these packaging runs. This is not a new benchmark, general
recall estimate or Windows native review. Published pins change only after
public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.4.7-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.4.7-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python -m build --outdir tmp/new-0.4.7-dist
python -m twine check --strict tmp/new-0.4.7-dist/*
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.4.7` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
