"""
Fidelity check against the source document.

The inspector answers "is this file self-consistent?". That is not enough: a
document stripped of every style, footnote and revision is perfectly
self-consistent. A second question is needed - "what was lost relative to the
original?".
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from .finding import ERROR, INFO, WARN, Finding

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


def _document(path: str | Path):
    with zipfile.ZipFile(path) as z:
        return etree.fromstring(z.read("word/document.xml"))


def _counts(path: str | Path) -> dict[str, int]:
    doc = _document(path)
    return {tag: len(list(doc.iter(W + tag))) for tag, _, _ in TRACKED}


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

    ta, tb = _text(source), _text(edited)
    if ta and len(tb) < len(ta) * TEXT_LOSS_THRESHOLD:
        out.append(Finding(
            "FID003", ERROR,
            f"text volume fell from {len(ta)} to {len(tb)} characters "
            f"({round(100 * (1 - len(tb) / len(ta)))}% of content lost)",
            extra={"before": len(ta), "after": len(tb)},
        ))
    return out
