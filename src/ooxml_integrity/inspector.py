"""
Deterministic structural-integrity inspector for .docx.

It does not answer "is this XML schema-valid". It answers "will this file
survive being opened in Word, and did it lose meaning on the way".

No model calls, no rendering, no network.
"""
from __future__ import annotations

import posixpath
import zipfile
from collections import Counter
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlsplit

from lxml import etree

from .archive import (
    DEFAULT_ARCHIVE_LIMITS,
    ArchiveLimits,
    PackageIssue,
    read_package,
)
from .finding import ERROR, INFO, WARN, Finding
from .comments import ASCII_LOWER, comment_part, comment_tree
from .xmlutil import UnsafeXML, fromstring as parse_xml, text_contexts

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}


def _w(tag: str) -> str:
    return f"{{{NS['w']}}}{tag}"


def _r(tag: str) -> str:
    return f"{{{NS['r']}}}{tag}"


def _paragraph_revision_pair(elements: list[etree._Element]) -> bool:
    """Recognize only the verified plain whole-paragraph mark/content pair.

    A paragraph-mark ins/del and a content ins/del have distinct OOXML types
    (SDK Inserted/Deleted vs InsertedRun/DeletedRun). Sharing an ID between
    these types is not itself a collision. Keep all unverified shapes on the
    conservative path; this is neither schema nor revision-identity validation.
    """
    if len(elements) != 2 or elements[0].tag != elements[1].tag:
        return False
    ident = elements[0].get(_w("id"), "")
    if not ident or any(c not in "0123456789" for c in ident):
        return False
    kind = elements[0].tag
    if kind not in (_w("ins"), _w("del")):
        return False
    content = next((e for e in elements if e.getparent() is not None
                    and e.getparent().tag == _w("p")), None)
    if content is None:
        return False
    paragraph = content.getparent()
    if paragraph.getparent() is None or paragraph.getparent().tag != _w("body"):
        return False
    mark = elements[1] if content is elements[0] else elements[0]
    props = paragraph.find(_w("pPr"))
    if (props is None or list(paragraph) != [props, content]
            or mark is not props.find(f"{_w('rPr')}/{kind}") or len(mark)):
        return False
    for attr in (_w("author"), _w("date")):
        if not mark.get(attr) or mark.get(attr) != content.get(attr):
            return False
    utc = "{http://schemas.microsoft.com/office/word/2023/wordml/word16du}dateUtc"
    if mark.get(utc) != content.get(utc):
        return False
    # No other revisions/property history, even with a different ID.
    revision_tags = {_w(t) for t in ("ins", "del", "moveFrom", "moveTo")}
    for e in paragraph.iter():
        if e.tag in revision_tags and e is not mark and e is not content:
            return False
        if isinstance(e.tag, str) and e.tag.startswith(f"{{{NS['w']}}}"):
            local = etree.QName(e).localname
            if local.endswith("Change") or local.startswith("move"):
                return False
    text_tag = _w("t" if kind == _w("ins") else "delText")
    has_text = False
    for run in content:
        if run.tag != _w("r"):
            return False
        for child in run:
            if child.tag == text_tag:
                if len(child):
                    return False
                has_text |= bool(child.text)
            elif child.tag != _w("rPr"):
                return False
    return has_text


# relationship types that are referenced from the package rather than from
# the body, so "declared but never used" is not meaningful for them
_IMPLICIT_RELS = (
    "styles", "numbering", "footnotes", "endnotes", "comments", "settings",
    "fontTable", "theme", "webSettings", "customXml", "people",
    "commentsExtended", "commentsIds", "glossaryDocument",
)


