#!/usr/bin/env python3
"""
Собирает реалистичный .docx напрямую из частей OOXML.

Задача: документ должен содержать ровно те конструкции, которые
агенты чаще всего ломают и которые никто не проверяет:
  - именованные стили (абзацные и знаковые)
  - многоуровневая нумерация (numId -> abstractNumId)
  - сноски
  - комментарии (rangeStart / rangeEnd / commentReference)
  - tracked changes (w:ins / w:del с уникальными id)
  - content control (w:sdt)
  - изображение (r:embed) и гиперссылка (r:id)
  - таблица с явным w:tblGrid
  - колонтитулы
"""
import os, zipfile, shutil, struct, zlib

#: Fixed timestamp so the package is byte-reproducible.
#: A corpus you cannot rebuild identically is not a fixture.
ZIP_EPOCH = (2026, 1, 1, 0, 0, 0)

OUT = os.environ.get("DI_BASE", "../corpus/base.docx")

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
WP = 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
PIC = 'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'

CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>
<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''

ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

DOC_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>
<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>
<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
<Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
<Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/chart.png"/>
<Relationship Id="rId8" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.org/spec" TargetMode="External"/>
</Relationships>'''

STYLES = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="259" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/><w:color w:val="1F4E5F"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:ind w:left="720"/><w:contextualSpacing/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="ClauseBody"><w:name w:val="Clause Body"/><w:basedOn w:val="Normal"/>
<w:pPr><w:jc w:val="both"/><w:spacing w:after="120"/></w:pPr></w:style>
<w:style w:type="character" w:styleId="DefinedTerm"><w:name w:val="Defined Term"/><w:rPr><w:b/><w:smallCaps/></w:rPr></w:style>
<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="FootnoteReference"><w:name w:val="footnote reference"/><w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>
<w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="auto"/><w:left w:val="single" w:sz="4" w:color="auto"/>
<w:bottom w:val="single" w:sz="4" w:color="auto"/><w:right w:val="single" w:sz="4" w:color="auto"/>
<w:insideH w:val="single" w:sz="4" w:color="auto"/><w:insideV w:val="single" w:sz="4" w:color="auto"/></w:tblBorders></w:tblPr></w:style>
</w:styles>'''

NUMBERING = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering {W}>
<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="multilevel"/>
<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:lvlJc w:val="left"/>
<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl>
<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%1.%2"/><w:lvlJc w:val="left"/>
<w:pPr><w:ind w:left="1440" w:hanging="360"/></w:pPr></w:lvl>
</w:abstractNum>
<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>
<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="&#8226;"/><w:lvlJc w:val="left"/>
<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr><w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol"/></w:rPr></w:lvl>
</w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>'''

SETTINGS = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings {W} xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
<w:zoom w:percent="100"/>
<w:defaultTabStop w:val="720"/>
<w:characterSpacingControl w:val="doNotCompress"/>
<w:footnotePr>
<w:footnote w:id="-1"/><w:footnote w:id="0"/>
</w:footnotePr>
<w:compat>
<w:compatSetting w:name="compatibilityMode"
 w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
<w:compatSetting w:name="overrideTableStyleFontSizeAndJustification"
 w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
<w:compatSetting w:name="enableOpenTypeFeatures"
 w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
<w:compatSetting w:name="doNotFlipMirrorIndents"
 w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
<w:compatSetting w:name="differentiateMultirowTableHeaders"
 w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
</w:compat>
</w:settings>'''

