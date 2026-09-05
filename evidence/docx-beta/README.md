# DOCX beta evidence corpus

This directory is the first versioned evidence tranche for DOCX structural and
source-fidelity checks. It contains 40 distinct synthetic source documents and
170 labelled source/output pairs. The files are intentionally committed: a
future checker is evaluated against the same producer bytes and labels, not a
freshly generated approximation of them.

## What is in the denominator

- Six document classes: seven contracts, six reports, six letters, seven
  table-heavy, seven multi-section, and seven review-heavy documents.
- Ten sources created with `python-docx` 1.2.0.
- Ten sources opened and saved as DOCX by LibreOfficeDev 26.8.0.0.alpha0.
- Ten sources opened and saved as DOCX by Microsoft Word for Mac 16.112.3.
- Ten sources opened and saved as DOCX by Microsoft Word for Windows
  16.0.14334.20848 (x64), on Windows 11 Pro 10.0.26200 (64-bit).
- Four outputs per source: a byte-identical control, a safe ordinary-text edit,
  and two isolated seeded defects appropriate to the document class.
- Ten additional clean pairs retain the actual synthetic input before Word for
  Windows and its saved, sanitised source after Word.
- Ninety clean pairs and eighty seeded-defect pairs in total. The ten before-Word
  inputs are supporting artifacts, not ten extra producer sources.

The precise producer version, source/output hashes, document class, mutation,
expected finding multiset, and reason for each label are in
[`manifest.json`](manifest.json). All content is synthetic. It contains no
customer text, personal data, real names, addresses, obligations, or externally
licensed templates, and is distributed under the repository's MIT license.
For the original thirty sources, the builder replaces only `lastModifiedBy`, `created`
and `modified` core properties and normalises ZIP container metadata. This
removes the local Office account name and volatile timestamps without changing
document content, comments, relationships, headers/footers, tables, or styles;
the postprocessing step is recorded on every source manifest entry. The Windows
tranche has a broader privacy audit and records raw/published hashes of every
package part in [`provenance/word-windows.json`](provenance/word-windows.json).
In these ten actual saves only core/extended properties and comment metadata
needed cleanup; every other part remains byte-identical to Word's output.

## Labelling method

Expected labels are declared in `research/build_docx_evidence.py` as part of
each isolated mutation before the checker is run. The evaluator combines the
ordinary DOCX inspection and requested source comparison, keeps actionable
error/warning findings, and compares the exact `(rule, severity, occurrence
count)` multiset with the label.

That makes the two error classes observable:

- an unexpected finding is a false positive, including on the 90 clean
  controls;
- an expected finding that is absent is a false negative.

Precision is `TP / (TP + FP)` and recall is `TP / (TP + FN)`. A repeated finding
counts repeatedly. Info-level diagnostics are outside this gate. Rules with no
positive or negative label are printed as **not measured**, not assigned a
perfect score. See the generated [rule-level results](RESULTS.md) and the raw
[`metrics.json`](metrics.json).

The ten Windows no-edit roundtrip labels are also declared clean before scoring.
A separate XML audit verifies identical body text, table-cell text, comment
bodies and anchor counts, section counts and effective header/footer text. Its
implementation does not call the checker. The Windows labels have automated
review by the coding agent; no independent human review is claimed.

Run the immutable evaluation without opening an Office application:

```bash
python research/build_docx_evidence.py evaluate
```

Rebuild only the labelled output mutations from the committed sources:

```bash
python research/build_docx_evidence.py rebuild-outputs
```

Rebuilding outputs preserves actual Office roundtrip records and bytes. The
regression suite verifies that it reproduces all committed DOCX files unchanged.

The legacy `build --word` route is Mac-only and requires LibreOffice as well.
It now refuses to overwrite an existing manifest. Use the separate
[Windows capture and import workflow](WINDOWS.md) to append a producer tranche;
do not regenerate the original corpus to add Windows support.

## Producer and renderer observations

- Every committed source passed the checker with no actionable finding before
  mutation.
- The LibreOffice and Word tranches were actually opened and saved by those
  applications. Their producer label does not come from editing package
  metadata or renaming a `python-docx` file.
- LibreOffice adds style references inside table cells. The original table-row
  mutation removed a cell and therefore caused both the intended `TBL002` and a
  legitimate `FID001`. The committed mutation instead changes `gridSpan`, so
  the label stays isolated without deleting producer-added content.
- Word and LibreOffice may retain empty header/footer parts alongside the
  content-bearing story. Story mutations therefore choose a non-empty story
  rather than assuming `header1.xml` is meaningful.
- The structural corpus does not score visual appearance. “Expected to open
  without repair” is recorded producer behaviour, not a pixel-equivalence
  claim.
- Windows Word completed all ten opens and saves without requesting repair.
  All ten roundtrips matched their clean labels; no Windows false positive was
  found in this capture. Deliberately damaged outputs were never sent to Word.
- Tests pin the original thirty source records and 120 pair records, including
  their hashes and labels, to commit `594cb6b`. Their original error result
  remains 65 TP, 0 FP, 0 FN; the Windows addition contributes 23 TP, 0 FP, 0 FN.

## Evidence still missing

This tranche meets the automated numerical floor, but it is not the complete
P0.5 beta evidence claim. Word Online remains outstanding; Windows evidence is
limited to the recorded desktop build and synthetic inputs. Customer documents
and a source supplied by an independent commercial/internal generator are absent.
The plan accepts defensible synthetic equivalents and asks for an additional
generator where available. Customer documents and independent dual human review
are useful confidence extensions, not mandatory substitutes for the plan's
synthetic evidence. These limitations are explicit in the manifest. Do not call
all P0.5 complete or generalise the measured 100% result to production documents.
