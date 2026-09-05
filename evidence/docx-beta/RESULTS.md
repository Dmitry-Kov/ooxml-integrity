# DOCX beta evidence results

This report is generated from `manifest.json` by `research/build_docx_evidence.py evaluate --write`. The manifest's expected labels are declared from isolated mutations or observed Office operations with independent XML audits; they are not snapshots of checker output.

## Corpus denominator

- Sources: **50**.
- Labelled source/output pairs: **220**.
- Clean controls: **120**.
- Seeded-defect pairs: **100**.
- Unit of counting: one actionable finding occurrence. Exact duplicate counts matter; info-level observations are outside this precision gate.

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

Rules with no positive or negative label in this tranche are explicitly not measured; silence is not treated as evidence:

`CMT003`, `FID002`, `FID005`, `FID006`, `FID008`, `FTN001`, `FTN002`, `INT001`, `NUM001`, `NUM002`, `NUM003`, `NUM004`, `PKG000`, `PKG001`, `PKG002`, `PKG003`, `PKG004`, `PKG005`, `PKG006`, `PKG007`, `PKG008`, `REL001`, `REL003`, `REV001`, `REV002`, `REV003`, `SDT001`, `SDT002`, `STY002`, `XML001`.

## Interpretation boundary

These numbers establish reproducible regression behaviour on synthetic DOCX package mutations and the recorded Office save/edit workflows. They do **not** establish production precision for unmeasured rules, customer document distributions, other Office builds or web sessions, or visual renderer fidelity. Those gaps are kept in `manifest.json` and the corpus README rather than being folded into the 100% measured-rule result.
