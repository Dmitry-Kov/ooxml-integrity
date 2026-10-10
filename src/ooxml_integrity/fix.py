"""Repair what is uniquely repairable in a .docx, and prove it.

`fix(IN, OUT)` writes a repaired copy. It has exactly two repairs:

    anchor-replies      CMT005 on a reply whose parent comment is anchored:
                        write the reply's range markers at the parent's range,
                        in the order Word writes a thread.
    renumber-revisions  REV001: keep the first element of a repeated revision
                        id and give every later one a fresh id above every
                        w:id in the package.

Neither restores or invents content: a top-level comment whose anchor is gone,
a lost style or a lost revision has no unique repair, and the agreed position
is that fix does not guess. Each repair runs only when its precondition holds
and otherwise refuses with the reason. Every finding not repaired is listed
with why.

A changed part is edited in place: only the bytes of the repair change, so
the XML declaration, attribute order, entity spellings and whitespace stay as
they were. The edited part is parsed again and must equal the intended tree.
Every other ZIP member is copied as stored (`repack`). The copy is written to
a temporary file, checked again (`check`, `compare` with the input and, when
given, with the source), and only then renamed to OUT.

See docs/fix.md.
"""
from __future__ import annotations

import collections
import copy
import hashlib
import os
import posixpath
import re
import tempfile
import xml.parsers.expat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from lxml import etree

from . import __version__
from .archive import DEFAULT_ARCHIVE_LIMITS, ArchiveLimits, PackageIssue, read_package
from .comments import (
    _existing, _relationships, _resolve, comment_part, comment_tree,
    office_documents, relationships_part, story_parts,
)
from .fidelity import TRACKED, compare
from .finding import INFO, Finding
from .inspector import _paragraph_revision_pair, check
from .repack import RepackError, differences, read_entries, repack
from .xmlutil import fromstring as parse_xml

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"
W15 = "{%s}" % W15_NS
COMMENTS_EXTENDED = "http://schemas.microsoft.com/office/2011/relationships/commentsExtended"

ANCHOR_REPLIES = "anchor-replies"
RENUMBER_REVISIONS = "renumber-revisions"
#: The finding each repair answers.
REPAIRS = {ANCHOR_REPLIES: "CMT005", RENUMBER_REVISIONS: "REV001"}

EXIT_REPAIRED, EXIT_NOTHING, EXIT_REFUSED, EXIT_UNVERIFIED = 0, 1, 2, 3

#: Findings that mean the package cannot be rewritten safely: it is missing,
#: unreadable, over a budget, Strict, malformed, or a check did not complete.
_BLOCKING = {
    "PKG000": "the file was not found",
    "PKG001": "the ZIP archive is corrupt",
    "PKG002": "the file is not a readable ZIP package",
    "PKG003": "[Content_Types].xml is missing",
    "PKG006": "the main document part is missing or is not WordprocessingML",
    "PKG007": "the package exceeds an archive budget",
    "PKG008": "the package has an unsafe or duplicate part name",
    "PKG009": "the package is Strict Open XML, which the repairs do not model",
    "XML001": "a part is not well-formed XML",
    "INT001": "a check did not complete, so the re-check could not prove the copy",
}

_REVISIONS = tuple(W + t for t in ("ins", "del", "moveFrom", "moveTo"))
_MARKERS = ("commentRangeStart", "commentRangeEnd", "commentReference")


class FixUsageError(ValueError):
    """The arguments cannot be acted on; nothing was read or written."""


class _Refused(Exception):
    """A precondition does not hold; the reason is reported, nothing changes."""


class _Unproved(Exception):
    """An edit did not produce the intended part; nothing is written."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _key(f: Finding) -> tuple:
    """A finding's identity for before/after: XPaths move when markers are added."""
    return (f.code, f.severity.value, f.message, f.part)


def _quote(value: str) -> str:
    return '"' + (value.replace("&", "&amp;").replace("<", "&lt;")
                  .replace('"', "&quot;")) + '"'


def _tag_end(data: bytes, start: int) -> int:
    """Index just past the '>' of the tag that starts at `start`."""
    quote = 0
    for i in range(start + 1, len(data)):
        c = data[i]
        if quote:
            if c == quote:
                quote = 0
        elif c in (0x22, 0x27):
            quote = c
        elif c == 0x3E:
            return i + 1
    raise _Unproved("a tag is not closed")


_ATTRIBUTE = re.compile(rb"""\s([^\s=/>]+)\s*=\s*("[^"]*"|'[^']*')""")


def _same(a, b) -> bool:
    """Same element tree: names, attributes, text and tails, in order.

    Namespace declarations and prefixes are spelling, not content.
    """
    if (a.tag != b.tag or (a.text or "") != (b.text or "")
            or (a.tail or "") != (b.tail or "") or dict(a.attrib) != dict(b.attrib)
            or len(a) != len(b)):
        return False
    return all(_same(x, y) for x, y in zip(a, b))


