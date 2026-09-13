# Existing revision evidence

This separate tranche contains **5 synthetic sources and 30 labelled pairs**
with pending tracked revisions. It leaves the original
[50-source / 220-pair corpus](../docx-beta/README.md) unchanged.
The current checker preserves the distinction between structural consistency,
preservation of an existing review record, and a requested accept/reject action.
It does not yet have a contract for intentional revision removal.

The sources combine multiple authors, nested insertion/deletion markup, table
cell revisions, a footnote insertion, a header insertion and a footer deletion.
Every profile also contains a comment, a footnote reference and body revisions.
These are controlled fixtures, not independently supplied customer documents.

## Results on 0.4.1

The unit below is a **document pair**, and a detection is any actionable
ERROR/WARN. INFO additions are excluded. These numbers are not comparable to
the beta corpus's finding-level denominator. No combined producer percentage is
reported.

| Cohort | Pairs | TP | FP | FN | TN |
| --- | ---: | ---: | ---: | ---: | ---: |
| Published adeu 3.0.4: five no-op saves and five nearby tracked edits | 10 | 0 | 0 | 0 | 10 |
| Observed Word Online: two nearby untracked marker edits | 2 | 0 | 0 | 0 | 2 |
| Observed Word for Windows: three no-op saves | 3 | 0 | 0 | 0 | 3 |
| Seeded XML defects | 9 | 7 | 0 | 2 | 0 |
| Accept/reject characterization | 6 | Excluded | Excluded | Excluded | Excluded |

There are **15 clean controls for preserving pre-existing review content**. A clean-only editor
cohort cannot measure recall or positive predictive value. The seeded cohort
detects 7 of its 9 defects; this says nothing about defect prevalence in real
documents. All 30 pairs match their expected current checker findings. Windows
expectations were declared before capture; the content assessment and comparison
profile below were finalized before checker evaluation.
Matching the expected absence of a warning on a known miss does **not** turn
that file into a clean control.

Five rules have seeded positive cases here: `REV001` (duplicate revision ID),
`REV002` (ordinary text under deletion), `REV003` (deleted text under insertion),
`FID001` (body revision count loss), and `FID008` (header/footer revision count
loss). [metrics.json](metrics.json) lists every DOCX rule without a positive case
in this tranche. Retained comments/footnotes are clean controls, not new positive
measurements of their diagnostic rules.

The two preservation false negatives are reproducible:

- `replace-unrelated-insertion`: the pending insertion by Reviewer B changes
  from `optional` to `invented`. Its tag count is unchanged; the independent
  payload comparison detects the lost original wording, while the checker is silent.
- `unwrap-note-insertion`: the footnote's insertion wrapper is removed while
  its text stays. The main-story revision rules do not inspect this part, and
  the note-body comparison sees the same text. The checker is silent.

The six characterization cases contain **five correct actions and one incorrect
action**, assessed against their declared requests. Four are explicit XML
operations and two are actual adeu accept/reject calls. A correct partial accept
and a partial accept that additionally loses an unrelated insertion both report
one `FID001`. The independent oracle distinguishes them. These warnings establish
that a count fell; they do not establish whether the requested edit was wrong.
No production rule is suppressed or weakened to accommodate these cases.

## Provenance and labels

[labels.json](labels.json) was written before the first adeu capture and checker
evaluation. Its SHA-256 is pinned in [capture-adeu.json](capture-adeu.json).
[labels-online.json](labels-online.json) was declared separately before uploading
either Word Online input and before checking either downloaded output. It is
pinned in [capture-online.json](capture-online.json). The manifest retains all
label hashes, every file hash, the requested action, allowed revision losses,
allowed text changes, current expected findings and the independent XML result.

[expectations-windows.json](expectations-windows.json) and
[batch-windows.json](batch-windows.json) are byte-exact copies of the handoff
prepared on 2026-09-12, before Word ran. The returned originals, all three input
hashes and the unchanged capture script match that handoff. The expectations
permit no revision removal or text edit. [labels-windows.json](labels-windows.json)
records the subsequent independent content assessment, the explicit comparison
profile and the originally expected empty finding set. No checker result was
used to set those labels. [capture-windows.json](capture-windows.json) pins both
the original expectations and the finalized labels, with raw/published hashes.

