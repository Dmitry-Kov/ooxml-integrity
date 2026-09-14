# Word follow-up: shared revision IDs and fragment coalescence

**Three actual local Word open / Save As / reopen observations, 2026-09-13 UTC.**
Word for Mac 16.112.4, build 16.112.26090911, opened the adeu split-format result
with a repeated deletion ID without an observed repair prompt. An otherwise
identical unique-ID diagnostic behaved the same. Both saves combined adjacent
deletions while retaining their text and direct bold/italic formatting. The
checker then reported a deletion as lost because its XML element count decreased.

This answers one practical question from [BND-001](../docx-benchmark-boundaries/ISSUES.md).
It does not change that benchmark's protocol, scores or captured files, certify
OOXML conformance, or compare another general editing pipeline.

## Declared method and observations

[PROTOCOL.md](PROTOCOL.md) and [declaration.json](declaration.json) precede every
Word open. Inputs, output hashes, Word version and operation status are retained
in [capture.json](capture.json); [UI observations](observations/UI.md) describe
the native CUA sequence. Normal local Open and Save As DOCX were used, followed
by close/reopen. No content edit, revision acceptance/rejection, repair mode,
alert suppression or global preference change was performed.

| Input and provenance | Open/save/reopen | Revision characters before/after | Deletion XML nodes before/after | Checker before -> after |
| --- | --- | ---: | ---: | --- |
| source-control: unchanged basic boundary source | Completed, no repair/save warning observed | 25 / 25 | 1 / 1 | No ERROR/WARN -> no findings |
| adeu-shared-id: exact actual adeu-1/basic-split output | Completed, no repair/save warning observed | 44 / 44 | 3 / 2 | REV001 ERROR -> FID001 ERROR |
| unique-id-control: synthetic ID-only diagnostic | Completed, no repair/save warning observed | 44 / 44 | 3 / 2 | No ERROR/WARN -> FID001 ERROR |

All inputs also had two REL003 INFO findings for unused relationships. The
diagnostic changes only the second deletion ID from 104 to 106; it is **not an
adeu fix or another adeu execution**. Each input received one Word save. These
are three related files from one basic fixture, not three independent documents
or repeat trials across Office installations.

The comment, footnote, old review wording and formatted edited/deleted markers
were visible in the captured and reopened documents. XML comparison found the
same current wording, ordered review characters, authors, effective UTC times,
paragraph positions and direct bold/italic values. Comment boundaries and note
references retained their text positions and definitions. Screenshots were
inspected in the CUA session but are not exported artifacts or pixel comparisons.

## What Word changed

In both edited inputs, adjacent deletion fragments `EDIT` and `BEFORE` became one
`w:del` containing two differently formatted runs. The inserted `DONEAFTER` stayed
present. Word renumbered the resulting revisions to 0–4; the source control's old
revisions became 0–2. Shared and unique IDs therefore led to the same observed
coalescence, rather than different opening outcomes.

For Evidence Editor revisions, `w:date` changed from `2026-09-13T11:24:16Z` to
`2026-09-13T11:24:00Z`. The existing `w16du:dateUtc` retained the exact timestamp.
The focused comparison uses that UTC attribute when present, while exposing both
raw attributes. Microsoft defines it as a UTC timestamp for a tracked change:
[MS-DOCX §2.12.2.1](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/d760867e-6bc3-43c7-ac53-b32247e1b7e6).
Consumers using only `w:date` see reduced precision.

**Full package preservation did not occur.** All three Word saves removed the
unreferenced `word/media/chart.png`, its relationship, and an unreferenced external
hyperlink relationship to `https://example.org/spec`. These removals also occur
in the source control and cannot be attributed to the repeated ID. No visible
image or hyperlink loss was demonstrated. Word added comment metadata, endnotes,
font/theme/web settings parts and rewrote other XML. Exact part/relationship
differences and raw hashes are retained in [evaluation.json](evaluation.json).
Core metadata now includes Word's local lastModifiedBy value, Dmitrii Kovalev;
captured outputs have not been scrubbed or otherwise modified.

## Standard versus observed tolerance

