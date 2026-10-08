# 0.5.2 candidate validation

Candidate preparation for #67 (`anonymize` replaces a firm's own schema
names), on main `9f821ac`. This record precedes publication; it does not
identify the later release archive hashes.
[Upgrade notes](../../../docs/releases/0.5.2.md) describe the change and its
limits. Historical evidence/labels and current published demo bytes are
unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 2221 passed, 7 skipped: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. Python 3.14 gives the same result. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches; identical to the 0.5.1 candidate apart from the version. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. The recorded findings match; 80 `FID012` findings are the declared addition. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Anonymize measurement | Rerun on the candidate checkout; its printed summary equals the one in [evidence/anonymize](../../anonymize/README.md), 1,062 labelled pairs and 1,848 public documents with every finding reproduced and no leak reports. |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match; the 0.5.2 control passes: the installed command anonymizes a template with a firm's custom XML schema, replaces its namespace, element names and binding path consistently and keeps the binding resolvable; the 0.5.0 and 0.5.1 controls still pass. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel. Public worker stays pinned to 0.5.1. |

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. The offline checks
ran with network access denied by `sandbox-exec`, as for 0.5.1. Private logs and
browser attachments remain under ignored tmp/release-0.5.2/ and tmp/browser-results/.

The completed PR and Release workflows rebuild the final tree and verify their
own exact archive hashes; do not equate local candidate hashes with published
files. The anonymize measurement and the security review belong to the change
(#67), not to these packaging runs. Published pins change only after public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.5.2-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.5.2-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python research/anonymize_eval.py --output tmp/new-0.5.2-anonymize.json
python -m build --outdir tmp/new-0.5.2-dist
python -m twine check --strict tmp/new-0.5.2-dist/*
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.5.2` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