class Inspector:
    """Runs every check against one package. Reusable, but cheap to recreate."""

    def __init__(self, path: str | Path,
                 limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS):
        self.path = Path(path)
        self.limits = limits
        self.findings: list[Finding] = []
        self.parts: dict[str, bytes] = {}
        self.trees: dict[str, etree._Element] = {}
        self.readable = True

    # ------------------------------------------------------------------ util
    def _add(self, code: str, sev, msg: str, where: str = "", part: str = "") -> None:
        self.findings.append(Finding(code, sev, msg, where, part))

    def _tree(self, name: str):
        return self.trees.get(name)

    @staticmethod
    def _xpath(el) -> str:
        try:
            return el.getroottree().getpath(el)
        except Exception:
            return ""

    # ------------------------------------------------------------------ load
    def load(self) -> bool:
        try:
            self.parts = read_package(self.path, self.limits)
        except FileNotFoundError:
            self._add("PKG000", ERROR, f"file not found: {self.path}")
            self.readable = False
            return False
        except PackageIssue as e:
            self._add(e.code, ERROR, str(e), part=e.part)
            self.readable = False
            return False
        except zipfile.BadZipFile as e:
            self._add("PKG002", ERROR, f"not a valid OPC package: {e}")
            self.readable = False
            return False
        except OSError as e:
            # A directory, an unreadable file, and an I/O failure are all bad
            # inputs, not reasons for the CLI to escape with a traceback.
            self._add("PKG002", ERROR, f"could not read OPC package: {e}")
            self.readable = False
            return False

        for name, data in self.parts.items():
            if name.endswith((".xml", ".rels")):
                try:
                    self.trees[name] = parse_xml(data)
                except UnsafeXML as e:
                    self._add(
                        "XML001", ERROR,
                        f"XML could not be safely parsed: {e}",
                        part=name,
                    )
                except etree.XMLSyntaxError as e:
                    self._add("XML001", ERROR, f"XML is not well-formed: {e}", part=name)
        return True

    # ---------------------------------------------------------------- checks
    def check_content_types(self) -> None:
        ct = self._tree("[Content_Types].xml")
        if ct is None:
            self._add("PKG003", ERROR, "missing [Content_Types].xml")
            return
        defaults = {
            d.get("Extension", "").lower() for d in ct.findall(f"{{{NS['ct']}}}Default")
        }
        overrides = {o.get("PartName") for o in ct.findall(f"{{{NS['ct']}}}Override")}
        if "rels" not in defaults:
            self._add(
                "PKG004", ERROR,
                'no <Default Extension="rels"> - OPC-legal, but Word reports the '
                "package as corrupt",
                part="[Content_Types].xml",
            )
        for name in self.parts:
            if name.endswith("/"):          # zip directory entry, not an OPC part
                continue
            if name == "[Content_Types].xml":  # the stream itself, not an OPC part
                continue
            if name.startswith("_rels/") or "/_rels/" in name:
                continue
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if "/" + name in overrides or ext in defaults:
                continue
            self._add("PKG005", ERROR, f"part not covered by content types: {name}",
                      part=name)

    def _rels_for(self, part: str) -> tuple[dict[str, tuple], str]:
        d, _, base = part.rpartition("/")
        rels = f"{d}/_rels/{base}.rels" if d else f"_rels/{base}.rels"
        t = self._tree(rels)
        out: dict[str, tuple] = {}
        if t is not None:
            for rel in t.findall(f"{{{NS['rel']}}}Relationship"):
                out[rel.get("Id")] = (
                    rel.get("Target"), rel.get("TargetMode"), rel.get("Type") or "",
                )
        return out, rels

    @staticmethod
    def _source_for_rels(rels: str) -> str | None:
        """The package part that owns a relationship part.

        `_rels/.rels` belongs to the package itself, represented by an empty
        string. `word/_rels/header1.xml.rels` belongs to `word/header1.xml`.
        A name that is not a relationship part returns None.
        """
        if rels == "_rels/.rels":
            return ""
        if rels.startswith("_rels/"):
            directory, leaf = "", rels[len("_rels/"):]
        else:
            directory, marker, leaf = rels.rpartition("/_rels/")
            if not marker:
                return None
        if not leaf.endswith(".rels"):
            return None
        source_leaf = leaf[:-len(".rels")]
        if not source_leaf:
            return None
        return f"{directory}/{source_leaf}" if directory else source_leaf

    @staticmethod
    def _target_candidates(source: str, target: str) -> tuple[str, ...]:
        """Package-part names an internal relationship target may denote.

        OPC targets are URI references. Resolve them relative to the owning
        part, strip a fragment, and accept both the spelling in the zip and its
        percent-decoded spelling. Producers in the wild use both for names
        containing spaces.
        """
        parsed = urlsplit(target)
        raw = parsed.path
        if not raw:
            return (source,) if source and parsed.fragment else ()
        if raw.startswith("/"):
            joined = raw.lstrip("/")
        else:
            base = posixpath.dirname(source) if source else ""
            joined = posixpath.join(base, raw) if base else raw
        resolved = posixpath.normpath(joined).lstrip("/")
        if resolved in ("", ".", "..") or resolved.startswith("../"):
            return ()
        decoded = unquote(resolved)
        return ((resolved, decoded) if decoded != resolved else (resolved,))

    def check_relationships(self) -> None:
        doc = self._tree("word/document.xml")
        if doc is None:
            self._add("PKG006", ERROR, "missing word/document.xml")

        # A DOCX is entered through the package-level officeDocument
        # relationship. Hard-coding word/document.xml without checking the root
        # graph can call a package clean even though Word has no way to find it.
        root_rels = self._tree("_rels/.rels")
        if root_rels is None:
            if "_rels/.rels" not in self.parts:  # malformed XML already has XML001
                self._add(
                    "REL001", ERROR,
                    "missing _rels/.rels - the package has no officeDocument "
                    "entry point",
                    part="_rels/.rels",
                )
        else:
            office_rels = [
                rel for rel in root_rels.findall(
                    f"{{{NS['rel']}}}Relationship")
                if (rel.get("Type") or "").endswith("/officeDocument")
            ]
            if not office_rels:
                self._add(
                    "REL001", ERROR,
                    "_rels/.rels has no officeDocument relationship - Word "
                    "cannot locate the document",
                    part="_rels/.rels",
                )
            elif not any(
                rel.get("TargetMode") != "External" and rel.get("Target")
                for rel in office_rels
            ):
                self._add(
                    "REL001", ERROR,
                    "the package officeDocument relationship must have an "
                    "internal target",
                    part="_rels/.rels",
                )

        # Relationship ids are scoped to the XML part that contains them. Scan
        # every successfully parsed XML part, not only the main document: headers,
        # footers, footnotes and custom parts may all own images or hyperlinks.
        used_by_source: dict[str, set[str]] = {}
        for source, tree in self.trees.items():
            if source.endswith(".rels"):
                continue
            rels, relsname = self._rels_for(source)
            used: set[str] = set()
            for el in tree.iter():
                for attr in (_r("id"), _r("embed"), _r("link")):
                    rid = el.get(attr)
                    if not rid:
                        continue
                    used.add(rid)
                    if rid not in rels:
                        self._add(
                            "REL001", ERROR,
                            f"relationship {rid} not found in {relsname} - Word "
                            "will error or drop the object",
                            self._xpath(el), source,
                        )
            used_by_source[source] = used

        # Every relationship part is still useful even when its source is binary
        # or malformed: an internal target must name a package part. REL003 is
        # deliberately narrower. It is only meaningful when the owning XML part
        # parsed and could be searched; root relationships and relationships of a
        # binary source are implicit and must not be called unused.
        equivalent_names = {name.translate(ASCII_LOWER) for name in self.parts}
        for relsname, tree in self.trees.items():
            if not relsname.endswith(".rels"):
                continue
            source = self._source_for_rels(relsname)
            if source is None:
                continue
            rels: dict[str | None, tuple[str | None, str | None, str]] = {}
            for rel in tree.findall(f"{{{NS['rel']}}}Relationship"):
                rid = rel.get("Id")
                target = rel.get("Target")
                mode = rel.get("TargetMode")
                rtype = rel.get("Type") or ""
                rels[rid] = (target, mode, rtype)
                if mode == "External":
                    continue
                if not target:
                    self._add(
                        "REL002", ERROR,
                        f"{rid} has no internal target",
                        part=relsname,
                    )
                    continue
                candidates = self._target_candidates(source, target)
                if not candidates or not any(
                    c.translate(ASCII_LOWER) in equivalent_names for c in candidates
                ):
                    self._add(
                        "REL002", ERROR,
                        f"{rid} points at a missing part: {target}",
                        part=relsname,
                    )

            if not source or source not in used_by_source:
                continue
            used = used_by_source[source]
            for rid, (_, _, rtype) in rels.items():
                if rid in used:
                    continue
                if any(k in rtype for k in _IMPLICIT_RELS):
                    continue
                self._add(
                    "REL003", INFO,
                    f"{rid} declared but never referenced",
                    part=relsname,
                )

    def check_styles(self) -> None:
        st = self._tree("word/styles.xml")
        doc = self._tree("word/document.xml")
        if doc is None:
            return
        if st is None and "word/styles.xml" in self.parts:
            # Parsing already produced XML001. Unknown definitions must not
            # become a cascade of supposedly undefined references.
            return
        # An absent styles part defines nothing; references still need checking.
        styles = st.findall(_w("style")) if st is not None else []
        defined = {s.get(_w("styleId")) for s in styles}
        for tag in ("pStyle", "rStyle", "tblStyle"):
            for el in doc.iter(_w(tag)):
                v = el.get(_w("val"))
                if v and v not in defined:
                    # Paragraph/table styles can carry numbering and structure;
                    # an undefined character style is a formatting warning.
                    self._add(
                        "STY001", WARN if tag == "rStyle" else ERROR,
                        f'{tag} references undefined style "{v}" - formatting is '
                        "silently lost",
                        self._xpath(el), "word/document.xml",
                    )
        for s in styles:
            for tag in ("basedOn", "next", "link"):
                el = s.find(_w(tag))
                if el is not None and el.get(_w("val")) not in defined:
                    self._add(
                        "STY002", WARN,
                        f'style {s.get(_w("styleId"))}: {tag} -> '
                        f'"{el.get(_w("val"))}" is undefined',
                        part="word/styles.xml",
                    )

    def check_numbering(self) -> None:
        doc = self._tree("word/document.xml")
        if doc is None:
            return
        num = self._tree("word/numbering.xml")
        nums: dict[str, str | None] = {}
        abstracts: dict[str, set] = {}
        overrides: dict[str, set] = {}
        if num is not None:
            for n in num.findall(_w("num")):
                a = n.find(_w("abstractNumId"))
                nums[n.get(_w("numId"))] = a.get(_w("val")) if a is not None else None
                # a w:lvlOverride may carry a complete w:lvl for this instance
                overrides[n.get(_w("numId"))] = {
                    o.get(_w("ilvl")) for o in n.findall(_w("lvlOverride"))
                    if o.find(_w("lvl")) is not None
                }
            for a in num.findall(_w("abstractNum")):
                abstracts[a.get(_w("abstractNumId"))] = {
                    lv.get(_w("ilvl")) for lv in a.findall(_w("lvl"))
                }
            self._inherit_numbering_style_levels(num, nums, abstracts)

        for npr in doc.iter(_w("numPr")):
            nid_el = npr.find(_w("numId"))
            if nid_el is None:
                continue
            nid = nid_el.get(_w("val"))
            if nid == "0":
                # ECMA-376 numId: 0 never points to a numbering instance; it
                # removes numbering inherited from the style hierarchy.
                continue
            where = self._xpath(npr)
            if num is None:
                self._add("NUM001", ERROR,
                          f"paragraph references numId={nid} but numbering.xml is "
                          "missing - the list becomes plain text", where)
                continue
            if nid not in nums:
                self._add("NUM002", ERROR,
                          f"numId={nid} undefined in numbering.xml - numbering "
                          "disappears", where)
                continue
            aid = nums[nid]
            if aid not in abstracts:
                self._add("NUM003", ERROR,
                          f"numId={nid} -> abstractNumId={aid}, which does not exist",
                          where)
                continue
            ilvl_el = npr.find(_w("ilvl"))
            lvl = ilvl_el.get(_w("val")) if ilvl_el is not None else "0"
            if lvl not in abstracts[aid] | overrides.get(nid, set()):
                self._add("NUM004", WARN,
                          f"level ilvl={lvl} undefined in abstractNum {aid}", where)

    def _inherit_numbering_style_levels(self, num, nums: dict, abstracts: dict) -> None:
        """Give an abstractNum with w:numStyleLink the levels of its list style.

        Word stores a list style's levels once, in the abstractNum whose
        w:styleLink names the style; abstractNums that use the style carry only
        w:numStyleLink. Resolve through w:styleLink first, then through the
        numbering style's own numId in styles.xml.
        """
        by_style: dict[str, set] = {}
        for a in num.findall(_w("abstractNum")):
            link = a.find(_w("styleLink"))
            if link is not None and link.get(_w("val")):
                by_style[link.get(_w("val"))] = abstracts.get(
                    a.get(_w("abstractNumId")), set())
        styles = self._tree("word/styles.xml")
        for a in num.findall(_w("abstractNum")):
            link = a.find(_w("numStyleLink"))
            if link is None or not link.get(_w("val")):
                continue
            name = link.get(_w("val"))
            levels = by_style.get(name)
            if levels is None and styles is not None:
                for style in styles.findall(_w("style")):
                    if style.get(_w("styleId")) != name:
                        continue
                    nid = style.find(f'{_w("pPr")}/{_w("numPr")}/{_w("numId")}')
                    target = nums.get(nid.get(_w("val"))) if nid is not None else None
                    if target is not None and target != a.get(_w("abstractNumId")):
                        levels = abstracts.get(target)
                    break
            if levels:
                aid = a.get(_w("abstractNumId"))
                abstracts[aid] = abstracts.get(aid, set()) | levels

    def check_footnotes(self) -> None:
        doc = self._tree("word/document.xml")
        if doc is None:
            return
        fn = self._tree("word/footnotes.xml")
        notes = fn.findall(_w("footnote")) if fn is not None else []
        defined = {f.get(_w("id")) for f in notes}
        # Separator notes are identified by w:type, not by id: Word 2010+
        # writes -1/0, while Word 2007 and LibreOffice write 0/1.
        special = {f.get(_w("id")) for f in notes
                   if f.get(_w("type")) not in (None, "normal")}
        used = set()
        for ref in doc.iter(_w("footnoteReference")):
            i = ref.get(_w("id"))
            used.add(i)
            if i not in defined:
                self._add("FTN001", ERROR,
                          f"footnote reference id={i} has no entry in footnotes.xml",
                          self._xpath(ref))
        for i in sorted(defined - used - special, key=lambda x: (x is None, x)):
            if i not in ("-1", "0"):
                self._add("FTN002", ERROR,
                          f"footnote id={i} is defined but never referenced - "
                          "the footnote no longer appears",
                          part="word/footnotes.xml")

    def check_comments(self) -> None:
        doc = self._tree("word/document.xml")
        if doc is None:
            return
        cm = None
        cm_part = None
        try:
            cm_part = comment_part(self.parts)
            if cm_part is not None:
                cm = comment_tree(self.parts, cm_part)
        except (ValueError, etree.XMLSyntaxError) as e:
            self._add("CMT006", ERROR,
                      f"comments could not be resolved or parsed: {e}",
                      part="word/_rels/document.xml.rels")
        cm_label = ("comments.xml" if cm_part == "word/comments.xml"
                    else cm_part or "the related comments part")
        defined = (
            {c.get(_w("id")) for c in cm.findall(_w("comment"))} if cm is not None
            else set()
        )
        starts = {e.get(_w("id")) for e in doc.iter(_w("commentRangeStart"))}
        ends = {e.get(_w("id")) for e in doc.iter(_w("commentRangeEnd"))}
        refs = {e.get(_w("id")) for e in doc.iter(_w("commentReference"))}

        srt = lambda s: sorted(s, key=lambda x: (x is None, x))
        for i in srt(starts - ends):
            self._add("CMT001", ERROR,
                      f"commentRangeStart id={i} with no commentRangeEnd - "
                      "malformed range", part="word/document.xml")
        for i in srt(ends - starts):
            self._add("CMT002", ERROR,
                      f"commentRangeEnd id={i} with no commentRangeStart",
                      part="word/document.xml")
        for i in srt(starts - refs):
            self._add("CMT003", ERROR,
                      f"comment range id={i} has no commentReference - the comment "
                      "will not render", part="word/document.xml")
        for i in srt(refs - defined):
            self._add("CMT004", ERROR,
                      f"commentReference id={i} not found in {cm_label}",
                      part="word/document.xml")
        for i in srt(defined - refs):
            self._add("CMT005", ERROR,
                      f"comment id={i} is orphaned - present in {cm_label} but "
                      "anchored to nothing - the reviewer's note is invisible in Word",
                      part=cm_part or "")

    def check_revisions(self) -> None:
        doc = self._tree("word/document.xml")
        if doc is None:
            return

        by_id: dict[str, list[etree._Element]] = {}
        for tag in ("ins", "del", "moveFrom", "moveTo"):
            for el in doc.iter(_w(tag)):
                revision_id = el.get(_w("id"))
                if revision_id is not None:
                    by_id.setdefault(revision_id, []).append(el)
        for i, elements in by_id.items():
            n = len(elements)
            if n > 1 and not _paragraph_revision_pair(elements):
                self._add("REV001", ERROR,
                          f"revision id {i} used {n} times - outside the verified "
                          "paragraph-mark/content pair; review for an ID collision",
                          part="word/document.xml")

        # w:del must carry w:delText, not w:t.
        # w:ins > w:del nesting (and the reverse) is legal and means "inserted by
        # one author, deleted by another before acceptance", so test the NEAREST
        # revision ancestor rather than any ancestor.
        def nearest_rev(el):
            p = el.getparent()
            while p is not None:
                if p.tag in (_w("ins"), _w("del")):
                    return p.tag
                p = p.getparent()
            return None

        for t in doc.iter(_w("t")):
            if nearest_rev(t) == _w("del"):
                self._add("REV002", ERROR,
                          "w:t inside w:del instead of w:delText - deleted text "
                          "reappears when changes are accepted", self._xpath(t))
        for t in doc.iter(_w("delText")):
            if nearest_rev(t) == _w("ins"):
                self._add("REV003", ERROR,
                          "w:delText inside w:ins with no nested w:del",
                          self._xpath(t))

    def check_tables(self) -> None:
        doc = self._tree("word/document.xml")
        if doc is None:
            return
        for ti, tbl in enumerate(doc.iter(_w("tbl")), 1):
            grid = tbl.find(_w("tblGrid"))
            if grid is None:
                self._add("TBL001", ERROR, f"table {ti}: missing w:tblGrid",
                          f"tbl[{ti}]")
                continue
            ncols = len(grid.findall(_w("gridCol")))
            for ri, tr in enumerate(tbl.findall(_w("tr")), 1):
                span = 0
                for tc in self._row_cells(tr):
                    gs = tc.find(f'{_w("tcPr")}/{_w("gridSpan")}')
                    try:
                        span += int(gs.get(_w("val"))) if gs is not None else 1
                    except (TypeError, ValueError):
                        span += 1
                # Grid columns skipped before the first or after the last cell
                # (ragged rows) are part of the row's width, not missing cells.
                trpr = tr.find(_w("trPr"))
                for tag in ("gridBefore", "gridAfter"):
                    skipped = trpr.find(_w(tag)) if trpr is not None else None
                    if skipped is not None:
                        try:
                            span += int(skipped.get(_w("val")))
                        except (TypeError, ValueError):
                            pass
                if span != ncols:
                    self._add("TBL002", WARN,
                              f"table {ti}, row {ri}: {span} cells vs {ncols} "
                              "tblGrid columns - Word will re-lay out the table",
                              f"tbl[{ti}]/tr[{ri}]")

    @staticmethod
    def _row_cells(container) -> list:
        """A row's cells, including cells wrapped in content controls or custom XML."""
        cells = []
        for child in container:
            if child.tag == _w("tc"):
                cells.append(child)
            elif child.tag == _w("sdt"):
                content = child.find(_w("sdtContent"))
                if content is not None:
                    cells.extend(Inspector._row_cells(content))
            elif child.tag == _w("customXml"):
                cells.extend(Inspector._row_cells(child))
        return cells

    def check_sdt(self) -> None:
        doc = self._tree("word/document.xml")
        if doc is None:
            return
        for i, sdt in enumerate(doc.iter(_w("sdt")), 1):
            if sdt.find(_w("sdtPr")) is None:
                self._add("SDT001", ERROR, f"content control {i}: no sdtPr",
                          f"sdt[{i}]")
            if sdt.find(_w("sdtContent")) is None:
                self._add("SDT002", ERROR,
                          f"content control {i}: no sdtContent - the field "
                          "disappears", f"sdt[{i}]")

    def check_whitespace(self) -> None:
        """XML edge whitespace without effective preservation risks being lost."""
        doc = self._tree("word/document.xml")
        if doc is None:
            return
        # Ordinary clean documents need no paths at all. Avoid a full path
        # traversal when every edge-space node already declares preservation.
        xml_space = "{http://www.w3.org/XML/1998/namespace}space"
        if not any(
            (t.text or "") != (t.text or "").strip(" \t\r\n")
            and t.get(xml_space) != "preserve"
            for t in doc.iter(_w("t"))
        ):
            return
        for t, where, space in text_contexts(doc, _w("t")):
            txt = t.text or ""
            if txt != txt.strip(" \t\r\n") and space != "preserve":
                self._add("TXT001", WARN,
                          'run has edge whitespace without xml:space="preserve" - '
                          f"it will vanish: {txt[:40]!r}", where)

    CHECKS = (
        check_content_types, check_relationships, check_styles, check_numbering,
        check_footnotes, check_comments, check_revisions, check_tables,
        check_sdt, check_whitespace,
    )

    # ------------------------------------------------------------------- run
    def run(self) -> list[Finding]:
        if not self.load():
            return self.findings
        for c in self.CHECKS:
            try:
                c(self)
            except Exception as e:  # a broken check must not hide the others
                self._add("INT001", WARN, f"check {c.__name__} raised: {e}")
        return self.findings


def check(path: str | Path, *,
          limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> list[Finding]:
    """Inspect one .docx for internal consistency. Returns every finding."""
    return Inspector(path, limits).run()


def check_many(paths: Iterable[str | Path], *,
               limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS
               ) -> dict[str, list[Finding]]:
    """Inspect several files. Keys are the paths as given."""
    return {str(p): check(p, limits=limits) for p in paths}
