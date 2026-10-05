"""Anonymize a DOCX, or a source/edited pair, so it can be shared.

A defect report is most useful with the documents that show it, and the
documents are usually confidential. This module rewrites the content of a
package and keeps its structure: every element, attribute, id and
relationship stays where it was, so the checker sees the same package with
other words in it.

What is replaced:

- Text. Each word becomes a replacement of the same length and character
  classes (upper, lower, digit), drawn at random for this run. The same word
  becomes the same replacement everywhere, in every file of the run, and two
  different words never share one while the alphabet allows; that is what
  keeps comparisons between a source and its edited copy meaningful.
  Whitespace, punctuation and numeric character references stay as they are.
  Words are read across runs, so a word split by a comment anchor or a
  formatting change is still one word, and as the paragraph reads with new
  tracked changes rejected, which is what the checker compares.
- People. Revision, comment and people-part authors become ``Author 1``,
  ``Author 2``, ...; a comment's initials follow its author (``A1``, ``A2``).
- Time. Every date is moved by one random offset, so order and equality
  survive and the real dates do not.
- Everything else that can carry content: document properties, alternative
  text, hyperlink and other external targets, field instructions, custom
  style names, content control titles and tags, document variables, mail
  merge sources, custom XML. Element text in a part this module has no rule
  for is replaced too.
- Pictures become 1x1 placeholders of the same format, embedded workbooks an
  empty workbook; other embedded objects and binary parts become empty.
  Embedded fonts are kept.

What is kept: the structure itself, built-in style names, font names,
numbering formats, cell references in chart formulas, paragraph and revision
ids, and the length and position of every word. A reader of the result learns
the shape of the document, not its text.

Afterwards the checker runs on the originals and on the results. The report
says whether every finding was reproduced, and lists the places where words
of the original text still occur in the results. docs/anonymize.md is the
user's account of the same, and evidence/anonymize the measurement.
"""
from __future__ import annotations

import base64
import collections
import datetime as _dt
import difflib
import random
import re
import shutil
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from lxml import etree

from .archive import DEFAULT_ARCHIVE_LIMITS, ArchiveLimits, read_package
from .xmlutil import UnsafeXML, fromstring

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
W15 = "{http://schemas.microsoft.com/office/word/2012/wordml}"
W16DU = "{http://schemas.microsoft.com/office/word/2023/wordml/word16du}"
W16CEX = "{http://schemas.microsoft.com/office/word/2018/wordml/cex}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
WP14 = "{http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing}"
C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
V = "{urn:schemas-microsoft-com:vml}"
O = "{urn:schemas-microsoft-com:office:office}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
EP = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
VT = "{http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes}"
CUSTOM = "{http://schemas.openxmlformats.org/officeDocument/2006/custom-properties}"
DCTERMS = "{http://purl.org/dc/terms/}"
CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"
THM15 = "{http://schemas.microsoft.com/office/thememl/2012/main}"

MAIN_DOCX = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "application/vnd.ms-word.document.macroEnabled.main+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
)

#: Namespaces whose attributes are structural unless listed below. In a part
#: whose root is in none of them (custom XML data, sensitivity labels, ink),
#: every attribute value is replaced as text. Office's own parts belong here:
#: an enumeration replaced in a chart style makes Word refuse the file.
KNOWN_NAMESPACES = frozenset(ns.strip("{}") for ns in (
    W, W14, W15, W16DU, W16CEX, A, M, WP, WP14, C, V, O, REL, CT, EP, VT, CUSTOM, DCTERMS, CP,
    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}",
    "{http://schemas.openxmlformats.org/drawingml/2006/picture}",
    "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}",
    "{http://schemas.microsoft.com/office/word/2010/wordprocessingGroup}",
    "{http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas}",
    "{http://schemas.openxmlformats.org/drawingml/2006/diagram}",
    "{http://schemas.microsoft.com/office/drawing/2008/diagram}",
    "{http://schemas.openxmlformats.org/drawingml/2006/chartDrawing}",
    "{http://schemas.openxmlformats.org/markup-compatibility/2006}",
    "{urn:schemas-microsoft-com:office:word}",
    "{http://schemas.microsoft.com/office/word/2006/wordml}",
    "{http://schemas.openxmlformats.org/officeDocument/2006/customXml}",
    "{http://purl.org/dc/elements/1.1/}",
    "{http://purl.org/dc/dcmitype/}",
    "{http://www.w3.org/2001/XMLSchema-instance}",
    "{http://schemas.microsoft.com/office/word/2018/wordml}",
    "{http://schemas.microsoft.com/office/word/2016/wordml/cid}",
    "{http://schemas.microsoft.com/office/word/2015/wordml/symex}",
    "{http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash}",
    "{http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock}",
    "{http://schemas.microsoft.com/office/drawing/2010/main}",
    "{http://schemas.microsoft.com/office/drawing/2014/main}",
    "{http://schemas.microsoft.com/office/drawing/2016/SVG/main}",
    "{http://schemas.microsoft.com/office/thememl/2012/main}",
    "{http://schemas.microsoft.com/office/drawing/2014/chartex}",
    "{http://schemas.microsoft.com/office/drawing/2012/chartStyle}",
    "{http://schemas.microsoft.com/office/2006/activeX}",
    "{http://schemas.microsoft.com/office/webextensions/webextension/2010/11}",
    "{http://schemas.microsoft.com/office/webextensions/taskpanes/2010/11}",
))
#: Never replaced, in any part: relationship ids, markup compatibility, xml:*.
RESERVED_NAMESPACES = (
    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}",
    "{http://schemas.openxmlformats.org/markup-compatibility/2006}",
    "{http://www.w3.org/XML/1998/namespace}",
)

