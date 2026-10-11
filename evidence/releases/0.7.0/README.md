# 0.7.0 candidate validation

Candidate preparation for #77 (`PKG010`), #78 and #80 (`fix` and its three
repairs) and #79 (the MCP server reads its config once; `py.typed`; Windows CI
on Python 3.9 and 3.14), on main `fa222c0`. This record precedes publication;
it does not identify the later release archive hashes.
[Upgrade notes](../../../docs/releases/0.7.0.md) describe the changes. Historical evidence/labels and current published demo
bytes are unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 2330 passed, 7 skipped: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. Python 3.14 gives the same result. |
| Suite from the sdist | 2302 passed, 35 skipped, run from the unpacked candidate sdist with its own `src/`: the extra skips are the demo, results-page and `fix` record tests, which read files the sdist does not ship. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches; identical to the 0.6.0 candidate apart from the version. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. The recorded findings match; 80 `FID012` findings are the declared addition. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Anonymize measurement | Rerun on the candidate checkout; its printed summary equals the one in [evidence/anonymize](../../anonymize/README.md). |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match and `py.typed` is installed; the 0.7.0 controls pass: the installed checker reports `PKG010` and `CMT005` on a Codex K5-S1 output, and the installed `fix` repairs both and writes a copy on which the checker finds nothing. The 0.5.0 to 0.6.0 controls still pass. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel. Public worker stays pinned to 0.6.0. |

The first run of the suite on this candidate failed one test, which compared
the checker version named in the `fix` record with the candidate's; this
preparation leaves that version out of the comparison, as it does the Python,
lxml and zlib versions, and both suites then passed. The failed logs are kept
under the ignored tmp/release-0.7.0/ as `pytest-attempt1` and
`pytest-py314-attempt1`.

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. The offline checks
ran with network access denied by `sandbox-exec`, as for 0.6.0. Private logs and
browser attachments remain under ignored tmp/release-0.7.0/ and tmp/browser-results/.

The completed PR and Release workflows rebuild the final tree and verify their
own exact archive hashes; do not equate local candidate hashes with published
files. Published pins change only after public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.7.0-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.7.0-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python research/anonymize_eval.py --output tmp/new-0.7.0-anonymize.json
python -m build --outdir tmp/new-0.7.0-dist
python -m twine check --strict tmp/new-0.7.0-dist/*
mkdir tmp/new-0.7.0-sdist && tar -xzf tmp/new-0.7.0-dist/*.tar.gz -C tmp/new-0.7.0-sdist --strip-components=1
(cd tmp/new-0.7.0-sdist && PYTHONPATH="$PWD/src" python -m pytest -p no:cacheprovider)
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.7.0` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
