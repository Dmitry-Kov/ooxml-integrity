# Public real-world corpora

The [labelled corpus](../evidence/docx-beta/README.md) is synthetic: its sources
were created for this project. This record runs the checker over documents that
other projects collected from real producers, mostly as regression inputs for
their own bugs. It measures noise on files Word, LibreOffice and other tools
actually wrote, and detection when a real document is damaged by an edit.

Many of these files are deliberately broken (fuzzing cases, truncated packages,
bug reproductions), so an error here is not automatically a false positive.
Findings were triaged by rule, with samples checked against the package and the
specification; the table under [What changed](#what-changed) lists the rules
whose findings were false.

## Sources

`python research/realworld_scan.py fetch corpora/` sparse-clones exactly these
commits and paths. The files are not vendored; their licences differ from this
repository's.

| Source | Commit | Paths |
| --- | --- | --- |
| [LibreOffice core](https://github.com/LibreOffice/core) | `382bad999f5d` | `sw/qa/extras/ooxmlexport/data`, `sw/qa/extras/ooxmlimport/data`, `sd/qa/unit/data/pptx` |
| [Apache POI](https://github.com/apache/poi) | `3b299acbf019` | `test-data/document`, `test-data/slideshow` |
| [docx4j](https://github.com/plutext/docx4j) | `49e66dd85bad` | sample and test resources |
| [Open XML SDK](https://github.com/dotnet/Open-XML-SDK) | `431ab05cf160` | test assets |
| [python-docx](https://github.com/python-openxml/python-docx) | `e45454602b53` | test files |
| [python-pptx](https://github.com/scanny/python-pptx) | `278b47b1dedd` | test files |

1,887 DOCX and 605 PPTX files. `docProps/app.xml` names Microsoft Word as the
producer of 1,522 of the DOCX files.

## Structural check

`python research/realworld_scan.py scan corpora/`, no config, 25 September 2026.

| DOCX | 0.4.3 | unreleased |
| --- | --- | --- |
| files with an ERROR | 283 | 130 |
| Word-saved files with an ERROR | 150 of 1,522 | 80 of 1,522 |
| ERROR findings | 498 | 203 |
| WARN findings | 421 | 244 |

### What changed

| Rule | 0.4.3 | now | Cause |
| --- | --- | --- | --- |
| `TBL002` WARN | 306 | 32 | `w:gridBefore`/`w:gridAfter` columns and cells inside `w:sdt`/`w:customXml` were not counted |
| `PKG005` ERROR | 130 | 36 | `[Content_Types].xml` itself was reported as a part without a content type |
| `PKG004` ERROR | 86 | 0 | Override-only relationship content types (older LibreOffice exports) are OPC-legal; now 86 WARN |
| `FTN002` ERROR | 67 | 6 | separator notes were recognised by ids `-1`/`0`; LibreOffice and Word 2007 write `0`/`1` |
| `NUM002` ERROR | 46 | 0 | `numId="0"` removes numbering; it is not a reference |
| `XML001` ERROR | 25 | 4 | a malformed part that no relationship reaches, such as a text dump named `*.xml`, is now a WARN (21); Word opened such a package without a prompt |
| `NUM004` WARN | 14 | 2 | levels inherited through `w:numStyleLink` were not followed |
| `PKG006` ERROR | 9 | 6 | the main part was looked up as `word/document.xml`, not through the `officeDocument` relationship. Two copies of docx4j's Word Online sample (`word/document22.xml`) are clean; a LibreOffice test (`word/trial.xml`) now reports 8 `TBL002` (`w:tblCol` instead of `w:gridCol`) and 2 `STY002` |
| `NUM001` ERROR | 1 | 0 | `numId="0"` without a numbering part |
| `PKG009` ERROR | 0 | 17 | new: each Strict DOCX, all saved by Word, passed with only `REL003` INFO although nothing was checked; it now reports that its Word checks were not run |

The remaining findings were sampled by rule. Most describe real damage in bug
reproductions: relationships to parts removed from a minimised test file
(`REL002`), undefined styles (`STY001`), orphaned comments and footnotes with
no anchor in any story (`CMT005`, `FTN002`), tables without `w:tblGrid`
(`TBL001`), encrypted or truncated packages (`PKG002`), and malformed or unsafe
XML in referenced parts (`XML001`). PPTX results are unchanged, except that the
four Strict decks report `PKG009` instead of `PKG002`.

### Checked in Word and PowerPoint

On 25 September 2026, Word for Mac 16.113 (16.113.26091433) and PowerPoint for
Mac 16.113.2 (16.113.26092012) on macOS 27.0 opened these files as a Finder
open would; the maintainer answered the prompts, and nothing was saved.

| file | result |
| --- | --- |
| LibreOffice's `absolute-link.docx`: every relationship part declared by `Override`, no `<Default Extension="rels">` | opened without a prompt; its text matched the XML |
| `corpus/base.docx` | opened |
| `base.docx` plus one unreferenced item without a content type: `[trash]/0000.dat`, `word/document.xml~` or `word/.document.xml.swp` | not opened in any of the three cases; a prompt offered to recover the document |
| `base.docx` without a content type for its referenced image | not opened; recovery offered |
| `base.docx` plus an unreferenced `word/dump.xml` that is not XML | opened without a prompt |
| `corpus/deck.pptx` | opened |
| `deck.pptx` plus one newline after the ZIP end record | PowerPoint offered to repair it |

An Override-only package stays a `PKG004` WARN. An item without a content type
stays a `PKG005` ERROR whether or not a relationship reaches it, and the
message now says that Word asks to recover the document: 26 of the 34 DOCX
files with errors only in unreferenced entries have such an item. Word
2007–2013 wrote the `[trash]/` items in 19 of them; Word for Windows was not
checked. The other 8 files only had malformed unreferenced parts, now `XML001`
WARN. The three POI decks with one trailing newline still fail with `PKG002`,
which now names the extra byte. Two of them are named after the web pages
they came from, so a transfer probably added it.

### Open questions

- **Dangling `w:link` and `w:next`.** 73 of the 79 `STY002` warnings point
  from a style to a missing linked (71) or next (2) style. The specification defines a
  fallback for both.
- **Parser depth.** A document nested deeper than 256 levels is reported as
  "not well-formed" (`XML001`) although the limit belongs to the parser.

## Comparison with the source

**No-op round trip.** `python research/realworld_scan.py noop corpora/` opens
and saves every DOCX with python-docx 1.2.0 and compares the pair. 1,819 pairs
produced no finding. Two comparisons raised an exception: an invalid header
reference type `odd` and a DOCTYPE the safe parser refuses. python-docx could
not open 66 files; they are not counted.

**Damaging and careful edits.** `python research/realworld_scan.py mutate corpora/`
applies, to the first paragraph that holds each construct, the edit that lost
the comment in the [original experiment](research.md): assigning
`Paragraph.text`. A careful edit changes the text of one run. A paragraph-mark
revision (`w:pPr/w:rPr/w:ins`) survives `Paragraph.text`, so only content
revisions select a paragraph.

| Construct in the edited paragraph | destructive edits | detected | careful edits | flagged |
| --- | --- | --- | --- | --- |
| comment anchor | 40 | 40 | 37 | 0 |
| footnote reference | 42 | 42 | 39 | 0 |
| content revision (`w:ins`/`w:del`) | 33 | 33 | 32 | 0 |

Detection means at least one new ERROR relative to the unedited file. These
are python-docx edits only, one operation per document; other editors and
operations are not measured here.
