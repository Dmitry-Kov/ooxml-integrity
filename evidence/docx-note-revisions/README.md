# Lost revision presence in footnotes and endnotes

The unreleased checker now detects the original `unwrap-note-insertion` defect
as **FID010 ERROR**. A footnote keeps its words but loses its insertion markup;
the independent oracle still reports lost review content. The same pair changed
from default CLI exit 0 at merged PR #16 (`6c075bf`) to exit 1. This is a seeded
XML defect, not an observed editor failure.

## Protocol and measured result

The [protocol](PROTOCOL.md) was declared before changing the checker. We reused
the five revision sources and existing XML oracle. [expectations.json](expectations.json)
retains the preceding FID009 correction and permits only one additional finding,
on the recorded note miss. Original sources, outputs, labels and receipts remain
unchanged. [baseline.json](baseline.json) and [candidate.json](candidate.json)
record imported checker source hashes, input/output hashes, protocol/evaluator
hashes, Python/lxml/platform versions and separate results.

| Stored evidence rechecked | Baseline after FID009 | Candidate with FID010 |
| --- | --- | --- |
| Seeded footnote-wrapper removal | Missed | FID010 ERROR |
| All 9 original seeded defects, document-pair denominator | 8 detected, 1 missed | 9 detected, 0 missed |
| 15 adeu/Word review-content controls | No ERROR/WARN | No ERROR/WARN |
| 6 accept/reject characterizations | 5 correct actions, 1 incorrect; excluded from preservation metrics | Same oracle results and findings |
| 168 saved benchmark/Word output pairs | Prior findings | All findings unchanged |
| 45 saved agent attempts without output | Unevaluated | Still unevaluated |
| Original 220-pair producer corpus | Historical regression labels | Zero label mismatches |

These checks have separate, partly overlapping scopes. The 9/9 result covers
deliberately injected defects in this set, not editor quality or general recall.
The 168 outputs include all three saved Word coalescence controls, which remain
without ERROR/WARN. No new editor, Office or model run took place. Endnote
removal is covered by synthetic tests, not new native Office evidence.

The benchmark fault-injection test also completes the requested marker edit
while removing the note revision. It independently confirms task completion
and collateral loss; FID010 now detects the latter. Historical evaluations
still replay against their archived checker, with their original false negatives.

## Exact scope and known gaps

The rule groups direct, non-housekeeping notes in conventional
`word/footnotes.xml` and `word/endnotes.xml` by normalized concatenated `w:t`
**and `w:delText`**. This includes deleted words and is not a rendered text view.
Only nonempty groups containing the same number of notes in both inputs qualify.
For each group, compare how many notes contain insertion or deletion markup,
separately. One note contributes at most once per kind, irrespective of the
number of revision fragments. IDs, note order, run splitting and within-note
coalescence therefore do not alone cause a finding.

The supported audit signal is presence, not full revision identity. In particular:

- Removing one of two insertions in a note remains missed while another survives.
- Moving the revision flag between two identically worded notes can remain missed.
- Empty note text, changed text, removed parts and changed group multiplicity
  skip this check. Existing FID005/FID006 body-loss checks continue unchanged;
  their own text-only limits still apply.
- Note reference targets, relocated note parts, detailed revision wording,
  author/date, anchors, formatting, other revision types and visual equivalence
  are outside FID010. A readable package is not proof of preservation.

The first two gaps have dedicated counterexample tests. Malformed note XML or
an unexpected conventional note-part root prevents comparison instead of giving
a clean result. An intentional accept/reject can remove the same audit signal:
unchanged words do not establish whether removal was authorized.

New `docx.fidelity.note-revisions` coverage counts assessed source note/kind
records. Empty or unmatched groups give `skipped`, or `estimated` when another
group was assessed. An unavailable source read for coverage is also skipped,
never reported as absent revisions. `checked` applies only to this presence test. FID010 and
invalid-root FID000 can change exit 0 to 1; baseline v2 and coverage schema v1
keep their formats. New baseline identities distinguish note part, revision kind,
normalized wording and missing multiplicity. No release/demo pin is changed.

## Reproduce from the repository root

Use the documented editable dev installation on Python 3.9+. The recorded local
environment was Python 3.9.6, lxml 6.1.3, macOS; package version remains `0.4.1`,
so compare the recorded source hashes when reproducing unreleased code.

```sh
python research/review_revision_text.py --evidence-dir evidence/docx-note-revisions --saved-outputs
python -m ooxml_integrity check evidence/docx-revisions/outputs/unwrap-note-insertion.docx --against evidence/docx-revisions/sources/notes.docx --no-config --coverage
python -m pytest tests/test_note_revisions.py tests/test_docx_benchmark.py -ra
python -m pytest -ra
python research/build_docx_evidence.py evaluate
python research/replay_frozen_docx.py
```

The direct CLI comparison intentionally exits 1. Add `--output tmp/new-note-review.json`
to save a fresh evaluation; overwriting receipts is refused. Two local candidate
runs produced byte-identical receipts. To run the immediate baseline without
switching the working tree, with the baseline commit available locally:

```sh
mkdir -p tmp/note-revisions/baseline
git archive 6c075bfabc13cce08703b0ed3af6ce29a37f17e9 src/ooxml_integrity | tar -x -C tmp/note-revisions/baseline
PYTHONPATH=tmp/note-revisions/baseline/src python research/review_revision_text.py --evidence-dir evidence/docx-note-revisions --baseline --saved-outputs
```

The evaluator's default directory preserves the preceding FID009-only contract;
use the explicit directory above for current results. Running
`python research/revision_evidence.py evaluate` with this checker intentionally
exits 1 for two historical-label mismatches, the corrected original misses.
Neither historical report is rewritten to hide those differences.

[Local validation](validation.json): **981 passed, 7 skipped** in the full suite;
the seven missing-font tests skip because their fonts are actually installed.
All 195 targeted cases and 15 separately replayed historical cases also passed.
The new tests cover footnotes/endnotes, insertion/deletion removal, note/run/ID
normalization, coalescence, duplicate text, nested presence, housekeeping notes,
empty/unmatched groups, malformed parts, CLI/JSON/SARIF, baseline discrimination
and explicit coverage gaps.
