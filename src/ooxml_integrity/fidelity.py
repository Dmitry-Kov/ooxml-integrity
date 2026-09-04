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
from dataclasses import dataclass
from pathlib import Path

from .archive import DEFAULT_ARCHIVE_LIMITS, ArchiveLimits, read_package
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


def _norm(text: str) -> str:
    """Whitespace-insensitive body text: a reflowed comment is not a lost one."""
    return re.sub(r"\s+", " ", text or "").strip()


def _bodies(parts: dict[str, bytes], part: str, tag: str
            ) -> tuple[collections.Counter, dict[str, str]]:
    """Normalised body text of every item in `part`, as a multiset.

    A multiset rather than a set, so losing one of two identically worded
    comments is still a loss.
    """
    blob = parts.get(part)
    if blob is None:
        return collections.Counter(), {}
    root = parse_xml(blob)
    out: collections.Counter = collections.Counter()
    authors: dict[str, str] = {}
    for item in root.iter(W + tag):
        if item.get(W + "type") in _BOILERPLATE:
            continue
        body = _norm("".join(t.text or "" for t in item.iter(W + "t")))
        if body:
            out[body] += 1
            authors.setdefault(body, item.get(W + "author") or "")
    return out, authors


@dataclass
class _Snapshot:
    counts: dict[str, int]
    bodies: dict[str, collections.Counter]
    authors: dict[tuple[str, str], str]
    text_length: int


def _snapshot(path: str | Path, limits: ArchiveLimits) -> _Snapshot:
    """Read one bounded package, retain only the fidelity facts, then release it."""
    wanted = {"word/document.xml", *(part for part, _, _, _ in BODY_PARTS)}
    parts = read_package(path, limits, members=wanted)
    doc = parse_xml(parts["word/document.xml"])
    counts = {tag: len(list(doc.iter(W + tag))) for tag, _, _ in TRACKED}
    text_length = sum(len(t.text or "") for t in doc.iter(W + "t"))
    bodies: dict[str, collections.Counter] = {}
    authors: dict[tuple[str, str], str] = {}
    for part, tag, _, _ in BODY_PARTS:
        body_counts, body_authors = _bodies(parts, part, tag)
        bodies[part] = body_counts
        authors.update(
            ((part, body), author) for body, author in body_authors.items()
        )
    return _Snapshot(counts, bodies, authors, text_length)


def compare(source: str | Path, edited: str | Path, *,
            limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> list[Finding]:
    """What did `edited` lose relative to `source`?

    Package reads are bounded by `limits`. Raises package/XML exceptions;
    callers that may be handed invalid input should use the CLI, which converts
    a failed requested comparison into an error-level `FID000` finding.
    """
    source_snapshot = _snapshot(source, limits)
    edited_snapshot = _snapshot(edited, limits)
    before, after = source_snapshot.counts, edited_snapshot.counts
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
        src_bodies = source_snapshot.bodies[part]
        out_bodies = edited_snapshot.bodies[part]
        for body, n in src_bodies.items():
            lost = n - out_bodies.get(body, 0)
            if lost <= 0:
                continue
            who = source_snapshot.authors.get((part, body), "")
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

    ta, tb = source_snapshot.text_length, edited_snapshot.text_length
    if ta and tb < ta * TEXT_LOSS_THRESHOLD:
        out.append(Finding(
            "FID003", ERROR,
            f"text volume fell from {ta} to {tb} characters "
            f"({round(100 * (1 - tb / ta))}% of content lost)",
            extra={"before": ta, "after": tb},
        ))
    return out
