# Sharing a defect: `anonymize`

A report about a lost comment or a misattributed revision is most useful with
the two files that show it, and those files are usually confidential.
`ooxml-integrity anonymize` writes copies with the content replaced and the
structure kept, then runs the checks on the originals and on the copies and
says whether every finding came back and whether every data binding still
selects its data.

```sh
ooxml-integrity anonymize original.docx edited.docx -o share/
```

```
anonymized 2 file(s) into share: source.docx, edited.docx
  replaced 347 word(s) (132 distinct), 2 author(s), 10 date(s); 2 picture(s) and embedded workbook(s) became placeholders
  findings reproduced (source 0, edited 3)
  no word of the original text found outside replaced text
Open the results before sharing them. This report holds no text from the documents.
```

Give the source first and the edited copy second, in one run: a word becomes
the same replacement in both files only within a run, and that is what keeps
the comparison meaningful. One file on its own works too (`document.docx`).
The copies get generic names, because a file name can say what it holds.

Exit codes: `0` when every finding was reproduced, every data binding selects
as many nodes as in the original and nothing was left; `1` when the copies
were written but a finding or a binding changed or the leak scan found
something (the report says what); `2` when the files could not be read, the
arguments are wrong or anonymize [refuses](#what-is-refused), and then nothing
is written. Existing copies are not overwritten without `--force`, and an
input never is; `--json` prints the report as JSON (`passed` is the exit-0
condition).

## What is replaced

| content | becomes |
|---|---|
| text: body, headers and footers, notes, comments, text boxes, deleted text, field instructions, equations, chart labels and values | each word a random word of the same length and character classes (capitals, lower case, digits); spaces and punctuation stay |
| authors of revisions and comments, and the people part | `Author 1`, `Author 2`, ...; a comment's initials follow its author (`A2`) |
| dates of revisions and comments, document dates | moved by one random offset, so order and the gaps between dates survive |
| document properties: title, subject, keywords, company, manager, custom properties | words replaced |
| hyperlink and other external addresses, template paths | the scheme (`https://`, `file:`) kept, the rest replaced |
| a firm's own schemas: the namespace URIs, element and attribute names of custom XML data and SharePoint columns | replaced the same way everywhere, so the bindings still resolve |
| an attribute in a firm's namespace, in any part (`<w:p a:client="...">`) | its value replaced like text |
| namespace prefixes bound to a firm's namespace (`<Acme:Contract xmlns:Acme=...>`), also in markup compatibility lists | a generic name, `ns0`, `ns1`, ...; a prefix that already is one is kept |
| data binding paths into custom XML data | step names and prefixes renamed as their elements are (a step whose prefix the binding does not declare too); string literals (`[@name='...']`) replaced the way the values they compare with are, so the binding still selects the same data, which the report checks |
| field instructions | the arguments replaced; the field type (`HYPERLINK`, `MERGEFIELD`) and switches (`\h`, `\* MERGEFORMAT`) kept, since LibreOffice does not open a document with a made-up field type |
| numbering formats (`Article %1.`) | the words replaced, the level placeholders kept |
| names: custom styles and every reference to them, bookmarks, content control titles and tags, form fields, document variables, building blocks, shape names and alternative text, theme names, mail merge source and query | words replaced, the same way at every use |
| custom XML data, sensitivity labels, any part in a namespace this tool does not know | every text and attribute value replaced |
| pictures and thumbnails | a 1x1 picture of the same format |
| embedded workbooks | an empty workbook |
| other embedded objects, macros, printer settings | emptied |

A word is read across runs, so a word split by a comment anchor or a change of
formatting is still one word. Inside a paragraph with tracked changes, the
words are read as the paragraph reads with the new changes rejected, which is
what the checker compares with the source; text inserted by an edit is
replaced on its own.

## What is refused

Nothing is written in these cases (exit `2`):

- An output that is an input, or is linked to one: the same path, a symbolic
  or hard link, another spelling of the name on a case-insensitive disk. Each
  output is compared with each input, so the edited copy of a pair is not
  written over its source either. `--force` does not change this.
- A data binding path whose replacement could select other data. A path may
  use steps on any axis but `namespace`, name and node type tests, positions
  (`[1]`, `[last()]`, `position() < last() - 1`), tests that a node exists,
  `not()`, `and`, `or`, and comparisons of nodes and string literals with `=`
  and `!=`. Equality survives the replacement, because equal values get equal
  replacements. Other functions (`name()`, `contains()`, `substring()`, ...),
  ordering values (`[@amount > 100]`), comparing a value with a number,
  arithmetic on values, unions and variables are refused: the message names
  what the path uses. Removing the content control's binding in a copy of the
  document, then anonymizing that copy, works around it.
- A deck, a file that is not a WordprocessingML package, or Strict Open XML
  (see [limits](#limits)).

## What is kept

- The structure: every element, attribute, id and relationship, and the order
  of everything.
- Part names. Word names its parts generically (`word/media/image1.png`); a
  tool that names a part after its content keeps that name, and the leak scan
  reports a part name that holds a word of the text.
- Names the format and Office define: built-in style names, element names in
  Office's own namespaces (SharePoint's `properties`), the prefixes bound to
  those namespaces, field types and switches, language tags, the ids Word
  generates for shapes.
- Font names and embedded fonts, the page setup, picture sizes, cell
  references in chart formulas (their sheet names are replaced).
- Paragraph and revision ids (`w14:paraId`, `w:rsid*`). Two copies of
  documents edited in the same Word session can share them.
- The document statistics Word stores (pages, words, characters) and the
  identity provider recorded for a reviewer (`AD`, `Windows Live`).

## What a reader can still learn

The shape of the text: how long each word is, where the capitals, digits and
punctuation are, which words repeat. A name keeps its length and capital
letters, an amount its number of digits. Also how many comments, revisions,
authors and pictures there are, which built-in styles and fonts are used, and
the order and spacing of the dates.

So this is not for a document whose shape alone gives it away, such as a
well-known form, and it does not replace looking at the copies before sharing
them.

## How the result is checked

Every check runs on the copies before they are moved into the output
directory, and the originals are read first.

- **Findings.** Each file is checked and the edited copy compared with the
  source, as the `check` command does. The findings of the originals and of
  the copies are compared by code, severity, part and location (messages hold
  text and are left out). A difference is listed as lost or gained.
- **Data bindings.** Each content control's data binding is evaluated against
  the data it names, in the original and in the copy, independently of how
  the path was replaced. One that selects another number of nodes is listed
  by part and position, and fails the run.
- **Leak scan.** The copies are searched for words of the original text.
  Element text is replaced everywhere, so any word of four or more letters
  found there, in a part name, in a name, prefix or attribute value of a
  firm's own schema, or in a data binding path's literals, is reported.
  Attribute values in the Office namespaces are
  mostly names the format defines (`left`, `auto`, `Normal`) that a text may
  use too; there two consecutive words of the text are reported. The report
  names the file, part and element or attribute, never the words.

[The measurement](../evidence/anonymize/README.md) runs this on every
labelled pair in this repository and on the public corpora, and opens a
sample of copies in Word.

## Limits

- `.docx` only. A deck is not anonymized: replacing words changes the widths
  the layout checks measure. Strict Open XML is refused, as the checker does
  not read it either.
- A finding that depends on the exact text can fail to come back, for
  example a tracked change inside a word that the edit accepted. The report
  then lists it; the copies are still written.
- The replacements are random in every run. Anonymizing the same pair twice
  gives different words.
- A package the checker cannot open (a broken ZIP, an encrypted file) cannot
  be anonymized either. A part that is not well-formed XML is rewritten as
  text, its markup unchanged, so it stays broken in the same way; the report
  lists such parts. Its character data, the attributes the rules above name
  and the attribute values in a firm's namespace are replaced; other
  attribute values, and a firm's element names and prefixes, stay as
  written. The leak scan reads them and reports words of the text it finds
  there (single words in a firm's names and values, two consecutive words
  elsewhere).
- Fonts are kept as they are; a custom corporate font keeps its name.

## From Python

```python
from ooxml_integrity.anonymize import anonymize

report = anonymize(["original.docx", "edited.docx"], "share/")
print(report.passed, report.reproduced, report.changed_bindings, report.leaks,
      report.differences())
```
