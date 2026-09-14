# adeu pilot: checker fixes and unresolved questions

Local follow-up, 14–15 September 2026. **Four mechanisms reproduced and fixed:**
legacy-stream output failure, comments-part name assumptions, whitespace false
alarms, and quadratic warning-location work. This is an unreleased checker
candidate on `fix/adeu-pilot-feedback`, based on `5aa06b7`; its package version
still reads 0.4.1. Published 0.4.1 does not contain these fixes.

## Question and evidence boundary

Can the checker produce a complete, useful report after adeu edits a DOCX?
Our [protocol](PROTOCOL.md) was recorded before changing the checker.

[Git-Uzair's external pilot report](https://github.com/dealfluence/adeu/pull/140#issuecomment-5661945776)
describes adeu 3.0.4 on Windows editing HUD Handbook 4000.1, revised 2025-11-26:
six successful tracked edits, nine Word revisions, one comment, no repair
prompt, about 144 seconds for the baseline check and 200 seconds for comparison.
It reports a 9.3 MB/3,556-part document and 258,568 baseline TXT001 warnings.
These are **participant observations**. The exact source/output pair, download
URL, hashes and edit commands were not attached; we have not repeated that run.
The source had no existing revisions/comments, so this pilot does not establish
preservation of an existing review trail.

Local probes use deterministic synthetic variants of `corpus/base.docx` on
macOS arm64, Python 3.9.6. The old checker is restored from `5aa06b7` without
changing the working tree. [Before](before.json), [candidate](after.json) and
[repeat](repeat.json) receipts retain the commands, stream settings, actual
imported checker location, per-source-file hashes and every fixture hash.
The script also generates the DOCX inputs locally; no editor/API is invoked.

## Results

| Local probe | Baseline checker | Candidate |
| --- | --- | --- |
| Unicode finding, redirected cp1252, human and JSON | All four runs truncate with UnicodeEncodeError and exit 1 | Complete output; default threshold exits 0, `--fail-on warn` exits 1; JSON restores Unicode exactly |
| Two intact comments moved to related `comments1.xml` | Two false CMT004 and two false FID004 | No findings; comment coverage includes both definitions |
| One body replaced in `comments1.xml`, counts retained | No FID004: real loss missed | One FID004, located in the actual source comments part |
| NBSP at both text edges | One TXT001 | None |
| Ordinary edge spaces, inherited preservation | One TXT001 | None |
| Ordinary edge spaces without preservation, or nearer `default` override | One TXT001 | One TXT001 |
| 4,000 paragraphs / 24,000 warnings | 0.379 s | 0.228 s; repeat 0.222 s |
| 16,000 paragraphs / 96,000 warnings | 5.767 s | 0.929 s; repeat 0.898 s |

Timings cover **only `check_whitespace` after XML loading, with cProfile**.
They are not end-to-end HUD timings. Original profiling put about 96% of this
rule's time in `_xpath`. Counting sibling positions once per parent removes
that repeated work. All 96,000 findings, including messages and paths, retain
identical hashes. No warning cap or severity reduction was used.

Comments now resolve through the main document's typed relationship, consistent
with the [SDK's main-part comments access](https://learn.microsoft.com/en-us/office/open-xml/word/how-to-insert-a-comment-into-a-word-processing-document).
Tests cover relative/absolute/escaped/case-equivalent names, misleading unlinked
conventional parts, missing definitions, malformed targets and ambiguous links.
New CMT006 ERROR explicitly reports failed comments resolution; an incomplete
comparison reports FID000 and skipped fidelity coverage. See
[compatibility](../../docs/compatibility.md) for gate and baseline effects.

The whitespace change follows [XML 1.0 whitespace and `xml:space` inheritance](https://www.w3.org/TR/xml/#sec-white-space):
ordinary space, tab, CR and LF differ from Unicode non-breaking/typographic
spaces. This supports the narrow synthetic fixes; it does not explain every HUD
warning or prove a specific Word rendering outcome. The legacy TXT001 message
says “will vanish”; treat that diagnostic as a risk heuristic, not a render result.

## Verification and reproduction

From the repository root with its development environment installed:

```sh
.venv/bin/python -m pytest tests/test_adeu_pilot_feedback.py tests/test_package_relationships.py -ra
.venv/bin/python research/adeu_pilot_probe.py --output tmp/pilot-current/results.json
.venv/bin/python research/adeu_pilot_probe.py --output tmp/pilot-repeat/results.json
mkdir -p tmp/pilot-before
git archive 5aa06b7 src/ooxml_integrity | tar -x -C tmp/pilot-before
PYTHONPATH=tmp/pilot-before/src .venv/bin/python research/adeu_pilot_probe.py --output tmp/pilot-before/results.json
.venv/bin/python research/build_docx_evidence.py evaluate
.venv/bin/python research/revision_evidence.py evaluate
.venv/bin/python research/replay_frozen_docx.py
.venv/bin/python -m pytest -ra
```

Generated `*-fixtures` directories contain the input documents. Fixture hashes
and finding hashes should match the receipts; local paths and timings will vary.
The actual imported checker hash inventory distinguishes the restored baseline
from the candidate. No network or editor is needed for these commands.

[Validation](validation.json): **919 passed, 7 font-condition skips**; separately,
10 historical-checker tests passed. The 220-pair corpus and 30 revision pairs
retain their expected findings; the two known seeded revision misses remain.
The original 220 pairs are not editor-comparison results. Re-evaluating 168
stored output pairs yields no change from the preceding FID001 fix; 45 attempts
without outputs remain unevaluated. No editor/model was rerun for that check.

Adding CMT006 changes the current rule inventory. Two additional tests that
assert old inventory receipts now use the existing archived-checker replay;
their exact assertions and old receipts remain intact. A separate current-checker
test checks all 30 revision-pair expectations and retains their known misses.

## Remaining decisions and limits

- **REV001 shared insertion/paragraph-mark ID remains unchanged.** The reported
  Word grouping is not the same case as the earlier adjacent-deletion study.
  We need the minimal XML or a shareable specimen and normative analysis before
  changing the collision rule. Word opening without repair alone is insufficient.
- The exact HUD warning population, complete runtime, six edits and Windows COM
  observations remain unverified locally. cp1252/ASCII stream tests are not a
  native Windows run. Existing CI is configured for Windows but was not triggered.
- Comments remain limited to the main story and ordinary comment bodies.
  Modern threads/people metadata and comments in other stories are not covered;
  footnote/endnote body lookup still uses conventional filenames. Count-neutral
  revision changes and visual identity remain outside these fixes.
- The reported FID002 paragraph-style addition is informational and expected
  for that split operation; no rule change was made.

Next external step, subject to the owner's decision: share a reviewed candidate
and request the public source URL plus SHA-256, exact six operations, and a
minimal output specimen for the paragraph-mark ID case. A Windows rerun should
retain complete JSON and separate ASCII-edge, Unicode-space and inherited-space
counts. No reply, publication, push or paid API call was made during this work.