| Material | Producer and operation | Scope |
| --- | --- | --- |
| Five sources | `revision-fixture-builder 1`; deterministic OOXML using parts of the MIT reference package | Synthetic source construction, not an Office observation |
| Twelve adeu outputs | Published Python `adeu==3.0.4`, CLI build `7461e17`; `RedlineEngine.save_to_stream()` or one `process_batch()` action followed by save | Controlled use of an external tool by this project's maintainer, not an independent pilot |
| Two web outputs | Word for the web, observed 2026-09-12; package AppVersion `16.0000`, exact service build not exposed | Basic and table profiles, one `EDITBEFORE` → `EDITAFTER` replacement each, autosave confirmed, downloaded through OneDrive |
| Three Windows outputs | Word `16.0.14334.20848` x64 on Windows 11 Pro `10.0.26200`; PowerShell `5.1.26100.9168`; captured 2026-09-13 | Owner-supplied COM Open/SaveAs2 of basic, nested and table sources, no edit, acceptance/rejection or requested repair |
| Thirteen remaining outputs | Nine seeded defects and four synthetic accept/reject characterizations | Reproducible XML operations, not editor-produced defects |

The adeu capture used Python 3.12.14, lxml 6.1.3, python-docx 1.2.0,
pydantic 2.13.5 and diff-match-patch 20241021 on macOS. Its saved bytes are retained
unchanged. A no-op save really opens and serializes through adeu; it is not a
file copy. The nearby edit creates new tracked revisions, while all prior
revision payloads and authors survive.

The web UI displayed each existing review record, the comment, one page, and
exactly one marker replacement. It confirmed autosave before download. Word's
in-editor download did not yield a reliably observable download event in this
session; the files were retrieved with OneDrive's selected-file Download action.
The web outputs renumber the footnote and its matching reference. The oracle
resolves reference IDs to note bodies, so this legitimate change is permitted
while dangling and retargeted references remain detectable. Existing revision
payloads, authors and dates are unchanged.

## Independent XML oracle

`research/revision_evidence.py` imports the checker only inside `evaluate()`.
Generation, label declaration, capture and the XML oracle do not use checker
findings. The oracle compares revision payload multisets, authors, dates and
nesting, then checks text with deleted content excluded. It checks comment
anchors and definitions, note references and definitions, table grids and story
references separately. It records undeclared revision loss, unresolved requested
actions, unexpected text changes and invalid revision text/IDs.

This is a fixture-specific oracle, not a complete OOXML validator or a public
intentional-changes API. It normalizes note/comment IDs through definitions,
but does not attempt arbitrary relationship rewrites or every revision type.
The nested example is synthetic and its XML preservation is measured; this is
not an observed Office accept/reject result for nested revisions. The relevant
nesting definitions are documented by Microsoft for
[inserted runs](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.insertedrun)
and [deleted runs](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.deletedrun).

### Windows content comparison and layout observations

The original comparison reports differences on all three Windows saves even
though revision payloads, authors, dates and nesting survive. Those original
results remain in `capture-windows.json`; they are not erased. Word renumbered
story relationships, added an empty body paragraph after the terminal table,
added separator-only endnotes and auxiliary XML parts, and recalculated table
column widths. The original 27 labels, pair records and fixture bytes are unchanged.

Only the three Windows cases opt into `word-save-content-v1`. It resolves
header/footer relationship IDs to their type and existing package target;
missing, external or retargeted references remain different. It omits the one
childless paragraph between the final table and section properties, empty
endnote separator paragraphs, and auxiliary parts with no protected structures.
It compares table columns, row/cell boundaries, cell text and merge markers,
while treating auto-layout column widths as a separate layout observation.
Fixed-layout widths stay protected. All revision, author, date, text, comment
and footnote checks remain active, with mutation regressions for these boundaries.

The source grid is `4600 / 4600` twips. Word saved `910 / 1589` for basic/nested
and `910 / 1377` for table; the local renders visibly show narrower tables.
These fixtures have no fixed layout, consistent with the documented
[auto-layout default](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.tablelayout?view=openxml-3.0.1).
This cohort measures preservation of review content, **not unchanged formatting
or layout**. It does not establish whether every Word layout change is acceptable.