#: Elements whose text is read as one paragraph-level stream.
TEXT_TAGS = frozenset((W + "t", W + "delText", W + "instrText", W + "delInstrText",
                       M + "t", A + "t"))
BLOCK_TAGS = frozenset((W + "p", A + "p"))
#: Visible boundaries inside a paragraph: a word does not continue across them.
#: Invisible markers (comment and bookmark ranges, proofing marks, soft
#: hyphens, rendered page breaks) are not boundaries, so a word split by one
#: is still one word.
SEPARATOR_TAGS = frozenset(W + t for t in (
    "tab", "ptab", "br", "cr", "noBreakHyphen", "sym", "fldChar", "footnoteReference",
    "endnoteReference", "commentReference", "annotationRef", "footnoteRef", "endnoteRef",
    "separator", "continuationSeparator", "drawing", "object", "pict", "pgNum",
    "dayShort", "dayLong", "monthShort", "monthLong", "yearShort", "yearLong",
    "contentPart",
)) | {A + "br", A + "fld"}

#: Element text that is structure, not content.
KEEP_TEXT = frozenset((
    WP + "posOffset", WP + "align", WP14 + "pctWidth", WP14 + "pctHeight",
    WP14 + "pctPosHOffset", WP14 + "pctPosVOffset", C + "formatCode", VT + "bool",
    VT + "i4", CP + "revision",
)) | {EP + t for t in (
    "Application", "AppVersion", "DocSecurity", "ScaleCrop", "LinksUpToDate",
    "SharedDoc", "HyperlinksChanged", "Pages", "Words", "Characters", "Lines",
    "Paragraphs", "CharactersWithSpaces", "TotalTime",
)}
DATE_TEXT = frozenset((DCTERMS + "created", DCTERMS + "modified", CP + "lastPrinted",
                       VT + "filetime", VT + "date"))
CX = "{http://schemas.microsoft.com/office/drawing/2014/chartex}"
#: Chart data references: the sheet names are replaced, the cell references
#: kept. A range of another shape than the chart's data makes Word refuse
#: the file, and a cell address says nothing about the content.
FORMULA_TEXT = frozenset((C + "f", CX + "f"))
SHEET_NAME = re.compile(r"('?)([^'!(),]+?)\1(?=!)")

AUTHOR_ATTRS = frozenset((W + "author", W15 + "author"))
INITIALS_ATTRS = frozenset((W + "initials",))
DATE_ATTRS = frozenset((W + "date", W16DU + "dateUtc", W16CEX + "dateUtc", W + "fullDate"))
#: Attributes that carry text on any element.
TEXT_ATTRS = frozenset((
    W + "tooltip", W + "anchor", W + "instr", W15 + "userId", W + "ed",
    V + "alt", O + "title", "string", "alt", "title", "descr", "tooltip", "phldrT",
))
#: Hyperlink addresses written on VML shapes.
HREF_ATTRS = frozenset(("href", O + "href"))
#: Attributes that carry text on specific elements.
TEXT_ATTRS_ON = {
    W + "bookmarkStart": {W + "name"},
    W + "moveFromRangeStart": {W + "name"},
    W + "moveToRangeStart": {W + "name"},
    W + "docVar": {W + "name", W + "val"},
    W + "alias": {W + "val"},
    W + "tag": {W + "val"},
    W + "tblCaption": {W + "val"},
    W + "tblDescription": {W + "val"},
    W + "helpText": {W + "val"},
    W + "statusText": {W + "val"},
    W + "listEntry": {W + "val"},
    W + "default": {W + "val"},
    W + "format": {W + "val"},
    W + "entryMacro": {W + "val"},
    W + "exitMacro": {W + "val"},
    W + "listItem": {W + "displayText", W + "value"},
    W + "attr": {W + "val"},
    W + "docPart": {W + "val"},
    W + "control": {W + "name"},
    CUSTOM + "property": {"name"},
    # mail merge: data source connection, query and field names
    W + "connectString": {W + "val"},
    W + "query": {W + "val"},
    W + "udl": {W + "val"},
    W + "table": {W + "val"},
    W + "mappedName": {W + "val"},
    W + "addressFieldName": {W + "val"},
    W + "mailSubject": {W + "val"},
    A + "theme": {"name"},
    A + "clrScheme": {"name"},
    A + "fontScheme": {"name"},
    A + "fmtScheme": {"name"},
    THM15 + "themeFamily": {"name"},
    # ActiveX control properties (captions, values) and web add-in settings
    "{http://schemas.microsoft.com/office/2006/activeX}ocxPr":
        {"{http://schemas.microsoft.com/office/2006/activeX}value"},
    "{http://schemas.microsoft.com/office/webextensions/webextension/2010/11}property": {"value"},
}
#: Elements whose own name child is content (form fields, building blocks,
#: mail merge field maps).
NAMED_PARENTS = frozenset((W + "ffData", W + "docPartPr", W + "category", W + "fieldMapData"))
CNVPR = re.compile(r"\}(?:c)?NvPr$|\}docPr$")
#: VML shapes repeat the drawing's object name as their id in the fallback
#: of a DrawingML object. Ids Word generates (``_x0000_s1026``) are kept;
#: any other id is replaced, and so is every reference to it. Shape types
#: are referenced by id and kept.
VML_SHAPES = frozenset(V + t for t in (
    "shape", "rect", "roundrect", "oval", "line", "polyline", "arc", "curve", "group", "image"))
SHAPE_REFERENCES = frozenset(("ShapeID", W + "shapeid", "idref", O + "spid", "spid"))
GENERATED_ID = re.compile(r"^_x[0-9A-Fa-f]{4}_[A-Za-z]*\d*$")

PROTECTED = re.compile(r"&(?:amp;)?#(?:[0-9]+|[xX][0-9a-fA-F]+);")
URL_SCHEME = re.compile(r"^(?:https?|mailto|file|ftp|ftps|news|tel):(?://)?", re.I)
DATE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(\.\d+)?)?)?(Z|[+-]\d{2}:\d{2})?$")

UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"

FONT_PARTS = re.compile(r"(?:^|/)fonts/|\.(?:odttf|ttf|otf|fntdata)$", re.I)
IMAGES = {
    "png": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGP4DwABAQEAsTj2FAAAAABJRU5ErkJggg==",
    "gif": "R0lGODdhAQABAIEAAP///wAAAAAAAAAAACwAAAAAAQABAAAIBAABBAQAOw==",
    "bmp": "Qk1CAAAAAAAAAD4AAAAoAAAAAQAAAAEAAAABAAEAAAAAAAQAAADEDgAAxA4AAAIAAAACAAAAAAAAAP///wCAAAAA",
    "tiff": ("SUkqAAgAAAAIAAABBAABAAAAAQAAAAEBBAABAAAAAQAAAAMBAwABAAAAAQAAAAYBAwABAAAAAQAAABEBBAABAAAA"
             "bgAAABYBBAABAAAAAQAAABcBBAABAAAAAQAAABwBAwABAAAAAQAAAAAAAACA"),
    "jpeg": ("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxO"
             "QERXRTc4UG1RV19iZ2hnPk1xeXBkeFxlZ2P/wAALCAABAAEBAREA/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAEC"
             "AwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAk"
             "M2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJ"
             "ipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3"
             "+Pn6/9oACAEBAAA/APQK/9k="),
}


def _wmf() -> bytes:
    """A placeable WMF holding nothing: placeable header, header, EOF."""
    import struct
    words = struct.unpack("<10H", struct.pack("<IHhhhhHI", 0x9AC6CDD7, 0, 0, 0, 1, 1, 1440, 0))
    checksum = 0
    for word in words:
        checksum ^= word
    placeable = struct.pack("<IHhhhhHIH", 0x9AC6CDD7, 0, 0, 0, 1, 1, 1440, 0, checksum)
    header = struct.pack("<HHHIHIH", 1, 9, 0x0300, 12, 0, 3, 0)
    return placeable + header + struct.pack("<IH", 3, 0)


def _emf() -> bytes:
    """An EMF holding nothing: EMR_HEADER and EMR_EOF."""
    import struct
    header = struct.pack("<II4i4iIIIIHHIIIiiii", 1, 88, 0, 0, 0, 0, 0, 0, 26, 26,
                         0x464D4520, 0x10000, 108, 2, 1, 0, 0, 0, 0, 1920, 1080, 508, 286)
    return header + struct.pack("<IIIII", 14, 20, 0, 16, 20)


def _blank_workbook() -> bytes:
    """An empty workbook with one sheet: what an embedded spreadsheet becomes.

    Word opens a chart's embedded workbook with the document; an empty part
    there makes it offer to repair the file.
    """
    import io
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    kind = "application/vnd.openxmlformats-officedocument.spreadsheetml"
    parts = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Override PartName="/xl/workbook.xml" ContentType="{kind}.sheet.main+xml"/>'
            f'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="{kind}.worksheet+xml"/>'
            '</Types>',
        "_rels/.rels":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg}">'
            f'<Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        "xl/workbook.xml":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{main}" '
            f'xmlns:r="{rel}"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>',
        "xl/_rels/workbook.xml.rels":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg}">'
            f'<Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>',
        "xl/worksheets/sheet1.xml":
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{main}">'
            '<sheetData/></worksheet>',
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in parts.items():
            z.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), text)
    return buffer.getvalue()


def placeholder(name: str) -> bytes | None:
    """Bytes of a 1x1 picture in the format `name`'s extension names; None if unknown."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    ext = {"jpg": "jpeg", "jpe": "jpeg", "jfif": "jpeg", "tif": "tiff", "dib": "bmp"}.get(ext, ext)
    if ext in IMAGES:
        return base64.b64decode(IMAGES[ext])
    if ext == "wmf":
        return _wmf()
    if ext == "emf":
        return _emf()
    if ext == "svg":
        return b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'
    if ext in ("xlsx", "xlsm"):
        return _blank_workbook()
    return None


def _word_char(char: str) -> bool:
    return unicodedata.category(char)[0] in "LNM"


_ESCAPE = re.compile(r"^x[0-9A-Fa-f]{4}$")


def _phrase_word(token: str) -> bool:
    """Counts toward a phrase: two characters or more, at least one a letter,
    and not Word's ``_x0000_`` escape, which generated ids are made of."""
    return len(token) >= 2 and any(c.isalpha() for c in token) and not _ESCAPE.match(token)


