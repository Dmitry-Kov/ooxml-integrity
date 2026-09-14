# FID001 correction: witnessed inline revision coalescence

The candidate checker no longer calls Word's joining of preserved inline revision
fragments a loss solely because the number of `w:ins` or `w:del` wrappers fell.
The captured [Word follow-up](../docx-word-id-followup/README.md) demonstrated this
false alarm with both repeated and unique input IDs. This is a separate checker
fix, not a change to that experiment or to any editor's benchmark score.

## Scope and compatibility

The exception requires a positive match of the complete ordered text of the
revision-bearing paragraphs, each fragment's insertion/deletion kind, author,
effective timestamp, direct run properties and paragraph ordinal. Adjacent text
with the same properties can be split across different runs or revision wrappers.
Revision IDs can be renumbered. Explicit true/false bold and italic spellings
normalize; other run properties compare structurally. Word's UTC extension is
used when present, falling back to `w:date`, as declared in the prior observation.

This intentionally supports only nonempty direct text runs in paragraphs with
plain runs and inline `ins`/`del`. Nested inline revisions, run-property changes, fields, drawings,
anchors inside such a paragraph, empty runs/revisions and other unsupported
structures retain the old count check. A change elsewhere in the same paragraph
or a paragraph-number shift can also leave a conservative count warning. Failure
to compute either signature never becomes permission to suppress a finding.

Loss of an entire revision, one fragment, characters, author, effective time,
direct formatting, or measured position prevents this exception. **These checks
are a guard on an existing count loss, not a new universal content check.** If
counts are equal, the old revision-payload/author/formatting blind spots remain.
Paragraph-property changes, inherited formatting, rendered appearance and
independently selectable revision groups are not certified. `REV001` and
header/footer `FID008` are unchanged.
Acceptance/rejection still reduces the audit record and is not inferred as an
authorized operation by the checker.

`FID001` retains its code, remaining ERROR severity, message and `extra` fields.
Affected pairs can change from CLI exit 1 to 0 because a false finding disappears.
No new CLI/config option, public schema, coverage ID or baseline identity was
introduced. Baseline v2 needs no migration or automatic regeneration; a stale
entry for a removed finding simply has nothing to suppress. Package/release
versions and the public demo remain unchanged; this is unreleased source code.

## Checked against saved evidence

| Stored evidence re-evaluated with candidate | Output pairs | Finding changes |
| --- | ---: | --- |
| v1 deterministic and local agent outputs | 70 | None |
| Boundary deterministic and successful local agent outputs | 95 | None; adeu REV001 remains |
| Word source control | 1 | None |
| Word adeu shared-ID and synthetic unique-ID control saves | 2 | FID001 ERROR removed; no output findings |

All **168 stored output pairs** were rechecked with their input/output hashes.
The 45 boundary agent failures have no output and remain explicitly unevaluated.
No new Word, library or model execution is claimed. [candidate.json](candidate.json)
records old and candidate findings separately, source hashes and changed pairs.
Removal of Word's unused image remains outside this fix, as documented previously.

The new fault-injection tests are separate from those observations. They cover
insertion and deletion coalescence, run fragmentation, loss/replacement/reordering
of review text, repeated text, author/time/format changes, acceptance/removal,
relocation, unsupported structures and CLI behavior without suppressions.
The old 220-pair and 30-pair labelled corpora are regression checks only and keep
their existing labels and known misses.

## Reproduce

From the repository root with the development environment:

```sh
.venv/bin/python -m pytest tests/test_revision_coalescence.py tests/test_fidelity.py tests/test_header_footer_fidelity.py -ra
.venv/bin/python research/review_fid001_fix.py
.venv/bin/python -m ooxml_integrity check \
  evidence/docx-word-id-followup/outputs/unique-id-control-word.docx \
  --against evidence/docx-word-id-followup/inputs/unique-id-control.docx --no-config --json
.venv/bin/python research/build_docx_evidence.py evaluate
.venv/bin/python research/revision_evidence.py evaluate
```

The current CLI example exits 0 with no findings; the archived 0.4.1 result for
the identical pair remains FID001 ERROR / exit 1. [validation.json](validation.json)
records the actual commands, environment, final suite results and receipt hashes.

## Frozen history stays replayable

Historical protocols require the original checker hash and must reject the
candidate checker. Run their exact assertions with their historical source:

```sh
.venv/bin/python research/replay_frozen_docx.py
```

[baseline-checker.zip](baseline-checker.zip) contains the 15 original Python source
files from commit `c66df6e`, under the repository's MIT license.
[baseline.json](baseline.json) pins every file and the archive hash; its source
tree hash agrees with the original declarations. The runner verifies all bytes,
then copies repository-owned research/tests/evidence to a temporary workspace
and runs a separate Python process with the archived package. It needs no Git
history, editor, service, install, download or modified hash gate.

Eight `frozen_checker` tests use this same path in the full suite. They still
execute their original assertions, including corruption/inventory rejection;
they are not skipped or rewritten as candidate results. All other tests,
including the new Word regression, use the current checker. Frozen protocols,
capture scripts, DOCX files, evaluations and original reports remain byte-for-byte
unchanged. No result has been pushed, published or sent to a maintainer.
