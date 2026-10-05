# Anonymizing documents and pairs: measurement

Does [`anonymize`](../../docs/anonymize.md) keep what the checker reads and
remove what a reader could use? It was run on every labelled pair in this
repository, as a pair, and on every DOCX of the public corpora
([real-world corpora](../../docs/real-world-corpora.md)), on its own. Each
item has its own seed, so a rerun gives the same replacements
([script](../../research/anonymize_eval.py)). *Reproduced* means the CLI's
findings on the originals and on the copies agree by code, severity, part and
location; the leak scan is the command's own. [results.json](results.json)
has every item.

| Items | Count | Anonymized | Findings reproduced | With findings | Leak reports |
| --- | ---: | ---: | ---: | ---: | ---: |
| DOCX producer corpus pairs | 220 | 220 | 220 | 100 | 0 |
| Existing-revision pairs | 30 | 30 | 30 | 30 | 0 |
| Saved editor output pairs | 168 | 168 | 168 | 168 | 0 |
| Agent run pairs | 8 | 8 | 8 | 7 | 0 |
| Review-history benchmark pairs | 636 | 636 | 636 | 431 | 0 |
| Public corpora documents | 1,887 | 1,848 | 1,848 | 275 | 0 |

The 39 public documents not anonymized: 20 packages the checker cannot read
either (truncated or inconsistent ZIP directories, OLE compound files, a bad
CRC), 17 in Strict Open XML, which is refused, and 2 OpenDocument files named
`.docx`.

Seventeen items hold a part that is not well-formed XML and was rewritten as
text with its markup unchanged: docxengine's comments part with an undeclared
prefix in two benchmark outputs (its `XML001`, `CMT004` and `CMT006` come back),
and 15 public documents. In six public documents some short words share a
replacement because their alphabet ran out; their findings were reproduced.

## Opening the copies

**LibreOffice.** 210 copies, every n-th of all results, converted to PDF
headless: 210 converted.

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

## Limits

These are the repository's own and public test documents. They cover many
constructs, few of them real confidential documents. The Word check is one
build of Word for Mac and seventeen documents. The leak scan finds words of
the text; what the shape of the text tells a reader is described in
[the command's documentation](../../docs/anonymize.md#what-a-reader-can-still-learn).

```sh
python research/anonymize_eval.py --libreoffice /Applications/LibreOffice.app/Contents/MacOS/soffice
```
