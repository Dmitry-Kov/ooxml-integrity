# Paragraph-mark and content revision IDs

This describes an **unreleased checkout change**. Published 0.4.2 reports
`REV001` when a paragraph mark and its tracked content share an ID, even in a
plain whole-paragraph insertion or deletion. That count alone does not establish
an ID collision or predict Word's unreadable-content warning.

## Scoped exception

The checker exempts a repeated ID only when all of these conditions hold:

- Exactly two occurrences among main-document `ins`, `del`, `moveFrom` and
  `moveTo`, with the same kind (`ins` or `del`) and an ASCII nonnegative integer ID.
- One empty mark at `p/pPr/rPr/ins|del`, and one direct content revision in that
  same paragraph, directly under `w:body`. Its only children are `pPr` and the
  content revision.
- Nonempty, equal `w:author` and `w:date`; optional `w16du:dateUtc` matches,
  including presence or absence. This compares metadata; it does not validate it.
- Content consists of direct runs with optional run properties and the appropriate
  literal text (`w:t` for insertion, `w:delText` for deletion), with some nonempty
  text. There are no other revisions, move markers or property-change histories
  in the paragraph.

Unrelated content duplicates, third occurrences, different paragraphs, mismatched
or missing metadata, nested/non-text structures, table paragraphs and moves remain
on the existing conservative ERROR path. These limits define the verified
exception; they do **not** establish that every excluded shape is invalid OOXML.
The checker remains a partial structural check, not a schema validator or a
prediction of every Word review operation. `FID009` coverage is unchanged.

## Independent evidence and boundaries

Microsoft distinguishes the tracked paragraph boundary from its content in the
[paragraph-mark implementation note](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/1d66ba8a-1eeb-4cff-ab8a-eaa79113cc89).
Open XML SDK 3.0.1 uses distinct `Inserted`/`Deleted` and
`InsertedRun`/`DeletedRun` types. Its
[uniqueness constraint](https://github.com/dotnet/Open-XML-SDK/blob/77bd9e991740fe4f2efb4fc1c8f85c91de3cf2ac/src/DocumentFormat.OpenXml.Framework/Validation/Semantic/UniqueAttributeValueConstraint.cs#L59)
groups by CLR element type, so a mark/content pair does not share a uniqueness
group merely because both serialize as `w:ins` or `w:del`.

Local validation with SDK 3.0.1 (.NET 8.0.31), targeting Office2019 and
Microsoft365, accepted shared-ID and unique-ID insertion/deletion controls.
Unrelated content duplicates and a third occurrence failed
`Sem_UniqueAttributeValue`. Some ambiguous metadata/placement controls also
passed SDK validation; that is not evidence of correct review behavior.

Word for Mac 16.113 (16.113.26091433) completed all 16 minimal cases:
insertion/deletion × shared/unique IDs × selected Accept/Reject and Accept All/
Reject All. Every result was saved, closed and reopened; paragraph boundaries
matched expectations. Selected actions retained the independent neighboring
revision. Shared and unique IDs behaved identically, so a shared ID was not
necessary for grouping in these controls. Selection used Review > Next Change,
not manual selection of the entire paragraph.

A separate large replay document also completed selected Accept and Reject on
fresh copies, saved and reopened in Draft view. Full text projections, remaining
revision payloads/authors, exact UTC timestamps, comment anchor and media matched
expectations. Word renumbered revision IDs and rounded legacy `w:date` seconds
while preserving `w16du:dateUtc`; byte-for-byte package equality is not claimed.
Private inputs and native captures are intentionally excluded from the repository.

These are Mac observations, not Windows verification, full-document layout
verification or certification of all ISO constraints. SDK success alone does not
prove Word behavior. Reproducible synthetic checker regressions are in
[test_paragraph_revision_ids.py](../tests/test_paragraph_revision_ids.py); they are
not represented as native captures. Historical adjacent content-fragment
collisions remain a different case and are not exempted by this change.

## Gate and compatibility impact

An exempted pair can lose its only ERROR and change exit 1 to 0. Other shared IDs
retain `REV001` ERROR. Report fields, coverage schema/counts and baseline v2
fingerprints are unchanged. `FID002` only says that a construct count increased;
correctness still needs review. No release, version bump or consumer-pin change
is implied by this local correction.
