# Findings kept outside editor scores

## Newly confirmed seeded gap: a comment range can move silently

`diagnostics/seeded-comment-anchor-move.docx` is an **artificial XML mutation**,
not an adeu/python-docx/agent output. It moves the existing `commentRangeStart`
id 1 from the delivery paragraph to the start of the second body paragraph.
The range now includes different text, while its end, reference, comment body,
IDs, revision payloads and document wording stay unchanged.

Checker 0.4.1 reports no ERROR/WARN. Its two REL003 INFO findings were already
present in the source. The reused revision oracle also passes this case: its
protected-marker sequence does not encode each anchor's position among text.
The benchmark's bounded package comparison detects the relocated anchor.

Reproduce the mutation and verify its bytes/assessment with:

```sh
.venv/bin/python -m pytest tests/test_docx_benchmark.py -k seeded_anchor_gap --basetemp tmp/benchmark-gap-test
.venv/bin/python research/docx_benchmark.py inspect \
  --source evidence/docx-revisions/sources/basic.docx \
  --output evidence/docx-benchmark/diagnostics/seeded-comment-anchor-move.docx \
  --action save --adapter python-docx-run-v1
```

Here `--adapter` selects untracked comparison semantics; `inspect` does not run
an editor. The saved JSON says `seeded_diagnostic_not_editor_output`. This is a
confirmed checker/original-oracle limitation on one synthetic case, not evidence
that any measured adapter relocates anchors. Production rules were not changed.
A future anchor-span fidelity check needs a separately scoped design: legitimate
nearby edits and comment-anchor renumbering must not become automatic defects.

## Existing checker gaps, independently retained

`replace-unrelated-insertion` and `unwrap-note-insertion` in the revision tranche
remain misses: equal-count revision payload replacement and removal of a
footnote insertion wrapper with its text retained. Benchmark mutation tests
combine each with a correctly completed marker edit and still classify the
unrelated loss independently. These tests are not editor observations. Run:

```sh
.venv/bin/python -m pytest tests/test_docx_benchmark.py -k existing_checker_misses --basetemp tmp/benchmark-known-gap-tests
```

Absence of the requested edit alone is another reason the task can fail while
the checker is quiet; this is outside its intent-unaware fidelity contract,
not automatically a checker false negative. No claims about general recall or
visual/layout preservation follow from the clean local adapter cohorts.

## Corrected benchmark evaluator issue, not an editor defect

The first two captures used harness SHA-256
`d770c8d6c7cd21480540bb635fc203acc713a33bb96197a5dd3936035e420654`.
Their original `evaluation.json` files and `capture-harness.py` snapshots remain
unchanged. The snapshots were saved after capture but before the correction;
their hashes match the pre-recorded capture hashes.

The initial bounded comparator rejected the `w16du:dateUtc` attribute on adeu's
new marker revisions, giving five `protected_package_changes` results and 5/10
successes for adeu's first capture. Its original revision oracle already passed
all ten tasks. The protocol permits a new exact marker pair and its generated
timestamps. The evaluator omitted that timestamp extension from its implementation.

The corrected evaluator recognizes `dateUtc` only on the new marker pair and
only when it equals `w:date`; prior revisions' attributes remain protected. This
implements the existing allowance, without editing the frozen protocol or
checker. Synthetic regressions cover the extension and ensure bold formatting
added inside a new insertion is still rejected. Adapter function ASTs are
identical across the old/current snapshots. `evaluation.reviewed.json` records
the corrected evaluation of every original output, and the second captures
confirm the same result. The report uses these reviewed evaluations and retains
the initial discrepancy here rather than silently replacing it.