FOOTNOTES = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes {W}>
<w:footnote w:type="separator" w:id="-1"><w:p><w:pPr><w:spacing w:after="0"/></w:pPr><w:r><w:separator/></w:r></w:p></w:footnote>
<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:pPr><w:spacing w:after="0"/></w:pPr><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>
<w:footnote w:id="1"><w:p><w:pPr><w:spacing w:after="0"/></w:pPr>
<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteRef/></w:r>
<w:r><w:t xml:space="preserve"> ECMA-376 Part 1, 5th edition, section 17.3.1.</w:t></w:r></w:p></w:footnote>
<w:footnote w:id="2"><w:p><w:pPr><w:spacing w:after="0"/></w:pPr>
<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteRef/></w:r>
<w:r><w:t xml:space="preserve"> Measured across the reference corpus, Q2 2026.</w:t></w:r></w:p></w:footnote>
</w:footnotes>'''

COMMENTS = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments {W}>
<w:comment w:id="1" w:author="M. Reviewer" w:initials="MR" w:date="2026-08-12T10:04:00Z">
<w:p><w:r><w:t>Confirm this figure against the source table before circulation.</w:t></w:r></w:p></w:comment>
<w:comment w:id="2" w:author="A. Counsel" w:initials="AC" w:date="2026-08-14T16:22:00Z">
<w:p><w:r><w:t>Defined term must match the definitions schedule.</w:t></w:r></w:p></w:comment>
</w:comments>'''

HEADER = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr {W}><w:p><w:pPr><w:jc w:val="right"/></w:pPr><w:r><w:t>Reference Agreement - Draft 7</w:t></w:r></w:p></w:hdr>'''

FOOTER = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr {W}><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:t>Confidential</w:t></w:r></w:p></w:ftr>'''

CORE = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Reference Agreement</dc:title><dc:creator>corpus-builder</dc:creator>
<cp:revision>7</cp:revision></cp:coreProperties>'''

APP = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
<Application>corpus-builder</Application></Properties>'''

DOCUMENT = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {W} {R} {WP} {A} {PIC}>
<w:body>

<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Master Services Agreement</w:t></w:r></w:p>

<w:p><w:pPr><w:pStyle w:val="ClauseBody"/></w:pPr>
<w:r><w:t xml:space="preserve">This agreement governs the provision of services described in Schedule A. The </w:t></w:r>
<w:commentRangeStart w:id="2"/>
<w:r><w:rPr><w:rStyle w:val="DefinedTerm"/></w:rPr><w:t>Effective Date</w:t></w:r>
<w:commentRangeEnd w:id="2"/>
<w:r><w:commentReference w:id="2"/></w:r>
<w:r><w:t xml:space="preserve"> is the date of last signature.</w:t></w:r>
<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteReference w:id="1"/></w:r>
</w:p>

<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>1. Scope of Services</w:t></w:r></w:p>

<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
<w:r><w:t>The Supplier shall deliver the services with reasonable skill and care.</w:t></w:r></w:p>

<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr></w:pPr>
<w:r><w:t xml:space="preserve">Service levels are set out in </w:t></w:r>
<w:hyperlink r:id="rId8"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr><w:t>the published specification</w:t></w:r></w:hyperlink>
<w:r><w:t>.</w:t></w:r></w:p>

<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
<w:ins w:id="101" w:author="A. Counsel" w:date="2026-08-14T16:20:00Z">
<w:r><w:t>The Supplier shall maintain professional indemnity insurance.</w:t></w:r></w:ins></w:p>

<w:p><w:pPr><w:pStyle w:val="ClauseBody"/></w:pPr>
<w:r><w:t xml:space="preserve">The parties agree the fee is </w:t></w:r>
<w:del w:id="102" w:author="A. Counsel" w:date="2026-08-14T16:21:00Z">
<w:r><w:delText xml:space="preserve">EUR 40,000 </w:delText></w:r></w:del>
<w:ins w:id="103" w:author="A. Counsel" w:date="2026-08-14T16:21:00Z">
<w:r><w:t xml:space="preserve">EUR 44,500 </w:t></w:r></w:ins>
<w:r><w:t>per annum.</w:t></w:r></w:p>

<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>2. Commercial Terms</w:t></w:r></w:p>