class Mapper:
    """One replacement table for every file of one run."""

    def __init__(self, rng: random.Random | None = None):
        self._rng = rng or random.SystemRandom()
        self._words: dict[str, str] = {}
        self._taken: set[str] = set()
        self._people: dict[str, str] = {}
        self._initials: dict[str, str] = {}
        days = self._rng.randint(365, 3650)
        self._shift = _dt.timedelta(days=days, seconds=self._rng.randint(0, 86399))
        self.collisions = 0
        self.dates = 0
        self.replaced = 0
        self.vocabulary: set[str] = set()
        #: pairs of consecutive words of the original text
        self.phrases: set[tuple[str, str]] = set()
        #: style ids marked w:customStyle in any styles part read so far
        self.custom_styles: set[str] = set()
        #: the source's inserted text per insertion context: (text, replacement)
        self.inserted: dict[tuple, list[tuple[str, str]]] = collections.defaultdict(list)
        self.reading_source = True

    def _draw(self, token: str) -> str:
        out = []
        for char in token:
            if unicodedata.category(char) == "Nd":
                out.append(self._rng.choice(DIGITS))
            elif char.isupper():
                out.append(self._rng.choice(UPPER))
            else:
                out.append(self._rng.choice(LOWER))
        return "".join(out)

    def word(self, token: str) -> str:
        out = self._words.get(token)
        if out is not None:
            return out
        # Distinct from every other replacement; for words long enough to be
        # recognised, also from the word itself and from every word of the
        # text. A short token (a digit, a one-letter word) may stay itself
        # when nothing else is left: the alphabet is that small.
        recognisable = len(token) >= 4
        for attempt in range(128):
            out = self._draw(token)
            if out in self._taken:
                continue
            if attempt < 64 and (out == token or (recognisable and out in self.vocabulary)):
                continue
            break
        else:
            self.collisions += 1
        self._words[token] = out
        self._taken.add(out)
        self.vocabulary.add(token)
        return out

    def text(self, text: str) -> str:
        """Replace every word of `text`, keeping everything between words."""
        if not text:
            return text
        protected = [False] * len(text)
        for match in PROTECTED.finditer(text):
            for i in range(match.start(), match.end()):
                protected[i] = True
        out, start, previous = [], None, None
        for i, char in enumerate(text + "\0"):
            inside = i < len(text) and not protected[i] and _word_char(char)
            if inside and start is None:
                start = i
            elif not inside and start is not None:
                token = text[start:i]
                out.append(self.word(token))
                self.replaced += 1
                if previous is not None and _phrase_word(previous) and _phrase_word(token):
                    self.phrases.add((previous, token))
                previous, start = token, None
            if i < len(text) and not inside:
                out.append(char)
        return "".join(out)

    def formula(self, value: str) -> str:
        """A chart formula: sheet names replaced, cell references kept."""
        return SHEET_NAME.sub(lambda m: m.group(1) + self.text(m.group(2)) + m.group(1), value)

    def target(self, value: str) -> str:
        """An external target: keep a known scheme, replace the rest."""
        match = URL_SCHEME.match(value)
        head = match.group(0) if match else ""
        return head + self.text(value[len(head):])

    def person(self, name: str) -> str:
        if name not in self._people:
            self._people[name] = f"Author {len(self._people) + 1}"
            self.vocabulary.update(t for t in re.split(r"\W+", name) if t)
        return self._people[name]

    def initials(self, value: str, author: str | None = None) -> str:
        """``A<n>`` for the author on the same element, so a comment by
        ``Author 2`` has initials ``A2``; otherwise numbered on their own."""
        if author is not None:
            return "A" + self.person(author).rsplit(" ", 1)[-1]
        if value not in self._initials:
            self._initials[value] = f"I{len(self._initials) + 1}"
        return self._initials[value]

    def date(self, value: str) -> str:
        match = DATE.match(value.strip())
        if not match:
            return self.text(value)
        year, month, day, hour, minute, second, fraction, zone = match.groups()
        try:
            moment = _dt.datetime(int(year), int(month), int(day), int(hour or 0),
                                  int(minute or 0), int(second or 0))
            moment -= self._shift
        except (ValueError, OverflowError):
            return self.text(value)
        self.dates += 1
        out = moment.strftime("%Y-%m-%d")
        if hour is not None:
            out += moment.strftime("T%H:%M")
            if second is not None:
                out += moment.strftime(":%S") + (fraction or "")
        return out + (zone or "")

    def known_insertion(self, context: tuple, text: str) -> str:
        """Replace text inside an insertion the source already had.

        In the source, remember it. In the edited copy, align it with the
        source's text of the same insertion and give every character the
        alignment matches the source's replacement: text a tool added inside
        another author's insertion, even inside a word, then still reads as
        the source text plus additions, which is what FID011 looks for.
        """
        mapped = self.text(text)
        if self.reading_source:
            self.inserted[context].append((text, mapped))
            return mapped
        candidates = self.inserted.get(context, ())
        if not candidates or any(text == old for old, _ in candidates):
            return mapped
        old, old_mapped = max(candidates, key=lambda c: difflib.SequenceMatcher(
            None, c[0], text, autojunk=False).ratio())
        out = list(mapped)
        matcher = difflib.SequenceMatcher(None, old, text, autojunk=False)
        for i, j, size in matcher.get_matching_blocks():
            out[j:j + size] = old_mapped[i:i + size]
        return "".join(out)

    @property
    def replacements(self) -> set[str]:
        """Every replacement word; one that is also a word of the text is chance."""
        return set(self._taken)

    @property
    def people(self) -> int:
        return len(self._people)

    @property
    def distinct(self) -> int:
        return len(self._words)


INSERTIONS = frozenset((W + "ins", W + "moveTo"))


def _context(node) -> tuple:
    return (node.tag, node.get(W + "author"), node.get(W + "date"))


def _lane(node, known: set | None) -> tuple[str, tuple | None]:
    """Which reading of the paragraph a text node belongs to.

    ``base`` is text outside insertions: the paragraph as it reads with
    every new change rejected, which is what the checker compares with the
    source. ``known`` is text inside insertions the source already had, and
    ``new`` text inside an insertion the source did not have. `known` is
    None for the source itself, where every insertion is known.
    """
    contexts = [_context(a) for a in node.iterancestors() if a.tag in INSERTIONS]
    if not contexts:
        return "base", None
    if known is None or all(c in known for c in contexts):
        return "known", contexts[-1]
    return "new", None


