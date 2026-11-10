# Bookmarks and fields against a source (FID015, FID016)

**On the public corpora, `FID015`, `FID016` and the two new `FID001` tags
report nothing on 1,841 files compared with themselves and nothing on 1,816
files python-docx loaded and saved. After `paragraph.text` was assigned in
every body paragraph holding a field or a bookmark, they report 186 of 235
files; the other 49 lost only hidden bookmarks nothing points at. After a
LibreOffice save of 119 files, 10 have a finding, and in each of the 10
LibreOffice did remove or rename what the finding names.** No save by Word of
a document with fields was measured.

The repository's own DOCX evidence could not measure these rules: none of its
1,555 files holds a bookmark or a field.

## What the rules read

`compare()` reads bookmarks, fields and internal links in the main document,
each effective header and footer slot, and the conventional footnote and
endnote parts ([module](../../src/ooxml_integrity/references.py)).

- **A bookmark is its name**, case ignored. Ids and ranges are not read.
- **A field is its kind** (`REF`, `PAGE`, `TOC`, `=` for a formula) **and, for
  `REF`, `PAGEREF` and `NOTEREF`, the bookmark it points at.** `w:fldSimple`
  and the `w:fldChar` form are the same field. An instruction split over runs
  is joined, nested fields are each read, and an instruction in a tracked
  deletion (`w:delInstrText`) still counts.
- **Switches are not compared.** An exploratory LibreOffice run, on a
  neighbouring sample of 120 files and not part of `results.json`, compared
  whole instructions and reported 53 files, most of them for rewrites that
  lose nothing: `TOC \o "1-3" \h \z \u` came back as
  `TOC \z \o "1-3" \u \h`, `PAGE \* Arabic` as `PAGE \* ARABIC`,
  `REF _Ref97634252 \r \h` as `REF _Ref97634252 \r \r \h`,
  `DOCPROPERTY Title` as `DOCPROPERTY "Title"`.

`FID015`, a bookmark of the source is gone from every story:

- ERROR when a `REF`, `PAGEREF` or `NOTEREF` field, a `HYPERLINK \l` field or
  a `w:hyperlink w:anchor` of the edited file still points at it. Word prints
  "Error! Reference source not found." in place of such a field when fields
  are updated, so the cross-reference a reader sees is replaced by an error.
- WARN when nothing points at it and its name does not start with `_`: the
  document reads the same, and only a link from outside would miss.
- Not reported when nothing points at it and the name starts with `_`. Word
  writes `_GoBack` for the cursor and `_Hlk…` while pasting and drops them as
  it likes; the 1,887 public files hold 1,071 `_GoBack` bookmarks.
- One finding per severity lists the names. A reference that already dangled
  in the source is not reported: its bookmark was never there to lose.

`FID016`, fields of the source are gone, per story and kind:

- ERROR when no field of that kind is left in the story, WARN when some are,
  the rule `FID001` follows for every counted construct. A footer whose only
  `PAGE` field is gone shows the same number on every page.
- A field pointed at another bookmark counts as gone, and the message says
  "gone or point elsewhere".
- A `HYPERLINK` field counts as lost only as far as the story did not gain
  `w:hyperlink` elements, since producers write a link either way.
- Fields an edit added are not reported, and what a field displays is
  paragraph text, which `FID014` compares.

`FID001`/`FID002` also count endnote references (ERROR when lost, like
footnote references) and section breaks (WARN; all lost is an ERROR, as for
every construct). The `w:sectPr` that a tracked section change keeps inside
`w:sectPrChange` is a record, not a break, and is not counted.

`--introduced` never sets these findings aside, and an intended removal is
declared as an expectation, such as `--expect FID016:story=document,kind=TOC`.
In a baseline, `FID015` is identified by its names and `FID016` by story,
kind, count and targets, each hashed.

## Result

`python -I research/reference_evidence.py CORPORA --soffice …/soffice`,
10 November 2026, on the [public corpora](../../docs/real-world-corpora.md) at
their pinned commits: 1,887 DOCX files, 272 of them with a field or a bookmark
other than `_GoBack` in the main document. LibreOffice 26.2.3.2, python-docx
1.2.0, Python 3.12.15. [results.json](results.json) has
every count and each LibreOffice finding.

| Pair | Files | With a new finding |
| --- | ---: | ---: |
| a file and itself | 1,841 | 0 |
| a file and python-docx's save of it | 1,816 (270 with a bookmark or field) | 0 |
| a file and its copy with `paragraph.text` assigned in every body paragraph holding a field or bookmark | 235 | 186 |
| a file and LibreOffice's save of it (every second of the 272, the first 120; one was not converted) | 119 | 10 |

46 files were not compared because `compare()` or the main document's parser
refuses them (many are fuzzing cases), python-docx cannot open 25 more, and in
35 of the 272 no body paragraph holds the field or bookmark (it is in a table,
a header or a note).

**Rebuilt paragraphs.** The 186 reported files carry 204 `FID016` errors and
12 warnings, 40 `FID015` errors, 39 `FID015` warnings and one lost endnote
reference. The 49 silent ones lost only hidden bookmarks nothing points at
(`_GoBack`, `_Toc…` without a table of contents, `__DdeLink__…`), which is the
documented boundary. None lost a field or a visible bookmark without a
finding.

**LibreOffice.** Six of the 10 files have an ERROR. Each of the 10 was checked
against the package LibreOffice wrote, and each finding names a real change:

- fields it did not write back: 32 of the 49 `PAGEREF` fields of one
  specification, both `TOC` fields of one file, the only `PAGEREF` of
  another, a `PAGE` and a `FILENAME` field of a footer, two `NEXT` fields, a
  `DOCPROPERTY` field and a symbol field written as `\SYMBOL`;
- bookmarks it renamed that nothing pointed at: `this is a bookmark` became
  `this_is_a_bookmark`, and a name ending in `_1` lost that suffix (`FID015`
  WARN, two files);
- section breaks: 3 to 1 in one file (`FID001` WARN).

So a LibreOffice save of a document with fields can fail a gate, and each time
it did here, the save had changed what the document's cross-references are
made of. In the exploratory sample LibreOffice also renamed `Text1` to
`Text1_Copy_1` while a `REF` field kept pointing at `Text1`, the case `FID015`
reports as an ERROR; that file is not in the recorded sample.

## Limits

- **Word.** No document with fields or bookmarks was saved by Word for this
  record. That Word keeps instructions and bookmark names on a save, and that
  it removes only hidden bookmarks, is taken from its file format behaviour,
  not measured here. Word Online and Word for Windows were not measured
  either.
- **Seeded damage is one kind**, the `paragraph.text` assignment of
  python-docx, in body paragraphs only. Fields in tables, headers and notes
  were compared in the controls and the LibreOffice saves, not damaged.
- **Counts, not places.** A field moved to another paragraph of the same story
  is the same field. A `PAGE` field deleted in one footer and added in another
  story is reported; one deleted and added within a story is not.
- **Not read:** switches and results, bookmark ranges, bookmarks and fields in
  comments, a `TOC \b` or `SET`/`ASK` bookmark as a reference, `w:pict` VML
  pictures, and whether a reference of the edited file dangled before the
  edit.
- The corpora are test files of other projects, many written to reproduce a
  bug. They show what producers write, not how often a contract has a broken
  cross-reference.