class _Part:
    """One XML part: its bytes, a tree edited as the model, and byte edits.

    Every edit is applied twice: to the tree, which states what the repair
    means, and to the bytes, at the offsets the element has in the input.
    `result()` parses the edited bytes and returns them only if they equal the
    tree.
    """

    def __init__(self, name: str, data: bytes):
        self.name, self.data = name, data
        self.tree = parse_xml(data)
        self._spans: Optional[dict] = None
        self._after: dict = {}
        self._elements: list = []
        self._at: dict = {}       # inserted element -> offset it was inserted at
        self._line: dict = {}     # inserted element -> input line it follows
        self._edits: list[tuple[int, int, int, bytes]] = []

    @property
    def changed(self) -> bool:
        return bool(self._edits)

    def locate(self) -> None:
        """Byte spans of every element, before the tree is first changed."""
        if self._spans is not None:
            return
        info = self.tree.getroottree().docinfo
        encoding = (info.encoding or "UTF-8").upper()
        if encoding not in ("UTF-8", "UTF8") or self.data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            raise _Refused(f"{self.name} is encoded as {encoding}; fix edits only "
                           "UTF-8 parts")
        self._elements = list(self.tree.iter(etree.Element))
        parser = xml.parsers.expat.ParserCreate()
        parser.SetParamEntityParsing(xml.parsers.expat.XML_PARAM_ENTITY_PARSING_NEVER)
        starts: list[int] = []
        names: list[str] = []
        ends: list[int] = []
        stack: list[int] = []

        def start(name, _attrs):
            stack.append(len(starts))
            starts.append(parser.CurrentByteIndex)
            names.append(name)
            ends.append(-1)

        def end(_name):
            ends[stack.pop()] = parser.CurrentByteIndex

        parser.StartElementHandler = start
        parser.EndElementHandler = end
        try:
            parser.Parse(self.data, True)
        except xml.parsers.expat.ExpatError as e:
            raise _Refused(f"{self.name} could not be located byte for byte: {e}") from e
        if len(starts) != len(self._elements):
            raise _Refused(f"{self.name}: the two parsers disagree on its elements")
        spans, closing = {}, {}
        for el, s, name, e in zip(self._elements, starts, names, ends):
            qname = (f"{el.prefix}:" if el.prefix else "") + etree.QName(el).localname
            if name != qname:
                raise _Refused(f"{self.name}: the two parsers disagree on its elements")
            head = _tag_end(self.data, s)
            empty = self.data[head - 2] == 0x2F
            spans[el] = (s, head, head if empty else _tag_end(self.data, e))
            if not empty:
                closing[el] = e
        # Where an element's tail text ends: lxml's addnext() puts a new
        # sibling there, so the bytes must too.
        after = {}
        for el in self._elements:
            nxt, parent = el.getnext(), el.getparent()
            if nxt is not None and isinstance(nxt.tag, str):
                after[el] = spans[nxt][0]
            elif nxt is None and parent is not None:
                after[el] = closing[parent]
        self._spans, self._after = spans, after

    def span(self, el) -> tuple[int, int, int]:
        """(start, end of start tag, end) of an element of the input."""
        self.locate()
        return self._spans[el]

    def raw(self, el) -> bytes:
        s, _, e = self.span(el)
        return self.data[s:e]

    def line(self, el) -> Optional[int]:
        return self._line.get(el, el.sourceline)

    def insert_after(self, anchor, elements: list, data: bytes) -> None:
        """Put `elements` after `anchor` and its tail text, as addnext() does."""
        self.locate()
        offset = self._at.get(anchor)
        if offset is None:
            offset = self._after.get(anchor)
            if offset is None:
                raise _Refused(f"{self.name}: a comment or processing instruction "
                               "follows the element the markers would follow")
        previous = anchor
        for el in elements:
            previous.addnext(el)
            self._at[el] = offset
            self._line[el] = self.line(anchor)
            previous = el
        self._edits.append((offset, offset, len(self._edits), data))

    def set_attribute(self, el, local: str, value: str) -> tuple[str, str]:
        """Change the w:`local` attribute of an input element; returns old and new text."""
        s, head, _ = self.span(el)
        hits = []
        for m in _ATTRIBUTE.finditer(self.data, s, head):
            prefix, _, name = m.group(1).decode("utf-8").rpartition(":")
            if name == local and prefix and el.nsmap.get(prefix) == W_NS:
                hits.append(m)
        if len(hits) != 1:
            raise _Refused(f"{self.name}: the w:{local} attribute could not be located")
        m = hits[0]
        quote = m.group(2)[:1]
        old = m.group(0).strip().decode("utf-8")
        new_bytes = m.group(1) + b"=" + quote + _quote(value)[1:-1].encode("utf-8") + quote
        el.set(W + local, value)
        self._edits.append((m.start(1), m.end(2), len(self._edits), new_bytes))
        return old, new_bytes.decode("utf-8")

    def result(self) -> bytes:
        out, position = [], 0
        for start, end, _, data in sorted(self._edits):
            if start < position:
                raise _Unproved(f"{self.name}: two edits overlap")
            out += [self.data[position:start], data]
            position = end
        out.append(self.data[position:])
        edited = b"".join(out)
        try:
            again = parse_xml(edited)
        except (ValueError, etree.XMLSyntaxError) as e:
            raise _Unproved(f"{self.name}: the edited part does not parse: {e}") from e
        if not _same(again, self.tree):
            raise _Unproved(f"{self.name}: the edited part does not parse to the "
                            "intended tree")
        return edited


@dataclass
class Change:
    """One element a repair added or changed in one part."""

    part: str
    element: str
    where: str
    line: Optional[int]
    old: Optional[str]
    new: str
    #: the element in the edited tree, until its XPath is known
    node: Any = field(default=None, repr=False, compare=False)

    def as_dict(self) -> dict[str, Any]:
        return {"part": self.part, "element": self.element, "where": self.where,
                "line": self.line, "old": self.old, "new": self.new}


