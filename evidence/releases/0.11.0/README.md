# 0.11.0 candidate validation

Candidate preparation for #125 to #140 on main `b92b84e`: reports that no
longer replace a file the run reads (#129, #133, #136, #139), a Word text box
read from its first `mc:AlternateContent` branch in `check`, `fix`, coverage
and the comparison (#131, #134, #135, #137, #140), `FID000` kept out of
baselines (#130), `FTN002` for an ordinary footnote numbered 0 (#138), no false
`PPT006` on Two Content slides (#132), the Action's threshold and exit code
(#133), the pre-commit hook and type checking (#126), and documentation and
agent instructions (#125, #127, #128). This record precedes publication; it
does not identify the later release archive hashes.
[Upgrade notes](../../../docs/releases/0.11.0.md) describe the changes.
Historical evidence/labels and current published demo bytes are unchanged.

| Check | Result |
| --- | --- |
| Full Python suite | 3207 passed, 7 skipped on Python 3.12: one optional macOS agent runtime unavailable; six missing-font cases skip because those fonts are installed. |
| Python 3.14 | **Not run locally.** The preparing machine has no Python 3.14 interpreter, as for 0.10.0. The pull request's CI matrix runs the suite on 3.9 to 3.14. |
| Suite from the sdist | 3105 passed, 109 skipped, run from the unpacked candidate sdist with its own `src/`. The 35 skips of 0.10.0 remain; the 74 new ones are the agent guard hook tests of #127, which read a hook the sdist does not ship. |
| Lint and types | `ruff check .` passes; `mypy` with the versions CI pins (2.4.1, `lxml-stubs` 0.5.1) finds no issue in 31 source files. |
| Producer corpus | 50 sources / 220 pairs, zero label mismatches; identical to the 0.10.0 candidate apart from the version. |
| Revision and saved outputs | 30 revision pairs and 168 stored output pairs pass the current declaration; 45 attempts without DOCX remain unevaluated. The recorded findings equal the 0.10.0 candidate's apart from the checker version, source hashes and platform string. |
| Frozen checker | 16 passed, 122 deselected; historical checker/hash contracts unchanged. |
| Comment-story pairs | 4 pairs, 3 TP, 0 FP, 0 FN. |
| Reference PPTX | Exactly the 11 expected findings with available local fonts. |
| Anonymize measurement | Rerun on the candidate checkout, with the public corpora at their pinned commits; its printed summary equals the one the 0.10.0 record holds. |
| Public corpora, 0.10.0 against 0.11.0 | New: 2,497 files (1,887 DOCX, 610 decks), 419 of them with `mc:AlternateContent` (294 DOCX). No DOCX changes its findings. Five decks do, all through the `PPT006` correction: 16 findings are gone and one `PPT001` ERROR is new (below). No crash in either version. [Record](public-corpora.json). |
| Wheel and sdist | Wheel built from sdist; strict Twine validation and both fresh installations pass. Source bytes match and `py.typed` is installed; the 0.11.0 controls pass (below). The 0.5.0 to 0.10.0 controls still pass. |
| Real Chromium/Pyodide wheel preview | 7 passed, 0 skipped against the recorded local wheel, downloaded from the isolated preview, with the locked Playwright 1.64.1 and Chromium 156.0.8078.4. The observed footer was **ooxml-integrity 0.11.0 · Pyodide 314.0.6**. Public worker stays pinned to 0.10.0; `demo/` is unchanged by the preview generator. |

The 0.11.0 controls of the installed-package smoke, on variants of the
reference document:

- Comment 2's paragraph in a text box written twice, as Word writes one: clean
  with the reference in both copies; `CMT003` and `CMT005` ERROR with the
  reference only in `mc:Fallback`.
- Against a source with the reference only in `mc:Choice`, that edit is
  `FID001` ERROR. Dropping only the fallback copy gives warnings only, and the
  default gate passes.
- Note 1 renumbered 0, the continuation separator 1: clean with its
  reference, `FTN002` ERROR without it.
- `--sarif` over the `--baseline` file, over an existing `.docx` outside the
  run and over a hard link to it: exit 2, each file unchanged.
- `corpus/deck.pptx` checked against itself: `--write-baseline` leaves
  `FID000` out with a warning, and the run with that baseline fails on it.

On 0.10.0, installed from public PyPI in a fresh environment, the same inputs
give no finding for the text box and the footnote (exit 0), no finding for the
moved reference, `FID001` and `FID003` ERROR for the dropped fallback copy
(exit 1), exit 0 with the baseline, the document and the linked document each
replaced by SARIF, and exit 0 for the deck with `FID000` accepted by the
baseline.

The one new finding on the public corpora is `PPT001` ERROR in LibreOffice's
`sd/qa/unit/data/pptx/bnc870233_1.pptx`: "text needs 35pt in a 15pt box".
0.10.0 gave both text placeholders of its slide the same geometry and reported
them as overlapping (`PPT006` ERROR); 0.11.0 gives the second one the 15pt
layout box of its own `idx`. Whether PowerPoint shows that text overflowing
was not checked.

[validation.json](validation.json) records commands, versions, durations, log
hashes, local archive hashes and browser metadata; [producer](docx-beta.json),
[revision](revisions.json) and [public corpora](public-corpora.json) receipts
retain independent scopes. The offline checks ran with network access denied
by `sandbox-exec`, as for 0.10.0; the build, the two installations, the public
corpora fetch and the browser suite need the network. The Python environment
was outside the checkout (`$VENV` in the record) and the checks ran in a Git
worktree of the repository. Private logs and browser attachments remained
under ignored `tmp/release-0.11.0/` and `tmp/browser-results/` of that
worktree. None of the 4,464 tracked files under `evidence/` and no file of
`demo/` was modified.

The public corpora comparison calls `check()` for each `.docx` and
`check_pptx()` for each `.pptx`, `.potx` and `.ppsx` under the clones that
`python research/realworld_scan.py fetch` makes, once with 0.10.0 from PyPI and
once with this checkout, and compares code, severity, part, location and
message per file. A file counts as having `mc:AlternateContent` when one of
its XML parts contains that name.

The local wheel does not depend on this record: built again from the committed
tree it has the same SHA-256. The sdist ships `evidence/` and `docs/`, so its
local hash is that of the tree before this record and the final notes were
written. The completed PR and Release workflows rebuild the final tree and
verify their own exact archive hashes; do not equate local candidate hashes
with published files. Published pins change only after public PyPI smoke.

Reproduce using fresh output paths:

```sh
python -m pytest -ra
python research/build_docx_evidence.py evaluate --output tmp/new-0.11.0-corpus.json
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-0.11.0-revisions.json
python research/replay_frozen_docx.py
python research/comment_story_evidence.py evaluate
python research/assert_deck.py corpus/deck.pptx
python research/realworld_scan.py fetch ../ooxml-corpora
python research/anonymize_eval.py --corpora ../ooxml-corpora --output tmp/new-0.11.0-anonymize.json
python -m build --outdir tmp/new-0.11.0-dist
python -m twine check --strict tmp/new-0.11.0-dist/*
mkdir tmp/new-0.11.0-sdist && tar -xzf tmp/new-0.11.0-dist/*.tar.gz -C tmp/new-0.11.0-sdist --strip-components=1
(cd tmp/new-0.11.0-sdist && PYTHONPATH="$PWD/src" python -m pytest -p no:cacheprovider)
```

Install each archive in a fresh environment and run
`python research/release_smoke.py --version 0.11.0` from the repository root.
Follow [browser instructions](../../../tests/browser/README.md) with that wheel
and a separate preview directory; preserve prior results before rerunning.
