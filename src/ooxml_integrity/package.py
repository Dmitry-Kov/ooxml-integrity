"""Single-pass cached OOXML package shared across check, compare and coverage.

Reading a ZIP archive and parsing every XML part once eliminates redundant I/O
and XML parsing across `check()`, `compare()`, `coverage_for()` and
`introduced()`, and prevents TOCTOU drift between those stages.

`LoadedPackage.open()` accepts filesystem paths, raw `bytes`/`bytearray`/
`memoryview`, or seekable binary streams (`io.BytesIO`, uploaded file objects),
applying the exact same `ArchiveLimits` preflight and safe XML parser to all of
them. Binary media/embedded members are stream-verified for ZIP integrity and
resource budgets without retaining their raw bytes in memory unless
`include_media=True` is requested.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from lxml import etree

from .archive import (
    DEFAULT_ARCHIVE_LIMITS,
    ArchiveLimits,
    PackageSource,
    read_package_for_loaded,
)
from .comments import comment_part, main_part, story_parts
from .paths import DECK_SUFFIXES
from .xmlutil import (
    UnsafeXML,
    fromstring as parse_xml,
    parser_limit,
    split_fallback,
)

_PRESENTATION_ROOTS = frozenset({
    "{http://schemas.openxmlformats.org/presentationml/2006/main}presentation",
    "{http://purl.oclc.org/ooxml/presentationml/main}presentation",
})


def _default_label(source: PackageSource) -> str:
    if isinstance(source, (str, Path)):
        return str(source)
    if isinstance(source, (bytes, bytearray, memoryview)):
        return "<bytes>"
    name = getattr(source, "name", None)
    return str(name) if isinstance(name, (str, Path)) and str(name) else "<stream>"


def _extra_word_parts(names: set[str], parts: dict[str, bytes]) -> Iterable[str]:
    """Story/comment targets that may not use a `.xml` filename extension."""
    main = main_part(parts, names=names)
    wanted: list[str] = [main]
    wanted.extend(story_parts(parts, main, names=names))
    try:
        cm = comment_part(parts, names=names, main=main)
    except (ValueError, etree.XMLSyntaxError):
        cm = None
    if cm is not None:
        wanted.append(cm)
    return wanted


@dataclass
class LoadedPackage:
    """One validated OOXML archive with its SHA-256 digest and cached XML trees.

    `names` contains every member name in the archive (including binary media).
    `parts` holds the retained member bytes (all XML, `.rels`, story and comment
    parts by default; all members when opened with `include_media=True`).
    Cached trees in `trees` are read-only for callers; use `split_tree()` to
    obtain `(primary, fallback)` views without mutating the shared tree.
    """

    label: str
    sha256: str
    limits: ArchiveLimits
    names: tuple[str, ...]
    parts: dict[str, bytes]
    main: str
    stories: tuple[str, ...]
    trees: dict[str, etree._Element]
    xml_errors: dict[str, str]
    path: Path | None = None
    _split_cache: dict[str, tuple[etree._Element, etree._Element | None]] = field(
        default_factory=dict, repr=False,
    )

    @classmethod
    def open(
        cls,
        source: PackageSource | LoadedPackage,
        *,
        limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
        label: str | None = None,
        include_media: bool = False,
    ) -> LoadedPackage:
        """Open and parse an OOXML package once under `limits`."""
        if isinstance(source, LoadedPackage):
            if not include_media or len(source.parts) == len(source.names):
                return source
            if source.path is not None:
                source = source.path
            else:
                return source
        names, parts, digest = read_package_for_loaded(
            source, limits, include_media=include_media,
            extra_members=_extra_word_parts,
        )
        name_set = set(names)
        main = main_part(parts, names=name_set)
        stories = tuple(story_parts(parts, main, names=name_set))
        story_set = set(stories)
        try:
            cm = comment_part(parts, names=name_set, main=main)
        except (ValueError, etree.XMLSyntaxError):
            cm = None
        if cm is not None:
            story_set.add(cm)
        trees: dict[str, etree._Element] = {}
        xml_errors: dict[str, str] = {}
        for name, data in parts.items():
            if name.endswith((".xml", ".rels")) or name in story_set:
                try:
                    trees[name] = parse_xml(data)
                except UnsafeXML as e:
                    xml_errors[name] = f"XML could not be safely parsed: {e}"
                except etree.XMLSyntaxError as e:
                    limit = parser_limit(e)
                    xml_errors[name] = (
                        f"XML could not be safely parsed: {limit}"
                        if limit else f"XML is not well-formed: {e}"
                    )
        resolved_path = Path(source) if isinstance(source, (str, Path)) else None
        return cls(
            label=label if label is not None else _default_label(source),
            sha256=digest,
            limits=limits,
            names=names,
            parts=parts,
            main=main,
            stories=stories,
            trees=trees,
            xml_errors=xml_errors,
            path=resolved_path,
        )

    def tree(self, name: str) -> etree._Element | None:
        """Return the cached immutable XML root for `name`, or None."""
        return self.trees.get(name)

    def split_tree(
        self, name: str,
    ) -> tuple[etree._Element | None, etree._Element | None]:
        """Return cached ``(primary, fallback)`` trees for `name` without mutating `trees`."""
        cached = self._split_cache.get(name)
        if cached is not None:
            return cached
        root = self.trees.get(name)
        if root is None:
            return None, None
        result = split_fallback(root)
        self._split_cache[name] = result
        return result

    @property
    def is_deck(self) -> bool:
        """True if this package is a PowerPoint deck (by suffix or presentation root)."""
        if self.path is not None and self.path.suffix.lower() in DECK_SUFFIXES:
            return True
        main_tree = self.trees.get(self.main)
        if main_tree is not None and main_tree.tag in _PRESENTATION_ROOTS:
            return True
        pres = self.trees.get("ppt/presentation.xml")
        return pres is not None and pres.tag in _PRESENTATION_ROOTS
