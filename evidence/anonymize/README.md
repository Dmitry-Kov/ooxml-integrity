# Anonymizing documents and pairs: measurement

Does [`anonymize`](../../docs/anonymize.md) keep what the checker reads and
remove what a reader could use? It was run on every labelled pair in this
repository, as a pair, and on every DOCX of the public corpora
([real-world corpora](../../docs/real-world-corpora.md)), on its own. Each
item has its own seed, so a rerun gives the same replacements
([script](../../research/anonymize_eval.py)). *Reproduced* means the CLI's
findings on the originals and on the copies agree by code, severity, part and
location; the data binding check and the leak scan are the command's own.
*With findings* counts INFO too, so it grew when `FID014` began listing the
paragraphs an edit changed. [results.json](results.json) has every item.

| Items | Count | Anonymized | Findings reproduced | With findings | Data bindings kept | Leak reports |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DOCX producer corpus pairs | 220 | 220 | 220 | 160 | — | 0 |
| Existing-revision pairs | 30 | 30 | 30 | 30 | — | 0 |
| Saved editor output pairs | 168 | 168 | 168 | 168 | — | 0 |
| Agent run pairs | 8 | 8 | 8 | 8 | — | 0 |
| Review-history benchmark pairs | 636 | 636 | 636 | 572 | — | 0 |
| Public corpora documents | 1,887 | 1,846 | 1,846 | 273 | 77 of 77 | 11 |

*Data bindings kept* counts the documents with data bindings in which every
binding selects as many nodes in the copy as in the original. The 77 hold 317
bindings: 234 select data in the original (in 71 documents), 44 are errors
there (most name a prefix they do not declare), 18 select nothing and 21 name
no data at all. The pairs in this repository have none.

The 41 public documents not anonymized: 20 packages the checker cannot read
either (truncated or inconsistent ZIP directories, OLE compound files, a bad
CRC), 17 in Strict Open XML, which is refused, 2 OpenDocument files named
`.docx`, and 2 refused because a data binding path compares element names
with `name()` (LibreOffice's `tdf147724.docx` and
`customxml-two-data-stores.docx`, the same Fabasoft binding).

The 11 leak reports are all in parts of LibreOffice test documents named
like `7973.xml` that are several XML files pasted together, each after a
`======= ./name =======` line: not well-formed, so read as raw text, their
markup kept with the attribute values the rules do not name (bibliography
and style names such as `APA Fifth Edition`). From 0.5.0 to 0.8.0 the scan
read those attributes' names instead of their values and reported nothing.

Seventeen items hold a part that is not well-formed XML and was rewritten as
text with its markup unchanged: docxengine's comments part with an undeclared
prefix in two benchmark outputs (its `XML001`, `CMT004` and `CMT006` come back),
and 15 public documents. In six public documents some short words share a
replacement because their alphabet ran out; their findings were reproduced.

## Opening the copies

**LibreOffice.** 209 copies, every n-th of all results, converted to PDF
headless one at a time, with two minutes for each: 207 converted. The copy of
`tdf38575_fullWidthLine.docx` was still converting after two minutes, and so
was its original; the copy of `tdf165348_broken_package.docx` gave no PDF,
and its original, a package broken on purpose, does not load either (LibreOffice
25.8.4.2). Until the review below, the sample went to LibreOffice in one call
and all 210 converted; the two refused documents shifted the sample onto
these two files, and the single call stalled on the first of them.

**Word.** 17 copies chosen for what they contain, opened one at a time in
Microsoft Word for Mac 16.113.3 ([word-check.json](word-check.json)): the
Word-written review record and an edited copy, the reference contract and the
fast agent's output, legacy form fields with ActiveX controls, SmartArt,
Office 2016 and classic charts with embedded workbooks, building blocks with
data binding and mail merge settings, a thumbnail, VML text boxes, a picture
in a header, embedded OLE objects, fields, equations, SharePoint properties
and web add-in parts. All 17 open without an error or an offer to repair; the
mail merge document asks for its data source, as its original does on a
machine without it.

That set is the second pass. In the first, the chart copy did not open: chart
formulas had their cell references replaced, so a range no longer had the
shape of the chart's data, and the chart style parts, in a namespace the
rules did not know yet, had their enumerations replaced; an emptied embedded
workbook made Word offer a repair. Formulas now keep their cell references,
Office's own part namespaces are known, and an embedded workbook becomes an
empty workbook.

