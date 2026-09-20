# 0.4.3 candidate validation

Candidate preparation for the scoped REV001 correction, following merged PR #20.
This record precedes publication; it does not identify the later release archive
hashes. [Upgrade notes](../../../docs/releases/0.4.3.md) describe gate changes and
limits. Historical evidence/labels and current published demo bytes are unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 1046 passed, 7 skipped: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration. Exactly 80 FID002 and 10 REV001 message replacements affect 40 saved pairs; all substantive fields are unchanged. 45 attempts without DOCX remain unevaluated. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match, including the REV001 pair and third-occurrence smoke cases. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel. Public worker stays pinned to 0.4.2. |

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. Private logs and
browser attachments remain under ignored tmp/release-0.4.3/. The first browser
launch used a nonexistent npm path and failed before executing tests; the corrected
launch used installed npm and bundled Node 24 against the same wheel.

The completed PR and Release workflows rebuild the final tree and verify their
own exact archive hashes; do not equate local candidate hashes with published
files. Native Word/SDK evidence belongs to the preceding correction, not these
packaging runs. This is not a new benchmark, general recall estimate or Windows
native review certification. Published pins change only after public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.4.3-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.4.3-revisions.json
python research/replay_frozen_docx.py
python research/assert_deck.py corpus/deck.pptx
python -m build --outdir tmp/new-0.4.3-dist
python -m twine check --strict tmp/new-0.4.3-dist/*
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.4.3` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
