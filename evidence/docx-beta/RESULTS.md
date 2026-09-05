# DOCX beta evidence results

This report is generated from `manifest.json` by `research/build_docx_evidence.py evaluate --write`. The manifest's expected labels are declared by isolated mutations; they are not snapshots of checker output.

## Corpus denominator

- Sources: **40**.
- Labelled source/output pairs: **170**.
- Clean controls: **90**.
- Seeded-defect pairs: **80**.
- Unit of counting: one actionable finding occurrence. Exact duplicate counts matter; info-level observations are outside this precision gate.

## Error-level result

- True positives: **88**.
- False positives: **0**.
- False negatives: **0**.
- Precision: **100.0%** (`TP / (TP + FP)`).
- Recall: **100.0%** (`TP / (TP + FN)`).

## Rule-level result

| rule | TP | FP | FN | precision | recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| `CMT001` | 7 | 0 | 0 | 100.0% | 100.0% |
| `CMT002` | 7 | 0 | 0 | 100.0% | 100.0% |
| `CMT004` | 7 | 0 | 0 | 100.0% | 100.0% |
| `CMT005` | 7 | 0 | 0 | 100.0% | 100.0% |
| `FID000` | 7 | 0 | 0 | 100.0% | 100.0% |
| `FID001` | 7 | 0 | 0 | 100.0% | 100.0% |
| `FID003` | 6 | 0 | 0 | 100.0% | 100.0% |
| `FID004` | 7 | 0 | 0 | 100.0% | 100.0% |
| `FID007` | 13 | 0 | 0 | 100.0% | 100.0% |
| `REL002` | 7 | 0 | 0 | 100.0% | 100.0% |
| `STY001` | 6 | 0 | 0 | 100.0% | 100.0% |
| `TBL001` | 7 | 0 | 0 | 100.0% | 100.0% |
| `TBL002` | 7 | 0 | 0 | 100.0% | 100.0% |
| `TXT001` | 6 | 0 | 0 | 100.0% | 100.0% |

## Producer and pair-kind error results

| group | pairs | clean | TP | FP | FN | precision | recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `kind:deterministic-mutation` | 160 | 80 | 88 | 0 | 0 | 100.0% | 100.0% |
| `kind:word-roundtrip` | 10 | 10 | 0 | 0 | 0 | not measured | not measured |
| `producer:libreoffice` | 40 | 20 | 21 | 0 | 0 | 100.0% | 100.0% |
| `producer:python-docx` | 40 | 20 | 23 | 0 | 0 | 100.0% | 100.0% |
| `producer:word-mac` | 40 | 20 | 21 | 0 | 0 | 100.0% | 100.0% |
| `producer:word-windows` | 50 | 30 | 23 | 0 | 0 | 100.0% | 100.0% |

Rules with no positive or negative label in this tranche are explicitly not measured; silence is not treated as evidence:

`CMT003`, `FID002`, `FID005`, `FID006`, `FID008`, `FTN001`, `FTN002`, `INT001`, `NUM001`, `NUM002`, `NUM003`, `NUM004`, `PKG000`, `PKG001`, `PKG002`, `PKG003`, `PKG004`, `PKG005`, `PKG006`, `PKG007`, `PKG008`, `REL001`, `REL003`, `REV001`, `REV002`, `REV003`, `SDT001`, `SDT002`, `STY002`, `XML001`.

## Interpretation boundary

These numbers establish reproducible regression behaviour on synthetic DOCX package mutations. They do **not** establish production precision for unmeasured rules, customer document distributions, other Windows Word versions, Word Online, or visual renderer fidelity. Those gaps are kept in `manifest.json` and the corpus README rather than being folded into the 100% measured-rule result.
