"""Bookmarks and fields: what a cross-reference is made of, and what an edit
lost of it.

"See clause 4.2" in a contract is a ``REF`` field whose instruction names a
bookmark around the clause number. A table of contents is a ``TOC`` field and
one ``PAGEREF`` per entry, each naming a ``_Toc`` bookmark in a heading. The
page number in a footer is a ``PAGE`` field. An edit that rebuilds a paragraph
drops whichever of these stood in it, and the file still opens: the field's
last result stays behind as plain text, or the field stays and its bookmark is
gone, and Word prints "Error! Reference source not found." in its place the
next time fields are updated.

Two findings, both against a source:

``FID015``  a bookmark of the source is gone. An error when a field or an
            internal link of the edited file still points at it; a warning
            when nothing does and the name is not one of Word's hidden ones.
``FID016``  a field of the source is gone, per story and kind of field.

What counts as the same:

- A bookmark is its name, compared without regard to case, as Word compares
  it. Ids are renumbered by every producer and are not read.
- A field is its kind (``REF``, ``PAGE``, ``TOC``) and, for a field that
  points at a bookmark, that bookmark. Switches are not compared: LibreOffice
  writes ``TOC \\o "1-3" \\h \\z \\u`` back as ``TOC \\z \\o "1-3" \\u \\h`` and
  ``PAGE \\* Arabic`` as ``PAGE \\* ARABIC``, and no field was lost. The simple
  form (``w:fldSimple``) and the complex form (``w:fldChar`` with
  ``w:instrText``) are the same field, since producers write either. An
  instruction inside a tracked deletion (``w:delInstrText``) is still there.

What is deliberately not reported:

- A hidden bookmark nothing refers to. Word writes ``_GoBack`` for the last
  cursor position and ``_Hlk…`` while pasting, and removes them as it likes.
- A ``HYPERLINK`` field that became a ``w:hyperlink`` element. Word writes
  the element where other producers write the field, so a lost ``HYPERLINK``
  field counts only as far as the story did not gain link elements.
- Fields an edit added, and what a field currently displays. The text a field
  shows is paragraph text, which ``FID014`` compares.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field

from .finding import ERROR, WARN, Finding

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: Fields whose first argument names a bookmark.
_REFERRING = ("REF", "PAGEREF", "NOTEREF")
_ARGUMENT = re.compile(r'"([^"]*)"|(\S+)')
_LOCAL_LINK = re.compile(r'\\l\s+(?:"([^"]*)"|(\S+))')

#: How many names or instructions a message spells out before "and N more".
_LISTED = 5


def _key(name: str) -> str:
    return name.casefold()


def normalise(instruction: str) -> tuple[str, str]:
    """(kind, instruction) of a field, or ("", "") when it names no kind.

    A formula field has no name of its own (``=SUM(ABOVE)``); its kind is
    ``=``.
    """
    text = " ".join((instruction or "").split())
    if not text:
        return "", ""
    if text.startswith("="):
        return "=", text
    kind, _, rest = text.partition(" ")
    kind = kind.upper()
    return kind, f"{kind} {rest}" if rest else kind


def instructions(root) -> list[tuple[str, str]]:
    """Every field of a story as (kind, instruction), in document order of
    where each field ends."""
    out = [normalise(node.get(W + "instr", "")) for node in root.iter(W + "fldSimple")]
    # A complex field is begin, instruction runs, an optional separate, result
    # runs, end. Fields nest, both inside an instruction and inside a result,
    # so the open fields are a stack and text goes to the innermost one that is
    # still reading its instruction.
    open_fields: list[list] = []
    for node in root.iter(W + "fldChar", W + "instrText", W + "delInstrText"):
        if node.tag != W + "fldChar":
            if open_fields and open_fields[-1][1]:
                open_fields[-1][0].append(node.text or "")
            continue
        state = node.get(W + "fldCharType")
        if state == "begin":
            open_fields.append([[], True])
        elif state == "separate" and open_fields:
            open_fields[-1][1] = False
        elif state == "end" and open_fields:
            out.append(normalise("".join(open_fields.pop()[0])))
    return [item for item in out if item[0]]


def _target(kind: str, instruction: str) -> str | None:
    """The bookmark a field refers to, if its kind refers to one."""
    rest = instruction.partition(" ")[2]
    if kind in _REFERRING:
        match = _ARGUMENT.search(rest)
        if match is None:
            return None
        name = match.group(1) if match.group(1) is not None else match.group(2)
        return None if name.startswith("\\") else name
    if kind == "HYPERLINK":
        match = _LOCAL_LINK.search(rest)
        if match is not None:
            return match.group(1) if match.group(1) is not None else match.group(2)
    return None


@dataclass
class References:
    """The bookmarks, fields and internal links of one document."""

    #: casefolded name -> the name as first written
    bookmarks: dict[str, str] = field(default_factory=dict)
    #: casefolded bookmark name -> how many fields and links point at it
    targets: collections.Counter = field(default_factory=collections.Counter)
    #: story -> (kind, casefolded bookmark it points at or "") -> count
    fields: dict[str, collections.Counter] = field(default_factory=dict)
    #: casefolded bookmark name -> the name as a field first wrote it
    written: dict[str, str] = field(default_factory=dict)
    #: story -> number of w:hyperlink elements
    links: collections.Counter = field(default_factory=collections.Counter)

    def read(self, story: str, root) -> None:
        """Add one story part. A story of several parts is read part by part."""
        for node in root.iter(W + "bookmarkStart"):
            name = node.get(W + "name")
            if name:
                self.bookmarks.setdefault(_key(name), name)
        found = self.fields.setdefault(story, collections.Counter())
        for kind, instruction in instructions(root):
            target = _target(kind, instruction)
            points = kind in _REFERRING and bool(target)
            found[(kind, _key(target) if points else "")] += 1
            if target:
                self.targets[_key(target)] += 1
                self.written.setdefault(_key(target), target)
        for node in root.iter(W + "hyperlink"):
            self.links[story] += 1
            anchor = node.get(W + "anchor")
            if anchor:
                self.targets[_key(anchor)] += 1


def _listed(items: list[str]) -> str:
    shown = ", ".join(f"'{item}'" for item in items[:_LISTED])
    more = len(items) - _LISTED
    return f"{shown} and {more} more" if more > 0 else shown


def assess(source: References, edited: References) -> list[Finding]:
    """FID015 and FID016: what `edited` lost of the source's bookmarks and
    fields."""
    out: list[Finding] = []

    gone = [name for key, name in source.bookmarks.items()
            if key not in edited.bookmarks]
    dangling = sorted(name for name in gone if edited.targets[_key(name)])
    unused = sorted(name for name in gone
                    if not edited.targets[_key(name)] and not name.startswith("_"))
    if dangling:
        pointing = sum(edited.targets[_key(name)] for name in dangling)
        out.append(Finding(
            "FID015", ERROR,
            f"{len(dangling)} bookmark(s) of the source are gone while "
            f"{pointing} field(s) or link(s) still point at them: "
            f"{_listed(dangling)} - Word prints 'Error! Reference source not "
            "found.' for such a field when fields are updated",
            extra={"referenced": True, "lost": len(dangling),
                   "references": pointing, "names": dangling},
        ))
    if unused:
        out.append(Finding(
            "FID015", WARN,
            f"{len(unused)} bookmark(s) of the source are gone: "
            f"{_listed(unused)} - nothing in the edited file points at them, "
            "but a link from another document would no longer land",
            extra={"referenced": False, "lost": len(unused), "names": unused},
        ))

    for story, before in source.fields.items():
        after = edited.fields.get(story, collections.Counter())
        for kind in sorted({kind for kind, _ in before}):
            had = sum(n for (k, _), n in before.items() if k == kind)
            has = sum(n for (k, _), n in after.items() if k == kind)
            # by bookmark for a field that points at one, by count otherwise
            missing: list[str] = []
            for (k, target), n in sorted(before.items()):
                if k == kind:
                    missing.extend([target] * max(0, n - after[(k, target)]))
            lost = len(missing)
            if kind == "HYPERLINK":
                # the field may have become a link element; see the module docstring
                lost = max(0, lost - max(0, edited.links[story] - source.links[story]))
            if not lost:
                continue
            targets = sorted(source.written.get(t, t) for t in missing if t)
            if has == 0:
                what = f"all {had} {kind} field(s) of the source are gone"
            elif targets:
                what = (f"{lost} of {had} {kind} field(s) of the source are gone "
                        f"or point elsewhere, {has} remain")
            else:
                what = f"{lost} of {had} {kind} field(s) of the source are gone"
            pointed = f" (to {_listed(targets)})" if targets else ""
            out.append(Finding(
                "FID016", ERROR if has == 0 else WARN,
                f"{story}: {what}{pointed} - what a lost field showed stays "
                "as plain text, if at all, and no longer updates",
                where=story,
                extra={"story": story, "kind": kind, "before": had,
                       "after": has, "lost": lost, "targets": targets},
            ))
    return out