## Privacy and visual review

All prose, dates and reviewer names in the fixtures are invented. The reference
package is this repository's MIT material. No customer or private working
document was used. The only external link in generated sources is the reserved
example URL `https://example.org/spec`.

Before publishing, XML metadata and external relationships were inspected.
For each Word Online and Windows output, only `docProps/core.xml`'s `lastModifiedBy` was
replaced with `Evidence Editor`, and the ZIP was repacked. Every other part's
bytes are unchanged from the download; raw/published per-part hashes are in the
capture receipt. Raw files containing the account name remain outside Git in
ignored staging. Account IDs, cloud document URLs and browser session IDs are
not part of the published receipt.

All 35 source/output documents were rendered with the bundled LibreOffice
renderer and reviewed as one-page images. Identical page images were checked
by hash against the same inspected image. Layout was readable; intentional
missing wording/revision marks in defect fixtures were retained. In particular,
the three malformed revision fixtures render identically to the clean source
in this renderer: a successful visual render does not prove structural validity.
Comments and references were also inspected structurally because PDF export
does not reliably show comments. This is local visual QA, not an Office-wide
layout compatibility claim or independent human review.

The three Windows outputs were also rendered before and after the metadata
scrub: each is one page, and each published page PNG matches its raw counterpart
byte-for-byte. The narrower tables have little cell padding; this observed
formatting is retained rather than edited in the evidence. All wording remains
readable. No Windows screenshots or independent human layout review are claimed.

## Reproduce

From the repository root, routine verification needs the project's development
dependencies and no Office login, network or adeu installation:

```sh
python research/revision_evidence.py evaluate
python -m pytest tests/test_revision_evidence.py tests/test_revision_windows.py
python research/revision_evidence.py rebuild
git diff --exit-code -- evidence/docx-revisions/outputs
```

`prepare` rebuilds five synthetic sources and thirteen XML outputs while refusing
to replace changed original labels. The tests compare rebuilt bytes and validate
every captured source/output hash and actionable finding multiset. Captured
editor outputs are immutable replay inputs; fresh adeu timestamps and future
Office saves are not claimed to reproduce identical ZIP bytes.

For a fresh external capture, install `adeu==3.0.4` in an isolated Python 3.12+
environment, then run `research/capture_revision_adeu.py --output-dir NEW_EMPTY_DIR`.
This records versions, source/label/output hashes and successful actions. Keep
fresh captures separate until their XML results and metadata have been reviewed.
For Word Online, upload the declared synthetic input, replace the marker once,
confirm autosave, and download the selected file through OneDrive. Stage raw
files and the observed counts/statuses as described in
`research/import_revision_online.py`; the importer refuses incomplete actions,
changed hashes, unreviewed author/link metadata and failed intent comparisons.

For Windows, copy the three declared sources into the batch's `inputs/`, and
run `research/save_docx_word_windows.ps1 -Batch PATH/TO/batch.json` in an ordinary
Windows desktop session with installed Word. Keep the original expectations,
batch, script, inputs, `raw/` outputs and `word-run.json` together. The reviewed
batch is imported with `python research/import_revision_windows.py --staging STAGING_DIR`;
the importer refuses to overwrite an existing published capture. Future builds
or additional cases need a new declared tranche, independent XML/metadata review
and visual review before publication. The importer does not execute the supplied
script or invoke the checker.

## Unmeasured cases and follow-up

- Word for Windows: only three no-op saves on one build. Nearby edits,
  partial accept/reject, note/story revision operations and other builds remain
  unmeasured; unchanged page layout is not established by these saves.
- Word Online: only two nearby edits in one service session. Web no-op saves,
  partial accept/reject, nested revisions, note/story revision operations and
  other sessions remain unmeasured.
- No independently supplied external generator/customer dataset, no independent
  dual human review, and no endnote/move/formatting-revision coverage here.
- Before expanding detection, define how an intentional acceptance request
  identifies its allowed removals while protecting unrelated revision payloads.
  The two preservation misses and the ambiguous `FID001` characterization are
  evidence for that follow-up, not fixes shipped in this tranche.
