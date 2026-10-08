# 0.5.1 candidate validation

Candidate preparation for #64 (`FID013`, a tracked replacement wider than the
change), on main `064a902`. This record precedes publication; it does not
identify the later release archive hashes.
[Upgrade notes](../../../docs/releases/0.5.1.md) describe the addition and its
limits. Historical evidence/labels and current published demo bytes are
unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 2217 passed, 7 skipped: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. Python 3.14 gives the same result. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches; identical to the 0.5.0 candidate apart from the version. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. The recorded findings match; 80 `FID012` findings are the declared addition. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Anonymize measurement | Rerun on the candidate checkout; its printed summary equals the one in [evidence/anonymize](../../anonymize/README.md), 1,062 labelled pairs and 1,848 public documents with every finding reproduced and no leak reports. |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match; the 0.5.1 control passes: `FID013` reports a sentence replaced to change one word (7 unchanged words, 1 changed) and not a replaced phrase; the 0.5.0 anonymize control still passes. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel, on the third attempt: the first two timed out while Pyodide installed its dependencies from PyPI over a local route to PyPI's CDN of about 50 KB/s; the third ran over Cloudflare WARP. Public worker stays pinned to 0.5.0. |

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. The offline checks
ran with network access denied by `sandbox-exec`, as for 0.5.0. Private logs and
browser attachments remain under ignored tmp/release-0.5.1/ and tmp/browser-results/.

The completed PR and Release workflows rebuild the final tree and verify their
own exact archive hashes; do not equate local candidate hashes with published
files. The benchmark re-reading with `FID013` belongs to the change (#64), not
to these packaging runs. Published pins change only after public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.5.1-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.5.1-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python research/anonymize_eval.py --output tmp/new-0.5.1-anonymize.json
python -m build --outdir tmp/new-0.5.1-dist
python -m twine check --strict tmp/new-0.5.1-dist/*
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.5.1` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
