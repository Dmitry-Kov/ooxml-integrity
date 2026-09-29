#!/usr/bin/env python3
"""Sources for the review-history benchmark.

S2 starts as a small generated contract with no review markup. Its review
record is then written by Word for Mac, following a checklist declared before
Word runs: two authors, a comment thread, a resolved comment, a replacement,
another author's deletion inside an insertion, a moved list item, run and
paragraph formatting changes, and revisions in the header and an endnote. The
markup is Word's own, not ours.

    python research/review_history_sources.py build [--out DIR]
    python research/review_history_sources.py declare --word-version V
    python research/review_history_sources.py audit FILE

`build` writes review-base.docx byte-reproducibly. `declare` records the hashes
of the base, the checklist and this script before Word runs, and refuses to
overwrite. `audit` lists the review structures and the personal metadata in a
package, and exits 1 when an S2 requirement is not met or the package names
anyone other than the two declared reviewers. It does not import the checker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "review-history-benchmark"
SOURCES = EVIDENCE / "sources"
BASE_NAME = "review-base.docx"
CHECKLIST = SOURCES / "s2-word-checklist.md"
DECLARATION = SOURCES / "s2-declaration.json"
REVIEWERS = ("Reviewer A", "Reviewer B")

#: Fixed timestamp so the package is byte-reproducible.
ZIP_EPOCH = (2026, 1, 1, 0, 0, 0)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
W = "{" + W_NS + "}"

WNS = f'xmlns:w="{W_NS}"'
RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
CT = "application/vnd.openxmlformats-officedocument.wordprocessingml."
RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"

CONTENT_TYPES = DECL + f'''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="{CT}document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="{CT}styles+xml"/>
<Override PartName="/word/settings.xml" ContentType="{CT}settings+xml"/>
<Override PartName="/word/numbering.xml" ContentType="{CT}numbering+xml"/>
<Override PartName="/word/footnotes.xml" ContentType="{CT}footnotes+xml"/>
<Override PartName="/word/endnotes.xml" ContentType="{CT}endnotes+xml"/>
<Override PartName="/word/header1.xml" ContentType="{CT}header+xml"/>
<Override PartName="/word/footer1.xml" ContentType="{CT}footer+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''

ROOT_RELS = DECL + f'''<Relationships xmlns="{REL_NS}">
<Relationship Id="rId1" Type="{RT}officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="{RT}extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

DOC_RELS = DECL + f'''<Relationships xmlns="{REL_NS}">
<Relationship Id="rId1" Type="{RT}styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="{RT}settings" Target="settings.xml"/>
<Relationship Id="rId3" Type="{RT}numbering" Target="numbering.xml"/>
<Relationship Id="rId4" Type="{RT}footnotes" Target="footnotes.xml"/>
<Relationship Id="rId5" Type="{RT}endnotes" Target="endnotes.xml"/>
<Relationship Id="rId6" Type="{RT}header" Target="header1.xml"/>
<Relationship Id="rId7" Type="{RT}footer" Target="footer1.xml"/>
<Relationship Id="rId8" Type="{RT}hyperlink" Target="https://example.org/contacts" TargetMode="External"/>
</Relationships>'''

STYLES = DECL + f'''<w:styles {WNS}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="259" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="240"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:ind w:left="720"/><w:contextualSpacing/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="FootnoteText"><w:name w:val="footnote text"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="20"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="EndnoteText"><w:name w:val="endnote text"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="20"/></w:rPr></w:style>
<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont"><w:name w:val="Default Paragraph Font"/><w:uiPriority w:val="1"/><w:semiHidden/></w:style>
<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:basedOn w:val="DefaultParagraphFont"/><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="FootnoteReference"><w:name w:val="footnote reference"/><w:basedOn w:val="DefaultParagraphFont"/><w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="EndnoteReference"><w:name w:val="endnote reference"/><w:basedOn w:val="DefaultParagraphFont"/><w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>
<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/><w:semiHidden/>
<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>
<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:basedOn w:val="TableNormal"/>
<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>
<w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/>
<w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/>
<w:insideH w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="auto"/></w:tblBorders></w:tblPr></w:style>
</w:styles>'''

NUMBERING = DECL + f'''<w:numbering {WNS}>
<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/>
<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="(%1)"/><w:lvlJc w:val="left"/>
<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl>
</w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>'''

# trackRevisions is on, as in a document circulated for review: Word opens it
# with Track Changes enabled, so the checklist cannot silently start untracked.
SETTINGS = DECL + f'''<w:settings {WNS}>
<w:zoom w:percent="100"/>
<w:trackRevisions/>
<w:defaultTabStop w:val="720"/>
<w:characterSpacingControl w:val="doNotCompress"/>
<w:footnotePr><w:footnote w:id="-1"/><w:footnote w:id="0"/></w:footnotePr>
<w:endnotePr><w:endnote w:id="-1"/><w:endnote w:id="0"/></w:endnotePr>
<w:compat>
<w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
<w:compatSetting w:name="overrideTableStyleFontSizeAndJustification" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
<w:compatSetting w:name="enableOpenTypeFeatures" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
<w:compatSetting w:name="doNotFlipMirrorIndents" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
<w:compatSetting w:name="differentiateMultirowTableHeaders" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>
</w:compat>
</w:settings>'''


def _notes(kind: str, style: str, ref: str, text: str) -> str:
    sep = '<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r>'
    return DECL + f'''<w:{kind}s {WNS}>
<w:{kind} w:type="separator" w:id="-1">{sep}<w:separator/></w:r></w:p></w:{kind}>
<w:{kind} w:type="continuationSeparator" w:id="0">{sep}<w:continuationSeparator/></w:r></w:p></w:{kind}>
<w:{kind} w:id="1"><w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>
<w:r><w:rPr><w:rStyle w:val="{ref}"/></w:rPr><w:{kind}Ref/></w:r>
<w:r><w:t xml:space="preserve"> {text}</w:t></w:r></w:p></w:{kind}>
</w:{kind}s>'''


FOOTNOTES = _notes("footnote", "FootnoteText", "FootnoteReference",
                   "Business days exclude public holidays in England and Wales.")
ENDNOTES = _notes("endnote", "EndnoteText", "EndnoteReference",
                  "Company details are taken from the public register on 1 September 2026.")

HEADER = DECL + f'''<w:hdr {WNS}><w:p><w:pPr><w:jc w:val="right"/></w:pPr>
<w:r><w:t>Consulting Services Agreement - Draft 3</w:t></w:r></w:p></w:hdr>'''

FOOTER = DECL + f'''<w:ftr {WNS}><w:p><w:pPr><w:jc w:val="center"/></w:pPr>
<w:r><w:t>Confidential</w:t></w:r></w:p></w:ftr>'''

CORE = DECL + f'''<cp:coreProperties xmlns:cp="{CP_NS}"
xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Consulting Services Agreement</dc:title><dc:creator>review-history-sources</dc:creator>
<cp:revision>3</cp:revision></cp:coreProperties>'''

APP = DECL + f'''<Properties xmlns="{EP_NS}">
<Application>review-history-sources</Application></Properties>'''


def _p(text: str, style: str = "", extra: str = "") -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{text}</w:t></w:r>{extra}</w:p>'


def _item(text: str) -> str:
    return ('<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/>'
            f'<w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>')


def _cell(text: str, bold: bool = False) -> str:
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return (f'<w:tc><w:tcPr><w:tcW w:w="3009" w:type="dxa"/></w:tcPr>'
            f'<w:p><w:r>{rpr}<w:t>{text}</w:t></w:r></w:p></w:tc>')


def _row(cells: tuple[str, str, str], header: bool = False) -> str:
    trpr = "<w:trPr><w:tblHeader/></w:trPr>" if header else ""
    return f'<w:tr>{trpr}{"".join(_cell(c, header) for c in cells)}</w:tr>'


def _note_ref(kind: str, style: str) -> str:
    return f'<w:r><w:rPr><w:rStyle w:val="{style}"/></w:rPr><w:{kind}Reference w:id="1"/></w:r>'


BODY = "\n".join([
    _p("Consulting Services Agreement", "Heading1"),
    _p("This agreement is made between Alder Street Analytics Ltd (the Client) and "
       "Kestrel Point Consulting LLP (the Consultant).", "",
       _note_ref("endnote", "EndnoteReference")),
    '<w:sdt><w:sdtPr><w:alias w:val="Contract Reference"/><w:tag w:val="contract_ref"/>'
    '<w:id w:val="918204"/><w:text/></w:sdtPr><w:sdtContent>'
    + _p("Contract reference: CSA-2026-0918") + "</w:sdtContent></w:sdt>",
    _p("1. Term", "Heading2"),
    _p("The Consultant shall provide the Services from the Effective Date until the "
       "Completion Date."),
    _p("2. Consultant Obligations", "Heading2"),
    _p("The Consultant shall:"),
    _item("Attend a monthly steering meeting with the Client."),
    _item("Maintain professional indemnity insurance of at least EUR 1,000,000."),
    _item("Comply with the Client's information security policy."),
    _p("3. Reporting", "Heading2"),
    _p("The Consultant shall deliver a monthly progress report within ten business days "
       "after the end of each month.", "", _note_ref("footnote", "FootnoteReference")),
    _p("4. Fees", "Heading2"),
    _p("Fees are payable within thirty days of receipt of a valid invoice."),
    '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>'
    '<w:tblGrid><w:gridCol w:w="3009"/><w:gridCol w:w="3009"/><w:gridCol w:w="3009"/></w:tblGrid>'
    + _row(("Milestone", "Due date", "Fee"), header=True)
    + _row(("Discovery", "15 October 2026", "EUR 12,000"))
    + _row(("Final report", "18 December 2026", "EUR 30,500")) + "</w:tbl>",
    _p("5. Liability", "Heading2"),
    _p("Neither party limits its liability for fraud or gross negligence."),
    _p("6. Termination", "Heading2"),
    _p("Either party may terminate this agreement on sixty days' written notice."),
    _p("7. Notices", "Heading2"),
    '<w:p><w:r><w:t xml:space="preserve">Notices must be sent to the addresses listed on the </w:t></w:r>'
    '<w:hyperlink r:id="rId8"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr>'
    '<w:t>Client contact page</w:t></w:r></w:hyperlink><w:r><w:t>.</w:t></w:r></w:p>',
])

DOCUMENT = DECL + f'''<w:document {WNS} {RNS}>
<w:body>
{BODY}
<w:sectPr>
<w:headerReference w:type="default" r:id="rId6"/>
<w:footerReference w:type="default" r:id="rId7"/>
<w:pgSz w:w="11906" w:h="16838"/>
<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
</w:sectPr>
</w:body></w:document>'''

PARTS = {
    "[Content_Types].xml": CONTENT_TYPES,
    "_rels/.rels": ROOT_RELS,
    "word/document.xml": DOCUMENT,
    "word/_rels/document.xml.rels": DOC_RELS,
    "word/styles.xml": STYLES,
    "word/settings.xml": SETTINGS,
    "word/numbering.xml": NUMBERING,
    "word/footnotes.xml": FOOTNOTES,
    "word/endnotes.xml": ENDNOTES,
    "word/header1.xml": HEADER,
    "word/footer1.xml": FOOTER,
    "docProps/core.xml": CORE,
    "docProps/app.xml": APP,
}


def _entry(name: str) -> zipfile.ZipInfo:
    """A zip entry with fixed metadata; see research/build_corpus.py."""
    zi = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    zi.create_system = 3
    return zi


def build(out: Path = SOURCES) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / BASE_NAME
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in PARTS.items():
            z.writestr(_entry(name), data)
    return path


# --- audit -----------------------------------------------------------------

#: S2 requirements, declared before Word runs. Each names the author, story and
#: text of one structure the checklist asks Word to write.
REQUIREMENTS = {
    "authors": "Every revision, comment and person names Reviewer A or Reviewer B, and both appear.",
    "comment-thread": "A comment by Reviewer A anchored on 'Completion Date' has a reply by "
                      "Reviewer B, and the thread is not resolved.",
    "comment-resolved": "A comment by Reviewer A anchored on 'EUR 12,000' in a table cell is resolved.",
    "replacement": "Reviewer A deletes 'thirty' and inserts 'forty-five' in the body.",
    "nested-deletion": "Reviewer B deletes 'any' inside Reviewer A's insertion of "
                       "'The Client may withhold any disputed amount.'",
    "move": "Reviewer A moves 'Comply with the Client's information security policy.' "
            "(moveFrom and moveTo).",
    "run-format-change": "Reviewer B's run formatting change on 'gross negligence' makes it bold.",
    "paragraph-format-change": "Reviewer B's paragraph formatting change on the paragraph "
                               "containing 'sixty days'.",
    "header-revision": "Reviewer A changes 'Draft 3' to 'Draft 4' in the header.",
    "endnote-revision": "Reviewer B changes '1 September' to '15 September' in the endnote.",
    "privacy": "No e-mail address, presence identity, sensitivity label or company name, and "
               "lastModifiedBy is a declared reviewer.",
}

PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
REVISION_KINDS = ("ins", "del", "moveFrom", "moveTo", "rPrChange", "pPrChange")
STORY_TYPES = ("header", "footer", "footnotes", "endnotes")


def _xml(z: zipfile.ZipFile, name: str):
    return etree.fromstring(z.read(name), PARSER) if name in z.namelist() else None


def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(W + "t", W + "delText"))


def _rels(z: zipfile.ZipFile, part: str = "word/document.xml") -> list[tuple[str, str]]:
    """(relationship type suffix, target part name) for one source part."""
    folder, name = part.rsplit("/", 1)
    rels = _xml(z, f"{folder}/_rels/{name}.rels")
    found = []
    for rel in [] if rels is None else rels:
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target", "")
        target = target.lstrip("/") if target.startswith("/") else f"{folder}/{target}"
        found.append((rel.get("Type", "").rsplit("/", 1)[-1], target))
    return sorted(found)


def _related(z: zipfile.ZipFile, kind: str):
    """The main part's first related part of one type, parsed, or None."""
    return next((_xml(z, t) for k, t in _rels(z) if k == kind), None)


