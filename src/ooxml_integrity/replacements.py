"""Tracked replacements wider than the change (FID013).

A tracked replacement is a deletion and an insertion side by side, by one
author. Word records the words that changed. A tool that replaces a whole
sentence or note to change one word of it records every other word as deleted
and inserted again: nothing is lost and accepting gives the right text, but a
reviewer sees unchanged words struck through and added again under the
editor's name, and cannot see what changed. In the review-history benchmark
docx-cli edited a footnote that way.

Only replacements an edit added are read: neither revision's kind, author and
effective date occurs in the source story. Words are what whitespace separates,
as a reader sees them. The unchanged ones are the words the two texts share at
their start and at their end, which the replacement could have left out;
words shared in the middle can be chance, a rewrite reusing "the" and "of",
and do not count. A replacement is reported when it carries at least
UNCHANGED_WORDS unchanged words and they outnumber the words it changes: a
rewritten sentence that keeps its first few words is a rewrite, a sentence
deleted and inserted again to change one word of it is not.
"""
from __future__ import annotations

import os
from typing import NamedTuple

from .finding import WARN, Finding

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DATE_UTC = "{http://schemas.microsoft.com/office/word/2023/wordml/word16du}dateUtc"

#: Unchanged words a replacement may carry before it is reported. A replaced
#: phrase often keeps a word or two of itself ("ten business days" becoming
#: "fifteen business days"); four is most of a clause.
UNCHANGED_WORDS = 4


def changed_words(deleted: str, inserted: str, unchanged: int) -> int:
    """Words the replacement changes, on its longer side."""
    return max(len(deleted.split()), len(inserted.split())) - unchanged


class Replacement(NamedTuple):
    #: (kind, author, effective date) of each revision, as compare() keys them
    deletion: tuple
    insertion: tuple
    deleted: str
    inserted: str


def _context(node) -> tuple:
    return (node.tag[len(W):], node.get(W + "author") or "",
            node.get(_DATE_UTC, node.get(W + "date")) or "")


def replacements(root) -> list[Replacement]:
    """Every deletion and insertion by one author that touch in a paragraph.

    Text is read in document order. Deleted text (``w:delText`` in a
    deletion) and inserted text (``w:t`` in an insertion and no deletion)
    form runs per revision context; anything else between them, text or a
    revision of another kind, separates them. Text of a paragraph nested in a
    text box belongs to that paragraph only.
    """
    out = []
    for paragraph in root.iter(W + "p"):
        runs: list[list] = []  # [state, context, texts]
        for node in paragraph.iter(W + "t", W + "delText"):
            if next(node.iterancestors(W + "p"), None) is not paragraph:
                continue
            wrappers = list(node.iterancestors(W + "del", W + "ins"))
            deletion = next((a for a in wrappers if a.tag == W + "del"), None)
            insertion = next((a for a in wrappers if a.tag == W + "ins"), None)
            if node.tag == W + "delText" and deletion is not None:
                state, context = "del", _context(deletion)
            elif node.tag == W + "t" and insertion is not None and deletion is None:
                state, context = "ins", _context(insertion)
            else:
                state, context = "other", None
            if runs and runs[-1][0] == state and runs[-1][1] == context:
                runs[-1][2].append(node.text or "")
            else:
                runs.append([state, context, [node.text or ""]])
        for a, b in zip(runs, runs[1:]):
            if {a[0], b[0]} == {"del", "ins"} and a[1][1] == b[1][1]:
                deleted, inserted = (a, b) if a[0] == "del" else (b, a)
                out.append(Replacement(deleted[1], inserted[1],
                                       "".join(deleted[2]), "".join(inserted[2])))
    return out


def unchanged_words(deleted: str, inserted: str) -> int:
    """Words the two texts share at their start and at their end."""
    old, new = deleted.split(), inserted.split()
    head = len(os.path.commonprefix([old, new]))
    tail = len(os.path.commonprefix([old[head:][::-1], new[head:][::-1]]))
    return head + tail


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 60 else text[:57] + "..."


def assess(story: str, edited: list[Replacement], known) -> list[Finding]:
    """FID013 for each replacement the edit added that carries unchanged words."""
    out = []
    for item in edited:
        if item.deletion in known or item.insertion in known:
            continue
        n = unchanged_words(item.deleted, item.inserted)
        changed = changed_words(item.deleted, item.inserted, n)
        if n < UNCHANGED_WORDS or n <= changed:
            continue
        author = item.deletion[1]
        who = f"by {author}" if author else "with no author"
        out.append(Finding(
            "FID013", WARN,
            f"{story}: a tracked replacement {who} deletes and inserts again "
            f"{n} words that did not change around {changed} that did, so a "
            f"reviewer sees them struck through and added again: deleted "
            f'"{_snippet(item.deleted)}", inserted "{_snippet(item.inserted)}"',
            where=story,
            extra={"story": story, "author": author, "unchanged_words": n,
                   "changed_words": changed,
                   "deleted": item.deleted, "inserted": item.inserted},
        ))
    return out
