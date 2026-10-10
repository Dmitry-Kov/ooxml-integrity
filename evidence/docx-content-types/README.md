# Content types of related parts (PKG010)

**The unreleased `PKG010` ERROR fires on exactly five of 3,283 WordprocessingML
files (2,714 distinct): Codex's K5-S1 outputs in the review-history benchmark.
Every other finding on every file is identical to `origin/main` (0.6.0,
`b101e4b`).** Word for Mac refuses those five files; with only the content type
corrected, it opens them ([Word check](../review-history-benchmark/word-check-content-type/README.md)).

## What the rule reads

A relationship from the main document names a part's role by its type, and Word
writes each role's part with one content type: `styles`, `numbering`, `settings`,
`webSettings`, `fontTable`, `footnotes`, `endnotes`, `header`, `footer` and
`comments` as `application/vnd.openxmlformats-officedocument.wordprocessingml.<role>+xml`;
`theme` as `application/vnd.openxmlformats-officedocument.theme+xml`; and the
Microsoft `commentsExtended`, `commentsIds`, `commentsExtensible` and `people`
relationships as the same `wordprocessingml.<role>+xml` form. `PKG010` reports a
target part whose declared content type (its `Override`, matched
ASCII-case-insensitively, else its extension's `Default`) is another one.
Parameters and letter case do not count as a difference.

It does not report:
- a missing target (`REL002`) or a part with no content type (`PKG005`);
- anything when the main part is a template or macro-enabled document
  (coverage item `package.related-content-types`: `unsupported`), Strict, or
  unreadable (`skipped`);
- relationships from other parts, such as a glossary document or a header's images.

The finding names the part. `extra` holds the relationship id and type, the
declared and expected content types, and the relationships part. Its baseline
identity is the general one: file, code and part.

## Result

`python research/content_type_scan.py --public ~/ooxml-corpora`, 10 October 2026,
Python 3.12.8, lxml 6.1.3. [results.json](results.json) lists each group and
each PKG010 finding with the file's SHA-256.

| Files | files | distinct | relationship pairs read | PKG010 |
| --- | ---: | ---: | ---: | ---: |
| This repository: evidence, `runs/`, `corpus/`, `demo/` | 1,380 | 849 | 8,917 | 5 |
| [Public corpora](../../docs/real-world-corpora.md) at their pinned commits, DOCX/DOCM/DOTX/DOTM | 1,903 | 1,865 | 11,771 | 0 |
| **All** | **3,283** | **2,714** | **20,688** | **5** |

The repository's files are the ones git tracks, including this change's three
Word variants. Pairs are counted once per distinct file.

- **The five.** `captures/codex-{1..5}/K5-S1-comment.docx` declare
  `word/commentsExtended.xml` as `application/vnd.ms-word.commentsExtended+xml`.
  The other 351 `commentsExtended` parts in these files, and all 20,332 parts of
  the other fourteen relationship types, have the content type the table expects.
- **The main part.** 2,663 distinct files have a document main part and were
  read. Thirteen templates and macro-enabled documents were not; neither were 13
  Strict files or the 25 that the scan's own reader could not open. The checker
  gives each of those 25 an ERROR: `PKG002` for 20 broken ZIPs; `XML001` and
  `PKG006` for 3; `PKG003`, `PKG006` and `REL001` for 2.
- **Agreement.** The scan reads each package a second time without the checker.
  It finds the same mismatching parts in every file, and no check crashed
  (`INT001`).
- **Nothing else changed.** The same files were checked with `origin/main`'s
  source (`git archive b101e4b src`, source digest `6d82e866…`). Apart from
  `PKG010`, every file's findings are identical: code, severity, part,
  location and message.

The repository's other gates give the same output as `origin/main`:
`research/build_docx_evidence.py evaluate` (220 producer pairs, no label
mismatch), `research/review_revision_text.py --evidence-dir
evidence/docx-paragraph-revision-ids --saved-outputs` (168 saved outputs),
`research/comment_story_evidence.py evaluate`, and `research/replay_frozen_docx.py`.
The [anonymize measurement](../anonymize/README.md) reproduces `PKG010` on all
five anonymized copies; its results record one more finding for each of them.

In the [expectations analysis](../review-history-benchmark/expectations/README.md),
the five outputs were already flagged for their unanchored reply (`CMT005`). They
now also carry `PKG010`, and no count changes. The frozen evaluation
counts them as correct and is unchanged.

## Limits

- Word's refusal was observed for one relationship type, `commentsExtended`,
  in one build: Word for Mac 16.113.4. For the other fourteen, the table is what
  every producer in these corpora wrote. A part declared otherwise was not
  opened in Word, so the message says Word *can* refuse the document.
- Only relationships from the main document are read. Glossary documents,
  headers, footers, notes, charts and custom XML have relationships of their own,
  and those are not checked.
- The expected types come from what Word writes and what these corpora
  contain, not from the whole of ISO/IEC 29500 and [MS-DOCX].

```sh
python research/content_type_scan.py --public ~/ooxml-corpora --output evidence/docx-content-types/results.json
```

Comparing with another checker's source:

```sh
git archive b101e4b src | tar -x -C /tmp/base
python research/content_type_scan.py --public ~/ooxml-corpora --checker-src /tmp/base/src --findings /tmp/base.json
python research/content_type_scan.py --public ~/ooxml-corpora --compare-with /tmp/base.json --output evidence/docx-content-types/results.json
```
