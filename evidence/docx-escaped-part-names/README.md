# Word refuses an `Override` whose name has an escape it does not accept

**`PKG012` (ERROR), released in 0.8.4.** OPC part names are URIs: a character outside
the unreserved set is written as a percent-escape, and an unreserved one — a
letter, a digit, `-`, `.`, `_`, `~` — must not be. Word for Mac 16.114.1 on
macOS 27.0.1 refuses a package with an `Override` whose `PartName` escapes such
a character, a slash, a backslash or a non-ASCII character, or has a `%` that
starts no escape, even when the `Override` names a part the package lacks. It
opens the same `Override` with escapes of other ASCII characters. The checker
reported none of these before.

## Variants

`python research/escaped_part_names.py build evidence/docx-escaped-part-names/variants`
writes them from the Word-saved
[`word-review.docx`](../review-history-benchmark/sources/word-review.docx).
Each adds one `Override`, for a part the package lacks, after the comments
`Override`, so only its name differs; every other entry keeps its name, order,
timestamp, compression method and content, and the build is byte-for-byte
reproducible. Word opened each file alone on 25 October 2026, idle before each;
nothing was saved.

| File | `PartName` | Escape | Word | `PKG012` |
| --- | --- | --- | --- | --- |
| [plain](variants/plain.docx) | `/word/nothere.xml` | none (control) | opens | — |
| [space](variants/space.docx) | `/word/no%20there.xml` | a space | opens | — |
| [percent](variants/percent.docx) | `/word/no%25there.xml` | a `%` | opens | — |
| [hash](variants/hash.docx) | `/word/no%23there.xml` | a `#` | opens | — |
| [letter-upper](variants/letter-upper.docx) | `/word/%6Eothere.xml` | `n`, unreserved | refused | ERROR |
| [letter-lower](variants/letter-lower.docx) | `/word/%6eothere.xml` | `n`, lower-case hex | refused | ERROR |
| [digit](variants/digit.docx) | `/word/nothere%31.xml` | `1`, unreserved | refused | ERROR |
| [tilde](variants/tilde.docx) | `/word/no%7Ethere.xml` | `~`, unreserved | refused | ERROR |
| [non-ascii](variants/non-ascii.docx) | `/word/n%C3%A9there.xml` | `é` as UTF-8 | refused | ERROR |
| [slash](variants/slash.docx) | `/word/no%2Fthere.xml` | `/` | refused | ERROR |
| [backslash](variants/backslash.docx) | `/word/no%5Cthere.xml` | `\` | refused | ERROR |
| [malformed](variants/malformed.docx) | `/word/no%ZZthere.xml` | `%ZZ`, no escape | refused | ERROR |
| control: `word-review.docx` | — | — | opens, before and after | — |

Refused means "Word found unreadable content", and after **No**, "Word
experienced an error trying to open the file". [observations.json](observations.json)
records each file's SHA-256, its `PartName`, Word's verdict and prompts.

## The rule

`PKG012` reads every `Override` in `[Content_Types].xml` and reports, once per
`Override`, each escape of these kinds in its `PartName`: an unreserved
character, `/` or `\`, a byte of a non-ASCII character, or a `%` not followed
by two hex digits. Escapes of other ASCII characters are not reported. The
finding names the escape; its baseline identity is file, code and the
`Override`'s location. It belongs to the existing coverage item
`package.content-types`.

The [case-override](../docx-case-overrides/README.md) check had already shown
Word refusing three escaped names, one of them for a part the package lacks;
`PKG012` now reports all three.

## Corpus run

Over the 1,903 public DOCX, DOCM, DOTX and DOTM files of the
[real-world corpora](../../docs/real-world-corpora.md) it fires on none, and in
this repository on the three case-override variants above only.

## Limits

- One Word build, on one source document. Word for Windows and Word on the web
  were not checked.
- One sample of each kind. Other escapes of ASCII characters than `%20`, `%25`
  and `%23` were not shown to Word, and neither was a non-ASCII character
  written as itself.
- Only `Override` names are read; relationship targets and ZIP item names have
  their own rules.
- The operator was Claude Code driving Word through AppleScript, with the
  maintainer's permission, and was not blind to the expectations. A first pass
  that opened files without waiting for Word to be idle mixed up the prompts and
  was discarded. An installed Adobe PDF add-in raised a Visual Basic error on
  launch, dismissed with **End**; it is unrelated to the documents.
