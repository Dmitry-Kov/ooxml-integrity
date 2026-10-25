# Word refuses a content type or relationship Id declared twice

**`PKG011` and `REL004` (ERROR), released in 0.8.3.** A script that adds a comments
part or a relationship without reading what the package already declares can
write a second `Override` for the same part name, a second `Default` for the
same extension, or a relationship `Id` that is already taken. Word for Mac
16.114.1 on macOS 27.0.1 refused all eight variants below on 24 October 2026:
"Word found unreadable content", and after **No**, "Word experienced an error
trying to open the file". It refused them also when the second declaration
repeats the first exactly. The source document opens. Before these rules the
checker reported nothing on six of the eight, and on the other two only what
followed from the duplicate: `CMT006` and `CMT004` for a second comments
relationship, `REL003` INFO for a relationship nothing referenced.

## Variants

`python research/opc_duplicates.py build evidence/docx-opc-duplicates/variants`
writes them from the Word-saved
[`word-review.docx`](../review-history-benchmark/sources/word-review.docx).
Each changes one entry. Every other entry keeps its name, order, timestamp,
compression method and content, and the build is byte-for-byte reproducible.

| File | Change | Word | Finding |
| --- | --- | --- | --- |
| [default-repeated](variants/default-repeated.docx) | the `xml` `Default` written twice | refused | `PKG011` |
| [default-conflicting](variants/default-conflicting.docx) | a second `xml` `Default`, `text/xml` | refused | `PKG011` |
| [default-case](variants/default-case.docx) | a second `Default` for `XML` | refused | `PKG011` |
| [override-repeated](variants/override-repeated.docx) | the `/word/comments.xml` `Override` written twice | refused | `PKG011` |
| [override-conflicting](variants/override-conflicting.docx) | a second `/word/comments.xml` `Override`, `application/xml` | refused | `PKG011` |
| [override-case](variants/override-case.docx) | a second `Override` for `/WORD/COMMENTS.XML` | refused | `PKG011` |
| [relationship-repeated](variants/relationship-repeated.docx) | the comments relationship `rId7` written twice | refused | `REL004` |
| [relationship-conflicting](variants/relationship-conflicting.docx) | a hyperlink relationship added as `rId2`, the styles relationship's `Id` | refused | `REL004` |
| control: `word-review.docx` | — | opens; 3 comments, 8 revisions | none |

[observations.json](observations.json) records each file's SHA-256, the change,
and Word's prompts with the answer given.

## The rules

`PKG011` groups the `Default` elements of `[Content_Types].xml` by extension and
the `Override` elements by part name, as OPC compares them: ASCII letters
without regard to case, a part name also unescaped. A group of two or more is
one finding on `[Content_Types].xml`, naming the spellings when they differ and
the content types when they differ.

`REL004` groups the relationships of each relationship part by `Id`, compared
exactly as XML ids are. Ids are per part: `rId1` in `_rels/.rels` and in
`word/_rels/document.xml.rels` is not a repeat. A relationship without an `Id`
is not counted.

Both are part of the existing checks and coverage items
(`package.content-types`, `package.relationships`). The baseline identity is
the general one: file, code and location of the second declaration.

## Corpus run

Over the 1,903 public DOCX, DOCM, DOTX and DOTM files of the
[real-world corpora](../../docs/real-world-corpora.md), neither rule fires and
no check fails (`INT001`).

## Limits

- One Word build, on one source document. Word for Windows and Word on the web
  were not checked.
- A percent-escaped spelling of a part name (`/word/%63omments.xml`) counts as a
  repeat because OPC says so. Word refuses such a package, but for the escaped
  name itself: it refuses an `Override` that escapes an unreserved character
  even when the name repeats nothing
  ([case and escapes](../docx-case-overrides/README.md)), which
  [`PKG012`](../docx-escaped-part-names/README.md), released in 0.8.4, reports.
- Only `.docx` packages are checked. A `.pptx` with the same duplicates is not.
- The operator was Claude Code driving Word through AppleScript, with the
  maintainer's permission, and was not blind to the expectations. On each
  launch an installed Adobe PDF add-in raised a Visual Basic error, dismissed
  with **End**; it is unrelated to the documents.
