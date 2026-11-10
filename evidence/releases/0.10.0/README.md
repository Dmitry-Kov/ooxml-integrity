# 0.10.0 candidate validation

Candidate preparation for #119 (`--introduced`: fail only on findings the edit
introduced), #120 (`CMT007`: a comment id marked more than once in a story),
#121 (`server.json` and the `mcp-name` line for MCP catalogs) and #122
(`FID015` and `FID016` for bookmarks and fields lost against a source, endnote
references and section breaks in `FID001`/`FID002`), on main `4ae7df9`. This
record precedes publication; it does not identify the later release archive
hashes. [Upgrade notes](../../../docs/releases/0.10.0.md) describe the changes.
Historical evidence/labels and current published demo bytes are unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 2993 passed, 7 skipped on Python 3.12: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. |
| Python 3.14 | **Not run locally.** The preparing machine has no Python 3.14 interpreter, so the second local run of the 0.9.0 record is missing here. The pull request's CI matrix runs the suite on 3.9 to 3.14. |
| Suite from the sdist | 2965 passed, 35 skipped, run from the unpacked candidate sdist with its own `src/`: the extra skips are the demo, results-page and `fix` record tests, which read files the sdist does not ship. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches; identical to the 0.9.0 candidate apart from the version. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. The recorded findings equal the 0.9.0 candidate's apart from the checker version, source hashes, platform and Python version. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Expected finding multiset passes with available local fonts. |
| Anonymize measurement | Rerun on the candidate checkout, with the public corpora at their pinned commits; its printed summary equals the one in [evidence/anonymize](../../anonymize/README.md). |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match and `py.typed` is installed; the 0.10.0 controls pass (below). The 0.5.0 to 0.9.0 controls still pass. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel, downloaded from the isolated preview, with the locked Playwright 1.64.1 and Chromium 156.0.8078.4. The observed footer was **ooxml-integrity 0.10.0 · Pyodide 314.0.6**. Public worker stays pinned to 0.9.0; `demo/` is unchanged by the preview generator. |

The 0.10.0 controls of the installed-package smoke:

- `CMT007` ERROR on the reference document with the range end and the
  reference of one comment written twice.
- `--introduced` on a copy of a source that already has that repeat: exit 0,
  the finding suppressed with `already in the source (--introduced)` and
  `"introduced": true` in the report; exit 1 without the flag. A repeat the
  edit made, a second one beside the source's, and the lost content of the
  reference edit (`CMT005`, `FID001`) are still reported. Without `--against`
  the flag exits 2. `introduced()` and the MCP `compare` tool with
  `"introduced": true` return the same.
- `FID015` ERROR when the bookmark under a `REF` field is gone, and `FID016`
  ERROR when the field is written as text, with `--introduced` setting neither
  aside and `--expect FID016:story=document,kind=REF` accepting the second.

On 0.9.0, installed from public PyPI in a fresh environment, the same inputs
give no `CMT007`, no `FID015` and no `FID016` (exit 0), and `--introduced` is
an unrecognized argument.

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json) and
[revision](revisions.json) receipts retain independent scopes. The offline checks
ran with network access denied by `sandbox-exec`, as for 0.9.0; the build, the
two installations and the browser suite need the network. The Python
environment was outside the checkout (`$VENV` in the record) and the checks ran
in a Git worktree of the repository. Private logs and browser attachments
remained under ignored tmp/release-0.10.0/ and tmp/browser-results/ of that
worktree. None of the 4,458 tracked files under `evidence/` and no file of
`demo/` was modified.

The local wheel does not depend on this record: built again from the committed
tree it has the same SHA-256. The sdist ships `evidence/` and `docs/`, so its
local hash is that of the tree before this record and the final notes were
written. The completed PR and Release workflows rebuild the final tree and
verify their own exact archive hashes; do not equate local candidate hashes
with published files. Published pins change only after public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.10.0-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.10.0-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python research/anonymize_eval.py --output tmp/new-0.10.0-anonymize.json
python -m build --outdir tmp/new-0.10.0-dist
python -m twine check --strict tmp/new-0.10.0-dist/*
mkdir tmp/new-0.10.0-sdist && tar -xzf tmp/new-0.10.0-dist/*.tar.gz -C tmp/new-0.10.0-sdist --strip-components=1
(cd tmp/new-0.10.0-sdist && PYTHONPATH="$PWD/src" python -m pytest -p no:cacheprovider)
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.10.0` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
