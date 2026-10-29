# A namespace name that is not a URI is not malformed XML

**`XML001`, changed and unreleased.** SharePoint document libraries write custom
XML parts that declare `xmlns:ns3="$ListId:Shared Documents;"`. Namespaces in
XML asks for a URI there, and libxml2 2.14 reports such a name as a namespace
warning at error level, so lxml refused the part and the checker reported it
as `XML001` ERROR, "XML is not well-formed". The XML is well-formed, and Word
and PowerPoint open such packages without a prompt. A part whose parse reports
nothing but such names is now parsed again, recovering from them alone; every
other error, and a `DOCTYPE`, still fail the part.

## Variants

`python research/namespace_names.py build evidence/xml-namespace-names/variants`
writes them from the Word-saved
[`word-review.docx`](../review-history-benchmark/sources/word-review.docx).
Each adds `customXml/item1.xml`, related from the main document, and changes
nothing else; every other entry keeps its name, order, timestamp, compression
method and content, and the build is byte-for-byte reproducible. Word for Mac
16.114.3 on macOS 27.0.1 opened each alone on 29 October 2026; nothing was
saved.

| File | `ns3` names | Word | before | now |
| --- | --- | --- | --- | --- |
| [not-a-uri](variants/not-a-uri.docx) | `$ListId:Shared Documents;` | opens; 3 comments, 8 revisions | `XML001` ERROR | — |
| [uri](variants/uri.docx) | `urn:example:shared-documents` (control) | opens; 3 comments, 8 revisions | — | — |
| control: `word-review.docx` | — | opens, before and after | — | — |

PowerPoint for Mac 16.114.3 opened LibreOffice's public
[`tdf89927.pptx`](https://github.com/LibreOffice/core/blob/382bad999f5d/sd/qa/unit/data/pptx/tdf89927.pptx),
whose `customXml/item3.xml`, related from the presentation, declares the same
name, without a prompt. [observations.json](observations.json) records each
file's SHA-256 and what the application showed.

## Corpus run

No DOCX, DOCM, DOTX or DOTM file of the
[real-world corpora](../../docs/real-world-corpora.md) or of this repository
has such a part, so no finding on them changes. `tdf89927.pptx` is the only
public file with one.

## Limits

- One Word build and one PowerPoint build. Word for Windows and the web
  versions were not checked.
- Only libxml2's namespace-name warning is tolerated. A part with any other
  error is still `XML001`, even when that error comes with such a name.
- The operator was Claude Code driving Word and PowerPoint through AppleScript,
  with the maintainer's permission, and was not blind to the expectations. An
  installed Adobe PDF add-in raised a Visual Basic error on each open,
  dismissed with **End**; it is unrelated to the documents.