def _stream(mapper: Mapper, pieces: list) -> None:
    """Replace the words of one paragraph.

    `pieces` holds (setter, text, lane, context) in document order and None
    for a visible boundary. Between boundaries, the base text is read as one
    text, across any insertion inside it, so a word that a new tracked
    change splits or replaces in part is the same word as in the source. A
    run of known inserted text is read across new insertions inside it, and
    a run of new inserted text on its own. Replacements keep every length, so
    each run is cut back into its pieces at the original lengths.
    """
    def apply(run):
        text = "".join(piece[1] for piece in run)
        if run[0][2] == "known":
            joined = mapper.known_insertion(run[0][3], text)
        else:
            joined = mapper.text(text)
        at = 0
        for setter, text, _, _ in run:
            setter(joined[at:at + len(text)])
            at += len(text)

    def runs(chunk):
        base = [p for p in chunk if p[2] == "base"]
        if base:
            yield base
        known, new = [], []
        for piece in chunk:
            lane = piece[2]
            if lane != "new" and new:
                yield new
                new = []
            if lane == "base" and known:
                yield known
                known = []
            if lane == "known":
                known.append(piece)
            elif lane == "new":
                new.append(piece)
        if known:
            yield known
        if new:
            yield new

    chunk: list = []
    for piece in pieces + [None]:
        if piece is not None:
            chunk.append(piece)
            continue
        for run in runs(chunk):
            apply(run)
        chunk = []


def _setter(node) -> Callable[[str], None]:
    return lambda value: setattr(node, "text", value)


def _anonymize_tree(root, mapper: Mapper, part: str, known: set | None) -> set:
    """Rewrite one parsed part in place; return its insertion contexts."""
    unknown = etree.QName(root).namespace not in KNOWN_NAMESPACES
    # Keyed by the elements themselves: lxml reuses the id() of a proxy that
    # nothing references any more, so ids would mix up unrelated elements.
    streams: dict = collections.defaultdict(list)
    order: list = []
    done: set = set()
    contexts: set = set()

    def block_of(node):
        for ancestor in node.iterancestors():
            if ancestor.tag in BLOCK_TAGS:
                return ancestor
        return None

    # Read every text node's lane before any author or date is replaced.
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        if node.tag in INSERTIONS:
            contexts.add(_context(node))
        if node.tag in TEXT_TAGS or node.tag in SEPARATOR_TAGS:
            block = block_of(node)
            key = block if block is not None else node
            if key not in streams:
                order.append(key)
            if node.tag in TEXT_TAGS:
                streams[key].append((_setter(node), node.text or "", *_lane(node, known)))
                done.add(node)
            else:
                streams[key].append(None)

    for node in root.iter():
        if not isinstance(node.tag, str):
            # comments and processing instructions: content, not structure
            if node.text:
                node.text = mapper.text(node.text)
            continue
        if node.tag in DATE_TEXT and node.text:
            node.text = mapper.date(node.text)
            done.add(node)
        elif node.tag in FORMULA_TEXT and node.text:
            node.text = mapper.formula(node.text)
            done.add(node)
        _attributes(node, mapper, unknown, part)

    for key in order:
        _stream(mapper, streams[key])

    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        if node not in done and node.tag not in KEEP_TEXT and node.text:
            node.text = mapper.text(node.text)
        if node.tail and node.tail.strip():
            node.tail = mapper.text(node.tail)
    return contexts


STYLES_PARTS = re.compile(r"^word/(?:glossary/)?(?:styles|stylesWithEffects)\.xml$")
STYLE_REFS = frozenset(W + t for t in (
    "pStyle", "rStyle", "tblStyle", "basedOn", "next", "link", "numStyleLink", "styleLink"))
ON = ("1", "true", "on")


def custom_styles(parts: dict[str, bytes]) -> set[str]:
    """Ids of the styles a document defines itself (``w:customStyle``).

    Their ids and names are often a client's or a firm's; built-in styles
    are Word's and are kept, so the result still opens with its own styles.
    """
    out = set()
    for name, blob in parts.items():
        if not STYLES_PARTS.match(name):
            continue
        try:
            root = fromstring(blob)
        except etree.XMLSyntaxError:
            continue
        for style in root.iter(W + "style"):
            if style.get(W + "customStyle") in ON and style.get(W + "styleId"):
                out.add(style.get(W + "styleId"))
    return out


def _attributes(node, mapper: Mapper, unknown: bool, part: str) -> None:
    on = TEXT_ATTRS_ON.get(node.tag, ())
    parent = node.getparent()
    if node.tag == W + "style" and node.get(W + "styleId") in mapper.custom_styles:
        node.set(W + "styleId", mapper.text(node.get(W + "styleId")))
    elif node.tag in STYLE_REFS and node.get(W + "val") in mapper.custom_styles:
        node.set(W + "val", mapper.text(node.get(W + "val")))
    elif (node.tag in (W + "name", W + "aliases") and parent is not None
          and parent.tag == W + "style" and parent.get(W + "customStyle") in ON
          and node.get(W + "val")):
        node.set(W + "val", mapper.text(node.get(W + "val")))
    named = (parent is not None and parent.tag in NAMED_PARENTS
             and etree.QName(node).localname == "name")
    author = node.get(W + "author")
    for name, value in node.attrib.items():
        if name in AUTHOR_ATTRS:
            node.set(name, mapper.person(value))
        elif name in INITIALS_ATTRS:
            node.set(name, mapper.initials(value, author))
        elif name in DATE_ATTRS:
            node.set(name, mapper.date(value))
        elif node.tag == REL + "Relationship" and name == "Target":
            if node.get("TargetMode") == "External":
                node.set(name, mapper.target(value))
        elif ((name == "id" and node.tag in VML_SHAPES) or name in SHAPE_REFERENCES) \
                and not GENERATED_ID.match(value):
            node.set(name, mapper.text(value))
        elif name in HREF_ATTRS:
            node.set(name, mapper.target(value))
        elif (name in TEXT_ATTRS or name in on or (named and name == W + "val")
              or (CNVPR.search(node.tag) and name in ("name", "descr", "title"))):
            node.set(name, mapper.target(value) if name == W + "instr" else mapper.text(value))
        elif unknown and not name.startswith(RESERVED_NAMESPACES):
            node.set(name, mapper.text(value))


