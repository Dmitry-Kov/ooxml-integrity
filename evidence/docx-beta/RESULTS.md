# DOCX beta evidence results

Run `python research/build_docx_evidence.py evaluate --write` to regenerate this report from `manifest.json`. Expected labels come from isolated mutations or observed Office operations checked by independent XML audits. The evaluator compares checker output with those labels.

## Corpus denominator

- Sources: **50**.
- Labelled source/output pairs: **220**.
- Clean controls: **120**.
- Seeded-defect pairs: **100**.
- Each actionable finding occurrence is counted, including repeated occurrences of the same finding. Info-level observations are excluded from the precision check.

## Error-level result

- True positives: **111**.
- False positives: **0**.
- False negatives: **0**.
- Precision: **100.0%** (`TP / (TP + FP)`).
- Recall: **100.0%** (`TP / (TP + FN)`).

## Rule-level result

| rule | TP | FP | FN | precision | recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| `CMT001` | 9 | 0 | 0 | 100.0% | 100.0% |
| `CMT002` | 9 | 0 | 0 | 100.0% | 100.0% |
| `CMT004` | 9 | 0 | 0 | 100.0% | 100.0% |
| `CMT005` | 9 | 0 | 0 | 100.0% | 100.0% |
| `FID000` | 9 | 0 | 0 | 100.0% | 100.0% |
| `FID001` | 9 | 0 | 0 | 100.0% | 100.0% |
| `FID003` | 7 | 0 | 0 | 100.0% | 100.0% |
| `FID004` | 9 | 0 | 0 | 100.0% | 100.0% |
| `FID007` | 16 | 0 | 0 | 100.0% | 100.0% |
| `REL002` | 9 | 0 | 0 | 100.0% | 100.0% |
| `STY001` | 7 | 0 | 0 | 100.0% | 100.0% |
| `TBL001` | 9 | 0 | 0 | 100.0% | 100.0% |
| `TBL002` | 9 | 0 | 0 | 100.0% | 100.0% |
| `TXT001` | 7 | 0 | 0 | 100.0% | 100.0% |

## Producer and pair-kind error results

| group | pairs | clean | TP | FP | FN | precision | recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `kind:deterministic-mutation` | 200 | 100 | 111 | 0 | 0 | 100.0% | 100.0% |
| `kind:word-online-edit` | 10 | 10 | 0 | 0 | 0 | not measured | not measured |
| `kind:word-roundtrip` | 10 | 10 | 0 | 0 | 0 | not measured | not measured |
| `producer:libreoffice` | 40 | 20 | 21 | 0 | 0 | 100.0% | 100.0% |
| `producer:python-docx` | 40 | 20 | 23 | 0 | 0 | 100.0% | 100.0% |
| `producer:word-mac` | 40 | 20 | 21 | 0 | 0 | 100.0% | 100.0% |
| `producer:word-online` | 50 | 30 | 23 | 0 | 0 | 100.0% | 100.0% |
| `producer:word-windows` | 50 | 30 | 23 | 0 | 0 | 100.0% | 100.0% |

The following rules have no positive or negative labels in this corpus, so their precision and recall have not been measured:

`CMT003`, `FID002`, `FID005`, `FID006`, `FID008`, `FTN001`, `FTN002`, `INT001`, `NUM001`, `NUM002`, `NUM003`, `NUM004`, `PKG000`, `PKG001`, `PKG002`, `PKG003`, `PKG004`, `PKG005`, `PKG006`, `PKG007`, `PKG008`, `REL001`, `REL003`, `REV001`, `REV002`, `REV003`, `SDT001`, `SDT002`, `STY002`, `XML001`.

## Interpretation boundary

These results describe the synthetic DOCX mutations and recorded Office save/edit workflows in this corpus. The 100% result applies to the measured rules under those conditions. Precision on customer documents, unmeasured rules, other Office builds and other web sessions remains unknown. Visual fidelity also needs separate evaluation. `manifest.json` and the corpus README record these evidence gaps.