<w:sdt><w:sdtPr><w:alias w:val="Contract Reference"/><w:tag w:val="contract_ref"/>
<w:id w:val="770011"/><w:text/></w:sdtPr>
<w:sdtContent><w:p><w:pPr><w:pStyle w:val="ClauseBody"/></w:pPr>
<w:r><w:t>Contract reference: MSA-2026-0417</w:t></w:r></w:p></w:sdtContent></w:sdt>

<w:tbl>
<w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>
<w:tblGrid><w:gridCol w:w="3000"/><w:gridCol w:w="3000"/><w:gridCol w:w="3000"/></w:tblGrid>
<w:tr><w:trPr><w:tblHeader/></w:trPr>
<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Milestone</w:t></w:r></w:p></w:tc>
<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Date</w:t></w:r></w:p></w:tc>
<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Fee</w:t></w:r></w:p></w:tc></w:tr>
<w:tr>
<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>Discovery</w:t></w:r></w:p></w:tc>
<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>2026-09-15</w:t></w:r></w:p></w:tc>
<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr><w:p>
<w:commentRangeStart w:id="1"/><w:r><w:t>EUR 12,000</w:t></w:r><w:commentRangeEnd w:id="1"/>
<w:r><w:commentReference w:id="1"/></w:r></w:p></w:tc></w:tr>
<w:tr>
<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>Delivery</w:t></w:r></w:p></w:tc>
<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>2026-12-01</w:t></w:r></w:p></w:tc>
<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>EUR 32,500</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>

<w:p><w:pPr><w:pStyle w:val="ClauseBody"/></w:pPr>
<w:r><w:t xml:space="preserve">Historic spend is shown below.</w:t></w:r>
<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteReference w:id="2"/></w:r></w:p>

<w:p><w:r><w:drawing>
<wp:inline distT="0" distB="0" distL="0" distR="0">
<wp:extent cx="3810000" cy="2286000"/><wp:docPr id="1" name="Picture 1" descr="Historic spend by quarter"/>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="chart.png"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="rId7"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="3810000" cy="2286000"/></a:xfrm>
<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>
</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>

<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>
<w:r><w:t>Invoices are payable within 30 days.</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>
<w:r><w:t>Late payment attracts statutory interest.</w:t></w:r></w:p>

<w:sectPr>
<w:headerReference w:type="default" r:id="rId5"/>
<w:footerReference w:type="default" r:id="rId6"/>
<w:pgSz w:w="11906" w:h="16838"/>
<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708"/>
</w:sectPr>
</w:body></w:document>'''


def make_png():
    """Минимальный валидный PNG 8x8, без внешних зависимостей."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    w = h = 8
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes([30, 92, 82] * w) for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _entry(name: str) -> zipfile.ZipInfo:
    """A zip entry with fixed metadata, so the build is reproducible.

    `create_system` has to be set explicitly. `ZipInfo.__init__` defaults it to
    0 on Windows and 3 everywhere else, and it is written into the central
    directory - so without this line the same content produces a different file
    on Windows, and the reproducibility check in CI fails there and only there.
    3 (Unix) is the value the committed fixture already has.
    """
    zi = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    zi.create_system = 3
    return zi


def build():
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    parts = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "word/document.xml": DOCUMENT,
        "word/_rels/document.xml.rels": DOC_RELS,
        "word/styles.xml": STYLES,
        "word/settings.xml": SETTINGS,
        "word/numbering.xml": NUMBERING,
        "word/footnotes.xml": FOOTNOTES,
        "word/comments.xml": COMMENTS,
        "word/header1.xml": HEADER,
        "word/footer1.xml": FOOTER,
        "docProps/core.xml": CORE,
        "docProps/app.xml": APP,
    }
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in list(parts.items()) + [("word/media/chart.png", make_png())]:
            z.writestr(_entry(name), data)
    print(f"built {OUT}  ({os.path.getsize(OUT)} bytes, {len(parts)+1} parts)")


if __name__ == "__main__":
    build()