#: Raw-text fallback for a part no XML parser accepts. Markup stays byte for
#: byte, so the part stays broken in the same way; character data and the
#: attributes the rules above name are replaced, matched by local name since
#: the prefixes cannot be resolved. Text outside any markup (a stray dump)
#: is character data too.
_MARKUP = re.compile(r"<[^<>]*>")
_CHARACTER_DATA = re.compile(r"[^<>]+(?=<|$)")
_ATTRIBUTE = re.compile(r"""(\s+)([^\s=/<>]+)\s*=\s*("[^"]*"|'[^']*')""")
_ENTITY = re.compile(r"&(?:[A-Za-z]+|#[0-9]+|#[xX][0-9a-fA-F]+);")


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


_TEXT_LOCALS = frozenset(_local(n) for n in TEXT_ATTRS)
_TEXT_ON_LOCALS = {_local(e): {_local(a) for a in attrs} for e, attrs in TEXT_ATTRS_ON.items()}


def _lexical(data: bytes, mapper: Mapper) -> bytes:
    text = data.decode("utf-8", errors="surrogateescape")

    def chars(value: str) -> str:
        out, at = [], 0
        for match in _ENTITY.finditer(value):
            out.append(mapper.text(value[at:match.start()]))
            out.append(match.group(0))
            at = match.end()
        out.append(mapper.text(value[at:]))
        return "".join(out)

    def tag(markup: str) -> str:
        if markup.startswith("<!--"):
            return "<!--" + chars(markup[4:-3]) + "-->"
        if markup.startswith(("<?", "<!", "</")):
            return markup
        element = _local(re.match(r"<\s*([^\s/>]*)", markup).group(1))

        def attribute(match):
            space, name, quoted = match.groups()
            local, inner = _local(name), quoted[1:-1]
            if local == "author":
                inner = mapper.person(inner)
            elif local == "initials":
                inner = mapper.initials(inner)
            elif local in ("date", "dateUtc", "fullDate"):
                inner = mapper.date(inner)
            elif (local in _TEXT_LOCALS or local in _TEXT_ON_LOCALS.get(element, ())
                  or (element in ("docPr", "cNvPr") and local in ("name", "descr", "title"))):
                inner = chars(inner)
            else:
                return match.group(0)
            return f"{space}{name}={quoted[0]}{inner}{quoted[0]}"

        return _ATTRIBUTE.sub(attribute, markup)

    out, at = [], 0
    for match in _MARKUP.finditer(text):
        out.append(chars(text[at:match.start()]))
        out.append(tag(match.group(0)))
        at = match.end()
    out.append(chars(text[at:]))
    return "".join(out).encode("utf-8", errors="surrogateescape")


def _content_types(parts: dict[str, bytes]) -> tuple[dict[str, str], dict[str, str]]:
    blob = parts.get("[Content_Types].xml")
    defaults, overrides = {}, {}
    if blob is None:
        return defaults, overrides
    root = fromstring(blob)
    for node in root:
        if node.tag == CT + "Default":
            defaults[(node.get("Extension") or "").lower()] = node.get("ContentType") or ""
        elif node.tag == CT + "Override":
            overrides[(node.get("PartName") or "").lstrip("/")] = node.get("ContentType") or ""
    return defaults, overrides


def _is_xml(name: str, defaults: dict, overrides: dict) -> bool:
    kind = overrides.get(name) or defaults.get(name.rsplit(".", 1)[-1].lower(), "")
    return (kind.endswith("xml") or name.lower().endswith((".xml", ".rels", ".vml"))
            or name == "[Content_Types].xml")


@dataclass
class FileResult:
    output: Path
    placeholders: list[str] = field(default_factory=list)
    emptied: list[str] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)
    lexical: list[str] = field(default_factory=list)
    contexts: set = field(default_factory=set, repr=False)


def _anonymize_package(source: Path, output: Path, mapper: Mapper,
                       limits: ArchiveLimits, known: set | None = None) -> FileResult:
    parts = read_package(source, limits)
    mapper.custom_styles |= custom_styles(parts)
    defaults, overrides = _content_types(parts)
    declared = any(kind in MAIN_DOCX for kind in [*overrides.values(), *defaults.values()])
    if not declared and not ("[Content_Types].xml" not in parts and "word/document.xml" in parts):
        raise ValueError(f"{source}: not a WordprocessingML (.docx) package")
    main = parts.get("word/document.xml", b"")[:2000]
    if b"purl.oclc.org/ooxml/wordprocessingml/main" in main:
        # its namespaces are not the ones these rules name; replacing by them
        # would miss authors and break relationship ids, and the checker
        # does not read Strict either (PKG009)
        raise ValueError(f"{source}: Strict Open XML is not supported")
    result = FileResult(output)
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
    with zipfile.ZipFile(output, "w") as out:
        for info in infos:
            name = info.filename
            data = parts.get(name, b"")
            if info.is_dir():
                pass
            elif _is_xml(name, defaults, overrides):
                try:
                    root = fromstring(data)
                except (etree.XMLSyntaxError, UnsafeXML):
                    data = _lexical(data, mapper)
                    result.lexical.append(name)
                else:
                    result.contexts |= _anonymize_tree(root, mapper, name, known)
                    data = _serialize(root, data)
            elif FONT_PARTS.search(name):
                result.fonts.append(name)
            else:
                image = placeholder(name)
                if image is not None:
                    data = image
                    result.placeholders.append(name)
                else:
                    data = b""
                    result.emptied.append(name)
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = info.compress_type
            entry.external_attr = info.external_attr
            out.writestr(entry, data)
    return result


