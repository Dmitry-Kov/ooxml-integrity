"""Paragraphs whose text an edit changed (FID014).

The loss rules say what an edit removed. They cannot say whether the edit
made the change it was asked for: a tool asked to replace "disputed amount"
inside another reviewer's pending insertion rewrote a different span of it,
lost nothing any rule counts, and in the review-history benchmark nothing
reported it. Only a caller who knows what the paragraph should now read can
tell. FID014 lists, as INFO, every paragraph whose text differs between the
source and the edited file, with both texts, so an expectation can require
the result: `FID014` with `after` set to the paragraph the edit was asked to
produce fails with `EXP001` when the edit produced something else.

A paragraph's text is read in two views, as a reader of the review sees it:
with every tracked change accepted (`before`, `after`) and with every tracked
change rejected (`before_original`, `after_original`). Whitespace is
normalised, as the story rules normalise it: runs of spaces, tabs and breaks
read as one space, and none leads or trails, so a change of spacing alone is
not a change of text. A paragraph inside a text box is a paragraph of its
own. An empty paragraph has no text to change and is left out, so adding a
section break or a blank line is not reported; paragraph numbers still count
every paragraph. A header or footer story is read as the distinct texts its
section slots show, each once, in the order a reader meets them: splitting a
shared header part into two with the same text, or one more section showing
it, changes nothing. Paragraphs are aligned in reading order, per story, with the
unchanged ones as anchors. A changed paragraph is one that stands where a
source paragraph stood, one for one; a block whose length changed is
reported as paragraphs removed and added.
"""
from __future__ import annotations

import difflib
from typing import NamedTuple

from .finding import INFO, Finding

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
#: Content a reader sees only with tracked changes accepted, or only rejected.
_INSERTED = {W + "ins", W + "moveTo"}
_REMOVED = {W + "del", W + "moveFrom"}
#: Characters of each text the message quotes; `extra` has them whole.
SHOWN = 120


class ParagraphText(NamedTuple):
    current: str
    original: str


def _own(paragraph):
    """A paragraph's own content: a paragraph nested in it (a text box) is not."""
    for node in paragraph.iter():
        if node is paragraph:
            continue
        owner = next(node.iterancestors(W + "p"), None)
        if owner is paragraph and node.tag != W + "p":
            yield node


def _token(node, view: str) -> str | None:
    tag = node.tag
    if tag not in (W + "t", W + "delText", W + "tab", W + "br", W + "cr"):
        return None
    ancestors = {a.tag for a in node.iterancestors()}
    if view == "current" and (tag == W + "delText" or ancestors & _REMOVED):
        return None
    if view == "original" and ancestors & _INSERTED:
        return None
    if tag == W + "tab":
        return "\t"
    if tag in (W + "br", W + "cr"):
        return "\n"
    return node.text or ""


def paragraph_text(paragraph, view: str) -> str:
    raw = "".join(t for t in (_token(n, view) for n in _own(paragraph)) if t is not None)
    return " ".join(raw.split())


def paragraph_views(root) -> list[ParagraphText]:
    """Every paragraph of a story part in reading order, in both views."""
    return [ParagraphText(paragraph_text(p, "current"), paragraph_text(p, "original"))
            for p in root.iter(W + "p")]


def _short(text: str) -> str:
    return text if len(text) <= SHOWN else text[:SHOWN - 3] + "..."


def _finding(story: str, change: str, number: int,
             before: ParagraphText | None, after: ParagraphText | None) -> Finding:
    empty = ParagraphText("", "")
    b, a = before or empty, after or empty
    if change == "added":
        what = f"paragraph {number} added: {_short(a.current)!r}"
    elif change == "removed":
        what = f"source paragraph {number} removed: {_short(b.current)!r}"
    elif b.current != a.current:
        what = f"paragraph {number} changed: {_short(b.current)!r} -> {_short(a.current)!r}"
    else:
        what = (f"paragraph {number} changed with its tracked changes rejected: "
                f"{_short(b.original)!r} -> {_short(a.original)!r}")
    return Finding(
        "FID014", INFO, f"{story}: {what}",
        where=f"{story}/p{number}" + ("" if change != "removed" else " (source)"),
        extra={"story": story, "change": change,
               "before": b.current, "after": a.current,
               "before_original": b.original, "after_original": a.original},
    )


def assess(story: str, before: list[ParagraphText],
           after: list[ParagraphText]) -> list[Finding]:
    """FID014 for one story: the paragraphs that differ, in reading order."""
    # Align the paragraphs that hold text; number them as they stand.
    old = [(n, p) for n, p in enumerate(before, 1) if p.current or p.original]
    new = [(n, p) for n, p in enumerate(after, 1) if p.current or p.original]
    out = []
    matcher = difflib.SequenceMatcher(None, [p for _, p in old], [p for _, p in new],
                                      autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if op == "replace" and i2 - i1 == j2 - j1:
            out.extend(_finding(story, "changed", new[j][0], old[i][1], new[j][1])
                       for i, j in zip(range(i1, i2), range(j1, j2)))
            continue
        out.extend(_finding(story, "removed", old[i][0], old[i][1], None) for i in range(i1, i2))
        out.extend(_finding(story, "added", new[j][0], None, new[j][1]) for j in range(j1, j2))
    return out
