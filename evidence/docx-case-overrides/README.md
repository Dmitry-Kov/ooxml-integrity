# An `Override` that names its part in other letters

**`PKG005` and `PKG010`, changed in 0.8.4.** OPC compares part names
ASCII-case-insensitively, and so does Word: an `Override` for
`/WORD/COMMENTS.XML` covers `word/comments.xml`. Through 0.8.3 both rules
compared the name exactly. A package with an `xml` `Default` hides that, since
the part is covered by the default; without one, `PKG005` reported such a part
as having no content type (ERROR, "Word asks to recover the document"), and
`PKG010` did not read its type. Both now compare names without regard to case,
and not unescaped: Word refuses a package whose `Override` escapes an
unreserved character, whatever part it names.

## Variants

`python research/case_overrides.py build evidence/docx-case-overrides/variants`
writes them from the Word-saved
[`word-review.docx`](../review-history-benchmark/sources/word-review.docx),
whose XML parts all have an `Override`. Each changes `[Content_Types].xml`
only; every other entry keeps its name, order, timestamp, compression method
and content, and the build is byte-for-byte reproducible. Word for Mac 16.114.1
on macOS 27.0.1 opened each alone on 24 October 2026; nothing was saved.

| File | Change | Word | 0.8.3 | now |
| --- | --- | --- | --- | --- |
| [no-xml-default](variants/no-xml-default.docx) | the `xml` `Default` removed | opens | — | — |
| [override-capitals](variants/override-capitals.docx) | and the comments `Override` names `/WORD/COMMENTS.XML` | opens; 3 comments, 8 revisions | `PKG005` | — |
| [override-capitals-wrong-type](variants/override-capitals-wrong-type.docx) | and the `commentsExtended` `Override` names `/WORD/COMMENTSEXTENDED.XML` with the type Codex wrote | refused | `PKG005` | `PKG010` |
| [override-escaped](variants/override-escaped.docx) | and the comments `Override` names `/word/%63omments.xml` | refused | `PKG005` | `PKG005`, `PKG012` |
| [override-escaped-repeat](variants/override-escaped-repeat.docx) | the `xml` `Default` kept; a second comments `Override` for `/word/%63omments.xml` | refused | `PKG011` | `PKG011`, `PKG012` |
| [override-absent-part](variants/override-absent-part.docx) | the `xml` `Default` kept; an `Override` for `/word/nothere.xml`, which the package lacks | opens | — | — |
| [override-absent-escaped](variants/override-absent-escaped.docx) | the same `Override` named `/word/%6Eothere.xml` | refused | — | `PKG012` |
| control: `word-review.docx` | — | opens, before and after | — | — |

`ooxml-integrity fix` now repairs `override-capitals-wrong-type`: it gives that
`Override` the `wordprocessingml` type and keeps its letters, and Word opens the
copy with 3 comments and 8 revisions. Through 0.8.3 the file had only a
`PKG005`, which `fix` does not repair.

[observations.json](observations.json) records each file's SHA-256, the change,
Word's prompts with the answer given, and the findings before and after.

## What the escaped names show

The last two variants differ only in `%6E` for `n`, in an `Override` for a part
the package lacks: Word opens the first and refuses the second. So Word refuses
an `Override` whose name escapes an unreserved character, which OPC forbids,
and an escaped name cannot cover a part. That is also why Word refused
`override-escaped-repeat`, the case
[`PKG011`](../docx-opc-duplicates/README.md) counts as a repeat.

## Corpus run

Over the 1,903 public DOCX, DOCM, DOTX and DOTM files of the
[real-world corpora](../../docs/real-world-corpora.md) and the 1,485 in this
repository, `PKG004`, `PKG005` and `PKG010` change on the two variants above
and nowhere else.

## Limits

- One Word build, on one source document. Word for Windows and Word on the web
  were not checked.
- An `Override` whose name escapes an unreserved character and names no part
  (`override-absent-escaped`) was reported by no rule when this record was made;
  [`PKG012`](../docx-escaped-part-names/README.md), released in 0.8.4, reports it.
- The operator was Claude Code driving Word through AppleScript, with the
  maintainer's permission, and was not blind to the expectations. An installed
  Adobe PDF add-in raised a Visual Basic error on launch, dismissed with
  **End**; it is unrelated to the documents.