def _stories(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    return [("document", "word/document.xml")] + [
        (kind, target) for kind, target in _rels(z) if kind in STORY_TYPES]


def _revisions(stories) -> list[dict]:
    found = []
    for story, root in stories:
        for kind in REVISION_KINDS:
            for el in root.iter(W + kind):
                if kind in ("rPrChange", "pPrChange"):
                    owner = el.getparent().getparent()
                    text = _text(owner)
                    detail = {"bold_now": el.getparent().find(W + "b") is not None}
                else:
                    text = _text(el)
                    detail = {}
                outer = next((a for a in el.iterancestors(W + "ins")), None)
                if kind == "del" and outer is not None:
                    detail["inside_insertion_by"] = outer.get(W + "author")
                    detail["insertion_text"] = _text(outer)
                found.append({"story": story, "kind": kind, "author": el.get(W + "author"),
                              "text": text, **detail})
    return found


def _anchors(stories) -> dict[str, dict]:
    """Comment id -> story and the text between its range start and end."""
    anchors: dict[str, dict] = {}
    for story, root in stories:
        open_ids: dict[str, list[str]] = {}
        for el in root.iter():
            if el.tag == W + "commentRangeStart":
                open_ids[el.get(W + "id")] = []
            elif el.tag == W + "commentRangeEnd":
                cid = el.get(W + "id")
                if cid in open_ids:
                    anchors[cid] = {"story": story, "text": "".join(open_ids.pop(cid)),
                                    "in_table": any(True for _ in el.iterancestors(W + "tc"))}
            elif el.tag in (W + "t", W + "delText"):
                for parts in open_ids.values():
                    parts.append(el.text or "")
    return anchors


def _comments(z: zipfile.ZipFile, stories) -> list[dict]:
    comments = _related(z, "comments")
    if comments is None:
        return []
    extended = {}
    ext = _related(z, "commentsExtended")
    if ext is not None:
        for ex in ext.iter("{%s}commentEx" % W15_NS):
            extended[ex.get("{%s}paraId" % W15_NS)] = ex
    anchors = _anchors(stories)
    para_to_id = {}
    found = []
    for c in comments.iter(W + "comment"):
        paras = c.findall(W + "p")
        para_id = paras[-1].get("{%s}paraId" % W14_NS) if paras else None
        para_to_id[para_id] = c.get(W + "id")
        ex = extended.get(para_id)
        found.append({
            "id": c.get(W + "id"), "author": c.get(W + "author"),
            "initials": c.get(W + "initials"), "text": _text(c).strip(),
            "anchor": anchors.get(c.get(W + "id")),
            "parent_para": None if ex is None else ex.get("{%s}paraIdParent" % W15_NS),
            "done": None if ex is None else ex.get("{%s}done" % W15_NS) == "1",
        })
    for item in found:
        item["reply_to"] = para_to_id.get(item.pop("parent_para"))
    return found


def _privacy(z: zipfile.ZipFile, people: list[dict]) -> dict:
    core = _xml(z, "docProps/core.xml")
    app = _xml(z, "docProps/app.xml")
    modified_by = core.findtext("{%s}lastModifiedBy" % CP_NS) if core is not None else None
    company = app.findtext("{%s}Company" % EP_NS) if app is not None else None
    emails, labels = set(), set()
    for name in z.namelist():
        if name.endswith((".xml", ".rels")):
            data = z.read(name).decode("utf-8", "replace")
            emails |= set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", data))
            labels |= set(re.findall(r"MSIP_Label_[\w-]+", data))
    return {"last_modified_by": modified_by, "company": company or None,
            "emails": sorted(emails), "sensitivity_labels": sorted(labels),
            "presence": [p for p in people if p["provider"] not in (None, "None")],
            "custom_properties": "docProps/custom.xml" in z.namelist()}


def _people(z: zipfile.ZipFile) -> list[dict]:
    root = _related(z, "people")
    if root is None:
        return []
    found = []
    for person in root.iter("{%s}person" % W15_NS):
        presence = person.find("{%s}presenceInfo" % W15_NS)
        found.append({
            "author": person.get("{%s}author" % W15_NS),
            "provider": None if presence is None else presence.get("{%s}providerId" % W15_NS),
            "user_id": None if presence is None else presence.get("{%s}userId" % W15_NS),
        })
    return found


def audit(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        stories = [(kind, _xml(z, part)) for kind, part in _stories(z) if part in z.namelist()]
        revisions = _revisions(stories)
        comments = _comments(z, stories)
        people = _people(z)
        privacy = _privacy(z, people)
    return {"revisions": revisions, "comments": comments, "people": people,
            "privacy": privacy, "requirements": _requirements(revisions, comments, people, privacy)}


def _has(revisions, story, kind, author, needle) -> bool:
    return any(r["story"] == story and r["kind"] == kind and r["author"] == author
               and needle in r["text"] for r in revisions)


def _requirements(revisions, comments, people, privacy) -> dict[str, bool]:
    a, b = REVIEWERS
    names = ([r["author"] for r in revisions] + [c["author"] for c in comments]
             + [p["author"] for p in people])
    by_anchor = {needle: [c for c in comments if c["anchor"] and c["author"] == a
                          and needle in c["anchor"]["text"]]
                 for needle in ("Completion Date", "EUR 12,000")}
    thread = [c for c in by_anchor["Completion Date"]
              if any(r["reply_to"] == c["id"] and r["author"] == b for r in comments)]
    moved = "information security policy"
    return {
        "authors": bool(names) and set(names) == set(REVIEWERS),
        "comment-thread": any(c["done"] is False for c in thread),
        "comment-resolved": any(c["done"] and c["anchor"]["in_table"]
                                for c in by_anchor["EUR 12,000"]),
        "replacement": _has(revisions, "document", "del", a, "thirty")
        and _has(revisions, "document", "ins", a, "forty-five"),
        "nested-deletion": any(
            r["story"] == "document" and r["kind"] == "del" and r["author"] == b
            and r["text"].strip() == "any" and r.get("inside_insertion_by") == a
            and "withhold" in r["insertion_text"] for r in revisions),
        "move": _has(revisions, "document", "moveFrom", a, moved)
        and _has(revisions, "document", "moveTo", a, moved),
        "run-format-change": any(
            r["kind"] == "rPrChange" and r["author"] == b and r["bold_now"]
            and "gross negligence" in r["text"] for r in revisions),
        "paragraph-format-change": _has(revisions, "document", "pPrChange", b, "sixty days"),
        "header-revision": _has(revisions, "header", "ins", a, "4"),
        "endnote-revision": _has(revisions, "endnotes", "ins", b, "5"),
        "privacy": not (privacy["emails"] or privacy["sensitivity_labels"]
                        or privacy["presence"] or privacy["company"]
                        or privacy["custom_properties"])
        and privacy["last_modified_by"] in REVIEWERS,
    }


# --- declaration -------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def declare(word_version: str) -> dict:
    record = {
        "declared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "purpose": "S2 review-history source: Word for Mac writes the review record "
                   "by following the checklist; nothing else edits the document.",
        "word_for_mac": word_version,
        "base": {"path": f"evidence/review-history-benchmark/sources/{BASE_NAME}",
                 "sha256": _sha256(SOURCES / BASE_NAME)},
        "checklist": {"path": "evidence/review-history-benchmark/sources/s2-word-checklist.md",
                      "sha256": _sha256(CHECKLIST)},
        "audit_script": {"path": "research/review_history_sources.py",
                         "sha256": _sha256(Path(__file__))},
        "requirements": REQUIREMENTS,
    }
    with DECLARATION.open("x", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
        f.write("\n")
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_build = sub.add_parser("build")
    p_build.add_argument("--out", type=Path, default=SOURCES)
    p_declare = sub.add_parser("declare")
    p_declare.add_argument("--word-version", required=True)
    p_audit = sub.add_parser("audit")
    p_audit.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    if args.command == "build":
        print(build(args.out))
        return 0
    if args.command == "declare":
        print(json.dumps(declare(args.word_version), indent=2))
        return 0
    report = audit(args.file)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if all(report["requirements"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
