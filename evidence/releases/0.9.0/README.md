# 0.9.0 candidate validation

Candidate preparation for #114 (the package rules run on `.pptx` decks, each
message saying what PowerPoint does), #113 (a namespace name that is not a URI
is not malformed XML) and the evidence of #111 (PowerPoint's render of the
thin-box fixture) and #112 (docx-cli 0.28.0 in the post-release recheck), on
main `3098a90`; #115 and #116 update the browser-test and workflow
dependencies. This record precedes publication; it does not identify the later
release archive hashes. [Upgrade notes](../../../docs/releases/0.9.0.md)
describe the changes. Historical evidence/labels and current published demo
bytes are unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 2910 passed, 7 skipped: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. Python 3.14 gives the same result. |
| Suite from the sdist | 2882 passed, 35 skipped, run from the unpacked candidate sdist with its own `src/`: the extra skips are the demo, results-page and `fix` record tests, which read files the sdist does not ship. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches; identical to the 0.8.4 candidate apart from the version. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. The recorded findings equal the 0.8.4 candidate's apart from the checker version and source hashes. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Anonymize measurement | Rerun on the candidate checkout; its printed summary equals the one in [evidence/anonymize](../../anonymize/README.md). |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match and `py.typed` is installed; the 0.9.0 controls pass: on the reference deck an `xml` `Default` written twice is `PKG011` ERROR and a missing thumbnail a `REL002` WARN, and a SharePoint namespace name in a custom XML part is no finding. Each fails on 0.8.4. The 0.5.0 to 0.8.4 controls still pass. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel, with the locally installed Playwright 1.63.0; the PR's `Distributions` workflow runs the suite with the locked 1.64.1. Public worker stays pinned to 0.8.4. |

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. The offline checks
ran with network access denied by `sandbox-exec`, as for 0.8.4. Private logs and
browser attachments remain under ignored tmp/release-0.9.0/ and tmp/browser-results/.

The completed PR and Release workflows rebuild the final tree and verify their
own exact archive hashes; do not equate local candidate hashes with published
files. Published pins change only after public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.9.0-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.9.0-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python research/anonymize_eval.py --output tmp/new-0.9.0-anonymize.json
python -m build --outdir tmp/new-0.9.0-dist
python -m twine check --strict tmp/new-0.9.0-dist/*
mkdir tmp/new-0.9.0-sdist && tar -xzf tmp/new-0.9.0-dist/*.tar.gz -C tmp/new-0.9.0-sdist --strip-components=1
(cd tmp/new-0.9.0-sdist && PYTHONPATH="$PWD/src" python -m pytest -p no:cacheprovider)
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.9.0` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