@dataclass
class Repaired:
    repair: str
    finding: Finding
    detail: str
    changes: list[Change] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"repair": self.repair, "finding": self.finding.as_dict(),
                "detail": self.detail,
                "changes": [c.as_dict() for c in self.changes]}


@dataclass
class NotRepaired:
    finding: Finding
    reason: str
    repair: Optional[str] = None
    #: "check" for check(IN), "against" for compare(SOURCE, IN)
    origin: str = "check"

    def as_dict(self) -> dict[str, Any]:
        d = {**self.finding.as_dict(), "origin": self.origin, "reason": self.reason}
        if self.repair:
            d["repair"] = self.repair
        return d


@dataclass
class Verification:
    passed: bool
    failures: list[str]
    check_removed: list[Finding]
    check_added: list[Finding]
    compare: list[Finding]
    against_added: Optional[list[Finding]]
    changed_parts: list[str]
    copied_parts: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failures": self.failures,
            "check": {"removed": [f.as_dict() for f in self.check_removed],
                      "added": [f.as_dict() for f in self.check_added]},
            "compare_input_output": [f.as_dict() for f in self.compare],
            "against_added": (None if self.against_added is None
                              else [f.as_dict() for f in self.against_added]),
            "zip": {"changed": self.changed_parts, "copied": self.copied_parts},
        }


@dataclass
class FixReport:
    """What fix did to one file, and why. `status` decides the exit code:

    repaired             OUT written; every repair re-checked          0
    nothing-to-repair    no CMT005/REV001, or every one refused        1
    input-refused        a package fix does not rewrite                2
    verification-failed  a repair could not be proved; nothing written 3
    """

    status: str
    reason: str
    input: Path
    input_sha256: Optional[str]
    output: Path
    output_sha256: Optional[str] = None
    against: Optional[Path] = None
    against_sha256: Optional[str] = None
    repaired: list[Repaired] = field(default_factory=list)
    not_repaired: list[NotRepaired] = field(default_factory=list)
    verification: Optional[Verification] = None

    @property
    def exit_code(self) -> int:
        return {"repaired": EXIT_REPAIRED, "nothing-to-repair": EXIT_NOTHING,
                "input-refused": EXIT_REFUSED,
                "verification-failed": EXIT_UNVERIFIED}[self.status]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "status": self.status,
            "reason": self.reason,
            "input": {"path": str(self.input), "sha256": self.input_sha256},
            "output": ({"path": str(self.output), "sha256": self.output_sha256}
                       if self.output_sha256 else None),
            "against": ({"path": str(self.against), "sha256": self.against_sha256}
                        if self.against is not None else None),
            "repaired": [r.as_dict() for r in self.repaired],
            "not_repaired": [n.as_dict() for n in self.not_repaired],
            "verification": self.verification.as_dict() if self.verification else None,
        }

    def render(self) -> str:
        lines = []
        if self.status == "repaired":
            lines.append(f"{self.input} -> {self.output}: {len(self.repaired)} "
                         f"finding(s) repaired, re-checked")
        else:
            lines.append(f"{self.input}: {self.status}, nothing written - {self.reason}")
        for r in self.repaired:
            lines.append(f"  {r.repair}  {r.finding.code}  {r.finding.message}")
            lines.append(f"    {r.detail}")
            for c in r.changes:
                lines.append(f"    {c.part}  {c.where}")
                lines.append(f"      {c.old or '(absent)'} -> {c.new}")
        if self.not_repaired:
            lines.append("not repaired:")
            for n in self.not_repaired:
                origin = "" if n.origin == "check" else " (against the source)"
                lines.append(f"  [{n.finding.severity.value.upper():5}] "
                             f"{n.finding.code}  {n.finding.message}{origin}")
                lines.append(f"          why: {n.reason}")
        v = self.verification
        if v is not None:
            if v.passed:
                gone = ", ".join(sorted({f.code for f in v.check_removed}))
                extra = "; ".join(f"{f.code} {f.severity.value.upper()} {f.message}"
                                  for f in v.compare) or "nothing"
                lines.append(f"verified: {len(v.check_removed)} finding(s) gone ({gone}), "
                             f"none added; compare(input, output): {extra}; "
                             f"{', '.join(v.changed_parts)} edited, "
                             f"{v.copied_parts} other ZIP member(s) copied as stored")
                if v.against_added is not None:
                    lines.append("verified against the source: nothing new beyond "
                                 "the declared count increases")
            else:
                lines.append("verification FAILED:")
                lines += [f"  {x}" for x in v.failures]
        lines.append(f"input  sha256 {self.input_sha256}")
        if self.output_sha256:
            lines.append(f"output sha256 {self.output_sha256}")
        return "\n".join(lines)


def _reason(f: Finding) -> str:
    if f.code.startswith("FID"):
        return ("a difference from the source; fix never restores lost content "
                "or changes what an edit did")
    if f.severity == INFO:
        return "reported for information, not a defect"
    return {
        "STY001": ("no unique repair: removing the style reference and defining "
                   "the style are both choices"),
        "TXT001": ('no unique repair: adding xml:space="preserve" changes the '
                   "text LibreOffice displays"),
        "CMT001": "no unique repair: where the range ended is not in the file",
        "CMT002": "no unique repair: where the range started is not in the file",
    }.get(f.code, f"fix has no repair for {f.code}; it repairs only CMT005 on "
                  "replies (anchor-replies) and REV001 (renumber-revisions)")


