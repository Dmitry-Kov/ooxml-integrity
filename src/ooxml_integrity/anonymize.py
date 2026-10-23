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
- A firm's own schemas: their namespace URIs and prefixes, the names of
  their elements and attributes, and the value of every attribute in them,
  in whatever part it occurs. Data binding paths follow: their step names,
  prefixes and string literals are replaced the way the data they select is.
  A path this module cannot map that way is refused, and so is the run.
  Custom XML markup and smart tags written into the document name the same
  elements and attributes, and are renamed the same way; Office's own smart
  tags keep their names.
- Pictures become 1x1 placeholders of the same format, embedded workbooks an
  empty workbook; other embedded objects and binary parts become empty.
  Embedded fonts are kept.

What is kept: the structure itself, built-in style names, font names,
numbering formats, cell references in chart formulas, paragraph and revision
ids, and the length and position of every word. A reader of the result learns
the shape of the document, not its text.

No output may be, or be linked to, an input: that is refused before anything
is written. Afterwards the checker runs on the originals, read before any
copy is moved into place, and on the results. The report says whether every
finding was reproduced and whether every data binding selects as many nodes
as in the original, and lists the places where words of the original text
still occur in the results. docs/anonymize.md is the user's account of the
same, and evidence/anonymize the measurement.
"""
from __future__ import annotations

import base64
import collections
import datetime as _dt
import difflib
import html
import itertools
import os
import posixpath
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
SL = "{http://schemas.openxmlformats.org/schemaLibrary/2006/main}"

MAIN_DOCX = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "application/vnd.ms-word.document.macroEnabled.main+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
)

#: Namespaces whose attributes are structural unless listed below. In a part
#: whose root is in none of them (custom XML data, sensitivity labels, ink),
#: every attribute value is replaced as text; so is the value of an attribute
#: in a custom namespace in any part (user_attribute). Office's own parts
#: belong here: an enumeration replaced in a chart style makes Word refuse
#: the file.
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
#: Namespaces the format and Office define. Any other namespace is someone's
#: own schema (a firm's contract data, a SharePoint library's columns): its
#: URI, and the names of the elements and attributes in it, can say whose the
#: document is, so they are replaced, the same way wherever they occur.
STANDARD_NAMESPACE = re.compile(
    r"^(?:https?://schemas\.openxmlformats\.org/|https?://schemas\.microsoft\.com/"
    r"|urn:schemas-microsoft-com:|https?://www\.w3\.org/|https?://purl\.org/"
    r"|https?://purl\.oclc\.org/|https?://ns\.adobe\.com/"
    # Exchange's contact schema: Office's person name smart tag writes the
    # parts of a name in it (GivenName, Sn)
    r"|urn:schemas:contacts$)", re.I)
#: Attributes whose value is a namespace URI, or the location of a schema in
#: the schema library, and data binding attributes.
URI_ATTRS = frozenset(("{http://schemas.openxmlformats.org/officeDocument/2006/customXml}uri",
                       W + "uri", W + "namespaceuri", W + "manifestLocation", W + "schemaLocation",
                       SL + "uri", SL + "manifestLocation", SL + "schemaLocation"))
DATA_BINDINGS = frozenset((W + "dataBinding", W15 + "dataBinding"))
PREFIX_MAPPING = re.compile(r"""xmlns:([\w.-]+)\s*=\s*['"]([^'"]*)['"]""")
#: XPath 1.0 tokens: a data binding path is read token by token, so that a
#: string literal is told apart from a step name.
XPATH_TOKEN = re.compile(r"""
    (?P<space>\s+)
  | (?P<literal>"[^"]*"|'[^']*')
  | (?P<number>\d+(?:\.\d*)?|\.\d+)
  | (?P<symbol>//|::|!=|<=|>=|\.\.|[/()\[\]@,|+\-=<>.*$])
  | (?P<name>[^\W\d][\w.\-]*(?::(?:[^\W\d][\w.\-]*|\*))?)
""", re.X)
XPATH_OPERATORS = frozenset(("and", "or", "mod", "div", "*", "/", "//", "|", "+", "-", "=", "!=",
                             "<", "<=", ">", ">="))
XPATH_AXES = frozenset(("child", "descendant", "descendant-or-self", "self", "parent", "ancestor",
                        "ancestor-or-self", "following", "following-sibling", "preceding",
                        "preceding-sibling", "attribute"))
XPATH_NODE_TYPES = frozenset(("text", "node", "comment"))
#: A prefix that says nothing: what Word writes in data bindings, and the
#: replacement anonymize gives the prefixes of custom namespaces.
GENERIC_PREFIX = re.compile(r"^ns\d+$")
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
XML_NS = "http://www.w3.org/XML/1998/namespace"
#: Markup compatibility attributes whose values name prefixes.
MC_PREFIX_LISTS = frozenset("{%s}%s" % (MC_NS, name) for name in (
    "Ignorable", "MustUnderstand", "ProcessContent", "PreserveElements", "PreserveAttributes"))
#: Never replaced, in any part: relationship ids, markup compatibility, xml:*.
RESERVED_NAMESPACES = (
    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}",
    "{%s}" % MC_NS,
    "{%s}" % XML_NS,
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
#: Hyperlink addresses written on VML shapes, and where a smart tag type's
#: recognizer is found.
HREF_ATTRS = frozenset(("href", O + "href"))
HREF_ATTRS_ON = {W + "smartTagType": {W + "url"}}
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
    W + "placeholder": {W + "val"},
    W + "saveThroughXslt": {W + "solutionID"},
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


class Refused(ValueError):
    """The input holds something that cannot be replaced safely, or an output
    would replace an input; nothing is written."""


def custom_namespace(uri: str | None) -> bool:
    return bool(uri) and not STANDARD_NAMESPACE.match(uri)


def _namespace(name: str) -> str | None:
    return name[1:name.index("}")] if name.startswith("{") else None


def user_attribute(tag: str, attr: str) -> bool:
    """An attribute whose value is someone's own data wherever it occurs: one
    in a custom namespace, or an unqualified one on an element of a custom
    namespace. The namespace of the part it is in does not matter."""
    namespace = _namespace(attr)
    return custom_namespace(namespace if namespace is not None else _namespace(tag))


def uri_attribute(tag: str, attr: str) -> bool:
    """An attribute whose value is a namespace URI or a schema's location."""
    return attr in URI_ATTRS or (tag == W + "attachedSchema" and attr == W + "val")


#: Custom XML markup and smart tags written into the document: an element of
#: someone's schema as a Word element (w:customXml at run, paragraph, row and
#: cell level; w:smartTag), w:element naming it and w:uri giving its
#: namespace. Its properties (w:customXmlPr, w:smartTagPr) come first in it
#: and name its attributes the same way: w:attr, with w:name, w:uri and the
#: value, w:val. A custom XML element's also hold its placeholder text. The
#: settings list each smart tag type by namespace (w:namespaceuri) and name.
MARKUP_OWNERS = frozenset((W + "customXml", W + "smartTag"))
MARKUP_PROPERTIES = frozenset((W + "customXmlPr", W + "smartTagPr"))
MARKUP_NAMED = MARKUP_OWNERS | {W + "smartTagType", W + "attr"}
#: Their values, and the other text the settings keep about custom XML: a
#: smart tag recognizer's address and the transform a document is saved
#: through. All are replaced; the leak scan reads them word by word.
MARKUP_VALUES = frozenset(((W + "attr", W + "val"), (W + "placeholder", W + "val"),
                           (W + "smartTagType", W + "url"),
                           (W + "saveThroughXslt", W + "solutionID")))


def _own(uri: str | None) -> bool:
    """Whether names in this namespace are someone's own: a custom namespace,
    or none (a custom XML element without w:uri is the firm's too)."""
    return not uri or custom_namespace(uri)


def markup_names(node) -> dict[str, bool]:
    """The attributes of `node` that name an element or attribute of custom
    XML markup or a smart tag, each with whether that name is someone's own,
    replaced, or one Office defines and kept (its smart tags ``City``,
    ``PersonName``, ``ProductID``).

    Names are judged as in a custom XML part (_rename_custom): a w:attr
    without w:uri names an attribute in no namespace, someone's own when its
    element is. One outside custom XML or smart tag properties counts as
    someone's own."""
    if node.tag in MARKUP_OWNERS:
        return {W + "element": _own(node.get(W + "uri"))}
    if node.tag == W + "smartTagType":
        return {W + "name": _own(node.get(W + "namespaceuri"))}
    if node.tag == W + "attr":
        uri, parent = node.get(W + "uri"), node.getparent()
        owner = parent.getparent() if parent is not None and parent.tag in MARKUP_PROPERTIES else None
        if not uri and owner is not None:
            uri = owner.get(W + "uri")
        return {W + "name": _own(uri)}
    return {}


class UnmappableXPath(ValueError):
    """A data binding path in a form whose replacement could select other nodes."""


def _xpath_tokens(value: str) -> list[list]:
    """[kind, text, start, end] for each token of an XPath 1.0 expression.

    Names and ``*`` are told apart as the XPath recommendation (3.7) says:
    after an operand, a name is an operator; before ``(``, a function; before
    ``::``, an axis; otherwise a name test.
    """
    tokens, at = [], 0
    while at < len(value):
        match = XPATH_TOKEN.match(value, at)
        if match is None:
            raise UnmappableXPath("is not an XPath expression this tool reads")
        if match.group() == "$":
            raise UnmappableXPath("uses a variable")
        kind = match.lastgroup
        if kind == "symbol" and match.group() in XPATH_OPERATORS and match.group() != "*":
            kind = "operator"
        if kind != "space":
            tokens.append([kind, match.group(), match.start(), match.end()])
        at = match.end()
    for i, token in enumerate(tokens):
        if not (token[0] == "name" or token[1] == "*"):
            continue
        before = tokens[i - 1] if i else None
        after = tokens[i + 1][1] if i + 1 < len(tokens) else None
        operand_before = before is not None and not (
            before[0] == "operator" or before[1] in ("@", "::", "(", "[", ","))
        if operand_before:
            if token[1] not in XPATH_OPERATORS:
                raise UnmappableXPath("is not an XPath expression this tool reads")
            token[0] = "operator"
        elif token[1] == "*":
            token[0] = "nametest"
        else:
            token[0] = {"(": "function", "::": "axis"}.get(after, "nametest")
    return tokens


class _XPathReader:
    """Accepts the expressions whose replacement selects the same nodes.

    Location paths with steps on any axis but ``namespace``, name and node
    type tests, and predicates made of positions (``[1]``, ``[last()]``,
    ``position() < last() - 1``), tests that a node exists, ``not()``,
    ``and``, ``or``, and comparisons of nodes and string literals with ``=``
    and ``!=``; the same at the top level. A literal is replaced the way the
    values it is compared with are, and equality survives a replacement that
    keeps equal strings equal. Everything else (other functions, arithmetic
    on values, unions, variables, an order or a number compared with a value)
    could select other nodes once the values change, and is refused.
    """

    def __init__(self, tokens: list[list]):
        self.tokens, self.at = tokens, 0

    def read(self) -> None:
        if not self.tokens:
            raise UnmappableXPath("is empty")
        self.disjunction()
        if self.at < len(self.tokens):
            self.refuse(self.tokens[self.at])

    def peek(self) -> list | None:
        return self.tokens[self.at] if self.at < len(self.tokens) else None

    def take(self, *texts: str) -> bool:
        token = self.peek()
        if token is not None and token[1] in texts and token[0] != "literal":
            self.at += 1
            return True
        return False

    def expect(self, text: str) -> None:
        if not self.take(text):
            self.refuse(self.peek())

    def refuse(self, token: list | None):
        if token is None:
            raise UnmappableXPath("is not an XPath expression this tool reads")
        kind, text = token[0], token[1]
        if kind == "function":
            raise UnmappableXPath(f"uses the function {text}()")
        if kind == "axis":
            raise UnmappableXPath(f"uses the {text} axis")
        if kind == "operator":
            raise UnmappableXPath(f"uses the operator {text}")
        raise UnmappableXPath("is not an XPath expression this tool reads")

    def at_step(self) -> bool:
        token = self.peek()
        return token is not None and (
            token[0] in ("nametest", "axis") or token[1] in ("@", ".", "..")
            or (token[0] == "function" and token[1] in XPATH_NODE_TYPES))

    def path(self) -> None:
        if self.take("/", "//"):
            if self.tokens[self.at - 1][1] == "/" and not self.at_step():
                return
        self.step()
        while self.take("/", "//"):
            self.step()

    def step(self) -> None:
        if self.take(".", ".."):
            return
        token = self.peek()
        if token is not None and token[0] == "axis":
            if token[1] not in XPATH_AXES:
                self.refuse(token)
            self.at += 1
            self.expect("::")
        else:
            self.take("@")
        token = self.peek()
        if token is not None and token[0] == "nametest":
            self.at += 1
        elif token is not None and token[0] == "function" and token[1] in XPATH_NODE_TYPES:
            self.at += 1
            self.expect("(")
            self.expect(")")
        else:
            self.refuse(token)
        while self.take("["):
            self.disjunction()
            self.expect("]")

    def disjunction(self) -> None:
        self.conjunction()
        while self.take("or"):
            self.conjunction()

    def conjunction(self) -> None:
        self.comparison()
        while self.take("and"):
            self.comparison()

    def comparison(self) -> None:
        left = self.sum()
        token = self.peek()
        if token is None or token[1] not in ("=", "!=", "<", "<=", ">", ">="):
            return
        self.at += 1
        kinds = {left, self.sum()}
        if kinds <= {"number", "position"}:
            return
        if kinds <= {"nodes", "literal"} and token[1] in ("=", "!="):
            return
        if token[1] not in ("=", "!="):
            raise UnmappableXPath(f"orders values with {token[1]}")
        raise UnmappableXPath("compares a value with a number or a condition")

    def sum(self) -> str:
        """An operand, or positions and numbers added and subtracted."""
        kind = self.operand()
        while True:
            token = self.peek()
            if token is None or token[0] != "operator" or token[1] not in ("+", "-"):
                return kind
            if kind not in ("number", "position"):
                self.refuse(token)
            self.at += 1
            if self.operand() not in ("number", "position"):
                self.refuse(token)
            kind = "position"

    def operand(self) -> str:
        token = self.peek()
        if token is None:
            self.refuse(token)
        if token[0] in ("literal", "number"):
            self.at += 1
            return token[0]
        if token[0] == "function" and token[1] in ("position", "last"):
            self.at += 1
            self.expect("(")
            self.expect(")")
            return "position"
        if token[0] == "function" and token[1] == "not":
            self.at += 1
            self.expect("(")
            self.disjunction()
            self.expect(")")
            return "condition"
        if self.take("("):
            self.disjunction()
            self.expect(")")
            return "condition"
        if self.at_step() or (token[1] in ("/", "//") and token[0] == "operator"):
            self.path()
            return "nodes"
        self.refuse(token)


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
        #: custom namespace URI -> replacement, the same in every part and file
        self._namespaces: dict[str, str] = {}
        #: prefix of a custom namespace -> its generic name, where a part allows
        self._prefixes: dict[str, str] = {}
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

    def text(self, text: str, keep: re.Pattern | None = None) -> str:
        """Replace every word of `text`, keeping everything between words and
        whatever `keep` matches."""
        if not text:
            return text
        protected = [False] * len(text)
        for match in [*PROTECTED.finditer(text), *(keep.finditer(text) if keep else ())]:
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

    def namespace(self, uri: str) -> str:
        """A custom namespace URI: its words replaced, a known scheme kept."""
        if uri not in self._namespaces:
            self._namespaces[uri] = self.target(uri)
        return self._namespaces[uri]

    def name(self, local: str) -> str:
        """An element or attribute name of a custom schema: still a valid name."""
        return self.text(local)

    def prefix(self, old: str, avoid: set[str]) -> str:
        """A generic name (``ns0``, ``ns1``, ...) for the prefix of a custom
        namespace: a prefix says whose a schema is as well as its URI does.
        A generic prefix stays. Any other gets the same name throughout the
        run, unless `avoid` (the prefixes a part already uses) holds it."""
        if GENERIC_PREFIX.match(old):
            return old
        new = self._prefixes.get(old)
        if new is not None and new not in avoid:
            return new
        taken = avoid | set(self._prefixes.values())
        new = next(f"ns{k}" for k in itertools.count() if f"ns{k}" not in taken)
        self._prefixes.setdefault(old, new)
        return new

    def binding(self, xpath: str | None, mappings: str | None) -> tuple[str | None, str | None]:
        """A data binding's path and prefix mappings, replaced together.

        A step in a custom namespace, in none, or with a prefix the binding
        does not declare (whose namespace nothing says) is renamed the way
        its element or attribute is; a step in a standard namespace is kept. A
        string literal is replaced the way the values it is compared with
        are. The prefixes the binding declares for custom namespaces get
        generic names in both. Raises UnmappableXPath for a path in a form
        whose replacement could select other nodes.
        """
        declared = PREFIX_MAPPING.findall(mappings or "")
        prefixes = dict(declared)
        tokens = _xpath_tokens(xpath) if xpath else []
        if xpath:
            _XPathReader(tokens).read()
        custom = [p for p, uri in declared if custom_namespace(uri)]
        used = set(prefixes) | {t[1].split(":")[0] for t in tokens
                                if t[0] == "nametest" and ":" in t[1]}
        # generic prefixes (Word writes ns0, ns1, ...) stay; the others get
        # generic names no other prefix of the binding has
        renamed = {p: p for p in custom if GENERIC_PREFIX.match(p)}
        for prefix in custom:
            if prefix not in renamed:
                taken = (used - set(custom)) | set(renamed.values())
                renamed[prefix] = next(f"ns{k}" for k in itertools.count()
                                       if f"ns{k}" not in taken)

        def name(qname: str) -> str:
            prefix, _, local = qname.rpartition(":")
            if prefix in prefixes and not custom_namespace(prefixes[prefix]):
                return qname
            new = local if local == "*" else self.name(local)
            return f"{renamed.get(prefix, prefix)}:{new}" if prefix else new

        if xpath:
            out, at = [], 0
            for kind, text, start, end in tokens:
                if kind == "literal":
                    out += [xpath[at:start], text[0], self.text(text[1:-1]), text[-1]]
                    at = end
                elif kind == "nametest":
                    out += [xpath[at:start], name(text)]
                    at = end
            xpath = "".join(out) + xpath[at:]
        if mappings and renamed:
            mappings = PREFIX_MAPPING.sub(
                lambda m: (m.group(0)[:m.start(1) - m.start()] + renamed.get(m.group(1), m.group(1))
                           + m.group(0)[m.end(1) - m.start():]), mappings)
        return xpath, mappings

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
    def namespaces(self) -> dict[str, str]:
        return dict(self._namespaces)

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

    `pieces` holds (setter, text, lane, context, is an instruction) in
    document order and None
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
            joined = mapper.text(text, keep=FIELD_CODE if all(p[4] for p in run) else None)
        at = 0
        for setter, text, *_ in run:
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
                streams[key].append((_setter(node), node.text or "", *_lane(node, known),
                                     node.tag in INSTRUCTION_TAGS))
                done.add(node)
            else:
                streams[key].append(None)

    _rename_markup(root, mapper)
    for node in root.iter():
        if not isinstance(node.tag, str):
            # comments and processing instructions: content, not structure
            if node.text:
                node.text = mapper.text(node.text)
            continue
        _rename_custom(node, mapper, unknown)
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


def _rename_markup(root, mapper: Mapper) -> None:
    """Rename what custom XML markup and smart tags name of someone's schema,
    as the same names are renamed in a custom XML part, so the markup still
    names the data's elements and attributes. Read before any namespace URI
    of the part is replaced, as markup_names() judges names by them."""
    for node in root.iter(*MARKUP_NAMED):
        for attr, own in markup_names(node).items():
            if own and node.get(attr):
                node.set(attr, mapper.name(node.get(attr)))


def _rename_custom(node, mapper: Mapper, unknown: bool) -> None:
    """Rename an element of a custom schema, and its own attributes.

    The namespace URIs themselves are replaced after serialization, in every
    part at once. An element without a namespace is custom only in a part
    whose root is not in a known namespace.
    """
    name = etree.QName(node)
    if custom_namespace(name.namespace) or (name.namespace is None and unknown):
        node.tag = etree.QName(name.namespace, mapper.name(name.localname)).text
        renamed = []
        for attr in list(node.attrib):
            qname = etree.QName(attr)
            if custom_namespace(qname.namespace) or qname.namespace is None:
                renamed.append((attr, etree.QName(qname.namespace, mapper.name(qname.localname)).text))
        for old, new in renamed:
            value = node.attrib.pop(old)
            node.set(new, value)
    else:
        for attr in list(node.attrib):
            qname = etree.QName(attr)
            if custom_namespace(qname.namespace):
                value = node.attrib.pop(attr)
                node.set(etree.QName(qname.namespace, mapper.name(qname.localname)).text, value)


#: Field instructions keep their syntax, which is a closed set of names, and
#: lose their arguments: the field type that opens them (HYPERLINK, REF,
#: MERGEFIELD), switches (\h, \* MERGEFORMAT) and URL schemes. LibreOffice
#: does not open a document whose field type is a made-up word.
FIELD_CODE = re.compile(
    r"^\s*[A-Z][A-Z0-9]*\b|\\[*@#!]?[A-Za-z]*|\b(?:MERGEFORMAT|CHARFORMAT|MERGEFORMATINET)\b"
    r"|\b(?:https?|mailto|ftp|file):")
INSTRUCTION_TAGS = frozenset((W + "instrText", W + "delInstrText"))
#: Level text keeps its level placeholders: "%1" names the first level.
LEVEL_PLACEHOLDER = re.compile(r"%\d")


def _attributes(node, mapper: Mapper, unknown: bool, part: str) -> None:
    on = TEXT_ATTRS_ON.get(node.tag, ())
    if node.tag in DATA_BINDINGS:
        xpath, mappings = mapper.binding(node.get(W + "xpath"), node.get(W + "prefixMappings"))
        for name, value in ((W + "xpath", xpath), (W + "prefixMappings", mappings)):
            if value is not None:
                node.set(name, value)
    if node.tag == W + "lvlText" and node.get(W + "val"):
        node.set(W + "val", mapper.text(node.get(W + "val"), keep=LEVEL_PLACEHOLDER))
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
        elif name in HREF_ATTRS or name in HREF_ATTRS_ON.get(node.tag, ()):
            node.set(name, mapper.target(value))
        elif uri_attribute(node.tag, name):
            if custom_namespace(value):
                node.set(name, mapper.namespace(value))
        elif (name in TEXT_ATTRS or name in on or (named and name == W + "val")
              or (CNVPR.search(node.tag) and name in ("name", "descr", "title"))):
            node.set(name, mapper.text(value, keep=FIELD_CODE) if name == W + "instr"
                     else mapper.text(value))
        elif ((unknown or user_attribute(node.tag, name))
              and not name.startswith(RESERVED_NAMESPACES)):
            node.set(name, mapper.text(value))


#: Raw-text fallback for a part no XML parser accepts. Markup stays byte for
#: byte, so the part stays broken in the same way; character data and the
#: attributes the rules above name are replaced, matched by local name since
#: the prefixes cannot be resolved. So are the values of attributes whose
#: prefix, or whose element's prefix, the part binds to a custom namespace
#: anywhere. Text outside any markup (a stray dump) is character data too.
_MARKUP = re.compile(r"<[^<>]*>")
_CHARACTER_DATA = re.compile(r"[^<>]+(?=<|$)")
_ATTRIBUTE = re.compile(r"""(\s+)([^\s=/<>]+)\s*=\s*("[^"]*"|'[^']*')""")
_ENTITY = re.compile(r"&(?:[A-Za-z]+|#[0-9]+|#[xX][0-9a-fA-F]+);")
_DECLARATION = re.compile(r"""xmlns:([\w.-]+)\s*=\s*(["'])(.*?)\2""")


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _raw_prefixes(text: str) -> set[str]:
    """Prefixes a part that cannot be parsed binds to a custom namespace, in
    any scope: without a parser, a prefix bound to one anywhere counts."""
    return {m.group(1) for m in _DECLARATION.finditer(text) if custom_namespace(m.group(3))}


def _raw_user_attribute(element: str, name: str, custom: set[str]) -> bool:
    """user_attribute() for raw markup: `element` and `name` as written."""
    owner = name if ":" in name else element
    return ":" in owner and owner.partition(":")[0] in custom


_TEXT_LOCALS = frozenset(_local(n) for n in TEXT_ATTRS)
_TEXT_ON_LOCALS = {_local(e): {_local(a) for a in attrs} for e, attrs in TEXT_ATTRS_ON.items()}
_HREF_ON_LOCALS = {_local(e): {_local(a) for a in attrs} for e, attrs in HREF_ATTRS_ON.items()}
_RAW_OWNERS = frozenset(_local(t) for t in MARKUP_OWNERS)
_RAW_PROPERTIES = frozenset(_local(t) for t in MARKUP_PROPERTIES)
_RAW_VALUES = frozenset((_local(e), _local(a)) for e, a in MARKUP_VALUES)
#: The namespace URIs custom XML markup and smart tags hold, by local names.
_RAW_URIS = {"customXml": "uri", "smartTag": "uri", "attr": "uri", "smartTagType": "namespaceuri"}


def _raw_tag(markup: str) -> tuple[str, dict[str, str]]:
    """A start tag's element and attribute values, by local names."""
    element = _local(re.match(r"<\s*([^\s/>]*)", markup).group(1))
    return element, {_local(m.group(2)): m.group(3)[1:-1] for m in _ATTRIBUTE.finditer(markup)}


class _RawMarkup:
    """markup_names() for raw markup, read tag by tag in document order. A
    w:attr without w:uri belongs to the custom XML element or smart tag whose
    properties are open (they come first in it); outside them it counts as
    someone's own."""

    def __init__(self):
        self.owner: str | None = None
        self.open = False

    def names(self, markup: str) -> dict[str, bool]:
        """Local attribute name -> someone's own, for one tag."""
        if markup.startswith("</"):
            if _local(markup[2:-1].strip()) in _RAW_PROPERTIES:
                self.open = False
            return {}
        if markup.startswith(("<?", "<!")):
            return {}
        element, values = _raw_tag(markup)
        if element in _RAW_OWNERS:
            self.owner = values.get("uri")
            return {"element": _own(self.owner)}
        if element in _RAW_PROPERTIES:
            self.open = not markup.endswith("/>")
        elif element == "smartTagType":
            return {"name": _own(values.get("namespaceuri"))}
        elif element == "attr":
            return {"name": _own(values.get("uri") or (self.owner if self.open else None))}
        return {}


def _lexical(data: bytes, mapper: Mapper) -> bytes:
    text = data.decode("utf-8", errors="surrogateescape")
    custom = _raw_prefixes(text)
    markup_state = _RawMarkup()

    def chars(value: str) -> str:
        out, at = [], 0
        for match in _ENTITY.finditer(value):
            out.append(mapper.text(value[at:match.start()]))
            out.append(match.group(0))
            at = match.end()
        out.append(mapper.text(value[at:]))
        return "".join(out)

    def tag(markup: str) -> str:
        names = markup_state.names(markup)
        if markup.startswith("<!--"):
            return "<!--" + chars(markup[4:-3]) + "-->"
        if markup.startswith(("<?", "<!", "</")):
            return markup
        raw = re.match(r"<\s*([^\s/>]*)", markup).group(1)
        element = _local(raw)

        def attribute(match):
            space, name, quoted = match.groups()
            local, inner = _local(name), quoted[1:-1]
            if local in names:
                if not names[local]:
                    return match.group(0)
                inner = mapper.name(inner)
            elif local in _HREF_ON_LOCALS.get(element, ()):
                inner = mapper.target(inner)
            elif _raw_user_attribute(raw, name, custom):
                inner = chars(inner)
            elif local == "author":
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


def custom_namespaces(parts: dict[str, bytes], defaults: dict, overrides: dict) -> set[str]:
    """Every custom namespace URI the package declares, uses or names."""
    found = set()
    for name, blob in parts.items():
        if not _is_xml(name, defaults, overrides):
            continue
        try:
            root = fromstring(blob)
        except (etree.XMLSyntaxError, UnsafeXML):
            text = blob.decode("utf-8", "replace")
            found.update(m.group(2) for m in re.finditer(
                r"""xmlns(?::[\w.-]+)?\s*=\s*(['"])([^'"]*)\1""", text))
            for markup in _MARKUP.finditer(text):
                if not markup.group(0).startswith(("<?", "<!", "</")):
                    element, values = _raw_tag(markup.group(0))
                    if values.get(_RAW_URIS.get(element)):
                        found.add(values[_RAW_URIS[element]])
            continue
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            found.update(node.nsmap.values())
            found.update(etree.QName(a).namespace for a in node.attrib)
            for attr, value in node.attrib.items():
                if uri_attribute(node.tag, attr):
                    found.add(value)
                elif node.tag in DATA_BINDINGS and attr == W + "prefixMappings":
                    found.update(uri for _, uri in PREFIX_MAPPING.findall(value))
    return {uri for uri in found if custom_namespace(uri)}


def _replace_namespaces(data: bytes, mapper: Mapper) -> bytes:
    for uri, new in mapper.namespaces.items():
        for quote in ('"', "'"):
            data = data.replace(f"{quote}{uri}{quote}".encode(), f"{quote}{new}{quote}".encode())
    return data


def custom_prefixes(root) -> bool:
    """Whether a part declares a prefix for a custom namespace."""
    return any(prefix and custom_namespace(uri)
               for _, (prefix, uri) in etree.iterwalk(root, events=("start-ns",)))


#: Markup as lxml writes it: comments, CDATA sections and processing
#: instructions, then tags. lxml escapes "<" and ">" in text and attribute
#: values, so a tag ends at the first ">".
_SERIALIZED = re.compile(
    r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<(/?)([^\s/>]+)([^>]*?)(/?)>", re.S)
_TAG_ATTRIBUTE = re.compile(r"""(\s+)([^\s=]+)(\s*=\s*)("[^"]*"|'[^']*')""")


def _rename_prefixes(data: bytes, mapper: Mapper, part: str) -> bytes:
    """Give every prefix bound to a custom namespace a generic name.

    ``<Acme:Contract xmlns:Acme="...">`` names a firm in the prefix as well
    as in the URI. A prefix is not part of what the XML means, so wherever
    one is bound to a custom namespace it is renamed: in tags, in attribute
    names, in its declaration and in the markup compatibility lists that
    name prefixes. The new names are none of the prefixes the part declares,
    so no declaration comes to hide another. `data` is lxml's serialization;
    the result must parse to the same tree, or the part is refused.
    """
    text = data.decode("utf-8")
    tags = list(_SERIALIZED.finditer(text))
    declared = {attr.group(2)[6:] for tag in tags if tag.group(2) and not tag.group(1)
                for attr in _TAG_ATTRIBUTE.finditer(tag.group(3))
                if attr.group(2).startswith("xmlns:")}
    renamed: dict[str, str] = {}

    def new(prefix: str) -> str:
        if prefix not in renamed:
            renamed[prefix] = mapper.prefix(prefix, declared | set(renamed.values()))
        return renamed[prefix]

    def qname(name: str, scope: dict) -> str:
        prefix, colon, local = name.partition(":")
        return f"{new(prefix)}:{local}" if colon and custom_namespace(scope.get(prefix)) else name

    def listed(token: str, scope: dict) -> str:
        if ":" in token:
            return qname(token, scope)
        return new(token) if custom_namespace(scope.get(token)) else token

    def clark(name: str, scope: dict, element: bool = False) -> str:
        prefix, colon, local = name.partition(":")
        if colon:
            return "{%s}%s" % (scope.get(prefix), local)
        return "{%s}%s" % (scope[None], name) if element and scope.get(None) else name

    out, at, stack = [], 0, [{"xml": XML_NS}]
    for tag in tags:
        out.append(text[at:tag.start()])
        at = tag.end()
        closing, name, attributes, empty = tag.groups()
        if name is None:
            out.append(tag.group(0))
            continue
        if closing:
            out.append(f"</{qname(name, stack.pop())}{attributes}>")
            continue
        if _TAG_ATTRIBUTE.sub("", attributes).strip():
            raise Refused(f"{part}: its markup could not be read to rename namespace prefixes")
        scope = dict(stack[-1])
        for attr in _TAG_ATTRIBUTE.finditer(attributes):
            if attr.group(2) == "xmlns" or attr.group(2).startswith("xmlns:"):
                scope[attr.group(2)[6:] or None] = html.unescape(attr.group(4)[1:-1])
        element = clark(name, scope, element=True)

        def attribute(attr, scope=scope, element=element):
            space, key, equals, quoted = attr.groups()
            value = quoted[1:-1]
            if key.startswith("xmlns:"):
                if custom_namespace(html.unescape(value)):
                    key = "xmlns:" + new(key[6:])
            else:
                full = clark(key, scope)
                if full in MC_PREFIX_LISTS or (element == "{%s}Choice" % MC_NS and key == "Requires"):
                    value = re.sub(r"\S+", lambda t: listed(t.group(), scope), value)
                key = qname(key, scope)
            return f"{space}{key}{equals}{quoted[0]}{value}{quoted[-1]}"

        out.append(f"<{qname(name, scope)}{_TAG_ATTRIBUTE.sub(attribute, attributes)}{empty}>")
        if not empty:
            stack.append(scope)
    out.append(text[at:])
    result = "".join(out).encode("utf-8")
    if all(old == new for old, new in renamed.items()):
        return data
    if not _same_tree(fromstring(data), fromstring(result)):
        raise Refused(f"{part}: its namespace prefixes could not be renamed safely")
    return result


def _same_tree(a, b) -> bool:
    """The same elements, names, attributes and text; prefixes aside, except
    that every namespace in scope stays in scope and every prefix of a
    standard namespace keeps its binding. (A renamed prefix that shadowed
    another no longer does, so `b` may see more.)"""
    def resolved(node, name, value):
        if name in MC_PREFIX_LISTS or (node.tag == "{%s}Choice" % MC_NS and name == "Requires"):
            return [(node.nsmap.get(t.partition(":")[0]), t.partition(":")[2])
                    for t in value.split()]
        return value
    pairs = itertools.zip_longest(a.iter(), b.iter())
    for x, y in pairs:
        if x is None or y is None or x.tag != y.tag or x.text != y.text or x.tail != y.tail:
            return False
        if not isinstance(x.tag, str):
            continue
        before, after = x.nsmap, y.nsmap
        if (sorted(x.attrib.keys()) != sorted(y.attrib.keys())
                or not set(before.values()) <= set(after.values())
                or any(after.get(p) != u for p, u in before.items() if not custom_namespace(u))
                or any(resolved(x, k, v) != resolved(y, k, y.get(k)) for k, v in x.attrib.items())):
            return False
    return True


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
    for uri in sorted(custom_namespaces(parts, defaults, overrides)):
        mapper.namespace(uri)
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
                    try:
                        result.contexts |= _anonymize_tree(root, mapper, name, known)
                    except UnmappableXPath as e:
                        raise Refused(f"{source}: a data binding path in {name} {e}, which "
                                      "anonymize cannot replace so that it selects the same "
                                      "data; nothing was written") from None
                    data = _serialize(root, data)
                    if custom_prefixes(root):
                        data = _rename_prefixes(data, mapper, f"{source}: {name}")
                data = _replace_namespaces(data, mapper)
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


DS = "{http://schemas.openxmlformats.org/officeDocument/2006/customXml}"
#: Store ids Word gives the package's own property parts in a data binding.
PROPERTY_STORES = {
    "/metadata/core-properties": "{6C3C8BC8-F283-45AE-878A-BAB7291924A1}",
    "/extended-properties": "{6668398D-A668-4E3E-A5EB-62B293D839F1}",
}
_RELS = re.compile(r"^(.*?)_rels/([^/]*)\.rels$")


def _stores(parts: dict[str, bytes]) -> dict[str, str]:
    """Upper-case store id -> the part a data binding with that id reads:
    each custom XML part by the id in its properties part, and the core and
    extended properties."""
    stores = {}
    for name, blob in parts.items():
        match = _RELS.match(name)
        if not match:
            continue
        base, source = match.group(1), match.group(1) + match.group(2)
        try:
            rels = fromstring(blob)
        except (etree.XMLSyntaxError, UnsafeXML):
            continue
        for rel in rels.iter(REL + "Relationship"):
            kind, target = rel.get("Type") or "", rel.get("Target") or ""
            target = (target.lstrip("/") if target.startswith("/")
                      else posixpath.normpath(posixpath.join(base, target)))
            if kind.endswith("/customXmlProps") and target in parts:
                try:
                    item = fromstring(parts[target]).get(DS + "itemID")
                except (etree.XMLSyntaxError, UnsafeXML):
                    continue
                if item:
                    stores[item.upper()] = source
            for suffix, store in PROPERTY_STORES.items():
                if kind.endswith(suffix) and target in parts:
                    stores[store] = target
    return stores


def _bindings(parts: dict[str, bytes]) -> dict[tuple[str, int], tuple]:
    """(part, n) -> what the n-th data binding with a path in that part
    selects: (store part, number of nodes) for the store it names, or for
    every custom XML store when it names none of them. A path or store that
    cannot be evaluated counts as "error"."""
    stores = _stores(parts)
    custom = sorted({p for p in stores.values() if p.startswith("customXml/")})
    trees: dict[str, object] = {}

    def select(store: str, xpath: str, prefixes: dict) -> int | str:
        if store not in trees:
            try:
                trees[store] = fromstring(parts[store])
            except (etree.XMLSyntaxError, UnsafeXML):
                trees[store] = None
        if trees[store] is None:
            return "error"
        try:
            found = trees[store].xpath(xpath, namespaces=prefixes)
        except (etree.XPathError, ValueError, TypeError):
            return "error"
        return len(found) if isinstance(found, list) else "error"

    out = {}
    for name, blob in parts.items():
        if b"dataBinding" not in blob:
            continue
        try:
            root = fromstring(blob)
        except (etree.XMLSyntaxError, UnsafeXML):
            continue
        nodes = [n for n in root.iter(*DATA_BINDINGS) if n.get(W + "xpath")]
        for k, node in enumerate(nodes, 1):
            prefixes = dict(PREFIX_MAPPING.findall(node.get(W + "prefixMappings") or ""))
            store = (node.get(W + "storeItemID") or "").upper()
            targets = [stores[store]] if store in stores else custom
            out[(name, k)] = tuple((t, select(t, node.get(W + "xpath"), prefixes))
                                   for t in targets)
    return out


def binding_check(originals: Sequence[Path], copies: Sequence[Path],
                  limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> tuple[int, list[dict]]:
    """Does every data binding select as many nodes in the copy as in the
    original? Independent of how the paths were replaced: each is evaluated
    against the data it names in both packages. Returns the number of
    bindings and the ones that differ, by file, part and position, with the
    number of nodes each selects; never a path or a value."""
    def total(result) -> int | str:
        if result is None:
            return "missing"
        counts = [n for _, n in result]
        return next((n for n in counts if isinstance(n, str)), sum(counts))

    checked, changed = 0, []
    for index, (original, copy) in enumerate(zip(originals, copies)):
        before = _bindings(read_package(original, limits))
        after = _bindings(read_package(copy, limits))
        checked += len(before)
        for key in sorted(set(before) | set(after)):
            if before.get(key) != after.get(key):
                changed.append({"file": index + 1, "part": key[0], "binding": key[1],
                                "original": total(before.get(key)),
                                "anonymized": total(after.get(key))})
    return checked, changed


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
    ("font", "name"), ("altName", "val"),
))


#: Attributes that are structure wherever they occur, and elements all of
#: whose attributes are: language tags, fonts, namespace URIs, store ids,
#: VML formulas, numbering formats. Data binding paths are not: they hold
#: names and literals of the data, and are read on their own.
STRUCTURE_ATTRS = frozenset((
    "space", "uri", "itemID", "storeItemID", "eqn", "typeface",
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


#: Words of conventional part names, which a document's text can contain too.
PART_NAME_WORDS = frozenset((
    "word", "document", "styles", "stylewitheffects", "styleswitheffects", "settings",
    "websettings", "fonttable", "numbering", "footnotes", "endnotes", "comments",
    "commentsextended", "commentsids", "commentsextensible", "people", "header", "footer",
    "theme", "media", "image", "embeddings", "oleobject", "microsoft", "excel", "worksheet",
    "chart", "charts", "colors", "style", "diagrams", "data", "layout", "quickstyle",
    "drawing", "customxml", "item", "itemprops", "docprops", "core", "custom", "thumbnail",
    "rels", "glossary", "fonts", "font", "activex", "vbaproject", "vbadata",
    "printersettings", "webextensions", "webextension", "taskpanes", "ink", "intelligence",
    "content", "types", "jpeg", "tiff", "odttf", "xlsx", "docx", "pptx", "package",
    "afchunk", "control", "label", "labelinfo", "docmetadata", "xmlsignatures", "origin",
    "sigs", "signature", "printer", "bibliography", "sources",
    # names Word gives embedded objects: Microsoft_Office_Excel_Worksheet1.xlsx
    "office", "powerpoint", "presentation", "visio", "slide", "binary", "macro", "enabled",
))


def _binding_words(node, single: Callable[[str], int]) -> tuple[int, int]:
    """Words of the text in a data binding's path and prefix mappings: those
    in places anonymize replaces (string literals, steps and prefixes of
    custom namespaces or of none), and those in the steps and prefixes of
    standard namespaces, which it keeps. A path that cannot be read is
    counted whole."""
    xpath, mappings = node.get(W + "xpath") or "", node.get(W + "prefixMappings") or ""
    prefixes = dict(PREFIX_MAPPING.findall(mappings))
    try:
        tokens = _xpath_tokens(xpath)
    except UnmappableXPath:
        return single(xpath) + single(mappings), 0
    found = kept = 0
    for prefix, uri in prefixes.items():
        if custom_namespace(uri):
            found += single(prefix)
        else:
            kept += single(prefix)
    for kind, text, _, _ in tokens:
        if kind == "literal":
            found += single(text[1:-1])
        elif kind == "nametest":
            prefix, _, local = text.rpartition(":")
            if prefix and prefix in prefixes and not custom_namespace(prefixes[prefix]):
                kept += single(local)
            else:
                found += single(local) + (single(prefix) if prefix not in prefixes else 0)
    return found, kept


def _replaced(tag: str, attr: str, value: str) -> str | None:
    """The part of an attribute's value that anonymize replaces word by word
    wherever it occurs, or None: a custom namespace URI or schema location
    but for the scheme the replacement keeps (Mapper.target), an attribute
    in a firm's namespace, and the values of custom XML markup and smart
    tags."""
    if uri_attribute(tag, attr) and custom_namespace(value):
        return URL_SCHEME.sub("", value, count=1)
    if user_attribute(tag, attr) or (tag, attr) in MARKUP_VALUES:
        return value
    return None


def leak_scan(paths: Sequence[Path], vocabulary: set[str], phrases: set[tuple[str, str]],
              replacements: set[str] = frozenset(),
              limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> tuple[list[dict], int]:
    """Places in `paths` that still hold words of the original text.

    Element text, the attributes of parts in unknown namespaces and the
    attributes in custom namespaces anywhere are replaced wholesale, so any
    word there of four or more letters is reported; so is one in a name, a
    namespace prefix or a namespace URI of a custom schema (also as custom
    XML markup and smart tags name it), in the values of that markup, or in
    a data binding path's string literals, custom step names and custom
    prefixes. Attributes in the known
    namespaces are kept unless listed as text, and their values are mostly
    names the format defines (``left``, ``auto``, ``Normal``), which a
    document's text may use too; there two consecutive words of the text are
    reported, so free text copied into an attribute this module does not
    know is found and an enumeration is not. Hits in the kept structure
    listed in STRUCTURE, and in the prefixes and binding steps of standard
    namespaces, are counted, not reported. Each report names the file, part
    and element or attribute, never the words, so it can be shared.
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
            # part names are kept; one that holds a word of the text is reported
            found = sum(1 for token in _tokens(name)
                        if token in words and token.lower() not in PART_NAME_WORDS)
            if found:
                hits[(index, name, "(part name)")] += found
            if not data or not _is_xml(name, defaults, overrides):
                continue
            try:
                root = fromstring(data)
            except Exception:
                raw = data.decode("utf-8", "replace")
                custom = _raw_prefixes(raw)
                markup_state = _RawMarkup()
                found = sum(single(m.group(0)) for m in _CHARACTER_DATA.finditer(raw))
                for tag in _MARKUP.finditer(raw):
                    names = markup_state.names(tag.group(0))
                    if tag.group(0).startswith(("<?", "<!", "</")):
                        continue
                    element = re.match(r"<\s*([^\s/>]*)", tag.group(0)).group(1)
                    local_element = _local(element)
                    # a firm's names and prefixes stay in raw markup: report them
                    if ":" in element and element.partition(":")[0] in custom:
                        found += single(element.partition(":")[0]) + single(_local(element))
                    for m in _ATTRIBUTE.finditer(tag.group(0)):
                        key, value = m.group(2), m.group(3)[1:-1]
                        local = _local(key)
                        if key.startswith("xmlns:") and key[6:] in custom:
                            found += single(key[6:])
                        elif local in names:
                            found += single(value) if names[local] else 0
                        elif (local_element, local) in _RAW_VALUES:
                            found += single(value)
                        elif _RAW_URIS.get(local_element) == local and custom_namespace(value):
                            found += single(URL_SCHEME.sub("", value, count=1))
                        elif _raw_user_attribute(element, key, custom):
                            found += single(value) + single(_local(key))
                        else:
                            found += phrase(value)
                if found:
                    hits[(index, name, "(unparsed part)")] += found
                continue
            unknown = etree.QName(root).namespace not in KNOWN_NAMESPACES
            for _, (prefix, uri) in etree.iterwalk(root, events=("start-ns",)):
                found = single(prefix)
                if found and custom_namespace(uri):
                    hits[(index, name, "(namespace prefix)")] += found
                elif found:
                    structural += found
                found = single(URL_SCHEME.sub("", uri, count=1)) if custom_namespace(uri) else 0
                if found:
                    hits[(index, name, "(namespace URI)")] += found
            for node in root.iter():
                if not isinstance(node.tag, str):
                    continue
                label = etree.QName(node).localname
                custom = custom_namespace(etree.QName(node).namespace)
                named = (single(label) if custom else 0) + sum(
                    single(etree.QName(a).localname) for a in node.attrib
                    if custom or custom_namespace(_namespace(a)))
                if named:
                    hits[(index, name, f"{label} (custom name)")] += named
                text = node.text
                if node.tag in INSTRUCTION_TAGS and text:
                    # field types and switches are kept on purpose
                    text = FIELD_CODE.sub(" ", text)
                found = single(text) + single(node.tail)
                if found and _located(node.tag, None):
                    structural += found
                elif found:
                    hits[(index, name, label)] += found
                binding = node.tag in DATA_BINDINGS
                if binding:
                    found, kept = _binding_words(node, single)
                    structural += kept
                    if found:
                        hits[(index, name, f"{label} (data binding path)")] += found
                names = markup_names(node)
                for attr, value in node.attrib.items():
                    if binding and attr in (W + "xpath", W + "prefixMappings"):
                        continue
                    local = etree.QName(attr).localname
                    if attr in names:
                        # custom XML markup and smart tags: a firm's names are
                        # replaced, Office's kept
                        found = single(value)
                        if found and names[attr]:
                            hits[(index, name, f"{label}/@{local} (custom name)")] += found
                        else:
                            structural += found
                        continue
                    replaced = _replaced(node.tag, attr, value)
                    if replaced is not None:
                        found = single(replaced)
                        if found:
                            hits[(index, name, f"{label}/@{local}")] += found
                        continue
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
    #: data bindings with a path in the originals
    bindings: int = 0
    #: bindings that select another number of nodes in the copy
    changed_bindings: list[dict] = field(default_factory=list)

    @property
    def reproduced(self) -> bool:
        return self.original == self.anonymized

    @property
    def passed(self) -> bool:
        """Every finding reproduced, every binding kept, nothing left."""
        return self.reproduced and not self.changed_bindings and not self.leaks

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
        if self.changed_bindings:
            lines.append(f"  data bindings NOT kept ({len(self.changed_bindings)} of "
                         f"{self.bindings}):")
            for row in self.changed_bindings:
                lines.append(f"    {self.outputs[row['file'] - 1].name} {row['part']} binding "
                             f"{row['binding']}: selects {row['anonymized']} node(s), the "
                             f"original {row['original']}")
        elif self.bindings:
            lines.append(f"  data bindings kept: each of {self.bindings} selects as many "
                         "nodes as in the original")
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
            "bindings": {"checked": self.bindings, "changed": self.changed_bindings},
            "leaks": self.leaks,
            "words_in_kept_structure": self.structural,
            "passed": self.passed,
        }


def output_names(count: int) -> list[str]:
    """Generic names: the originals' file names can say what they hold."""
    return ["document.docx"] if count == 1 else ["source.docx", "edited.docx"]


def _same_file(a: Path, b: Path) -> bool:
    """Whether `b` is `a`: the same path once resolved, or the same file
    through a symbolic or hard link, a case-insensitive name or a mount."""
    try:
        if a.resolve() == b.resolve():
            return True
        first, second = os.stat(a), os.stat(b)
    except (OSError, RuntimeError):
        return False
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def check_outputs(paths: Sequence[str | Path], out_dir: str | Path,
                  names: Sequence[str]) -> None:
    """Refuse outputs that would replace an input, before anything is written.

    Each output is checked against every input, so the edited copy of a pair
    cannot be written over its source either. Raises Refused.
    """
    if len(set(names)) != len(names):
        raise Refused("the outputs need distinct names")
    for name in names:
        target = Path(out_dir) / name
        for source in paths:
            if _same_file(Path(source), target):
                raise Refused(f"the output {target} would replace the input {source}; "
                              "anonymize never writes over its inputs, so choose another "
                              "output directory")
        if target.is_dir():
            raise Refused(f"the output {target} is a directory")


def anonymize(paths: Sequence[str | Path], out_dir: str | Path, *,
              names: Sequence[str] | None = None, rng: random.Random | None = None,
              limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> Report:
    """Anonymize one DOCX or a source/edited pair into `out_dir` and verify it.

    Nothing is written into `out_dir` until the copies are made and checked
    in a scratch directory; an output that is, or links to, an input is
    refused first (Refused). Existing outputs that are not inputs are
    replaced.
    """
    sources = [Path(p) for p in paths]
    if not 1 <= len(sources) <= 2:
        raise ValueError("anonymize takes one document or a source and an edited copy")
    if names is None:
        names = output_names(len(sources))
    if len(names) != len(sources):
        raise ValueError("anonymize needs one output name per input")
    out = Path(out_dir)
    check_outputs(sources, out, names)
    mapper = Mapper(rng)
    with tempfile.TemporaryDirectory() as scratch:
        staged = [Path(scratch) / name for name in names]
        files = [_anonymize_package(sources[0], staged[0], mapper, limits)]
        mapper.reading_source = False
        if len(sources) == 2:
            files.append(_anonymize_package(sources[1], staged[1], mapper, limits,
                                            known=files[0].contexts))
        # The originals are read before any copy is moved into place, and
        # every check runs on the staged copies.
        original = findings_of(sources, limits)
        anonymized = findings_of(staged, limits)
        leaks, structural = leak_scan(staged, mapper.vocabulary, mapper.phrases,
                                      mapper.replacements, limits)
        bindings, changed = binding_check(sources, staged, limits)
        check_outputs(sources, out, names)
        out.mkdir(parents=True, exist_ok=True)
        outputs = []
        for result, name in zip(files, names):
            target = out / name
            shutil.move(str(result.output), target)
            result.output = target
            outputs.append(target)
    return Report(outputs, mapper.replaced, mapper.distinct, mapper.people, mapper.dates,
                  mapper.collisions, files, original, anonymized, leaks, structural,
                  bindings=bindings, changed_bindings=changed)
