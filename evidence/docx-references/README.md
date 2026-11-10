# Bookmarks and fields against a source (FID015, FID016)

**`FID015`, `FID016` and the two new `FID001` tags, released in 0.10.0. On the
public corpora they report nothing on 1,841 files compared with themselves and
nothing on 1,816 files python-docx loaded and saved. After `paragraph.text` was assigned in
every body paragraph holding a field or a bookmark, they report 188 of 278
files; the other 90 lost nothing the rules compare. After a LibreOffice save
of 385 files, 38 have a finding, and each of their 54 findings names a field,
a bookmark or a section break that the save did change.** No save by Word of
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
- **Switches are not compared.** An exploratory LibreOffice run on 120 files,
  not part of `results.json`, compared whole instructions and reported 53
  files, most of them for rewrites that lose nothing: `TOC \o "1-3" \h \z \u` came back as
  `TOC \z \o "1-3" \u \h`, `PAGE \* Arabic` as `PAGE \* ARABIC`,
  `REF _Ref97634252 \r \h` as `REF _Ref97634252 \r \r \h`,
  `DOCPROPERTY Title` as `DOCPROPERTY "Title"`.

- **A field inside another field's result is not counted.** Each entry of a
  table of contents holds a `PAGEREF`, and each entry of a table of figures a
  `SEQ`, that the outer field wrote and writes again when it updates.
  LibreOffice saves a table of contents without them: before this was left
  out, one clean save reported "all 44 PAGEREF field(s) are gone" with the
  `TOC` field and every `_Toc` bookmark intact. The bookmark such a field
  names still counts as pointed at.
- **Headers and footers are counted per slot**, as their other constructs are:
  two sections showing one footer part and two showing identical parts hold
  the same fields.
- **A text box is read once.** Word writes it in `mc:Choice` and again in
  `mc:Fallback`; a later branch of `mc:AlternateContent` is not read.

`FID015`, a bookmark of the source is gone from every story:

- ERROR when a `REF`, `PAGEREF` or `NOTEREF` field of the edited file still
  points at it. Word prints "Error! Reference source not found." or "Error!
  Bookmark not defined." in place of such a field when fields are updated, so
  the cross-reference a reader sees is replaced by an error.
- WARN when only a `HYPERLINK \l` field or a `w:hyperlink w:anchor` still
  points at it: the link leads nowhere, and no error is printed.
- WARN when nothing points at it and its name does not start with `_`: the
  document reads the same, and only a link from outside would miss.
- Not reported when nothing points at it and the name starts with `_`. Word
  writes `_GoBack` for the cursor and `_Hlk…` while pasting and drops them as
  it likes; the 1,887 public files hold 1,071 `_GoBack` bookmarks.
- One finding per severity lists the names. A reference that already dangled
  in the source is not reported: its bookmark was never there to lose.

`FID016`, fields of the source are gone, per story and kind:

- ERROR for a lost `REF`, `PAGEREF` or `NOTEREF`, even when others remain. A
  cross-reference turned into plain text reads the same today and goes stale
  when the clause is renumbered, with nothing left in the file to say so.
- For every other kind, ERROR when no field of that kind is left in the
  story and WARN when some are, the rule `FID001` follows for every counted
  construct. A footer whose only `PAGE` field is gone shows the same number
  on every page.
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
their pinned commits: 1,887 DOCX files, 386 of them with a field or a bookmark
other than `_GoBack` in the main document, a header, a footer or a note.
LibreOffice 26.2.3.2, python-docx 1.2.0, Python 3.12.15.
[results.json](results.json) has every count and each LibreOffice finding.

| Pair | Files | With a new finding |
| --- | ---: | ---: |
| a file and itself | 1,841 | 0 |
| a file and python-docx's save of it | 1,816 (382 of the 386) | 0 |
| a file and its copy with `paragraph.text` assigned in every body paragraph holding a field or bookmark | 278 | 188 |
| a file and LibreOffice's save of it (all 386; one was not converted) | 385 | 38 |

