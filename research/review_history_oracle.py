#!/usr/bin/env python3
"""Independent oracle for the review-history benchmark.

Reads a DOCX package into review facts and compares a tool's output with its
source: what was lost, what was added, and what changed. It never imports the
checker, so the checker's findings can be scored against it.

    python research/review_history_oracle.py facts FILE
    python research/review_history_oracle.py compare SOURCE OUTPUT [--ignore-dates]

Facts are matched by content, never by ids, which tools may renumber. Each
category is a multiset. A lost and an added fact with the same identity (for
example the same revision with a new date, or the same comment with a new
anchor) are reported together as changed. `compare` exits 1 when anything was
lost or changed. Which changes a task allows is declared with the task, not here.

Text is read in two views: `original` rejects every revision (inserted and
moved-to text left out, deleted and moved-from text kept) and `current`
accepts every revision. A correctly tracked edit changes a paragraph's current
text but not its original text. Formatting and layout are out of scope, except
as the payload of a tracked formatting change.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{" + W_NS + "}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
W15 = "{http://schemas.microsoft.com/office/word/2012/wordml}"
W16CID = "{http://schemas.microsoft.com/office/word/2016/wordml/cid}"
W16CEX = "{http://schemas.microsoft.com/office/word/2018/wordml/cex}"
W16DU = "{http://schemas.microsoft.com/office/word/2023/wordml/word16du}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"
EP = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
DCTERMS = "{http://purl.org/dc/terms/}"

PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)

#: Run-level wrappers whose content is inserted or deleted text.
TEXT_REVISIONS = ("ins", "del", "moveFrom", "moveTo")
#: Revisions of properties; each holds the previous properties.
PROPERTY_REVISIONS = ("rPrChange", "pPrChange", "sectPrChange", "tblPrChange",
                      "tblGridChange", "trPrChange", "tcPrChange", "numberingChange")
#: Table cell revisions, which are empty markers inside w:tcPr.
CELL_REVISIONS = ("cellIns", "cellDel", "cellMerge")
INSERTED = {W + "ins", W + "moveTo"}
REMOVED = {W + "del", W + "moveFrom"}
#: Markup that may sit between two fragments of one revision without splitting it.
TRANSPARENT = {W + t for t in ("bookmarkStart", "bookmarkEnd", "commentRangeStart",
                               "commentRangeEnd", "proofErr", "permStart", "permEnd")}
RUN_OBJECTS = {W + t: t for t in ("drawing", "pict", "object", "footnoteReference",
                                  "endnoteReference", "commentReference", "fldChar", "sym")}
SETTINGS = ("trackRevisions", "doNotTrackMoves", "doNotTrackFormatting",
            "removePersonalInformation", "removeDateAndTime")
#: Package metadata that any save may legitimately rewrite. Word for Mac's
#: Save As also rewrites the creation date.
MUTABLE_CORE = {DCTERMS + "created", DCTERMS + "modified", CP + "lastModifiedBy", CP + "revision"}
MUTABLE_APP = {EP + t for t in ("TotalTime", "Pages", "Words", "Characters", "Lines",
                                "Paragraphs", "CharactersWithSpaces", "Application",
                                "AppVersion", "DocSecurity")}
MUTABLE_SETTINGS = {W + "rsids", W14 + "docId", W15 + "docId", W + "proofState"}

#: category -> function of a fact giving its identity, used to pair a lost and
#: an added fact as one changed fact.
IDENTITY = {
    "comment": lambda f: f[2],
    "comment_anchor": lambda f: f[0],
    "comment_date": lambda f: f[0],
    "comment_thread": lambda f: f[0],
    "comment_done": lambda f: f[0],
    "comment_durable_id": lambda f: f[0],
    "person": lambda f: f[0],
    # A property revision's body is (run text, previous, current): changed properties pair.
    "revision": lambda f: (f[0], f[1], f[2], f[5][0] if isinstance(f[5], tuple) else f[5]),
    "move_range": lambda f: (f[0], f[1], f[2]),
    "paragraph": lambda f: None,
    "paragraph_current": lambda f: f[:2],
    "note": lambda f: None,
    "note_current": lambda f: f[:2],
    "note_reference": lambda f: f[:2],
    "story": lambda f: f[:3],
    "story_current": lambda f: f[:4],
    "list_item": lambda f: f[:2],
    "content_control": lambda f: f[:3],
    "table": lambda f: f[0],
    "hyperlink": lambda f: f[:2],
    "image": lambda f: (f[0], f[4]),
    "setting": lambda f: f[0],
    "part": lambda f: f[0],
}


# --- package ------------------------------------------------------------------

class Package:
    def __init__(self, path: Path):
        with zipfile.ZipFile(path) as z:
            self.parts = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
        self._xml: dict[str, object] = {}
        self.main = self.related("", "officeDocument")[0][1]

    def xml(self, name):
        if name not in self._xml:
            blob = self.parts.get(name)
            self._xml[name] = None if blob is None else etree.fromstring(blob, PARSER)
        return self._xml[name]

    def rels(self, source: str) -> dict[str, tuple[str, str, bool]]:
        """Relationship id -> (type suffix, target part or URL, external).

        `source` is a part name, or "" for the package itself.
        """
        folder, _, name = source.rpartition("/")
        root = self.xml(f"{folder}/_rels/{name}.rels" if folder
                        else f"_rels/{name}.rels" if name else "_rels/.rels")
        found = {}
        for rel in [] if root is None else root.iter(REL + "Relationship"):
            target = rel.get("Target", "")
            kind = rel.get("Type", "").rsplit("/", 1)[-1]
            if (rel.get("TargetMode") or "").lower() == "external":
                found[rel.get("Id")] = (kind, target, True)
                continue
            path = unquote(target.lstrip("/") if target.startswith("/")
                           else posixpath.normpath(posixpath.join(folder, target)))
            found[rel.get("Id")] = (kind, path, False)
        return found

    def related(self, source: str, kind: str) -> list[tuple[str, str]]:
        return sorted((rid, target) for rid, (k, target, external) in self.rels(source).items()
                      if k == kind and not external)

    def first(self, kind: str):
        found = self.related(self.main, kind)
        return found[0][1] if found else None


# --- text ---------------------------------------------------------------------

def _own(paragraph):
    """Descendants of a paragraph, excluding paragraphs nested in it (text boxes)."""
    for node in paragraph.iter():
        if node is not paragraph and node.tag == W + "p":
            continue
        owner = next(node.iterancestors(W + "p"), None) if node is not paragraph else paragraph
        if owner is paragraph:
            yield node


def _in(node, tags) -> bool:
    return any(a.tag in tags for a in node.iterancestors())


def _token(node, view: str) -> str | None:
    tag = node.tag
    if tag not in (W + "t", W + "delText", W + "tab", W + "br", W + "cr"):
        return None
    if view == "original" and _in(node, INSERTED):
        return None
    if view == "current" and (tag == W + "delText" or _in(node, REMOVED)):
        return None
    if tag == W + "tab":
        return "\t"
    if tag in (W + "br", W + "cr"):
        return "\n"
    return node.text or ""


def paragraph_text(paragraph, view: str) -> str:
    return "".join(t for t in (_token(n, view) for n in _own(paragraph)) if t is not None)


def text(element, view: str) -> str:
    """Paragraph texts of an element, one line per paragraph."""
    paragraphs = [element] if element.tag == W + "p" else list(element.iter(W + "p"))
    return "\n".join(paragraph_text(p, view) for p in paragraphs)


def payload(element) -> str:
    """Everything a text revision holds, deleted or not, with object markers."""
    out = []
    for node in element.iter():
        if node.tag in (W + "t", W + "delText"):
            out.append(node.text or "")
        elif node.tag == W + "tab":
            out.append("\t")
        elif node.tag in (W + "br", W + "cr"):
            out.append("\n")
        elif node.tag in RUN_OBJECTS:
            out.append(f"[{RUN_OBJECTS[node.tag]}]")
    return "".join(out)


def signature(node) -> tuple:
    """Canonical XML: attributes sorted, insignificant whitespace dropped."""
    if not isinstance(node.tag, str):
        return ()
    body = (node.text or "") if node.tag in (W + "t", W + "delText", W + "instrText") else (
        (node.text or "").strip())
    return (node.tag, tuple(sorted(node.attrib.items())), body,
            tuple(signature(c) for c in node if isinstance(c.tag, str)))


def _digest(value) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:16]


# --- stories ------------------------------------------------------------------

def stories(pkg: Package) -> list[tuple[str, str, object]]:
    """(story name, part, root) for the body, headers/footers per section slot,
    notes and comments."""
    main = pkg.xml(pkg.main)
    found = [("document", pkg.main, main)]
    rels = pkg.rels(pkg.main)
    sections = [s for s in main.iter(W + "sectPr")
                if not any(a.tag == W + "sectPrChange" for a in s.iterancestors())]
    for index, section in enumerate(sections, 1):
        for ref in section:
            kind = {W + "headerReference": "header", W + "footerReference": "footer"}.get(ref.tag)
            if kind is None:
                continue
            target = rels.get(ref.get(R + "id"), (None, None, True))
            root = None if target[2] else pkg.xml(target[1])
            if root is not None:
                found.append((f"{kind}/{ref.get(W + 'type') or 'default'}/{index}", target[1], root))
    for kind in ("footnotes", "endnotes", "comments"):
        part = pkg.first(kind)
        root = pkg.xml(part) if part else None
        if root is not None:
            found.append((kind, part, root))
    return found


def _context(node):
    paragraph = node if node.tag == W + "p" else next(node.iterancestors(W + "p"), None)
    return None if paragraph is None else paragraph_text(paragraph, "original")


# --- facts --------------------------------------------------------------------

def _revision_dates(node, ignore_dates: bool):
    return None if ignore_dates else (node.get(W + "date"), node.get(W16DU + "dateUtc"))


def _revision_key(node):
    return (node.tag, node.get(W + "author"), node.get(W + "date"), node.get(W16DU + "dateUtc"))


def revisions(name, root, ignore_dates: bool, out: collections.Counter):
    nesting = lambda node: tuple(  # noqa: E731
        (a.tag[len(W):], a.get(W + "author")) for a in reversed(list(node.iterancestors()))
        if a.tag in INSERTED | REMOVED)
    for node in root.iter(*(W + t for t in TEXT_REVISIONS)):
        if _in(node, {W + "pPrChange", W + "rPrChange"}):
            continue  # part of the previous properties a property revision keeps
        parent = node.getparent()
        kind = node.tag[len(W):]
        if parent.tag == W + "rPr":
            if parent.getparent().tag == W + "pPr":
                kind, body = kind + "-mark", "¶"
            else:
                continue
        elif parent.tag == W + "trPr":
            kind, body = kind + "-row", text(parent.getparent(), "original")
        else:
            previous = node.getprevious()
            while previous is not None and previous.tag in TRANSPARENT:
                previous = previous.getprevious()
            if previous is not None and _revision_key(previous) == _revision_key(node):
                continue  # a later fragment of one revision; counted with the first
            body, following = payload(node), node.getnext()
            while following is not None:
                if following.tag in TRANSPARENT:
                    following = following.getnext()
                    continue
                if _revision_key(following) != _revision_key(node):
                    break
                body += payload(following)
                following = following.getnext()
        out[(name, kind, node.get(W + "author"), _revision_dates(node, ignore_dates),
             nesting(node), body, _context(node))] += 1
    for node in root.iter(*(W + t for t in PROPERTY_REVISIONS)):
        owner = node.getparent()
        skipped = {node.tag, W + "sectPr"} | ({W + "rPr"} if node.tag == W + "pPrChange" else set())
        current = tuple(signature(c) for c in owner if c.tag not in skipped)
        previous = tuple(signature(grand) for child in node for grand in child)
        target = owner.getparent()
        body = payload(target) if node.tag == W + "rPrChange" and target.tag == W + "r" else (
            "¶" if node.tag == W + "rPrChange" else "")
        out[(name, node.tag[len(W):], node.get(W + "author"), _revision_dates(node, ignore_dates),
             (), (body, _digest(previous), _digest(current)), _context(target))] += 1
    for node in root.iter(*(W + t for t in CELL_REVISIONS)):
        cell = next(node.iterancestors(W + "tc"))
        out[(name, node.tag[len(W):], node.get(W + "author"), _revision_dates(node, ignore_dates),
             (), text(cell, "original"), None)] += 1


def move_ranges(name, root, ignore_dates: bool, out: collections.Counter):
    for node in root.iter(W + "moveFromRangeStart", W + "moveToRangeStart"):
        out[(name, node.tag[len(W):], node.get(W + "author"),
             _revision_dates(node, ignore_dates))] += 1


def comments(pkg: Package, all_stories, ignore_dates: bool, facts: dict):
    part = pkg.first("comments")
    root = pkg.xml(part) if part else None
    if root is None:
        return
    extended = {}
    part = pkg.first("commentsExtended")
    if part and pkg.xml(part) is not None:
        extended = {e.get(W15 + "paraId"): e for e in pkg.xml(part).iter(W15 + "commentEx")}
    durable, utc = {}, {}
    part = pkg.first("commentsIds")
    if part and pkg.xml(part) is not None:
        durable = {c.get(W16CID + "paraId"): c.get(W16CID + "durableId")
                   for c in pkg.xml(part).iter(W16CID + "commentId")}
    part = pkg.first("commentsExtensible")
    if part and pkg.xml(part) is not None:
        utc = {c.get(W16CEX + "durableId"): c.get(W16CEX + "dateUtc")
               for c in pkg.xml(part).iter(W16CEX + "commentExtensible")}
    anchors = _anchors(all_stories)
    by_id, by_para = {}, {}
    for comment in root.iter(W + "comment"):
        key = (comment.get(W + "author"), comment.get(W + "initials"),
               text(comment, "current").strip())
        paras = comment.findall(W + "p")
        para = paras[-1].get(W14 + "paraId") if paras else None
        by_id[comment.get(W + "id")] = key
        by_para[para] = key
        facts["comment"][key] += 1
        if not ignore_dates:
            facts["comment_date"][(key, comment.get(W + "date"),
                                   utc.get(durable.get(para)))] += 1
        anchor = anchors.get(comment.get(W + "id"), {})
        facts["comment_anchor"][(key, anchor.get("story"), anchor.get("original"),
                                 anchor.get("current"), "start" in anchor, "end" in anchor,
                                 "reference" in anchor)] += 1
        if para in durable:
            facts["comment_durable_id"][(key,)] += 1
        ex = extended.get(para)
        if ex is not None:
            facts["comment_done"][(key, ex.get(W15 + "done") in ("1", "true"))] += 1
    for para, ex in extended.items():
        parent = ex.get(W15 + "paraIdParent")
        if para in by_para and parent:
            facts["comment_thread"][(by_para[para], by_para.get(parent))] += 1
    part = pkg.first("people")
    if part and pkg.xml(part) is not None:
        for person in pkg.xml(part).iter(W15 + "person"):
            presence = person.find(W15 + "presenceInfo")
            facts["person"][(person.get(W15 + "author"),
                             None if presence is None else presence.get(W15 + "providerId"),
                             None if presence is None else presence.get(W15 + "userId"))] += 1


def _anchors(all_stories) -> dict[str, dict]:
    anchors: dict[str, dict] = {}
    for name, _, root in all_stories:
        if name == "comments":
            continue
        open_ranges: dict[str, dict] = {}
        for node in root.iter():
            if node.tag == W + "commentRangeStart":
                cid = node.get(W + "id")
                open_ranges[cid] = {"original": [], "current": [], "para": None}
                anchors.setdefault(cid, {})["start"] = True
                anchors[cid]["story"] = name
            elif node.tag == W + "commentRangeEnd":
                cid = node.get(W + "id")
                anchors.setdefault(cid, {})["end"] = True
                span = open_ranges.pop(cid, None)
                if span is not None:
                    anchors[cid]["original"] = "".join(span["original"])
                    anchors[cid]["current"] = "".join(span["current"])
            elif node.tag == W + "commentReference":
                anchors.setdefault(node.get(W + "id"), {})["reference"] = True
                anchors[node.get(W + "id")].setdefault("story", name)
            elif node.tag in (W + "t", W + "delText", W + "tab", W + "br", W + "cr"):
                paragraph = next(node.iterancestors(W + "p"), None)
                for span in open_ranges.values():
                    if span["para"] is not None and paragraph is not span["para"]:
                        span["original"].append("\n")
                        span["current"].append("\n")
                    span["para"] = paragraph
                    for view in ("original", "current"):
                        token = _token(node, view)
                        if token is not None:
                            span[view].append(token)
    return anchors


def notes(pkg: Package, all_stories, facts: dict):
    bodies = {}
    for kind in ("footnotes", "endnotes"):
        part = pkg.first(kind)
        root = pkg.xml(part) if part else None
        if root is None:
            continue
        for note in root.findall(W + kind[:-1]):
            if note.get(W + "type") in ("separator", "continuationSeparator", "continuationNotice"):
                continue
            original, current = text(note, "original").strip(), text(note, "current").strip()
            bodies[(kind, note.get(W + "id"))] = original
            facts["note"][(kind, original)] += 1
            facts["note_current"][(kind, original, current)] += 1
    for name, _, root in all_stories:
        for tag, kind in ((W + "footnoteReference", "footnotes"), (W + "endnoteReference", "endnotes")):
            for ref in root.iter(tag):
                facts["note_reference"][(kind, bodies.get((kind, ref.get(W + "id"))), name,
                                         _context(ref))] += 1


def lists(pkg: Package, all_stories, facts: dict):
    numbering = pkg.xml(pkg.first("numbering")) if pkg.first("numbering") else None
    abstract, nums = {}, {}
    if numbering is not None:
        abstract = {a.get(W + "abstractNumId"): a for a in numbering.iter(W + "abstractNum")}
        nums = {n.get(W + "numId"): n for n in numbering.iter(W + "num")}

    def level(num_id, ilvl):
        num = nums.get(num_id)
        if num is None:
            return None, None
        for override in num.iter(W + "lvlOverride"):
            lvl = override.find(W + "lvl")
            if override.get(W + "ilvl") == ilvl and lvl is not None:
                break
        else:
            ref = num.find(W + "abstractNumId")
            base = abstract.get(None if ref is None else ref.get(W + "val"))
            lvl = None if base is None else next(
                (x for x in base.iter(W + "lvl") if x.get(W + "ilvl") == ilvl), None)
        if lvl is None:
            return None, None
        fmt, label = lvl.find(W + "numFmt"), lvl.find(W + "lvlText")
        return (None if fmt is None else fmt.get(W + "val"),
                None if label is None else label.get(W + "val"))

    for name, _, root in all_stories:
        for num_pr in root.iter(W + "numPr"):
            if num_pr.getparent().tag != W + "pPr" or _in(num_pr, {W + "pPrChange"}):
                continue
            num_id, ilvl = num_pr.find(W + "numId"), num_pr.find(W + "ilvl")
            num_id = None if num_id is None else num_id.get(W + "val")
            ilvl = "0" if ilvl is None else ilvl.get(W + "val")
            if num_id == "0":
                continue
            facts["list_item"][(name, _context(num_pr), ilvl, *level(num_id, ilvl))] += 1


def objects(pkg: Package, all_stories, facts: dict):
    for name, part, root in all_stories:
        rels = pkg.rels(part)
        for sdt in root.iter(W + "sdt"):
            props = sdt.find(W + "sdtPr")
            content = sdt.find(W + "sdtContent")
            kinds = tuple(sorted(c.tag.split("}")[-1] for c in ([] if props is None else props)
                                 if c.tag not in (W + "id", W + "alias", W + "tag", W + "rPr")))
            value = lambda tag: None if props is None or props.find(tag) is None else (  # noqa: E731
                props.find(tag).get(W + "val"))
            body = "" if content is None else "\n".join(
                paragraph_text(p, "original") for p in content.iter(W + "p")) or (
                "".join(t for t in (_token(n, "original") for n in content.iter()) if t))
            facts["content_control"][(name, value(W + "tag"), value(W + "alias"), kinds, body)] += 1
        for table in root.iter(W + "tbl"):
            grid = tuple(g.get(W + "w") for g in table.findall(W + "tblGrid/" + W + "gridCol"))
            rows = tuple(tuple(text(cell, "original") for cell in row.findall(W + "tc"))
                         for row in table.findall(W + "tr"))
            header = sum(1 for row in table.findall(W + "tr")
                         if row.find(W + "trPr/" + W + "tblHeader") is not None)
            facts["table"][(name, grid, header, rows)] += 1
        for link in root.iter(W + "hyperlink"):
            target = rels.get(link.get(R + "id"), (None, None, None))[1] if link.get(R + "id") \
                else "#" + (link.get(W + "anchor") or "")
            facts["hyperlink"][(name, target, "".join(
                t for t in (_token(n, "original") for n in link.iter()) if t))] += 1
        for blip in root.iter(A + "blip"):
            rid = blip.get(R + "embed") or blip.get(R + "link")
            kind, target, external = rels.get(rid, (None, None, None))
            blob = None if external or target is None else pkg.parts.get(target)
            drawing = next(blip.iterancestors(W + "drawing"), None)
            extent = None if drawing is None else drawing.find(".//" + WP + "extent")
            doc_pr = None if drawing is None else drawing.find(".//" + WP + "docPr")
            facts["image"][(name, None if blob is None else hashlib.sha256(blob).hexdigest(),
                            None if extent is None else extent.get("cx"),
                            None if extent is None else extent.get("cy"),
                            None if doc_pr is None else doc_pr.get("descr"))] += 1


def settings(pkg: Package, facts: dict):
    part = pkg.first("settings")
    root = pkg.xml(part) if part else None
    for name in SETTINGS:
        node = None if root is None else root.find(W + name)
        on = node is not None and node.get(W + "val", "true") not in ("0", "false", "off")
        facts["setting"][(name, on)] += 1


def parts(pkg: Package, covered: set[str], facts: dict):
    for name, blob in sorted(pkg.parts.items()):
        if name in covered:
            continue
        if not name.endswith((".xml", ".rels")):
            facts["part"][(name, hashlib.sha256(blob).hexdigest()[:16])] += 1
            continue
        root = etree.fromstring(blob, PARSER)
        drop = {"docProps/core.xml": MUTABLE_CORE, "docProps/app.xml": MUTABLE_APP}.get(name, set())
        if root.tag == W + "settings":
            drop = MUTABLE_SETTINGS | {W + t for t in SETTINGS}  # settings are their own facts
        for node in [c for c in root if c.tag in drop]:
            root.remove(node)
        if name.endswith(".rels") or name == "[Content_Types].xml":
            _anonymise(root, name, covered)
        sig = signature(root)
        if name.endswith(".rels") or name == "[Content_Types].xml":
            # Relationship ids and element order are a producer's private business.
            children = sorted((c[0], tuple(a for a in c[1] if a[0] != "Id"), c[2], c[3])
                              for c in sig[3])
            sig = (sig[0], sig[1], sig[2], tuple(children))
        facts["part"][(name, _digest(sig))] += 1


def _anonymise(root, name: str, covered: set[str]):
    """Name compared parts by role, so renaming one is not a package change."""
    folder = "" if name == "[Content_Types].xml" else name.rpartition("_rels/")[0].rstrip("/")
    for node in root:
        if node.get("PartName", "").lstrip("/") in covered:
            node.set("PartName", "compared")
        target = node.get("Target")
        if target is not None and (node.get("TargetMode") or "").lower() != "external":
            path = unquote(target.lstrip("/") if target.startswith("/")
                           else posixpath.normpath(posixpath.join(folder, target)))
            if path in covered:
                node.set("Target", "compared")


def facts(path: Path, *, ignore_dates: bool = False) -> dict[str, collections.Counter]:
    pkg = Package(Path(path))
    found = {category: collections.Counter() for category in IDENTITY}
    all_stories = stories(pkg)
    for name, _, root in all_stories:
        revisions(name, root, ignore_dates, found["revision"])
        move_ranges(name, root, ignore_dates, found["move_range"])
        if name == "comments":
            continue  # comment bodies are compared as comments
        for paragraph in root.iter(W + "p"):
            original = paragraph_text(paragraph, "original")
            found["paragraph"][(name, original)] += 1
            found["paragraph_current"][(name, original, paragraph_text(paragraph, "current"))] += 1
        if name.startswith(("header", "footer")):
            kind, variant, section = name.split("/")
            original, current = text(root, "original"), text(root, "current")
            found["story"][(kind, variant, section, original)] += 1
            found["story_current"][(kind, variant, section, original, current)] += 1
    comments(pkg, all_stories, ignore_dates, found)
    notes(pkg, all_stories, found)
    lists(pkg, all_stories, found)
    objects(pkg, all_stories, found)
    settings(pkg, found)
    covered = {pkg.main}
    for kind in ("header", "footer"):
        covered.update(t for _, t in pkg.related(pkg.main, kind))
    for kind in ("footnotes", "endnotes", "comments", "commentsExtended", "commentsIds",
                 "commentsExtensible", "people"):
        covered.update(t for _, t in pkg.related(pkg.main, kind))
    parts(pkg, covered, found)
    return found


# --- comparison ---------------------------------------------------------------

def compare(source: Path, output: Path, *, ignore_dates: bool = False) -> dict:
    """Per category: facts lost from the source, added in the output, and changed."""
    before = facts(source, ignore_dates=ignore_dates)
    after = facts(output, ignore_dates=ignore_dates)
    report = {"lost": {}, "added": {}, "changed": {}}
    for category, identity in IDENTITY.items():
        lost = sorted((before[category] - after[category]).elements(), key=repr)
        added = sorted((after[category] - before[category]).elements(), key=repr)
        changed = []
        for fact in list(lost):
            key = identity(fact)
            if key is None:
                continue
            partner = next((a for a in added if identity(a) == key), None)
            if partner is not None:
                lost.remove(fact)
                added.remove(partner)
                changed.append([fact, partner])
        for name, value in (("lost", lost), ("added", added), ("changed", changed)):
            if value:
                report[name][category] = value
    return report


def summary(report: dict) -> dict[str, tuple[int, int, int]]:
    """category -> (lost, added, changed) counts, only nonzero categories."""
    names = set(report["lost"]) | set(report["added"]) | set(report["changed"])
    return {c: (len(report["lost"].get(c, [])), len(report["added"].get(c, [])),
                len(report["changed"].get(c, []))) for c in sorted(names)}


def _jsonable(value):
    if isinstance(value, collections.Counter):
        return sorted(([_jsonable(k), n] for k, n in value.items()), key=repr)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_facts = sub.add_parser("facts")
    p_facts.add_argument("file", type=Path)
    p_facts.add_argument("--ignore-dates", action="store_true")
    p_compare = sub.add_parser("compare")
    p_compare.add_argument("source", type=Path)
    p_compare.add_argument("output", type=Path)
    p_compare.add_argument("--ignore-dates", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "facts":
        print(json.dumps(_jsonable(facts(args.file, ignore_dates=args.ignore_dates)),
                         indent=1, ensure_ascii=False))
        return 0
    report = compare(args.source, args.output, ignore_dates=args.ignore_dates)
    print(json.dumps(_jsonable(report), indent=1, ensure_ascii=False))
    return 1 if report["lost"] or report["changed"] else 0


if __name__ == "__main__":
    sys.exit(main())
