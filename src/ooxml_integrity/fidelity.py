"""
Fidelity check against the source document.

The inspector answers "is this file self-consistent?". That is not enough: a
document stripped of every style, footnote and revision is perfectly
self-consistent. A second question is needed - "what was lost relative to the
original?".
"""
from __future__ import annotations

import collections
import re
import zipfile
from pathlib import Path

from .finding import ERROR, INFO, WARN, Finding
from .xmlutil import fromstring as parse_xml

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: (tag, human label, severity when some are lost)
#:
#: The severity rule: losing something that makes content or an audit trail
#: INVISIBLE is an error, because nothing downstream will report it. Losing
#: something that only changes how the document looks is a warning. Losing all
#: of any construct is always an error.
TRACKED: tuple[tuple[str, str, object], ...] = (
    ("commentReference", "comment anchors", ERROR),
    ("footnoteReference", "footnote references", ERROR),
    ("ins", "tracked insertions", ERROR),
    ("del", "tracked deletions", ERROR),
    ("sdt", "content controls", ERROR),
    ("drawing", "images and charts", ERROR),
    ("tbl", "tables", ERROR),
    ("hyperlink", "hyperlinks", WARN),
    ("pStyle", "paragraph style references", WARN),
    ("rStyle", "character style references", WARN),
    ("numPr", "numbered list items", WARN),
    ("tblHeader", "table header rows", WARN),
)

#: below this fraction of the source's text length, report FID003
TEXT_LOSS_THRESHOLD = 0.95

#: Parts whose bodies are compared by content rather than by count, and the
#: element that holds one item.
#:
#: Counting is not enough, and this is the hole that counting leaves: remove
#: one comment and add another, and every count matches. The document is then
#: perfectly self-consistent - nothing is orphaned, because both the anchor and
#: the comments.xml entry went together - so the inspector is silent too, and
#: the tool reports a clean file while the reviewer's note is gone. That is the
#: exact defect this project exists to catch, missed by its own fidelity check
#: until someone pointed at the arithmetic.
#:
#: Matching is on the item's normalised body text, not its id. Ids are a
#: producer's private business and get renumbered legitimately; the reviewer's
#: sentence is the thing that either survived or did not.
BODY_PARTS: tuple[tuple[str, str, str, str], ...] = (
    ("word/comments.xml", "comment", "FID004", "comment"),
    ("word/footnotes.xml", "footnote", "FID005", "footnote"),
    ("word/endnotes.xml", "endnote", "FID006", "endnote"),
)

#: Footnote and endnote parts always carry these two housekeeping items, which
#: hold no author's words and are not interesting to compare.
_BOILERPLATE = {"separator", "continuationSeparator", "continuationNotice"}


def _document(path: str | Path):
    with zipfile.ZipFile(path) as z:
        return parse_xml(z.read("word/document.xml"))


def _counts(path: str | Path) -> dict[str, int]:
    doc = _document(path)
    return {tag: len(list(doc.iter(W + tag))) for tag, _, _ in TRACKED}


def _norm(text: str) -> str:
    """Whitespace-insensitive body text: a reflowed comment is not a lost one."""
    return re.sub(r"\s+", " ", text or "").strip()


def _bodies(path: str | Path, part: str, tag: str) -> collections.Counter:
    """Normalised body text of every item in `part`, as a multiset.

    A multiset rather than a set, so losing one of two identically worded
    comments is still a loss.
    """
    try:
        with zipfile.ZipFile(path) as z:
            blob = z.read(part)
    except KeyError:
        return collections.Counter()
    root = parse_xml(blob)
    out: collections.Counter = collections.Counter()
    for item in root.iter(W + tag):
        if item.get(W + "type") in _BOILERPLATE:
            continue
        body = _norm("".join(t.text or "" for t in item.iter(W + "t")))
        if body:
            out[body] += 1
    return out


def _author_of(path: str | Path, part: str, tag: str, body: str) -> str:
    """Who wrote the item with this body, for a message worth reading."""
    try:
        with zipfile.ZipFile(path) as z:
            root = parse_xml(z.read(part))
    except KeyError:
        return ""
    for item in root.iter(W + tag):
        if _norm("".join(t.text or "" for t in item.iter(W + "t"))) == body:
            return item.get(W + "author") or ""
    return ""


def _text(path: str | Path) -> str:
    doc = _document(path)
    return "".join(t.text or "" for t in doc.iter(W + "t"))


def compare(source: str | Path, edited: str | Path) -> list[Finding]:
    """What did `edited` lose relative to `source`?

    Raises the same exceptions as opening a zip - callers that may be handed a
    corrupt file should run `check()` first, which reports rather than raises.
    """
    before, after = _counts(source), _counts(edited)
    out: list[Finding] = []

    for tag, label, sev in TRACKED:
        a, b = before[tag], after[tag]
        if not a:
            continue
        if b < a:
            lost = a - b
            out.append(Finding(
                "FID001",
                ERROR if b == 0 else sev,
                f"{label}: {a} -> {b} "
                f'({"all lost" if b == 0 else f"{lost} lost"})',
                extra={"tag": tag, "before": a, "after": b},
            ))
        elif b > a:
            # A higher count is not itself a defect: the agent may legitimately
            # have added an item, or wrapped its edit in w:ins. Real duplication
            # is caught by colliding ids (REV001), not by a counter.
            out.append(Finding(
                "FID002", INFO,
                f"{label}: {a} -> {b} - added during editing "
                "(only a defect if ids collide, see REV001)",
                extra={"tag": tag, "before": a, "after": b},
            ))

    for part, tag, code, label in BODY_PARTS:
        src_bodies = _bodies(source, part, tag)
        out_bodies = _bodies(edited, part, tag)
        for body, n in src_bodies.items():
            lost = n - out_bodies.get(body, 0)
            if lost <= 0:
                continue
            who = _author_of(source, part, tag, body)
            snippet = body if len(body) <= 60 else body[:57] + "..."
            times = "" if lost == 1 and n == 1 else f" ({lost} of {n})"
            out.append(Finding(
                code, ERROR,
                f"a {label} present in the source is gone from the edited "
                f"file{times} - its text is not there under any id, so nothing "
                f"downstream will report it"
                + (f". {label.capitalize()} by {who}: " if who
                   else f". {label.capitalize()}: ")
                + f'"{snippet}"',
                part=part,
                extra={"body": body, "author": who, "lost": lost,
                       "in_source": n},
            ))

    ta, tb = _text(source), _text(edited)
    if ta and len(tb) < len(ta) * TEXT_LOSS_THRESHOLD:
        out.append(Finding(
            "FID003", ERROR,
            f"text volume fell from {len(ta)} to {len(tb)} characters "
            f"({round(100 * (1 - len(tb) / len(ta)))}% of content lost)",
            extra={"before": len(ta), "after": len(tb)},
        ))
    return out
