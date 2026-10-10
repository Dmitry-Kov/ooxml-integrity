"""The content type each relationship from the main document requires (PKG010)."""
from __future__ import annotations

import posixpath
from dataclasses import dataclass
from urllib.parse import unquote

from .comments import (
    ASCII_LOWER,
    DOCUMENT,
    STRICT,
    STRICT_DOCUMENT,
    _existing,
    _resolve,
    relationships_part,
)

CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_OR = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_WP = "application/vnd.openxmlformats-officedocument.wordprocessingml."
WORD_MAIN = _WP + "document.main+xml"

#: Relationship type from the main document -> the content type Word writes
#: for its target. Word for Mac 16.113.4 refused Codex outputs whose
#: commentsExtended part was declared application/vnd.ms-word.commentsExtended+xml
#: and opened them with only that type corrected
#: (evidence/review-history-benchmark/word-check-content-type).
RELATED = {
    **{_OR + k: _WP + k + "+xml" for k in (
        "styles", "numbering", "settings", "webSettings", "fontTable",
        "footnotes", "endnotes", "header", "footer", "comments")},
    _OR + "theme": "application/vnd.openxmlformats-officedocument.theme+xml",
    "http://schemas.microsoft.com/office/2011/relationships/commentsExtended":
        _WP + "commentsExtended+xml",
    "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds":
        _WP + "commentsIds+xml",
    "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible":
        _WP + "commentsExtensible+xml",
    "http://schemas.microsoft.com/office/2011/relationships/people":
        _WP + "people+xml",
}


def media_type(value: str | None) -> str:
    """A content type without parameters, compared ASCII-case-insensitively."""
    return (value or "").split(";", 1)[0].strip().translate(ASCII_LOWER)


@dataclass(frozen=True)
class Pair:
    """One relationship of a known type and what the package declares for its target."""

    relationship: str
    relationship_type: str
    part: str
    declared: tuple[str, ...]     # empty: no content type at all (PKG005)
    expected: str

    @property
    def mismatch(self) -> bool:
        return bool(self.declared) and media_type(self.expected) not in map(
            media_type, self.declared)


@dataclass(frozen=True)
class Related:
    """The pairs read, or why none could be: `skipped` or `unsupported`."""

    pairs: tuple[Pair, ...] = ()
    skipped: str = ""
    unsupported: str = ""


def related(parts: dict[str, bytes], trees: dict, main: str) -> Related:
    """Relationships from the main document whose type has one content type.

    Only a plain document main part is read: a template or macro-enabled main
    part is `unsupported`, and Strict, a missing or unreadable main part, its
    relationship part or `[Content_Types].xml` is `skipped`. An override applies
    to its part name ASCII-case-insensitively, else the extension default; a
    part neither covers exactly has no content type, as for PKG005.
    """
    types = trees.get("[Content_Types].xml")
    if types is None:
        return Related(skipped="[Content_Types].xml was missing or could not be parsed")
    document = trees.get(main)
    if document is not None and document.tag == STRICT_DOCUMENT:
        return Related(skipped=f"{main}: {STRICT}")
    if document is None or document.tag != DOCUMENT:
        return Related(skipped=f"{main} was missing, unreadable or not a "
                               "WordprocessingML document")
    defaults = {d.get("Extension", "").lower(): d.get("ContentType") or ""
                for d in types.findall(CT + "Default")}
    exact = {o.get("PartName") for o in types.findall(CT + "Override")}
    overrides: dict[str, list[str]] = {}
    for o in types.findall(CT + "Override"):
        key = unquote((o.get("PartName") or "").lstrip("/")).translate(ASCII_LOWER)
        overrides.setdefault(key, []).append(o.get("ContentType") or "")

    def declared(name: str) -> tuple[str, ...]:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if "/" + name not in exact and ext not in defaults:
            return ()
        return tuple(overrides.get(unquote(name).translate(ASCII_LOWER))
                     or [defaults[ext]])

    main_types = declared(main)
    if [media_type(t) for t in main_types] != [media_type(WORD_MAIN)]:
        return Related(unsupported=(
            f"{main} is declared as {', '.join(main_types) or 'nothing'}; only a "
            "document main part is read, not a template or macro-enabled one"))
    rels_name = relationships_part(main)
    if rels_name not in parts:
        return Related()
    rels = trees.get(rels_name)
    if rels is None:
        return Related(skipped=f"{rels_name} could not be parsed")
    names = set(parts)
    pairs = []
    for rel in rels.findall(REL + "Relationship"):
        kind = rel.get("Type") or ""
        if kind not in RELATED or rel.get("TargetMode") == "External":
            continue
        resolved = _resolve(rel.get("Target") or "", posixpath.dirname(main))
        part = (_existing((resolved, unquote(resolved)), names)
                if resolved is not None else None)
        if part is not None:                 # REL002 reports a missing target
            pairs.append(Pair(rel.get("Id") or "", kind, part, declared(part),
                              RELATED[kind]))
    return Related(tuple(pairs))
