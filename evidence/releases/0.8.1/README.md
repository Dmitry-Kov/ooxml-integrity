# 0.8.1 candidate validation

Candidate preparation for the fixes of an external review of 0.8.0: #90 (run
content read alike by the text rules, segment-wise globs, the `FID014`
recipe), #91 (`fix` refusing non-unique repairs, publishing without replacing)
and #92 (four `anonymize` security defects), on main `8b33d45`. This record
precedes publication; it does not identify the later release archive hashes.
[Upgrade notes](../../../docs/releases/0.8.1.md) describe the changes. Historical evidence/labels and current published demo
bytes are unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 2659 passed, 7 skipped: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. Python 3.14 gives the same result. |
| Suite from the sdist | 2631 passed, 35 skipped, run from the unpacked candidate sdist with its own `src/`: the extra skips are the demo, results-page and `fix` record tests, which read files the sdist does not ship. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches; identical to the 0.8.0 candidate apart from the version. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. The recorded findings match; 80 `FID012` and 95 `FID014` findings are the declared additions. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Anonymize measurement | Rerun on the candidate checkout; its printed summary equals the one in [evidence/anonymize](../../anonymize/README.md). |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match and `py.typed` is installed; the 0.8.1 controls pass: `anonymize` refuses an output that is its input and leaves the input unchanged, and replaces a firm's attribute value on a Word element; `fix` refuses a part whose root contradicts its relationship; `FID014` reads a non-breaking hyphen; `**` spans whole segments. The 0.5.0 to 0.8.0 controls still pass. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel. Public worker stays pinned to 0.8.0. |

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. The offline checks
ran with network access denied by `sandbox-exec`, as for 0.8.0. Private logs and
browser attachments remain under ignored tmp/release-0.8.1/ and tmp/browser-results/.

The completed PR and Release workflows rebuild the final tree and verify their
own exact archive hashes; do not equate local candidate hashes with published
files. Published pins change only after public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.8.1-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.8.1-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python research/anonymize_eval.py --output tmp/new-0.8.1-anonymize.json
python -m build --outdir tmp/new-0.8.1-dist
python -m twine check --strict tmp/new-0.8.1-dist/*
mkdir tmp/new-0.8.1-sdist && tar -xzf tmp/new-0.8.1-dist/*.tar.gz -C tmp/new-0.8.1-sdist --strip-components=1
(cd tmp/new-0.8.1-sdist && PYTHONPATH="$PWD/src" python -m pytest -p no:cacheprovider)
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.8.1` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