def _serialize(root, original: bytes) -> bytes:
    head = original[:200].lstrip()
    declaration = head.startswith(b"<?xml")
    standalone = None
    if declaration:
        match = re.search(rb'standalone\s*=\s*["\'](yes|no)["\']', head)
        if match:
            standalone = match.group(1) == b"yes"
    if not declaration:
        return etree.tostring(root, encoding="UTF-8", xml_declaration=False)
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=standalone)


# --- verification -----------------------------------------------------------

def _signature(findings) -> collections.Counter:
    return collections.Counter((f.code, f.severity.value, f.part, f.where) for f in findings)


def findings_of(paths: Sequence[Path],
                limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> dict[str, collections.Counter]:
    """The CLI's findings: each file checked, the edited copy compared."""
    from .cli import _run_one
    if len(paths) == 1:
        return {"document": _signature(_run_one(paths[0], None, limits))}
    return {"source": _signature(_run_one(paths[0], None, limits)),
            "edited": _signature(_run_one(paths[1], paths[0], limits))}


def _tokens(text: str) -> Iterable[str]:
    start = None
    for i, char in enumerate(text + "\0"):
        inside = i < len(text) and _word_char(char)
        if inside and start is None:
            start = i
        elif not inside and start is not None:
            yield text[start:i]
            start = None


#: Kept locations whose values are names the format defines: enumerations,
#: built-in style names, part names, content and relationship types, the
#: producing application. A word of the text that also occurs there was not
#: copied from the text. (element, attribute); None stands for element text.
STRUCTURE = frozenset((
    ("style", "type"), ("style", "styleId"), ("name", "val"), ("aliases", "val"),
    ("basedOn", "val"), ("next", "val"), ("link", "val"), ("pStyle", "val"),
    ("rStyle", "val"), ("tblStyle", "val"), ("numStyleLink", "val"), ("styleLink", "val"),
    ("lsdException", "name"), ("Override", "ContentType"), ("Override", "PartName"),
    ("Default", "ContentType"), ("Default", "Extension"), ("Relationship", "Type"),
    ("Relationship", "Target"), ("Application", None), ("rFonts", "hint"),
    ("headerReference", "type"), ("footerReference", "type"), ("brkBin", "val"),
    ("brkBinSub", "val"), ("idmap", "ext"), ("shapedefaults", "ext"),
    ("shapelayout", "ext"), ("docGrid", "type"), ("pitch", "val"),
    ("font", "typeface"), ("latin", "typeface"), ("ea", "typeface"), ("cs", "typeface"),
    ("font", "name"), ("altName", "val"), ("attr", "name"), ("smartTag", "element"),
))


#: Attributes that are structure wherever they occur, and elements all of
#: whose attributes are: language tags, fonts, namespace URIs, store ids,
#: VML formulas, numbering formats.
STRUCTURE_ATTRS = frozenset((
    "space", "uri", "itemID", "storeItemID", "prefixMappings", "xpath", "eqn", "typeface",
    "hint", "type", "ext", "style", "inset", "path", "modelId", "lang", "namespaceuri",
    "Ignorable", "ShapeID", "shapeid", "idref", "spid", "ID"))
STRUCTURE_ELEMENTS = frozenset(("lang", "themeFontLang", "rFonts", "lvlText", "font", "altName",
                                "docPartGallery", "mathFont", "lid", "sym", "dateFormat"))


def _located(tag: str, attr: str | None) -> bool:
    if attr is None:
        return tag in KEEP_TEXT
    local = etree.QName(tag).localname
    return ((local, attr) in STRUCTURE or attr in STRUCTURE_ATTRS
            or local in STRUCTURE_ELEMENTS)


def leak_scan(paths: Sequence[Path], vocabulary: set[str], phrases: set[tuple[str, str]],
              replacements: set[str] = frozenset(),
              limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> tuple[list[dict], int]:
    """Places in `paths` that still hold words of the original text.

    Element text and the attributes of parts in unknown namespaces are
    replaced wholesale, so any word there of four or more letters is
    reported. Attributes in the known namespaces are kept unless listed as
    text, and their values are mostly names the format defines (``left``,
    ``auto``, ``Normal``), which a document's text may use too; there two
    consecutive words of the text are reported, so free text copied into an
    attribute this module does not know is found and an enumeration is not.
    Hits in the kept structure listed in STRUCTURE are counted, not reported.
    Each report names the file, part and element or attribute, never the
    words, so it can be shared.
    """
    words = {w for w in vocabulary - replacements
             if len(w) >= 4 and not any(c.isdigit() for c in w)}
    hits: collections.Counter = collections.Counter()
    structural = 0

    def single(text):
        return sum(1 for token in _tokens(text or "") if token in words)

    def phrase(text):
        tokens = list(_tokens(text or ""))
        return sum(1 for pair in zip(tokens, tokens[1:])
                   if pair in phrases and not set(pair) & replacements)

    for index, path in enumerate(paths):
        parts = read_package(path, limits)
        defaults, overrides = _content_types(parts)
        for name, data in parts.items():
            if not data or not _is_xml(name, defaults, overrides):
                continue
            try:
                root = fromstring(data)
            except Exception:
                raw = data.decode("utf-8", "replace")
                found = sum(single(m.group(0)) for m in _CHARACTER_DATA.finditer(raw))
                found += sum(phrase(m.group(2)[1:-1]) for m in _ATTRIBUTE.finditer(raw))
                if found:
                    hits[(index, name, "(unparsed part)")] += found
                continue
            unknown = etree.QName(root).namespace not in KNOWN_NAMESPACES
            for node in root.iter():
                if not isinstance(node.tag, str):
                    continue
                label = etree.QName(node).localname
                found = single(node.text) + single(node.tail)
                if found and _located(node.tag, None):
                    structural += found
                elif found:
                    hits[(index, name, label)] += found
                for attr, value in node.attrib.items():
                    local = etree.QName(attr).localname
                    found = single(value) if unknown else phrase(value)
                    if found and _located(node.tag, local):
                        structural += found
                    elif found:
                        hits[(index, name, f"{label}/@{local}")] += found
    return ([{"file": i + 1, "part": part, "where": where, "words": n}
             for (i, part, where), n in sorted(hits.items())], structural)


# --- entry point --------------------------------------------------------------

@dataclass
class Report:
    outputs: list[Path]
    words: int
    distinct: int
    people: int
    dates: int
    collisions: int
    files: list[FileResult]
    original: dict[str, collections.Counter]
    anonymized: dict[str, collections.Counter]
    leaks: list[dict]
    structural: int = 0

    @property
    def reproduced(self) -> bool:
        return self.original == self.anonymized

    def differences(self) -> dict[str, dict[str, list[dict]]]:
        """Findings the originals had and the results lack, and the reverse,
        by code, severity, part and location; messages hold text and are left
        out."""
        def rows(counter):
            return [dict(zip(("code", "severity", "part", "where"), key), count=n)
                    for key, n in sorted(counter.items())]
        out = {}
        for stage in self.original:
            lost = self.original[stage] - self.anonymized.get(stage, collections.Counter())
            gained = self.anonymized.get(stage, collections.Counter()) - self.original[stage]
            if lost or gained:
                out[stage] = {"lost": rows(lost), "gained": rows(gained)}
        return out

    def render(self, out_dir: Path) -> str:
        """The human report. It names parts and places, never the text."""
        emptied = sorted({p for f in self.files for p in f.emptied})
        fonts = sorted({p for f in self.files for p in f.fonts})
        lexical = sorted({p for f in self.files for p in f.lexical})
        placeholders = sum(len(f.placeholders) for f in self.files)
        lines = [f"anonymized {len(self.outputs)} file(s) into {out_dir}: "
                 + ", ".join(p.name for p in self.outputs),
                 f"  replaced {self.words} word(s) ({self.distinct} distinct), "
                 f"{self.people} author(s), {self.dates} date(s); {placeholders} picture(s) "
                 "and embedded workbook(s) became placeholders"]
        if emptied:
            lines.append(f"  emptied {len(emptied)} binary part(s): " + ", ".join(emptied))
        if fonts:
            lines.append(f"  kept {len(fonts)} embedded font part(s)")
        if lexical:
            lines.append("  read as raw text, not well-formed XML: " + ", ".join(lexical))
        if self.collisions:
            lines.append(f"  {self.collisions} word(s) share a replacement: the "
                         "alphabet ran out for their shape")
        counts = ", ".join(f"{stage} {sum(c.values())}" for stage, c in self.original.items())
        if self.reproduced:
            lines.append(f"  findings reproduced ({counts})")
        else:
            lines.append(f"  findings NOT reproduced (originals: {counts}):")
            for stage, change in self.differences().items():
                for kind in ("lost", "gained"):
                    for row in change[kind]:
                        lines.append(f"    {stage}: {kind} {row['code']} ({row['severity']}) "
                                     f"in {row['part'] or '-'} x{row['count']}")
        if self.leaks:
            lines.append("  words of the original text are still present in:")
            for leak in self.leaks:
                lines.append(f"    {self.outputs[leak['file'] - 1].name} {leak['part']} "
                             f"{leak['where']}: {leak['words']} word(s)")
        else:
            lines.append("  no word of the original text found outside replaced text")
        lines.append("Open the results before sharing them. This report holds no text "
                     "from the documents.")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        def counts(sig):
            return {stage: sum(c.values()) for stage, c in sig.items()}
        return {
            "outputs": [p.name for p in self.outputs],
            "words_replaced": self.words, "distinct_words": self.distinct,
            "authors": self.people, "dates_shifted": self.dates,
            "collisions": self.collisions,
            "placeholders": sum(len(f.placeholders) for f in self.files),
            "emptied_parts": sorted({p for f in self.files for p in f.emptied}),
            "fonts_kept": sorted({p for f in self.files for p in f.fonts}),
            "lexical_parts": sorted({p for f in self.files for p in f.lexical}),
            "findings": {"original": counts(self.original),
                         "anonymized": counts(self.anonymized),
                         "reproduced": self.reproduced,
                         "differences": self.differences()},
            "leaks": self.leaks,
            "words_in_kept_structure": self.structural,
        }


def output_names(count: int) -> list[str]:
    """Generic names: the originals' file names can say what they hold."""
    return ["document.docx"] if count == 1 else ["source.docx", "edited.docx"]


def anonymize(paths: Sequence[str | Path], out_dir: str | Path, *,
              names: Sequence[str] | None = None, rng: random.Random | None = None,
              limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> Report:
    """Anonymize one DOCX or a source/edited pair into `out_dir` and verify it."""
    sources = [Path(p) for p in paths]
    if not 1 <= len(sources) <= 2:
        raise ValueError("anonymize takes one document or a source and an edited copy")
    if names is None:
        names = output_names(len(sources))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mapper = Mapper(rng)
    with tempfile.TemporaryDirectory() as scratch:
        staged = [Path(scratch) / name for name in names]
        files = [_anonymize_package(sources[0], staged[0], mapper, limits)]
        mapper.reading_source = False
        if len(sources) == 2:
            files.append(_anonymize_package(sources[1], staged[1], mapper, limits,
                                            known=files[0].contexts))
        outputs = []
        for result, name in zip(files, names):
            target = out / name
            shutil.move(str(result.output), target)
            result.output = target
            outputs.append(target)
    leaks, structural = leak_scan(outputs, mapper.vocabulary, mapper.phrases,
                                  mapper.replacements, limits)
    return Report(outputs, mapper.replaced, mapper.distinct, mapper.people, mapper.dates,
                  mapper.collisions, files, findings_of(sources, limits),
                  findings_of(outputs, limits), leaks, structural)
