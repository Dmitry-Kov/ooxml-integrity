# Word for the web evidence

On 2026-09-06, ten synthetic DOCX files were uploaded to the signed-in editor at
`word.cloud.microsoft` with permission. Each was opened, edited, autosaved to
OneDrive and downloaded as DOCX. No personal documents were opened or changed.
The UI did not expose the service build, so the capture can be identified by
date but cannot be tied to a reproducible Microsoft service version.

## Observed operation and independent labels

Each input contains exactly one `WEBINPUT` marker. In the web editor, Replace
All changed it to `WEBSAVED`. For each of the ten files, the UI reported one
replacement and then a completed save. File → Create a copy → Download a copy
produced the retained output. The capture retains the DOCX downloaded after
this observed edit. Files went to the local Downloads folder and were copied
into ignored capture staging.

[`provenance/word-online.json`](provenance/word-online.json) records the coding
agent's observations. It has no Microsoft signature or independent human review.
Hashes tie the receipt to the captured bytes, although they cannot by themselves
prove which application produced a file. The public receipt omits account names
and private document URLs.

The clean edit label is declared before running the checker. A separate XML
audit requires the single intended replacement and exact preservation of every
other body-text character, table-cell text, comment body, ordered comment
range/reference ID with its body-text offset, section count and effective
header/footer text. This audit does not call `check()` or `compare()`. It applies
to both the raw download and its sanitised published copy.

## Privacy and rendering

All inputs use the existing synthetic fixture builder and are MIT-licensed
with this repository. Raw downloads remain in ignored local staging because
Office metadata can include account information. The published files reuse
the fail-closed Windows metadata sanitiser and privacy audit. All ten downloads
needed changes only in `docProps/core.xml`, `docProps/app.xml` and
`word/comments.xml`. No parts were removed; all other package parts are the
exact Word-written bytes. Raw and published hashes of every part are recorded.

The ten inputs and ten sanitised saves were rendered with the bundled
LibreOfficeDev 26.8.0.0.alpha0 renderer and all 15 pages of each set inspected.
The intended marker change is present, with no newly observed clipping or
content disappearance. Existing fixture pagination is retained, including the
letter's short closing on page two. This visual review supplements the XML
checks; Word-versus-LibreOffice pixel equivalence was not scored. Comments and
their anchors are checked directly in XML. The deliberately damaged mutation
outputs were not uploaded to Word, and their rendering was not validated.

## Repeating the workflow

From the repository root, with the development dependencies installed
(`python-docx` 1.2.0 was used for these comment-bearing seeds):

```bash
python research/online_docx_evidence.py prepare --staging tmp/new-web-capture
```

Use a fresh staging directory. Upload only the ten files listed in `batch.json`.
For each document, replace `WEBINPUT` with `WEBSAVED` once, observe completed
autosave, and download into the listed `raw/` path. Do not use desktop Word,
LibreOffice, or package edits as substitutes for the actual web operation.

Record `web-run.json` only after observing those actions. Required top-level
fields are `completed: true`, `operation` equal to the script's `OPERATION`,
`observed_on` as an ISO date, `service: "word.cloud.microsoft"`, and `documents`.
Each document entry has its `id`, input and raw-output SHA-256 hashes,
`replace_count: 1`, `saved: true` and `downloaded: true`. Do not include URLs,
account information or machine paths. A failed or unobserved run is not evidence.

```bash
python research/online_docx_evidence.py import --staging tmp/new-web-capture
python research/build_docx_evidence.py evaluate --write
python -m pytest tests/test_online_evidence.py tests/test_evidence_corpus.py
```

Import refuses to replace an existing web capture or overwrite corpus files.
It validates the complete batch, hashes, privacy and semantic audit before
writing corpus data. The committed capture is immutable. Any further capture
must be reviewed separately and appended while preserving this one.

## Result and boundary

This addition contributes 10 sources and 50 pairs: 20 deterministic clean
controls, 20 seeded-defect pairs and 10 actual web edits. Error findings are
23 TP, 0 FP and 0 FN. The combined corpus has 50 sources, 220 pairs
(120 clean, 100 seeded defects), and 111 error TP, 0 FP and 0 FN.
The web-edit-only group has no positive denominator, so its precision/recall is
reported as `not measured`.

The pre-web 40 sources and 170 pairs, their bytes, labels and supporting
receipts are preserved and pinned to commit `3022ac2`. The P0.5 mandatory
synthetic beta scope is now covered by five producers. No independently
supplied commercial/internal generator or licensed access was available for
the conditional additional-generator item. Customer distributions, other
Office builds/web sessions, independent dual human review and unmeasured rules
remain outside this evidence.
