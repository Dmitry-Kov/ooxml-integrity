"""FID017: two identifiable review comments traded their selected text."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import re
from typing import NamedTuple

from .comments import W
from .finding import ERROR, Finding
from .paragraphs import SHOWN, ParagraphText, paragraph_text
from .revision_text import MAX_SCAN_WORK
from .runtext import shown
from .xmlutil import extract_fallback


class Comment(NamedTuple):
    text: str
    author: str


@dataclass(frozen=True)
class Anchor:
    paragraph: str
    selected: str
    number: int = field(compare=False)  # Inserting an earlier paragraph only shifts the location.


_MARKERS = tuple(W + name for name in ("commentRangeStart", "commentRangeEnd", "commentReference"))
_COMPLEX = {W + tag for tag in ("ins", "del", "moveFrom", "moveTo", "delText",
                                "fldSimple", "fldChar", "instrText", "delInstrText",
                                "drawing", "pict", "object", "txbxContent", "altChunk")}


def _id(node) -> str | None:
    value = node.get(W + "id", "").strip(" \r\n\t")
    if not re.fullmatch(r"[+-]?[0-9]+", value):
        return None
    digits = value.lstrip("+-").lstrip("0") or "0"
    return "-" + digits if value.startswith("-") and digits != "0" else digits


def _comments(root) -> dict[str, Comment]:
    """Count every direct definition, including unanchored copies of a body."""
    extract_fallback(root)
    definitions = root.findall(W + "comment")
    ids = Counter(_id(node) for node in definitions)
    candidates = {}
    texts: Counter[str] = Counter()
    for node in definitions:
        paragraphs = (paragraph_text(p, "current") for p in node.iter(W + "p"))
        body = " ".join(filter(None, paragraphs))
        texts[body] += 1
        cid = _id(node)
        if cid is not None and ids[cid] == 1 and body and next(node.iter(*_COMPLEX), None) is None:
            candidates[cid] = Comment(body, node.get(W + "author", ""))
    return {cid: comment for cid, comment in candidates.items() if texts[comment.text] == 1}


def inventory(doc, comments, paragraphs: list[ParagraphText]) -> dict[Comment, Anchor]:
    """Both ends and the reference must belong to a single, unique plain paragraph."""
    if comments is None:
        return {}
    notes = _comments(comments)
    if len(notes) < 2:
        return {}
    # A second start/end/reference elsewhere makes even a well-formed local triple ambiguous.
    markers = Counter(_id(node) for node in doc.iter(*_MARKERS))
    copies = Counter(p.current for p in paragraphs)
    anchors = {}
    for number, (p, view) in enumerate(zip(doc.iter(W + "p"), paragraphs), 1):
        if copies[view.current] != 1 or next(p.iter(_MARKERS[0]), None) is None:
            continue
        if next(p.iter(*_COMPLEX), None) is not None or any(
                a.tag in _COMPLEX for a in p.iterancestors()):
            continue
        pieces = []
        offsets: dict[str, list[tuple[str, int]]] = defaultdict(list)
        length = 0
        for node in p.iter():
            if node.tag in _MARKERS:
                cid = _id(node)
                if cid is not None and cid in notes and markers[cid] == 3:
                    offsets[cid].append((node.tag, length))
            else:
                text = shown(node)
                if text:
                    pieces.append(text)
                    length += len(text)
        # Searching one long paragraph for many overlapping ranges must stay bounded.
        if length * len(offsets) > MAX_SCAN_WORK:
            continue
        raw = "".join(pieces)
        for cid, positions in offsets.items():
            if tuple(tag for tag, _ in positions) != _MARKERS:
                continue
            selected = " ".join(raw[positions[0][1]:positions[1][1]].split())
            if selected and view.current.find(selected) == view.current.rfind(selected) != -1:
                anchors[notes[cid]] = Anchor(view.current, selected, number)
    counts = Counter(anchors.values())
    return {comment: anchor for comment, anchor in anchors.items() if counts[anchor] == 1}


def assess(source: dict[Comment, Anchor], edited: dict[Comment, Anchor], part: str) -> list[Finding]:
    at_source = {anchor: comment for comment, anchor in source.items()}
    out = []
    for comment in sorted(source.keys() & edited.keys()):
        before, after = source[comment], edited[comment]
        partner = at_source.get(after)
        if partner is None or partner <= comment or edited.get(partner) != before:
            continue
        moves = []
        descriptions = []
        for note in (comment, partner):
            old, new = source[note], edited[note]
            moves.append({"comment": note.text, "author": note.author,
                          "before": old.selected, "after": new.selected,
                          "paragraph_sha256": hashlib.sha256(old.paragraph.encode()).hexdigest()})
            descriptions.append(f"{note.text[:SHOWN]!r} moved from {old.selected[:SHOWN]!r} "
                                f"(source paragraph {old.number}) to {new.selected[:SHOWN]!r} "
                                f"(edited paragraph {new.number})")
        out.append(Finding("FID017", ERROR, "Two comments exchanged their anchors. "
                           + ". ".join(descriptions), where="document", part=part,
                           extra={"story": "document", "moves": moves}))
    return out
