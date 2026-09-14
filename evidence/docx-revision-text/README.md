# Missing revision text with unchanged counts

The unreleased checker detects the existing seeded `optional` → `invented`
substitution as **FID009 ERROR**. The original insertion wording disappears,
but its XML wrapper count stays unchanged. The default CLI now exits 1 for
this pair; baseline commit `83a773c` exited 0. No editor or model was rerun.

## Method and results

The [protocol](PROTOCOL.md) was declared before changing the checker. We reuse
the five synthetic revision sources, unchanged stored outputs and independent
XML oracle. [expectations.json](expectations.json) permits exactly one new
finding in the 30-pair corpus. Original labels, captures and metrics remain
unchanged; [baseline.json](baseline.json) and [candidate.json](candidate.json)
record both evaluations with input/output hashes, imported checker source hashes,
Python/lxml/platform versions and protocol/evaluator hashes.

| Evidence rechecked locally | Baseline | Candidate |
| --- | --- | --- |
| Recorded seeded main-document substitution | Missed | FID009 ERROR |
| Recorded seeded footnote revision unwrapping | Missed | Still missed |
| All 9 seeded defects, document-pair denominator | 7 detected, 2 missed | 8 detected, 1 missed |
| 15 adeu/Word review-content controls in revision corpus | No ERROR/WARN | No ERROR/WARN |
| 6 accept/reject characterizations | 5 correct tasks, 1 incorrect; excluded from preservation metrics | Same tasks and findings |
| 168 saved benchmark/Word output pairs | Prior merged-checker findings | Identical findings on every pair |
| 45 saved agent attempts without an output | Unevaluated | Still unevaluated |
| Original 220-pair producer corpus | Historical regression labels | Zero label mismatches |

These are separate, partly overlapping checks, not a combined accuracy score.
The 8/9 result measures deliberately injected defects, not editor quality or
real-world defect prevalence. The 168-pair check retains existing failure and
REV001 results as well as clean outputs. It includes all three saved Word
coalescence controls; none gains an ERROR/WARN. Old editor/model receipts and
their requested-edit verdicts are not rewritten.

The new tests also complete `EDITBEFORE` → `EDITAFTER` while independently
injecting either known defect. The oracle still distinguishes successful task
completion from unrelated loss: FID009 detects the insertion substitution;
the note loss stays a false negative. New tests are synthetic fault injection,
not additional editor captures or visual observations.

## Scope and remaining gaps

FID009 compares insertions and deletions separately in `word/document.xml`,
only at equal, nonzero same-kind wrapper counts. All revisions of that kind in
both inputs must contain nonempty plain text in direct runs below a paragraph.
Run properties are ignored. Exact payload multiplicities are checked first;
unmatched wording is searched as nonoverlapping literal occurrences across the
concatenated same-kind output text. This permits run/wrapper fragmentation and
coalescence, including coalescence compensated by a new revision at equal counts.
Existing FID001's stricter exception for reduced counts is unchanged.

This is not revision identity matching. For example, source insertions
`["optional", "optional optional"]` versus output
`["invented", "optional optional"]` remain quiet because the second revision
supplies enough literal occurrences. A regression test records this limitation.
Cross-wrapper joins can similarly mask loss; IDs, authors, dates, position,
formatting, independent review groups and visual appearance are not certified.

Nested, empty, property-only and non-text revision content skips that entire
kind. Unequal counts use existing FID001/FID002 only. Fallback searches share a
64 × 1024 × 1024 scanned-character budget per assessment; unsearched candidates
are skipped. New `docx.fidelity.revision-text` coverage reports assessed source
occurrences and reasons for incomplete checks. A skipped check alone does not
fail the CLI. Use `--coverage` to see those gaps.

Footnote/header/footer revision text, move revisions and accept/reject intent
remain outside FID009. Intentional revision rewrites can therefore need review
of an FID009 finding. The recorded `unwrap-note-insertion` miss is the next
separate fix. Broad customer-document behavior and additional Office builds
remain unconfirmed; no layout equivalence or universal recall is claimed.

## Reproduce from the repository root

Use Python 3.9+ and the documented editable dev installation. The local run used
Python 3.9.6 and lxml 6.1.3 on macOS; receipts identify the exact source rather
than relying on the unchanged package version `0.4.1`.

```sh
python research/review_revision_text.py --saved-outputs
python -m ooxml_integrity check evidence/docx-revisions/outputs/replace-unrelated-insertion.docx --against evidence/docx-revisions/sources/basic.docx --no-config --coverage
python -m pytest tests/test_revision_text.py tests/test_revision_coalescence.py tests/test_docx_benchmark.py -ra
python -m pytest -ra
python research/build_docx_evidence.py evaluate
python research/replay_frozen_docx.py
```

The direct CLI comparison intentionally exits 1. To save a fresh evaluation,
add `--output tmp/new-review.json`; existing receipts cannot be overwritten.
Two candidate runs produced byte-identical receipts locally. To reproduce the
immediate pre-fix checker without switching the working tree (Git history must
contain the baseline commit):

```sh
mkdir -p tmp/revision-text/baseline
git archive 83a773cc340a851ecb2a0a4d5a03203ed0945c05 src/ooxml_integrity | tar -x -C tmp/revision-text/baseline
PYTHONPATH=tmp/revision-text/baseline/src python research/review_revision_text.py --baseline --saved-outputs
```

The current gate checks the original oracle plus explicit current expectations.
Directly running `python research/revision_evidence.py evaluate` with the changed
checker intentionally exits 1 for one historical-label mismatch: the corrected
miss. The separate frozen replay verifies the original receipts with their
archived checker; this does not turn the old missed defect into a clean file.

[Local validation](validation.json): **952 passed, 7 skipped** in the full suite;
the skips are missing-font tests whose fonts are actually installed. The frozen
replay also passed all 15 selected historical cases. CLI/JSON/SARIF, baseline
multiplicity, ID/run normalization, duplicate wording, coalescence, unsupported
content and search-budget coverage are included. Baseline v2 and coverage schema
v1 retain their formats; new FID009 errors can change a gate. No release, demo-pin
change, new Office save, agent call or external pilot rerun is claimed.
