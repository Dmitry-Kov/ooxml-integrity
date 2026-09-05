# Windows Word evidence capture

The Windows part of P0.5 was captured on 2026-09-06 local time
(2026-09-05 UTC). Ten distinct synthetic inputs were opened and saved by real
desktop Microsoft Word, not assigned a producer name by editing DOCX metadata.

| Component | Observed version |
| --- | --- |
| Word executable | 16.0.14334.20848, x64 |
| Word COM Version / Build | 16.0 / 16.0.14334 |
| Windows | Windows 11 Pro, 10.0.26200, build 26200, 64-bit |
| Windows PowerShell | 5.1.26100.9168 |
| Python / python-docx | 3.12.14 / 1.2.0 |

## Capture and import

Run from the repository root in an ordinary, signed-in desktop user session.
Install the development dependencies (`python -m pip install -e ".[dev]"`).
If Word displays login, activation or repair UI, stop and resolve it manually;
do not suppress the dialog or treat an interrupted run as evidence.

```powershell
python research/build_docx_evidence.py prepare-windows --staging tmp/word-capture-new
powershell.exe -NoProfile -File research/save_docx_word_windows.ps1 -Probe
powershell.exe -NoProfile -File research/save_docx_word_windows.ps1 -Batch tmp/word-capture-new/batch.json
python research/build_docx_evidence.py import-windows --staging tmp/word-capture-new
python research/build_docx_evidence.py evaluate --write
python -m pytest
```

Use a fresh staging directory. The existing committed Windows tranche is
immutable: `import-windows` refuses a second import rather than replacing it.
The first two capture steps can be repeated in a fresh staging directory on this
checkout to inspect another real Word run. Initial import requires a corpus
without Windows sources, such as the original thirty-source tranche. Word output
bytes need not be deterministic across runs/builds; evaluation always uses the
committed bytes and hashes. `rebuild-outputs` deterministically reproduces the
package mutations and retains real Word roundtrips as captured artifacts.

On this machine Windows PowerShell blocked local scripts. The reviewed capture
was run with `-ExecutionPolicy Bypass` on that PowerShell process only. No system
execution policy, Office Trust Center, Protected View or registry security
setting was changed. Use your organisation's approved script execution route.

The script creates `Word.Application`, verifies a new process and an empty
document collection, then verifies each opened document's window belongs to
that process. It never attaches to an existing Word instance or kills Word
processes. It closes only the document objects it opened; it quits its instance
only when no unexpected document remains. Macros are disabled in that instance
and the prior value is restored on exit. Alerts remain enabled. Inputs open
read-only with recent-file registration disabled; `OpenAndRepair` is omitted
(default false). Save uses DOCX format 12 and disables recent-file registration.
The calls follow Microsoft's [Documents.Open](https://learn.microsoft.com/en-us/office/vba/api/word.documents.open)
and [Document.SaveAs2](https://learn.microsoft.com/en-us/office/vba/api/word.saveas2)
interfaces. No intentionally damaged output is opened in Word.

## Provenance and privacy

The chain is: `_build_seed` synthetic input → actual Word COM open/save →
privacy postprocessing → committed Windows source → deterministic labelled
mutations. The synthetic before-Word input is retained in `roundtrips/` and
paired with that source. Every Windows source includes comments, a table, and
headers/footers; the two multi-section sources have three sections, and the two
review-heavy sources have three comments each.

[`provenance/word-windows.json`](provenance/word-windows.json) records the Word
operation, versions, counts observed via COM, input/raw output/published output
SHA-256, and every raw and published package-part hash. The raw saves and raw log
remain in ignored `tmp/` staging because Office may insert account metadata.
The public receipt includes no account, hostname, process ID, absolute path or
licence identifier. It is an automated capture receipt, not a signed Microsoft
attestation or independent human review.

The sanitizer normalises ZIP metadata and core identities/dates, extended
company/manager/template fields, comment authors/initials/dates and Office
account attributes. It can remove optional thumbnails, printer settings,
custom properties, document variables and attached-template references. It
rejects remaining local paths, email addresses, unexpected identity fields or
unreviewed binary parts. In **this capture**, only `docProps/core.xml`,
`docProps/app.xml`, and metadata in `word/comments.xml` changed after Word;
no part was removed. Raw/published hashes prove that all other Word-written
parts, including main XML, styles, tables, stories and relationships, are
unchanged. Direct XML checks verify that comment text also survived cleanup.

The forty new deterministic pairs use the existing mutation labels and rationale.
The ten no-edit roundtrips are labelled clean from the intended operation and a
direct XML audit, independently of checker output. That audit compares body
text, table cells, comment bodies/anchors, section counts and effective story
text. It does not establish visual equivalence or completeness of all OOXML
features. No Windows false positive was found; all captured pairs remain
regression fixtures.

## Scope

Windows adds 10 sources and 50 pairs: 30 clean and 20 seeded defects. Its error
result is 23 TP, 0 FP, 0 FN. The combined result is 40 sources, 170 pairs,
88 error TP, 0 FP, 0 FN. Warnings and per-rule results remain part of the exact
multiset gate in [RESULTS.md](RESULTS.md). Clean roundtrip precision/recall has
no positive denominator and is reported as **not measured**, with zero false
positives, rather than as a separate 100% accuracy claim.

Word Online is still a separate P0.5 task. The numerical floor, synthetic
content, and this Windows capture do not establish accuracy for arbitrary
customer documents, other Word builds or visual rendering. An independently
supplied commercial/internal generator remains desirable where available;
neither real client documents nor dual independent human review is required
by the original synthetic-corpus plan.