ECMA-376 Part 1, fifth edition (December 2016), §17.13.5.14, printed page 846
(PDF page 856), describes `w:id` as a unique annotation identifier and requires
its presence. That clause does not provide a same-ID exception for adjacent
deletion fragments. This supports retaining a conformance concern; successful
opening by Word does not establish that such reuse is permitted. Conversely,
the normative description does not predict a repair dialog in every consumer.
See the [official ECMA publication and edition listing](https://ecma-international.org/publications-and-standards/standards/ecma-376/)
and [Part 1 download](https://ecma-international.org/wp-content/uploads/ECMA-376-1_5th_edition_december_2016.zip).

The primary PDF was read locally; its complete entry was verified against the
archive entry's length and CRC. [standards.json](standards.json) records the PDF
SHA-256 and clause locator. Only this focused clause was reviewed; no complete
standards validator or cross-version conformance audit was run. The benchmark's
ID violation remains unchanged, while its practical Word impact is now narrowed
by the observations above.

## Checker and oracle limits exposed here

* **WORD-001 / FID001:** both edited saves produce `tracked deletions: 3 -> 2
  (1 lost)` at ERROR severity. Deleted text and its measured formatting survive;
  the decrease is wrapper coalescence. This is a false loss-of-content inference
  from a real count change. Separate select/accept/reject behavior for the former
  fragments was not tested, so preservation of independently actionable groups
  is not established. Reproduce with the unique-ID control to exclude REV001.
* **WORD-002 / REV001:** the input's repeated ID is real, but the warning about
  Word unreadable content was not observed in this installation. This does not
  establish that all duplicate IDs are valid or harmless, and does not justify
  disabling the rule across documents.
* **WORD-003 / package coverage:** removal of unused media and relationships is
  not reported as a fidelity loss. The source control has no output findings
  despite those package changes. Treat this as a measured coverage boundary,
  not proof that displayed document content was lost.
* **Existing XML oracle:** the unchanged `word-save-content-v1` oracle passes the
  source control but reports revision mismatches for both edited saves. It matches
  wrapper payloads and raw `w:date`, so coalescence and timestamp normalization
  exceed its tolerance. Those residuals remain in evaluation.json. A new focused
  character ledger explains them; it does not replace the oracle, become a new
  pass profile, or rewrite earlier results.

The diagnostic script is [research/inspect_word_revision_ids.py](../../research/inspect_word_revision_ids.py).
It compares ordinary inline insertions/deletions in this basic fixture, with raw
IDs and package changes recorded separately. It is not a general semantic diff:
no moves, nested revisions, property changes, arbitrary inherited formatting,
same-paragraph relocation of revisions, or visual equivalence are certified.
No production checker rule changed.

## Reproduce

From the repository root with the existing development environment (Python
3.9.6, checker 0.4.1), replay the saved DOCX and verify declaration, source,
output, evaluator and checker hashes without opening Word or using the network:

```sh
.venv/bin/python research/inspect_word_revision_ids.py
.venv/bin/python -m pytest tests/test_word_revision_ids.py --basetemp tmp/word-id-tests -ra
```

Inspect the specific FID001 pair directly:

```sh
.venv/bin/python -m ooxml_integrity check \
  evidence/docx-word-id-followup/outputs/unique-id-control-word.docx \
  --against evidence/docx-word-id-followup/inputs/unique-id-control.docx --no-config --json
```

The direct checker command exits 1 because FID001 is an ERROR; that is the
observed result being reproduced, not a failed evidence replay.

For a fresh native observation, record the actual Word/macOS build and copy these
three inputs to a new directory. Follow the exact [UI sequence](observations/UI.md),
save to new output paths, retain all prompts and hash the files. Do not overwrite
the archived captures or reuse their receipt as a new observation. Compare the
new pair with `compare(source, output, id)` from the diagnostic script. Office
timestamps/IDs/package bytes may vary; raw-byte identity is not a reproducibility
criterion for fresh Word saves. Native UI actions are documented, not a headless
automated replay.

## Validation and next decision

The full suite passed **839 tests, with 7 expected font-related skips**. Eleven
new tests cover the ID-only control, coalescence, genuine review/format/author/time
and reference mutations, and replay of the three saved Word cases. Artificial
mutations are diagnostic tests only; none is in the native observation table.
All 140 boundary and 70 v1 attempts replayed; the old 220-pair and 30-pair corpora
had zero label mismatches. Commands, hashes and logs are in [validation.json](validation.json).

The next useful work is a separate, scoped checker change for FID001's count-only
loss inference, with genuine-loss regression cases and an explicit compatibility
decision. REV001's normative scope needs its own decision; this single Word result
cannot settle it. Windows/Online Word, independent revision actions, more source
profiles, visual identity and maintainer feedback remain unmeasured. Publishing
or sending this evidence is a separate owner decision. Nothing was pushed or sent.