46 files were not compared because `compare()` or the main document's parser
refuses them (many are fuzzing cases), python-docx cannot open 25 more, and in
104 of the 386 no body paragraph holds the field or bookmark (it is in a
table, a header, a footer or a note).

**Rebuilt paragraphs.** The 188 reported files carry 198 `FID016` errors and
6 warnings, 31 `FID015` errors, 52 `FID015` warnings and two lost endnote
references. Of the 90 silent files, 88 lost only hidden bookmarks nothing
points at (`_GoBack`, `_Toc…` without a table of contents, `__DdeLink__…`),
and two lost nothing the rules compare. None lost a counted field or a visible
bookmark without a finding.

**LibreOffice.** 25 of the 38 files have an ERROR. Their 54 findings were each
checked against the package LibreOffice wrote, by a count that uses none of
the rules' logic (every field and bookmark of every part under `word/`):

- 49 agree with the raw count: the kind of field has fewer instances in the
  whole package, the bookmark's name is gone, or the main document has fewer
  section breaks.
- 2 are `IF` fields whose instruction holds a nested field, which the raw
  count cannot read; read by hand, four of five are gone.
- 3 are `PAGE` fields of one header or footer slot while the package holds as
  many as before or more. In each, LibreOffice gave a section header and
  footer parts of its own in place of the ones it inherited, and `FID007`
  reports that story as changed in the same run.

Among what LibreOffice did not write back: `PAGE`, `NUMPAGES`, `FILENAME`, `STYLEREF`
and `AUTONUM` in headers and footers, both `TOC` fields of two files, `REF`,
`NEXT`, `MERGEFIELD`, `DOCPROPERTY` (14 of 25 in one file), `EQ` (all 11 in
two files), `BIBLIOGRAPHY` and `CITATION`, `TITLE`, `FORMTEXT`, `GOTOBUTTON`,
`INCLUDEPICTURE`, a locked `PRINTDATE` and `SAVEDATE`. It renamed bookmarks:
`Text1` became `Text1_Copy_1` under one `REF` field, and `SSEDate` and
`SSNumber` under 13 (`FID015` ERROR, two files); `this is a bookmark` became
`this_is_a_bookmark` and 25 form-field names of one file changed with nothing
pointing at them (`FID015` WARN, seven files). It merged section breaks in
four files (`FID001` WARN).

So a LibreOffice save of a document with fields fails the default gate in 25
of 385 files here, and each time the save had changed what the document's
cross-references, page numbers or form fields are made of.

## Limits

- **Word.** No document with fields or bookmarks was saved by Word for this
  record. That Word keeps instructions and bookmark names on a save, and that
  it removes only hidden bookmarks, is taken from its file format behaviour,
  not measured here. Word Online and Word for Windows were not measured
  either.
- **Seeded damage is one kind**, the `paragraph.text` assignment of
  python-docx, in body paragraphs only. Fields in tables, headers and notes
  were compared in the controls and the LibreOffice saves, not damaged.
- **Slots, not pages.** A header or footer slot counts whether or not the
  section shows it (`w:titlePg`, even and odd headers), as for `FID007`. A
  save that gives a section its own copies of inherited parts can change the
  count of a slot.
- **Counts, not places.** A field moved to another paragraph of the same story
  is the same field. A `PAGE` field deleted in one footer and added in another
  story is reported; one deleted and added within a story is not.
- **Not read:** switches and results, bookmark ranges (a bookmark whose end
  moved so that it encloses nothing is still there), bookmarks and fields in
  comments, a `TOC \b` or `SET`/`ASK` bookmark as a reference, `w:pict` VML
  pictures, and whether a reference of the edited file dangled before the
  edit.
- The corpora are test files of other projects, many written to reproduce a
  bug. They show what producers write, not how often a contract has a broken
  cross-reference.
