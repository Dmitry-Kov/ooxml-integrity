"""Per-file checked, absent, estimated, skipped and unsupported declarations."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from lxml import etree

from .archive import (
    DEFAULT_ARCHIVE_LIMITS,
    ArchiveLimits,
    package_names,
    read_package,
)
from .finding import Finding
from .fonts import resolve_face
from .pptx_layout import Deck, read_deck
from .xmlutil import fromstring as parse_xml


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
STRICT_WORD = "{http://purl.oclc.org/ooxml/wordprocessingml/main}"
BODY_PARTS = {"word/comments.xml", "word/footnotes.xml", "word/endnotes.xml"}


class CoverageStatus(str, Enum):
    CHECKED = "checked"
    NOT_PRESENT = "not-present"
    ESTIMATED = "estimated"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class CoverageItem:
    id: str
    status: CoverageStatus
    reason: str
    count: int | None = None

    def as_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "id": self.id,
            "status": self.status.value,
            "reason": self.reason,
        }
        if self.count is not None:
            out["count"] = self.count
        return out


@dataclass(frozen=True)
class CoverageReport:
    items: tuple[CoverageItem, ...]

    def summary(self) -> dict[str, int]:
        counts = Counter(item.status.value for item in self.items)
        return {status.value: counts[status.value] for status in CoverageStatus}

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "summary": self.summary(),
            "items": [item.as_dict() for item in self.items],
        }


def _item(identifier: str, status: CoverageStatus, reason: str,
          count: int | None = None) -> CoverageItem:
    return CoverageItem(identifier, status, reason, count)


def _unreadable(reason: str) -> CoverageReport:
    return CoverageReport((
        _item(
            "package.read", CoverageStatus.SKIPPED,
            f"coverage inventory could not read the package: {reason}",
        ),
    ))


def _element_surface(root, tag: str, identifier: str, singular: str,
                     plural: str | None = None) -> CoverageItem:
    if root is None:
        return _item(
            identifier, CoverageStatus.SKIPPED,
            "word/document.xml was missing or could not be safely parsed",
        )
    count = len(list(root.iter(W + tag)))
    if not count:
        return _item(identifier, CoverageStatus.NOT_PRESENT,
                     f"no {plural or singular + 's'} were present", 0)
    label = singular if count == 1 else (plural or singular + "s")
    return _item(identifier, CoverageStatus.CHECKED,
                 f"evaluated {count} {label}", count)


def _combined_surface(document, supporting, tag: str, supporting_tag: str,
                      identifier: str, label: str) -> CoverageItem:
    """Describe checks that consider both references and definitions."""
    if document is None:
        return _item(
            identifier, CoverageStatus.SKIPPED,
            "word/document.xml was missing or could not be safely parsed",
        )
    references = len(list(document.iter(W + tag)))
    definitions = (
        len(list(supporting.iter(W + supporting_tag)))
        if supporting is not None else 0
    )
    count = references + definitions
    if not count:
        return _item(
            identifier, CoverageStatus.NOT_PRESENT,
            f"no {label} references or definitions were present", 0,
        )
    return _item(
        identifier, CoverageStatus.CHECKED,
        f"evaluated {references} reference(s) and {definitions} definition(s)",
        count,
    )


def docx_coverage(path: str | Path, findings: list[Finding], *,
                  source: Path | None = None,
                  limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
                  ) -> CoverageReport:
    """Inventory the DOCX surfaces reached by the current implementation."""
    try:
        parts = read_package(path, limits)
    except Exception as e:
        return _unreadable(str(e))

    trees: dict[str, etree._Element] = {}
    failed_xml: list[str] = []
    xml_names = [name for name in parts if name.endswith((".xml", ".rels"))]
    for name in xml_names:
        try:
            trees[name] = parse_xml(parts[name])
        except Exception:
            failed_xml.append(name)

    items: list[CoverageItem] = [
        _item(
            "package.read", CoverageStatus.CHECKED,
            f"archive budgets passed and {len(parts)} members were loaded",
            len(parts),
        ),
        _item(
            "package.xml",
            CoverageStatus.SKIPPED if failed_xml else CoverageStatus.CHECKED,
            (f"{len(failed_xml)} of {len(xml_names)} XML parts could not be "
             "safely parsed" if failed_xml else
             f"safely parsed {len(xml_names)} XML parts"),
            len(xml_names),
        ),
    ]

    content_types = trees.get("[Content_Types].xml")
    items.append(_item(
        "package.content-types",
        CoverageStatus.CHECKED if content_types is not None
        else CoverageStatus.SKIPPED,
        "content-type coverage was evaluated" if content_types is not None
        else "[Content_Types].xml was missing or could not be parsed",
    ))

    rel_names = [name for name in parts if name.endswith(".rels")]
    bad_rels = [name for name in rel_names if name not in trees]
    root_rels = trees.get("_rels/.rels")
    relationships_ok = root_rels is not None and not bad_rels
    items.append(_item(
        "package.relationships",
        CoverageStatus.CHECKED if relationships_ok else CoverageStatus.SKIPPED,
        (f"evaluated {len(rel_names)} relationship parts" if relationships_ok
         else "the root or another relationship part was missing or malformed"),
        len(rel_names),
    ))

    document = trees.get("word/document.xml")
    style_tree = trees.get("word/styles.xml")
    style_refs = sum(
        len(list(document.iter(W + tag))) for tag in ("pStyle", "rStyle", "tblStyle")
    ) if document is not None else 0
    style_defs = (
        len(list(style_tree.iter(W + "style"))) if style_tree is not None else 0
    )
    if document is None:
        styles = _item(
            "docx.styles", CoverageStatus.SKIPPED,
            "word/document.xml was missing or could not be safely parsed",
        )
    elif not style_refs and not style_defs:
        styles = _item("docx.styles", CoverageStatus.NOT_PRESENT,
                       "no style references or definitions were present", 0)
    elif style_tree is None:
        styles = _item(
            "docx.styles", CoverageStatus.SKIPPED,
            f"{style_refs} style references were present but styles.xml was unavailable",
            style_refs,
        )
    else:
        styles = _item(
            "docx.styles", CoverageStatus.CHECKED,
            f"evaluated {style_refs} reference(s) and {style_defs} definition(s)",
            style_refs + style_defs,
        )
    items.append(styles)

    items.extend((
        _element_surface(document, "numPr", "docx.numbering",
                         "numbered-list property", "numbered-list properties"),
        _combined_surface(
            document, trees.get("word/footnotes.xml"),
            "footnoteReference", "footnote", "docx.footnotes", "footnote",
        ),
        _combined_surface(
            document, trees.get("word/comments.xml"),
            "commentReference", "comment", "docx.comments", "comment",
        ),
    ))

    if document is None:
        revisions = _item(
            "docx.revisions", CoverageStatus.SKIPPED,
            "word/document.xml was missing or could not be safely parsed",
        )
    else:
        revision_count = sum(
            len(list(document.iter(W + tag)))
            for tag in ("ins", "del", "moveFrom", "moveTo")
        )
        revisions = _item(
            "docx.revisions",
            CoverageStatus.CHECKED if revision_count else CoverageStatus.NOT_PRESENT,
            (f"evaluated {revision_count} tracked revisions" if revision_count
             else "no tracked insertions or deletions were present"),
            revision_count,
        )
    items.append(revisions)
    items.extend((
        _element_surface(document, "tbl", "docx.tables", "table"),
        _element_surface(document, "sdt", "docx.content-controls",
                         "content control"),
        _element_surface(document, "t", "docx.text-whitespace", "text run"),
    ))

    story_names = [
        name for name in parts
        if re.match(r"word/(?:header|footer)[^/]*\.xml$", name)
    ]
    items.append(_item(
        "docx.header-footer-semantics",
        CoverageStatus.UNSUPPORTED if story_names else CoverageStatus.NOT_PRESENT,
        ("header/footer XML and relationships were checked, but their Word "
         "semantics and layout were not" if story_names else
         "no header or footer parts were present"),
        len(story_names),
    ))

    media = [
        name for name in parts
        if name.startswith(("word/media/", "word/embeddings/"))
    ]
    items.append(_item(
        "docx.media-content",
        CoverageStatus.UNSUPPORTED if media else CoverageStatus.NOT_PRESENT,
        ("relationships to media were checked, but media bytes and rendering "
         "were not" if media else "no Word media or embedded-object parts were present"),
        len(media),
    ))

    strict = document is not None and document.tag.startswith(STRICT_WORD)
    items.append(_item(
        "docx.strict-wordprocessingml",
        CoverageStatus.UNSUPPORTED if strict else CoverageStatus.NOT_PRESENT,
        ("Strict WordprocessingML namespaces are outside the current rules"
         if strict else "Strict WordprocessingML was not encountered"),
        1 if strict else 0,
    ))

    comparison_failure = next((f for f in findings if f.code == "FID000"), None)
    if source is None:
        fidelity_status = CoverageStatus.SKIPPED
        fidelity_reason = "source comparison was not requested"
        source_names: list[str] = []
    elif comparison_failure is not None:
        fidelity_status = CoverageStatus.SKIPPED
        fidelity_reason = comparison_failure.message
        source_names = []
    else:
        fidelity_status = CoverageStatus.CHECKED
        fidelity_reason = "source and edited main-story fidelity was compared"
        try:
            source_names = package_names(source, limits)
        except Exception:
            source_names = []

    items.append(_item(
        "docx.fidelity.main-story", fidelity_status, fidelity_reason,
    ))
    if fidelity_status is CoverageStatus.CHECKED:
        note_parts = BODY_PARTS.intersection(parts).union(
            BODY_PARTS.intersection(source_names)
        )
        items.append(_item(
            "docx.fidelity.note-bodies",
            CoverageStatus.CHECKED if note_parts else CoverageStatus.NOT_PRESENT,
            ("comment, footnote and endnote bodies were compared as multisets"
             if note_parts else "neither file contained note-body parts"),
            len(note_parts),
        ))
        source_stories = [
            name for name in source_names
            if re.match(r"word/(?:header|footer)[^/]*\.xml$", name)
        ]
        all_stories = set(story_names).union(source_stories)
        items.append(_item(
            "docx.fidelity.headers-footers",
            CoverageStatus.UNSUPPORTED if all_stories else CoverageStatus.NOT_PRESENT,
            ("header/footer fidelity is not implemented" if all_stories
             else "neither file contained header or footer stories"),
            len(all_stories),
        ))
    else:
        items.extend((
            _item("docx.fidelity.note-bodies", fidelity_status, fidelity_reason),
            _item("docx.fidelity.headers-footers", fidelity_status, fidelity_reason),
        ))

    return CoverageReport(tuple(items))


def _font_coverage(deck: Deck, findings: list[Finding]) -> CoverageItem:
    eligible = [
        shape for shape in deck.shapes
        if shape.has_text and not shape.vertical_text
    ]
    if not eligible:
        return _item(
            "pptx.font-metrics", CoverageStatus.NOT_PRESENT,
            "no supported text runs required font metrics", 0,
        )
    unavailable = [finding for finding in findings if finding.code == "PPT000"]
    if unavailable:
        return _item(
            "pptx.font-metrics", CoverageStatus.SKIPPED,
            unavailable[0].message, len(unavailable),
        )

    requests = {
        (run.font, run.bold, run.italic)
        for shape in eligible for para in shape.paragraphs for run in para.runs
        if run.text.strip()
    }
    matches: Counter[str] = Counter()
    try:
        for family, bold, italic in requests:
            matches[resolve_face(family, bold, italic).match] += 1
    except Exception as e:
        return _item(
            "pptx.font-metrics", CoverageStatus.SKIPPED,
            f"font metrics could not be resolved: {e}",
        )
    if not matches:
        return _item(
            "pptx.font-metrics", CoverageStatus.NOT_PRESENT,
            "no ordinary text runs required font metrics", 0,
        )
    detail = ", ".join(f"{key}={value}" for key, value in sorted(matches.items()))
    if any(key != "exact" for key in matches):
        return _item(
            "pptx.font-metrics", CoverageStatus.ESTIMATED,
            f"font substitution reduced confidence ({detail})", sum(matches.values()),
        )
    return _item(
        "pptx.font-metrics", CoverageStatus.CHECKED,
        f"all requested font faces were exact ({detail})", sum(matches.values()),
    )


def _feature(deck: Deck, key: str, identifier: str, label: str) -> CoverageItem:
    count = deck.features.get(key, 0)
    return _item(
        identifier,
        CoverageStatus.UNSUPPORTED if count else CoverageStatus.NOT_PRESENT,
        (f"{count} {label} were encountered but are outside the layout model"
         if count else f"no {label} were present"),
        count,
    )


def pptx_coverage(path: str | Path, findings: list[Finding], *,
                  source: Path | None = None,
                  limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
                  ) -> CoverageReport:
    """Inventory supported and recognised-unsupported PPTX surfaces."""
    try:
        deck = read_deck(path, limits=limits)
    except Exception as e:
        return _unreadable(str(e))

    features = deck.features
    items: list[CoverageItem] = [
        _item(
            "package.read", CoverageStatus.CHECKED,
            f"archive budgets passed and {features.get('entries', 0)} members were loaded",
            features.get("entries", 0),
        ),
        _item(
            "pptx.package-integrity", CoverageStatus.UNSUPPORTED,
            "only relationships needed for layout were followed; the complete PPTX "
            "OPC graph and XML set were not validated",
        ),
    ]

    order_count = features.get("presentation_order_entries", 0)
    items.append(_item(
        "pptx.slide-order",
        CoverageStatus.UNSUPPORTED if order_count else CoverageStatus.SKIPPED,
        ("presentation.xml slide order was present, but slides were read by part "
         "number" if order_count else "presentation.xml had no readable slide order"),
        order_count,
    ))

    font_item = _font_coverage(deck, findings)
    items.append(font_item)
    eligible_text = [
        shape for shape in deck.shapes
        if shape.has_text and not shape.vertical_text
    ]
    unread = features.get("unread_text_shapes", 0)
    vertical = features.get("vertical_text_shapes", 0)
    if vertical and not eligible_text and not unread:
        overflow_status = CoverageStatus.UNSUPPORTED
        overflow_reason = (
            f"{vertical} vertical-text shapes were outside the layout model"
        )
    elif not eligible_text and not unread:
        overflow_status = CoverageStatus.NOT_PRESENT
        overflow_reason = "no supported plain text shapes were present"
    elif unread:
        overflow_status = CoverageStatus.SKIPPED
        overflow_reason = f"{unread} text shapes had no usable geometry"
    else:
        overflow_status = font_item.status
        overflow_reason = (
            "text overflow was evaluated with the reported font confidence"
            if font_item.status in (CoverageStatus.CHECKED, CoverageStatus.ESTIMATED)
            else font_item.reason
        )
    items.append(_item(
        "pptx.text-overflow", overflow_status, overflow_reason,
        len(eligible_text),
    ))

    items.append(_item(
        "pptx.off-slide-geometry",
        CoverageStatus.CHECKED if deck.shapes else CoverageStatus.NOT_PRESENT,
        (f"evaluated {len(deck.shapes)} ungrouped shape rectangles" if deck.shapes
         else "no supported shape rectangles were present"),
        len(deck.shapes),
    ))
    overlap_shapes = [
        shape for shape in deck.shapes
        if shape.has_text and not shape.rotation
    ]
    items.append(_item(
        "pptx.text-shape-overlap",
        CoverageStatus.CHECKED if len(overlap_shapes) >= 2
        else CoverageStatus.NOT_PRESENT,
        (f"evaluated {len(overlap_shapes)} unrotated text shapes"
         if len(overlap_shapes) >= 2 else
         "fewer than two supported unrotated text shapes were present"),
        len(overlap_shapes),
    ))

    items.extend((
        _feature(deck, "grouped_shapes", "pptx.grouped-shapes", "shape groups"),
        _feature(deck, "tables", "pptx.tables", "PowerPoint tables"),
        _feature(deck, "smartart", "pptx.smartart", "SmartArt graphics"),
        _feature(deck, "charts", "pptx.charts", "charts"),
        _feature(deck, "fields", "pptx.fields", "DrawingML fields"),
        _feature(deck, "rotated_shapes", "pptx.rotated-bounds", "rotated shapes"),
        _feature(deck, "vertical_text_shapes", "pptx.vertical-text",
                 "vertical-text shapes"),
        _feature(deck, "master_layout_text_shapes", "pptx.master-layout-objects",
                 "text objects defined only on masters or layouts"),
    ))

    items.append(_item(
        "pptx.fidelity.source",
        CoverageStatus.UNSUPPORTED if source is not None else CoverageStatus.SKIPPED,
        ("PPTX source comparison is not implemented" if source is not None
         else "source comparison was not requested"),
    ))
    return CoverageReport(tuple(items))


def coverage_for(path: str | Path, findings: list[Finding], *,
                 source: Path | None = None,
                 limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
                 ) -> CoverageReport:
    suffix = Path(path).suffix.lower()
    if suffix in (".pptx", ".potx", ".ppsx"):
        return pptx_coverage(path, findings, source=source, limits=limits)
    return docx_coverage(path, findings, source=source, limits=limits)
