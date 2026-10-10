# 0.6.0 candidate validation

Candidate preparation for #74 (`ooxml-integrity mcp`, a local MCP server that
serves `check` and `compare` to an agent), on main `89c4287`. This record
precedes publication; it does not identify the later release archive hashes.
[Upgrade notes](../../../docs/releases/0.6.0.md) describe the change. Historical evidence/labels and current published demo
bytes are unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 2255 passed, 7 skipped: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. Python 3.14 gives the same result. |
| Suite from the sdist | 2228 passed, 34 skipped, run from the unpacked candidate sdist with its own `src/`: the extra skips are the demo and results-page tests, whose files the sdist does not ship. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches; identical to the 0.5.3 candidate apart from the version. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. The recorded findings match; 80 `FID012` findings are the declared addition. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Anonymize measurement | Rerun on the candidate checkout; its printed summary equals the one in [evidence/anonymize](../../anonymize/README.md). |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match; the 0.6.0 control passes: the installed `ooxml-integrity mcp` answers over stdio, its `compare` result carries the report the CLI prints for the same pair, and a URL is refused. The 0.5.0 to 0.5.2 controls still pass. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel. Public worker stays pinned to 0.5.3. |

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. The offline checks
ran with network access denied by `sandbox-exec`, as for 0.5.3. Private logs and
browser attachments remain under ignored tmp/release-0.6.0/ and tmp/browser-results/.

The completed PR and Release workflows rebuild the final tree and verify their
own exact archive hashes; do not equate local candidate hashes with published
files. Published pins change only after public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.6.0-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.6.0-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python research/anonymize_eval.py --output tmp/new-0.6.0-anonymize.json
python -m build --outdir tmp/new-0.6.0-dist
python -m twine check --strict tmp/new-0.6.0-dist/*
mkdir tmp/new-0.6.0-sdist && tar -xzf tmp/new-0.6.0-dist/*.tar.gz -C tmp/new-0.6.0-sdist --strip-components=1
(cd tmp/new-0.6.0-sdist && PYTHONPATH="$PWD/src" python -m pytest -p no:cacheprovider)
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.6.0` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
