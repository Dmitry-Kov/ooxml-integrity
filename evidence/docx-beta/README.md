# DOCX beta evidence corpus

This directory is the first versioned evidence tranche for DOCX structural and
source-fidelity checks. It contains 30 distinct synthetic source documents and
120 labelled source/output pairs. The files are intentionally committed: a
future checker is evaluated against the same producer bytes and labels, not a
freshly generated approximation of them.

## What is in the denominator

- Six document classes, five sources each: contracts, reports, letters,
  table-heavy documents, multi-section documents, and review-heavy documents.
- Ten sources created with `python-docx` 1.2.0.
- Ten sources opened and saved as DOCX by LibreOfficeDev 26.8.0.0.alpha0.
- Ten sources opened and saved as DOCX by Microsoft Word for Mac 16.112.3.
- Four outputs per source: a byte-identical control, a safe ordinary-text edit,
  and two isolated seeded defects appropriate to the document class.
- Sixty clean pairs and sixty seeded-defect pairs in total.

The precise producer version, source/output hashes, document class, mutation,
expected finding multiset, and reason for each label are in
[`manifest.json`](manifest.json). All content is synthetic. It contains no
customer text, personal data, real names, addresses, obligations, or externally
licensed templates, and is distributed under the repository's MIT license.
After each producer save, the builder replaces only `lastModifiedBy`, `created`
and `modified` core properties and normalises ZIP container metadata. This
removes the local Office account name and volatile timestamps without changing
document content, comments, relationships, headers/footers, tables, or styles;
the postprocessing step is recorded on every source manifest entry.

## Labelling method

Expected labels are declared in `research/build_docx_evidence.py` as part of
each isolated mutation before the checker is run. The evaluator combines the
ordinary DOCX inspection and requested source comparison, keeps actionable
error/warning findings, and compares the exact `(rule, severity, occurrence
count)` multiset with the label.

That makes the two error classes observable:

- an unexpected finding is a false positive, including on the 60 clean
  controls;
- an expected finding that is absent is a false negative.

Precision is `TP / (TP + FP)` and recall is `TP / (TP + FN)`. A repeated finding
counts repeatedly. Info-level diagnostics are outside this gate. Rules with no
positive or negative label are printed as **not measured**, not assigned a
perfect score. See the generated [rule-level results](RESULTS.md) and the raw
[`metrics.json`](metrics.json).

Run the immutable evaluation without opening an Office application:

```bash
python research/build_docx_evidence.py evaluate
```

Rebuild only the labelled output mutations from the committed sources:

```bash
python research/build_docx_evidence.py rebuild-outputs
```

Rebuilding producer sources requires the development dependencies, LibreOffice
on `PATH`, and explicit permission to automate the installed Word for Mac:

```bash
python research/build_docx_evidence.py build --word
```

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

## Evidence still missing

This tranche meets the automated numerical floor, but it is not the complete
P0.5 beta evidence claim. It does not contain Word for Windows, Word Online,
customer documents, or a source supplied by an independent commercial/internal
generator. Labels have one maintainer review rather than independent dual
review. Those gaps are repeated in machine-readable form in the manifest and
must be closed before calling P0.5 complete or generalising the measured 100%
result to production documents.