## How the leak scan was checked

The scan is a heuristic of the same code, so the copies of the public corpora
were also searched by hand: every attribute value the rules keep that holds
any word of four or more letters of the document's text. All were names the
format defines: enumerations (`auto`, `single`, `left`), built-in style
names, SmartArt layout names, Word-generated shape ids and the `Author` names
the command writes. One place was added to the rules from it (SmartArt
placeholder text). Earlier rounds of the same search found the places now
replaced: VML shape ids that repeat a drawing's name, document properties,
hyperlinks on VML shapes.

## A firm's own schemas and field types

A security review after 0.5.1 found what the hand search above could not:
it read attribute values, and a firm's template carries its identity in names.
A synthetic bank template kept its custom XML namespace
(`http://schemas.<bank>/contracts`), the element names of its data
(`Contract`, `ClientName`) and the data binding path pointing into them, while
their values were replaced; the leak scan saw nothing, since none of those
names occurs in the text. Custom namespace URIs and the element and attribute
names in them are now replaced, the same way in the data, in its properties
part and in the binding paths, so the bindings still resolve; names in Office's
own namespaces, such as SharePoint's `properties`, are kept. The leak scan now
also reads part names and names in custom namespaces. 75 public documents use
custom namespaces (opendope.org data, SharePoint columns and others); all their
findings are still reproduced, and LibreOffice converts 72 of the 73 copies,
the one it does not being a document it does not convert in the original
either.

The same check found a copy LibreOffice does not open at all: the
`BIBLIOGRAPHY` field type of `tdf124384.docx` had been replaced with a made-up
word. Field instructions now keep their field type and switches and lose their
arguments, and numbering formats keep their `%1` placeholders.

## The security review of 0.8.0

An external review of 0.8.0 found four defects in the anonymizer, each shown
with a synthetic document (`tests/test_anonymize.py` holds each case, and
each test fails on 0.8.0):

- An output named like an input (`anonymize(["share/document.docx"],
  "share")`, or `--force` on the command line) replaced the original, and the
  findings were then compared between the copy and itself. An output that is,
  or links to, an input is now refused before anything is written, and the
  originals are checked before any copy is moved into place.
- `<w:p a:client="Acme">`, with `a` a firm's namespace: the namespace and the
  attribute's name were replaced, its value not. Attribute values in a custom
  namespace are now replaced in any part.
- `/ns0:Contract/ns0:Client[@name='Acme']`: the step names were renamed, the
  literal not, so the path kept `Acme` and selected nothing in the copy. The
  literal is now replaced as the value it compares with is, a path that
  cannot be mapped that way is refused, and every binding is checked against
  its data in the original and in the copy.
- `<Acme:Contract xmlns:Acme="...">`: the prefix stayed. Prefixes of custom
  namespaces now get generic names (`ns0`, `ns1`, ...), in markup
  compatibility lists and binding mappings too.

0.8.0's leak scan reported none of it: it did not read prefixes or binding
literals, and in an attribute value it looked for two consecutive words of
the text. It now reads all of them, single words in a firm's names and
values; rewriting how it reads unparsed parts turned up the bug described
above.

What the fixes changed on these corpora, with the same seeds: of the 2,908
items both versions anonymize, 2,894 get copies byte for byte the same as
0.8.0's.
Thirteen differ only in prefixes (opendope's `odx`, `odc`, ..., WPS's
`wpsCustomData`, Google Docs' `go`): parsed, they have the same
elements, names, attributes and text, and their markup compatibility lists
name the same namespaces. One, `tdf151912.docx`, differs only in a binding
path whose undeclared prefix had kept Word's blog tool names. LibreOffice
converts all fourteen and their originals. No document here has a firm's
attribute value in an Office part or a string literal in a binding path, so
those two fixes rest on the synthetic cases.

## Limits

These are the repository's own and public test documents. They cover many
constructs, few of them real confidential documents. The Word check is one
build of Word for Mac and seventeen documents. The leak scan finds words of
the text; what the shape of the text tells a reader is described in
[the command's documentation](../../docs/anonymize.md#what-a-reader-can-still-learn).

```sh
python research/anonymize_eval.py --libreoffice /Applications/LibreOffice.app/Contents/MacOS/soffice --output evidence/anonymize/results.json
```