class _Package:
    """The input's parts, and the XML parts a repair edits."""

    def __init__(self, parts: dict[str, bytes]):
        self.parts = parts
        found = office_documents(parts)
        self.main = found[0]
        self.stories = story_parts(parts, self.main)
        self._edited: dict[str, _Part] = {}

    def part(self, name: str) -> _Part:
        if name not in self._edited:
            self._edited[name] = _Part(name, self.parts[name])
        return self._edited[name]

    def related(self, rel_type: str) -> list[str]:
        """Existing internal targets of the main part's relationships of a type."""
        out = []
        for rel in _relationships(self.parts, relationships_part(self.main)):
            if rel.get("Type") != rel_type or rel.get("TargetMode", "Internal") != "Internal":
                continue
            resolved = _resolve(rel.get("Target") or "", posixpath.dirname(self.main))
            out.append(_existing((resolved,), set(self.parts)) if resolved else None)
        return out

    def edited(self) -> dict[str, bytes]:
        return {n: p.result() for n, p in self._edited.items() if p.changed}


def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(W + "t"))


def _snippet(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[:n - 3] + "..."


def _qname(el) -> str:
    return (f"{el.prefix}:" if el.prefix else "") + etree.QName(el).localname


def _path(el) -> str:
    return el.getroottree().getpath(el)


# ----------------------------------------------------------------- anchor-replies
def _w_prefix(el) -> str:
    if el.prefix and el.nsmap.get(el.prefix) == W_NS:
        return el.prefix
    for prefix, uri in sorted(el.nsmap.items(), key=lambda x: x[0] or ""):
        if prefix and uri == W_NS:
            return prefix
    raise _Refused("no namespace prefix is bound to WordprocessingML where the "
                   "markers would go")


def _anchor_replies(pkg: _Package, targets: list[tuple[str, Finding]]
                    ) -> tuple[list[Repaired], dict[int, str], collections.Counter]:
    """Returns the repairs, the refusals by target index, and how many of each
    construct compare() counts were added to the main part."""
    refused: dict[int, str] = {}
    added: collections.Counter = collections.Counter()
    try:
        cpart = comment_part(pkg.parts, main=pkg.main)
        ctree = comment_tree(pkg.parts, cpart) if cpart else None
    except (ValueError, etree.XMLSyntaxError) as e:
        return [], {i: f"the comments part could not be resolved: {e}"
                    for i in range(len(targets))}, added
    if ctree is None:
        return [], {i: "the main document relates no comments part"
                    for i in range(len(targets))}, added
    styles = pkg.parts.get("word/styles.xml")
    defined = ({s.get(W + "styleId") for s in parse_xml(styles).iter(W + "style")}
               if styles is not None else set())

    comments: dict[str, Any] = {}
    defined_twice: set[str] = set()
    by_para: dict[str, list[str]] = collections.defaultdict(list)
    for c in ctree.iter(W + "comment"):
        cid = c.get(W + "id")
        paras = list(c.iter(W + "p"))
        para = (paras[-1].get(W14 + "paraId") or "").upper() if paras else ""
        if cid in comments:
            defined_twice.add(cid)
        comments.setdefault(cid, (c, para))
        if para:
            by_para[para].append(cid)

    xparts = pkg.related(COMMENTS_EXTENDED)
    links: dict[str, list[str]] = collections.defaultdict(list)
    xroot = None
    xname = None
    if len(xparts) == 1 and xparts[0] is not None:
        xname = xparts[0]
        xroot = parse_xml(pkg.parts[xname])
        for ex in xroot.iter(W15 + "commentEx"):
            para = (ex.get(W15 + "paraId") or "").upper()
            links[para].append((ex.get(W15 + "paraIdParent") or "").upper())

    # Markers per comment id across stories, from the trees the repair edits.
    markers: dict[str, list[tuple[str, str, Any]]] = collections.defaultdict(list)
    for story in pkg.stories:
        tree = pkg.part(story).tree
        for kind in _MARKERS:
            for el in tree.iter(W + kind):
                markers[el.get(W + "id")].append((story, kind, el))

    def parent_of(cid: str) -> Optional[str]:
        """The parent comment's id, or None for a top-level comment."""
        para = comments[cid][1]
        if not para:
            raise _Refused(f"comment {cid} is not a reply: its last paragraph has "
                           "no w14:paraId, so nothing links it to a parent; a "
                           "top-level comment's anchor position is lost and fix "
                           "does not guess it")
        if len(by_para[para]) > 1:
            raise _Refused(f"comment {cid}: paraId {para} is used by several comments")
        if xroot is None:
            reason = ("the package has no commentsExtended part" if not xparts else
                      "the commentsExtended relationship is missing its part or "
                      "is not unique")
            raise _Refused(f"comment {cid} is not a reply: {reason}, so nothing "
                           "links it to a parent; a top-level comment's anchor "
                           "position is lost and fix does not guess it")
        found = links.get(para, [])
        if len(found) > 1:
            raise _Refused(f"comment {cid}: commentsExtended describes paraId "
                           f"{para} more than once")
        if not found or not found[0]:
            return None
        parents = by_para.get(found[0], [])
        if len(parents) != 1:
            raise _Refused(f"comment {cid}: its parent paraId {found[0]} names "
                           f"{len(parents)} comments, not one")
        return parents[0]

    def anchored(cid: str) -> Optional[tuple[str, dict]]:
        """(story, {kind: element}) when anchored once in one story."""
        found = markers.get(cid, [])
        kinds = collections.Counter(kind for _, kind, _ in found)
        stories = {story for story, _, _ in found}
        if len(stories) != 1 or any(kinds[k] != 1 for k in _MARKERS) or len(found) != 3:
            return None
        return stories.pop(), {kind: el for _, kind, el in found}

    nonstandard = (xroot is not None and xroot.tag != W15 + "commentsEx")
    order = list(comments)
    repaired: list[Repaired] = []
    for index, (cid, finding) in sorted(
            enumerate(targets), key=lambda x: order.index(x[1][0])
            if x[1][0] in comments else len(order)):
        try:
            if cid not in comments:
                raise _Refused(f"comment {cid} is not in the comments part")
            if cid in defined_twice:
                raise _Refused(f"comment id {cid} is defined more than once")
            if markers.get(cid):
                raise _Refused(f"comment {cid} has range markers but no reference; "
                               "where its reference belongs is not in the file")
            parent = parent_of(cid)
            if parent is None:
                raise _Refused(f"comment {cid} is not a reply: commentsExtended gives "
                               "it no parent; a top-level comment's anchor position "
                               "is lost and fix does not guess it")
            try:
                grandparent = parent_of(parent)
            except _Refused as e:
                raise _Refused(f"comment {cid} replies to comment {parent}, whose own "
                               f"thread link is unclear: {e}") from e
            if grandparent is not None:
                raise _Refused(f"comment {cid} replies to comment {parent}, which is "
                               "itself a reply; its range is not unique")
            home = anchored(parent)
            if home is None:
                raise _Refused(f"comment {cid} replies to comment {parent}, which is "
                               "not anchored once with a start, an end and a "
                               "reference in one story; the thread's range is lost")
            story, own = home
            thread = [parent] + [
                other for other in order
                if other not in (parent, cid) and markers.get(other)
                and _safe_parent(parent_of, other) == parent]
            members = []
            for member in thread:
                where = anchored(member)
                if where is None or where[0] != story:
                    raise _Refused(f"comment {cid}: reply {member} in the same thread "
                                   "is not anchored like its parent")
                members.append(where[1])
            part = pkg.part(story)
            tree = part.tree
            position = {el: n for n, el in enumerate(tree.iter())}
            starts = [m["commentRangeStart"] for m in members]
            first = min(starts, key=position.get)
            block, nxt = [first], first.getnext()
            while nxt is not None and nxt.tag == W + "commentRangeStart":
                block.append(nxt)
                nxt = nxt.getnext()
            if not set(starts) <= set(block):
                raise _Refused(f"comment {cid}: the thread of comment {parent} does "
                               "not share one range start")
            last_start = max(starts, key=position.get)
            last_ref = max((m["commentReference"] for m in members), key=position.get)
            ref_run = last_ref.getparent()
            if (ref_run is None or ref_run.tag != W + "r" or ref_run.getparent() is None
                    or ref_run.getparent().tag != W + "p"):
                raise _Refused(f"comment {cid}: the thread's last reference is not in "
                               "a run directly inside a paragraph; where Word puts "
                               "a reply there is not established")
            if position[last_ref] < position[own["commentRangeEnd"]]:
                raise _Refused(f"comment {cid}: the thread's reference precedes "
                               f"the end of comment {parent}'s range")
            parent_run = own["commentReference"].getparent()
            rpr = parent_run.find(W + "rPr") if parent_run.tag == W + "r" else None
            if rpr is not None and any(
                    isinstance(e.tag, str) and (e.tag in _REVISIONS
                                                or e.tag.endswith("Change"))
                    for e in rpr.iter()):
                raise _Refused(f"comment {cid}: the parent's reference run has "
                               "tracked formatting; copying it would add a revision")
            undefined = sorted({e.get(W + "val") for e in (rpr.iter(W + "rStyle")
                                if rpr is not None else ())} - defined)
            if undefined:
                raise _Refused(f"comment {cid}: the parent's reference run uses the "
                               f"undefined style {undefined[0]}; copying it would add "
                               "an STY001 finding")

            prefix = _w_prefix(last_start)
            q = _quote(cid)
            new_start = etree.Element(W + "commentRangeStart", nsmap={prefix: W_NS})
            new_start.set(W + "id", cid)
            start_xml = f"<{prefix}:commentRangeStart {prefix}:id={q}/>"
            run_prefix = _w_prefix(ref_run)
            new_end = etree.Element(W + "commentRangeEnd", nsmap={run_prefix: W_NS})
            new_end.set(W + "id", cid)
            new_run = etree.Element(W + "r", nsmap={run_prefix: W_NS})
            rpr_xml = b""
            if rpr is not None:
                copied = copy.deepcopy(rpr)
                copied.tail = None
                new_run.append(copied)
                rpr_xml = part.raw(rpr)
            ref = etree.SubElement(new_run, W + "commentReference")
            ref.set(W + "id", cid)
            p = run_prefix
            end_xml = (f"<{p}:commentRangeEnd {p}:id={q}/><{p}:r>".encode("utf-8")
                       + rpr_xml
                       + f"<{p}:commentReference {p}:id={q}/></{p}:r>".encode("utf-8"))
            part.insert_after(last_start, [new_start], start_xml.encode("utf-8"))
            part.insert_after(ref_run, [new_end, new_run], end_xml)
        except _Refused as e:
            refused[index] = str(e)
            continue
        markers[cid] = [(story, "commentRangeStart", new_start),
                        (story, "commentRangeEnd", new_end),
                        (story, "commentReference", ref)]
        if story == pkg.main:
            for tag, _, _ in TRACKED:
                added[tag] += sum(1 for el in (new_start, new_end, new_run)
                                  for _ in el.iter(W + tag))
        reply, pc = comments[cid][0], comments[parent][0]
        others = [m for m in thread if m != parent]
        detail = (f"reply {cid} by {reply.get(W + 'author') or 'no author'} "
                  f'("{_snippet(_text(reply))}") anchored at the range of comment '
                  f"{parent} by {pc.get(W + 'author') or 'no author'}"
                  + (f", after reply {', '.join(others)}" if others else "")
                  + f", in {story}, in the order Word writes a thread; Word does "
                  "not show a reply without an anchor, so the reply becomes visible")
        if nonstandard:
            detail += (f". The thread link comes from {xname}, whose root is "
                       f"{etree.QName(xroot).localname}, not w15:commentsEx: Word "
                       "16.113.4 threads the reply, LibreOffice shows it as a "
                       "separate comment on the same range")
        changes = [
            Change(story, _qname(el), "", part.line(el), None, xml_text, el)
            for el, xml_text in (
                (new_start, start_xml),
                (new_end, f"<{p}:commentRangeEnd {p}:id={q}/>"),
                (new_run, (f"<{p}:r>".encode("utf-8") + rpr_xml
                           + f"<{p}:commentReference {p}:id={q}/></{p}:r>"
                           .encode("utf-8")).decode("utf-8")),
            )]
        repaired.append(Repaired(ANCHOR_REPLIES, finding, detail, changes))
    return repaired, refused, +added


def _safe_parent(parent_of, cid: str) -> Optional[str]:
    try:
        return parent_of(cid)
    except _Refused:
        return None


# ------------------------------------------------------------- renumber-revisions
def _renumber_revisions(pkg: _Package, targets: list[tuple[str, Finding]]
                        ) -> tuple[list[Repaired], dict[int, str]]:
    part = pkg.part(pkg.main)
    tree = part.tree
    used = []
    for name, data in pkg.parts.items():
        if not name.endswith(".xml") and name not in pkg.stories:
            continue
        root = tree if name == pkg.main else parse_xml(data)
        for el in root.iter(etree.Element):
            value = el.get(W + "id")
            if value is not None and re.fullmatch(r"-?\d+", value.strip()):
                used.append(int(value))
    fresh = max(used, default=0) + 1
    groups: dict[str, list] = {}
    for el in tree.iter(*_REVISIONS):
        if el.get(W + "id") is not None:
            groups.setdefault(el.get(W + "id"), []).append(el)

    repaired: list[Repaired] = []
    refused: dict[int, str] = {}
    for index, (rid, finding) in enumerate(targets):
        elements = groups.get(rid, [])
        if len(elements) < 2 or _paragraph_revision_pair(elements):
            refused[index] = f"revision id {rid}: no repeated use found to renumber"
            continue
        if len(elements) > 2 and any(
                _paragraph_revision_pair([a, b])
                for n, a in enumerate(elements) for b in elements[n + 1:]):
            refused[index] = (f"revision id {rid}: two of its {len(elements)} uses "
                              "are a paragraph-mark/content pair that Word writes "
                              "with one id, so which use collides is not unique")
            continue
        changes = []
        try:
            for el in elements[1:]:
                old, new = part.set_attribute(el, "id", str(fresh))
                changes.append(Change(pkg.main, _qname(el), "", el.sourceline, old, new, el))
                fresh += 1
        except _Refused as e:
            refused[index] = str(e)
            continue
        first = elements[0]
        detail = (f"revision id {rid} was used by {len(elements)} elements; the "
                  f"first, {_qname(first)} by {first.get(W + 'author') or 'no author'} "
                  f"at line {first.sourceline}, keeps it and "
                  + ", ".join(f"{_qname(e)} by {e.get(W + 'author') or 'no author'} "
                              f"at line {e.sourceline} gets {e.get(W + 'id')}"
                              for e in elements[1:])
                  + "; nothing in the package refers to a revision by its id")
        repaired.append(Repaired(RENUMBER_REVISIONS, finding, detail, changes))
    return repaired, refused


# -------------------------------------------------------------------- the command
_CMT005 = re.compile(r"comment id=(.*?) is orphaned")
_REV001 = re.compile(r"revision id (.*) used \d+ times")


_LABELS = {tag: label for tag, label, _ in TRACKED}


def _counts(findings: list[Finding], added: collections.Counter) -> list[Finding]:
    """The count findings of compare() for constructs a repair added."""
    return [f for f in findings if f.code in ("FID001", "FID002")
            and f.extra.get("tag") in added]


def _verify(source: Path, output: Path, *, repaired: list[Repaired],
            before: list[Finding], against: Optional[Path],
            before_against: Optional[list[Finding]], added: collections.Counter,
            changed: list[str], limits: ArchiveLimits) -> Verification:
    """Prove the copy: the targets are gone, nothing is new, and compare()
    reports only what the repairs declared they add.

    `added` counts the constructs compare() tracks that the repairs inserted
    in the main part: a comment reference per anchored reply, and the
    character style its copied run properties name, if any.
    """
    failures: list[str] = []
    after = check(output, limits=limits)
    b = collections.Counter(map(_key, before))
    a = collections.Counter(map(_key, after))
    gone, new = b - a, a - b
    wanted = collections.Counter(_key(r.finding) for r in repaired)
    for k in (wanted - gone).elements():
        failures.append(f"still reported after the repair: {k[0]} {k[2]}")
    for k in (gone - wanted).elements():
        failures.append(f"a finding no repair targeted disappeared: {k[0]} {k[2]}")
    for k in new.elements():
        failures.append(f"new in the output: {k[0]} {k[1].upper()} {k[2]}")
    by_key = {_key(f): f for f in before + after}

    try:
        delta = compare(source, output, limits=limits)
    except Exception as e:  # a comparison that cannot run proves nothing
        delta = []
        failures.append(f"compare(input, output) did not run: {e}")
    unexpected = list(delta)
    for tag, n in sorted(added.items()):
        declared = next((
            f for f in unexpected if f.code == "FID002" and f.severity == INFO
            and f.extra.get("tag") == tag
            and f.extra.get("after", 0) - f.extra.get("before", 0) == n), None)
        if declared is None:
            failures.append(f"compare(input, output) does not report the {n} "
                            f"added {_LABELS[tag]}")
        else:
            unexpected.remove(declared)
    failures += [f"compare(input, output) reports {f.code} "
                 f"{f.severity.value.upper()} {f.message}" for f in unexpected]

    against_added = None
    if against is not None:
        try:
            after_against = compare(against, output, limits=limits)
        except Exception as e:
            after_against = []
            failures.append(f"compare(source, output) did not run: {e}")
        counted_in = _counts(before_against, added)
        rest_in = collections.Counter(
            _key(f) for f in before_against if f not in counted_in)
        news = [f for f in after_against if f not in _counts(after_against, added)
                and not _take(rest_in, _key(f))]
        old = {(f.extra.get("tag"), f.extra.get("before")): f.extra.get("after")
               for f in counted_in}
        for f in _counts(after_against, added):
            tag = f.extra.get("tag")
            if f in counted_in or (f.code == "FID002" and f.severity == INFO):
                continue  # unchanged, or the declared INFO
            if old.get((tag, f.extra.get("before")), -1) + added[tag] == f.extra.get("after"):
                continue  # the same loss, smaller by what the repair added
            news.append(f)
        against_added = news
        failures += [f"compare(source, output) gains {f.code} "
                     f"{f.severity.value.upper()} {f.message}" for f in news]

    try:
        failures += differences(source, output, set(changed))
    except RepackError as e:
        failures.append(f"the output's ZIP layout could not be read: {e}")
    copied = len(read_entries(source)) - len(changed)
    return Verification(
        not failures, failures,
        [by_key[k] for k in gone.elements()], [by_key[k] for k in new.elements()],
        delta, against_added, changed, copied)


def _take(counter: collections.Counter, key) -> bool:
    if counter[key] > 0:
        counter[key] -= 1
        return True
    return False


def _check_paths(path: Path, output: Path, against: Optional[Path], force: bool) -> None:
    if path.suffix.lower() != ".docx":
        raise FixUsageError(f"fix repairs .docx files only, not {path.name}")
    if not path.is_file():
        raise FixUsageError(f"file not found: {path}")
    if against is not None and not against.is_file():
        raise FixUsageError(f"--against file not found: {against}")
    if output.exists() or output.is_symlink():
        if output.is_dir():
            raise FixUsageError(f"{output} is a directory; -o names the output file")
        if output.exists() and os.path.samefile(path, output):
            raise FixUsageError("the output must be a new file, not the input: fix "
                                "never repairs in place")
        if output.exists() and against is not None and os.path.samefile(against, output):
            raise FixUsageError("the output must not be the --against source")
        if not force:
            raise FixUsageError(f"{output} already exists; use --force to replace it")
    if output.resolve() == path.resolve():
        raise FixUsageError("the output must be a new file, not the input")
    if not output.resolve().parent.is_dir():
        raise FixUsageError(f"the output's directory does not exist: {output.parent}")


def fix(path: str | Path, output: str | Path, *, against: str | Path | None = None,
        force: bool = False, limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS
        ) -> FixReport:
    """Write a repaired, re-checked copy of `path` to `output`.

    Raises FixUsageError for arguments that cannot be acted on; every other
    outcome, including a refusal, is a FixReport.
    """
    path, output = Path(path), Path(output)
    against = Path(against) if against is not None else None
    _check_paths(path, output, against, force)
    report = FixReport("nothing-to-repair", "", path, _sha256(path), output,
                       against=against,
                       against_sha256=_sha256(against) if against else None)

    findings = check(path, limits=limits)
    blocking = [f for f in findings if f.code in _BLOCKING]
    if blocking:
        report.status = "input-refused"
        report.reason = (f"{_BLOCKING[blocking[0].code]} ({blocking[0].code}); "
                         "fix rewrites only packages it can read whole")
        report.not_repaired = [NotRepaired(f, "the package was not repaired")
                               for f in findings]
        return report
    try:
        parts = read_package(path, limits)
    except (PackageIssue, OSError) as e:
        report.status, report.reason = "input-refused", f"the package could not be read: {e}"
        return report
    refusal = None
    if len(office_documents(parts)) != 1:
        refusal = "the package has no single officeDocument entry point"
    else:
        try:
            entries = read_entries(path)
            stories = set(story_parts(parts, office_documents(parts)[0]))
            for entry in entries:
                if entry.name in stories and entry.method not in (0, 8):
                    raise RepackError(f"{entry.name} uses compression method "
                                      f"{entry.method}")
        except RepackError as e:
            refusal = f"the ZIP layout cannot be copied exactly: {e}"
    if refusal:
        report.status, report.reason = "input-refused", refusal
        report.not_repaired = [NotRepaired(f, "the package was not repaired")
                               for f in findings]
        return report

    before_against = None
    if against is not None:
        try:
            before_against = compare(against, path, limits=limits)
        except Exception as e:
            report.status = "input-refused"
            report.reason = f"the source could not be compared with the input: {e}"
            return report

    comments = [(i, f) for i, f in enumerate(findings) if f.code == "CMT005"]
    revisions = [(i, f) for i, f in enumerate(findings) if f.code == "REV001"]
    reasons: dict[int, tuple[str, str]] = {}
    repaired: list[Repaired] = []
    added: collections.Counter = collections.Counter()
    try:
        pkg = _Package(parts)
        for repair, found, pattern in (
                (ANCHOR_REPLIES, comments, _CMT005),
                (RENUMBER_REVISIONS, revisions, _REV001)):
            targets, kept = [], []
            for i, f in found:
                m = pattern.search(f.message)
                if m is None:
                    reasons[i] = (repair, "the finding's message does not name its target")
                else:
                    targets.append((m.group(1), f))
                    kept.append(i)
            if not targets:
                continue
            if repair == ANCHOR_REPLIES:
                done, refused, added = _anchor_replies(pkg, targets)
            else:
                done, refused = _renumber_revisions(pkg, targets)
            repaired += done
            for n, why in refused.items():
                reasons[kept[n]] = (repair, why)
        repaired_ids = {id(r.finding) for r in repaired}
        report.not_repaired = [
            NotRepaired(f, reasons[i][1], reasons[i][0]) if i in reasons
            else NotRepaired(f, _reason(f))
            for i, f in enumerate(findings) if id(f) not in repaired_ids]
        report.not_repaired += [NotRepaired(f, _reason(f), origin="against")
                                for f in before_against or []]
        report.repaired = repaired
        if not repaired:
            report.reason = ("every CMT005/REV001 finding was refused"
                             if comments or revisions else
                             "no CMT005 or REV001 finding; fix has nothing it can repair")
            return report
        edited = pkg.edited()
        for r in repaired:
            for c in r.changes:
                c.where = _path(c.node)
    except _Unproved as e:
        report.status, report.reason = "verification-failed", str(e)
        return report
    except Exception as e:  # a bug must not pass for a repair or a refusal
        report.status = "verification-failed"
        report.reason = f"internal error: {type(e).__name__}: {e}"
        return report

    directory = output.resolve().parent
    fd, temp = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".partial",
                                dir=directory)
    try:
        return _write(report, path, output, temp, fd, edited, repaired=repaired,
                      findings=findings, against=against,
                      before_against=before_against, added=added, force=force,
                      limits=limits)
    except FixUsageError:
        raise
    except Exception as e:  # a bug must not leave a file or pass for a repair
        report.status = "verification-failed"
        report.reason = f"internal error: {type(e).__name__}: {e}"
        return report
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _write(report: FixReport, path: Path, output: Path, temp: str, fd: int,
           edited: dict[str, bytes], *, repaired: list[Repaired],
           findings: list[Finding], against: Optional[Path],
           before_against: Optional[list[Finding]], added: collections.Counter,
           force: bool, limits: ArchiveLimits) -> FixReport:
    """Write the copy to `temp`, re-check it, then move it to `output`."""
    with os.fdopen(fd, "wb") as fh:
        repack(path, fh, edited)
        fh.flush()
        os.fsync(fh.fileno())
    verification = _verify(
        path, Path(temp), repaired=repaired, before=findings, against=against,
        before_against=before_against, added=added,
        changed=sorted(edited), limits=limits)
    if _sha256(path) != report.input_sha256:
        verification.failures.append("the input changed while it was repaired")
        verification.passed = False
    report.verification = verification
    if not verification.passed:
        report.status = "verification-failed"
        report.reason = "the re-check did not prove the repaired copy"
        return report
    mask = os.umask(0)
    os.umask(mask)
    os.chmod(temp, 0o666 & ~mask)
    if force:
        os.replace(temp, output)
    else:
        try:
            os.link(temp, output)
        except FileExistsError:
            raise FixUsageError(f"{output} appeared while fixing; nothing written")
        except OSError:
            if output.exists():
                raise FixUsageError(f"{output} appeared while fixing; nothing written")
            os.replace(temp, output)
    report.status = "repaired"
    report.reason = f"{len(repaired)} finding(s) repaired and re-checked"
    report.output_sha256 = _sha256(output)
    return report
