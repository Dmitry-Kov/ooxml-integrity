"""
Resolving what a .pptx run is actually formatted as, and laying out its text.

This is the part python-pptx has declined to implement for a decade (issues
#69, #715, #973, #982, #1021): text autofit and overflow need text measurement,
and text measurement needs the *effective* font size, which is almost never
written on the run itself.

The inheritance chain, longest to shortest precedence:

    a:rPr/@sz on the run
    a:pPr/a:defRPr/@sz on the paragraph
    a:lstStyle/a:lvl{N}pPr/a:defRPr on the shape's own txBody
    the layout placeholder's lstStyle, matched by idx then by type
    the master placeholder's lstStyle
    the master's p:txStyles - titleStyle / bodyStyle / otherStyle at level N
    p:defaultTextStyle on the presentation
    PowerPoint's built-in default (18pt)

Font family goes through the same chain but ends at the theme: `+mn-lt` means
"minor latin", `+mj-lt` "major latin", both defined in the theme's fontScheme.
Bold and italic are resolved independently through the same chain. Explicit
false overrides inherited true; only still-unset flags default to false.

Everything here is geometry and table lookups. No rendering.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from lxml import etree

from .archive import DEFAULT_ARCHIVE_LIMITS, ArchiveLimits, PackageIssue, read_package
from .fonts import EMU_PER_POINT, Metrics, load_metrics
from .xmlutil import fromstring as parse_xml

#: split on whitespace but keep it, so word boundaries survive
_WORD_TOKENS = re.compile(r"(\n|[^\S\n]+)")

# Character wrapping is calibrated for basic Latin letters/digits, not Unicode
# line breaking or grapheme shaping. Do not split combining sequences or URLs
# with an invented punctuation/hyphenation policy.
_LATIN_TOKEN = re.compile(r"[A-Za-z0-9]+\Z")
EMERGENCY_WRAP_TOLERANCE = 0.05

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"

_a = lambda t: f"{{{A}}}{t}"
_p = lambda t: f"{{{P}}}{t}"

#: PowerPoint's defaults when nothing in the chain says otherwise.
DEFAULT_SIZE_PT = 18.0
DEFAULT_INSETS_EMU = (91440, 45720, 91440, 45720)   # l, t, r, b
DEFAULT_SLIDE_W, DEFAULT_SLIDE_H = 9144000, 6858000

#: Single line spacing in DrawingML is a flat multiple of the font size, NOT
#: the font's own vertical metrics.
#:
#: This was established by measurement, not read from the spec. Rendering the
#: same string in Calibri, Arial, Times New Roman, Courier New, Cambria and
#: Verdana at 12pt and 20pt gives a baseline-to-baseline pitch of exactly
#: 1.2000 x size in every case, while those faces' own metrics range from
#: 0.80 to 1.22. Deriving line height from ascender + descender + lineGap - the
#: right approach for Word body text - is wrong here, and was giving a
#: consistent +1.7% error on Carlito before this was measured.
#:
#: Font metrics are still used for advance widths, which is what line breaking
#: depends on.
DRAWINGML_LINE_SPACING = 1.2


# --------------------------------------------------------------------- models
@dataclass
class Run:
    text: str
    size_pt: float
    font: str
    bold: bool
    italic: bool


@dataclass
class Paragraph:
    runs: list[Run]
    level: int = 0
    line_spacing: float = 1.0        # multiple of single spacing
    line_spacing_pt: float = 0.0     # exact spacing, when spcPts is used
    space_before_pt: float = 0.0
    space_after_pt: float = 0.0
    bullet_indent_emu: int = 0
    latin_line_break: bool = False

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class Shape:
    name: str
    slide: int
    left: int
    top: int
    width: int
    height: int
    rotation: float = 0.0
    paragraphs: list[Paragraph] = field(default_factory=list)
    insets: tuple[int, int, int, int] = DEFAULT_INSETS_EMU
    wrap: bool = True
    autofit: str = "none"            # none | normAutofit | spAutoFit
    font_scale: float = 1.0          # normAutofit's stored shrink
    line_space_reduction: float = 0.0
    anchor: str = "t"
    is_placeholder: bool = False
    placeholder_type: str = ""
    vertical_text: bool = False

    @property
    def has_text(self) -> bool:
        return any(p.text.strip() for p in self.paragraphs)

    @property
    def usable_width_emu(self) -> int:
        return max(0, self.width - self.insets[0] - self.insets[2])

    @property
    def usable_height_emu(self) -> int:
        return max(0, self.height - self.insets[1] - self.insets[3])

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@dataclass
class Deck:
    path: Path
    slide_width: int
    slide_height: int
    shapes: list[Shape]
    theme_fonts: dict[str, str]
    features: dict[str, int] = field(default_factory=dict)
    #: Themes actually used to resolve text, indexed by presentation position.
    slide_theme_fonts: dict[int, dict[str, str]] = field(default_factory=dict)


# ---------------------------------------------------------------- xml helpers
def _pct(el, attr="val", default=None):
    if el is None:
        return default
    v = el.get(attr)
    return None if v is None else int(v) / 100000.0


def _int(el, attr, default=None):
    if el is None:
        return default
    v = el.get(attr)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _bool(el, attr, default=False):
    if el is None:
        return default
    v = el.get(attr)
    if v is None:
        return default
    return v in ("1", "true", "on")


class _Package:
    """Zip plus relationship resolution, so parts can be followed by rId."""

    def __init__(self, path: str | Path,
                 limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS):
        self.path = Path(path)
        self.parts = read_package(self.path, limits)
        self._trees: dict[str, etree._Element | None] = {}

    def tree(self, name: str):
        if name not in self._trees:
            data = self.parts.get(name)
            try:
                self._trees[name] = parse_xml(data) if data else None
            except etree.XMLSyntaxError:
                self._trees[name] = None
        return self._trees[name]

    def rels(self, part: str) -> dict[str, str]:
        d, _, base = part.rpartition("/")
        relname = f"{d}/_rels/{base}.rels" if d else f"_rels/{base}.rels"
        t = self.tree(relname)
        out: dict[str, str] = {}
        if t is None:
            return out
        for rel in t.findall(f"{{{REL}}}Relationship"):
            if rel.get("TargetMode") == "External":
                continue
            target = rel.get("Target") or ""
            # Bounded normalization also handles package-absolute paths.
            # Repeated regex stripping could loop on targets above the root.
            uri = urlsplit(target)
            if uri.scheme or uri.netloc or "\\" in target:
                continue
            joined = uri.path.lstrip("/") if uri.path.startswith("/") else posixpath.join(d, uri.path)
            resolved = posixpath.normpath(joined)
            if resolved == ".." or resolved.startswith("../"):
                continue
            decoded = unquote(resolved)
            out[rel.get("Id")] = resolved if resolved in self.parts else decoded
        return out

    def required_related(self, part: str, rel_suffix: str, root_tag: str) -> str:
        """Resolve one dependency without borrowing a different owner's part."""
        d, _, base = part.rpartition("/")
        relname = f"{d}/_rels/{base}.rels" if d else f"_rels/{base}.rels"
        t = self.tree(relname)

        def invalid(reason):
            raise PackageIssue("PKG002", f"cannot resolve theme dependency {rel_suffix} "
                               f"from {part}: {reason}", part=relname)

        if t is None or t.tag != f"{{{REL}}}Relationships":
            invalid("missing or unreadable relationships")
        matches = [r for r in t.findall(f"{{{REL}}}Relationship")
                   if r.get("Type") == R + rel_suffix]
        if len(matches) != 1:
            invalid("expected one internal relationship")
        rel = matches[0]
        rid = rel.get("Id")
        if not rid or sum(r.get("Id") == rid for r in t) != 1:
            invalid("missing or ambiguous relationship id")
        target = rel.get("Target", "")
        uri = urlsplit(target)
        if (rel.get("TargetMode", "Internal") != "Internal" or not uri.path
                or uri.scheme or uri.netloc or uri.query or uri.fragment
                or "\\" in target or any(ord(c) < 32 for c in target)):
            invalid("invalid or external target")
        resolved = self.rels(part).get(rid)
        tree = self.tree(resolved) if resolved else None
        if tree is None or tree.tag != root_tag:
            invalid("missing, unreadable or unsupported target root")
        return resolved

    def has_relationship(self, part: str, rel_suffix: str) -> bool:
        d, _, base = part.rpartition("/")
        t = self.tree(f"{d}/_rels/{base}.rels" if d else f"_rels/{base}.rels")
        return t is not None and any(r.get("Type") == R + rel_suffix
                                    for r in t.findall(f"{{{REL}}}Relationship"))

    def related(self, part: str, rel_suffix: str) -> str | None:
        d, _, base = part.rpartition("/")
        relname = f"{d}/_rels/{base}.rels" if d else f"_rels/{base}.rels"
        t = self.tree(relname)
        if t is None:
            return None
        for rel in t.findall(f"{{{REL}}}Relationship"):
            if (rel.get("Type") or "").endswith(rel_suffix):
                return self.rels(part).get(rel.get("Id"))
        return None


# --------------------------------------------------------------- the resolver
class DeckReader:
    """Reads a deck into Shape objects with every property resolved."""

    def __init__(self, path: str | Path,
                 limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS):
        self.pkg = _Package(path, limits)
        self.path = Path(path)
        pres = self.pkg.tree("ppt/presentation.xml")
        if pres is None or pres.tag != _p("presentation"):
            raise PackageIssue(
                "PKG002", "missing, unreadable or unsupported presentation root; "
                "slide order could not be read", part="ppt/presentation.xml")
        self.presentation = pres
        sz = pres.find(_p("sldSz")) if pres is not None else None
        self.slide_w = _int(sz, "cx", DEFAULT_SLIDE_W)
        self.slide_h = _int(sz, "cy", DEFAULT_SLIDE_H)
        self.pres_default_style = (
            pres.find(_p("defaultTextStyle")) if pres is not None else None
        )
        self._slide_themes: dict[str, dict[str, str]] = {}
        self._theme_parts: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------ theme
    def _theme_fonts(self, slide_part: str) -> dict[str, str]:
        """Resolve the owning master's Latin theme only when a run needs it."""
        if slide_part in self._slide_themes:
            return self._slide_themes[slide_part]
        layout = self.pkg.required_related(slide_part, "/slideLayout", _p("sldLayout"))
        master = self.pkg.required_related(layout, "/slideMaster", _p("sldMaster"))
        theme = self.pkg.required_related(master, "/theme", _a("theme"))
        for owner in (layout, slide_part):
            if self.pkg.has_relationship(owner, "/themeOverride"):
                override = self.pkg.required_related(owner, "/themeOverride", _a("themeOverride"))
                if self.pkg.tree(override).find(_a("fontScheme")) is not None:
                    raise PackageIssue(
                        "PKG002", "themeOverride font schemes are outside the supported "
                        "master-theme model; themed text was NOT measured", part=override)
        if theme not in self._theme_parts:
            out: dict[str, str] = {}
            scheme = self.pkg.tree(theme).find(f'{_a("themeElements")}/{_a("fontScheme")}')
            if scheme is not None:
                for key, tag in (("major", "majorFont"), ("minor", "minorFont")):
                    latin = scheme.find(f'{_a(tag)}/{_a("latin")}')
                    name = latin.get("typeface", "").strip() if latin is not None else ""
                    if name and not name.startswith("+"):
                        out[key] = name
            self._theme_parts[theme] = out
        self._slide_themes[slide_part] = self._theme_parts[theme]
        return self._slide_themes[slide_part]

    def _resolve_typeface(self, name: str | None, slide_part: str) -> str:
        if name and name not in ("+mn-lt", "+mn-ea", "+mn-cs", "+mj-lt", "+mj-ea", "+mj-cs"):
            return name  # an explicit font does not depend on a theme
        key = "major" if name and name.startswith("+mj-") else "minor"
        fonts = self._theme_fonts(slide_part)
        if key not in fonts:
            raise PackageIssue("PKG002", f"cannot resolve {key} Latin theme font for "
                               f"{slide_part}; text was NOT measured", part=slide_part)
        return fonts[key]

    # ------------------------------------------------------- style hierarchy
    @staticmethod
    def _lvl_props(lst_style, level: int):
        """a:lvl{N}pPr from an a:lstStyle, N being 1-based."""
        if lst_style is None:
            return None
        return lst_style.find(_a(f"lvl{level + 1}pPr"))

    def _placeholder_chain(self, slide_part: str, ph_idx, ph_type: str):
        """lstStyle sources from the layout and master, in precedence order."""
        chain = []
        layout = self.pkg.related(slide_part, "/slideLayout")
        master = self.pkg.related(layout, "/slideMaster") if layout else None

        for part in (layout, master):
            if not part:
                continue
            t = self.pkg.tree(part)
            if t is None:
                continue
            for sp in t.iter(_p("sp")):
                nv = sp.find(f'{_p("nvSpPr")}/{_p("nvPr")}/{_p("ph")}')
                if nv is None:
                    continue
                if ph_idx is not None and nv.get("idx") == str(ph_idx):
                    chain.append(sp.find(f'{_p("txBody")}/{_a("lstStyle")}'))
                elif ph_type and (nv.get("type") or "body") == ph_type:
                    chain.append(sp.find(f'{_p("txBody")}/{_a("lstStyle")}'))

        # the master's global text styles for this placeholder class
        if master:
            mt = self.pkg.tree(master)
            styles = mt.find(_p("txStyles")) if mt is not None else None
            if styles is not None:
                which = {"title": "titleStyle", "ctrTitle": "titleStyle",
                         "subTitle": "bodyStyle", "body": "bodyStyle"}.get(
                             ph_type, "otherStyle")
                chain.append(styles.find(_p(which)))
        chain.append(self.pres_default_style)
        return [c for c in chain if c is not None]

    def _effective_run_props(self, rpr, ppr, txbody_lst, style_chain, level: int,
                             slide_part: str):
        """Walk the chain for size, family, bold, italic - first hit per property wins."""
        candidates = []
        if rpr is not None:
            candidates.append(rpr)
        if ppr is not None:
            candidates.append(ppr.find(_a("defRPr")))
        for src in [txbody_lst, *style_chain]:
            lvl = self._lvl_props(src, level)
            if lvl is not None:
                candidates.append(lvl.find(_a("defRPr")))
        candidates = [c for c in candidates if c is not None]

        size_pt = None
        typeface = None
        bold = italic = None
        for c in candidates:
            if size_pt is None and c.get("sz"):
                size_pt = int(c.get("sz")) / 100.0
            if bold is None and c.get("b") is not None:
                bold = c.get("b") in ("1", "true")
            if italic is None and c.get("i") is not None:
                italic = c.get("i") in ("1", "true")
            if typeface is None:
                latin = c.find(_a("latin"))
                if latin is not None and latin.get("typeface"):
                    typeface = latin.get("typeface")
            # Size and family can be explicit while style flags are inherited.
            # False is a resolved override, distinct from an unset flag.
            if (size_pt is not None and typeface is not None
                    and bold is not None and italic is not None):
                break
        return (
            size_pt if size_pt is not None else DEFAULT_SIZE_PT,
            self._resolve_typeface(typeface, slide_part),
            bool(bold), bool(italic),
        )

    def _paragraph_spacing(self, ppr, txbody_lst, style_chain, level: int):
        """lnSpc / spcBef / spcAft, following the same chain."""
        sources = [ppr]
        for src in [txbody_lst, *style_chain]:
            sources.append(self._lvl_props(src, level))
        sources = [s for s in sources if s is not None]

        mult, exact, before, after = None, None, None, None
        for s in sources:
            if mult is None and exact is None:
                ln = s.find(_a("lnSpc"))
                if ln is not None:
                    pct = _pct(ln.find(_a("spcPct")))
                    pts = _int(ln.find(_a("spcPts")), "val")
                    if pct is not None:
                        mult = pct
                    elif pts is not None:
                        exact = pts / 100.0
            if before is None:
                b = s.find(_a("spcBef"))
                if b is not None:
                    pts = _int(b.find(_a("spcPts")), "val")
                    if pts is not None:
                        before = pts / 100.0
            if after is None:
                a_ = s.find(_a("spcAft"))
                if a_ is not None:
                    pts = _int(a_.find(_a("spcPts")), "val")
                    if pts is not None:
                        after = pts / 100.0
        return (mult if mult is not None else 1.0,
                exact or 0.0, before or 0.0, after or 0.0)

    # ------------------------------------------------------------------ shapes
    def _shape_geometry(self, sp, slide_part, ph_idx, ph_type):
        """a:xfrm on the shape, or inherited from the layout placeholder."""
        xfrm = sp.find(f'{_p("spPr")}/{_a("xfrm")}')
        if xfrm is None:
            layout = self.pkg.related(slide_part, "/slideLayout")
            t = self.pkg.tree(layout) if layout else None
            if t is not None:
                for lsp in t.iter(_p("sp")):
                    nv = lsp.find(f'{_p("nvSpPr")}/{_p("nvPr")}/{_p("ph")}')
                    if nv is None:
                        continue
                    same = (ph_idx is not None and nv.get("idx") == str(ph_idx)) or \
                           (ph_type and (nv.get("type") or "body") == ph_type)
                    if same:
                        xfrm = lsp.find(f'{_p("spPr")}/{_a("xfrm")}')
                        if xfrm is not None:
                            break
        if xfrm is None:
            return None
        off, ext = xfrm.find(_a("off")), xfrm.find(_a("ext"))
        if off is None or ext is None:
            return None
        rot = _int(xfrm, "rot", 0) / 60000.0
        return (_int(off, "x", 0), _int(off, "y", 0),
                _int(ext, "cx", 0), _int(ext, "cy", 0), rot)

    def _body_properties(self, txbody):
        bodypr = txbody.find(_a("bodyPr")) if txbody is not None else None
        insets = tuple(
            _int(bodypr, k, d) for k, d in
            zip(("lIns", "tIns", "rIns", "bIns"), DEFAULT_INSETS_EMU)
        )
        wrap = True
        autofit, scale, reduction = "none", 1.0, 0.0
        anchor = "t"
        vertical_text = False
        if bodypr is not None:
            wrap = (bodypr.get("wrap") or "square") != "none"
            anchor = bodypr.get("anchor") or "t"
            text_rotation = _int(bodypr, "rot", 0) or 0
            vertical_text = (
                (bodypr.get("vert") or "horz") != "horz"
                or text_rotation % (180 * 60000) != 0
            )
            if bodypr.find(_a("normAutofit")) is not None:
                na = bodypr.find(_a("normAutofit"))
                autofit = "normAutofit"
                scale = _pct(na, "fontScale", 1.0) or 1.0
                reduction = _pct(na, "lnSpcReduction", 0.0) or 0.0
            elif bodypr.find(_a("spAutoFit")) is not None:
                autofit = "spAutoFit"
        return insets, wrap, autofit, scale, reduction, anchor, vertical_text

    def _slide_parts(self) -> list[str]:
        """Follow the main slide list, never ZIP order or slide filenames.

        Validate every referenced slide before producing any geometry. A
        broken entry must not disappear and renumber all subsequent findings.
        Unlisted parts and custom-show sequences are not the main slide list.
        """
        pres_part = "ppt/presentation.xml"
        rel_part = "ppt/_rels/presentation.xml.rels"

        def invalid(message: str, part: str = pres_part):
            raise PackageIssue("PKG002", "cannot resolve presentation slide order: "
                               + message, part=part)

        lists = self.presentation.findall(_p("sldIdLst"))
        if len(lists) > 1:
            invalid("multiple slide lists")
        if not lists:
            return []  # the optional list is absent in a zero-slide deck
        entries = [child for child in lists[0] if isinstance(child.tag, str)]
        if not entries:
            return []
        rels = self.pkg.tree(rel_part)
        if rels is None or rels.tag != f"{{{REL}}}Relationships":
            invalid("missing or unreadable presentation relationships", rel_part)
        by_id: dict[str, list[etree._Element]] = {}
        for rel in rels.findall(f"{{{REL}}}Relationship"):
            by_id.setdefault(rel.get("Id", ""), []).append(rel)

        result: list[str] = []
        seen_ids: set[int] = set()
        seen_parts: set[str] = set()
        for number, entry in enumerate(entries, 1):
            if entry.tag != _p("sldId"):
                invalid(f"unrecognised slide-list entry at position {number}")
            raw_id = entry.get("id", "")
            if not raw_id.isdecimal():
                invalid(f"missing or invalid slide id at position {number}")
            slide_id = int(raw_id)
            if slide_id in seen_ids:
                invalid(f"duplicate slide id {slide_id}")
            seen_ids.add(slide_id)
            rid = entry.get(f"{{{R}}}id", "")
            matches = by_id.get(rid, []) if rid else []
            if len(matches) != 1:
                invalid(f"slide {number} relationship {rid!r} is missing or ambiguous", rel_part)
            rel = matches[0]
            if rel.get("Type") != R + "/slide":
                invalid(f"slide {number} relationship {rid!r} is not a slide", rel_part)
            if rel.get("TargetMode", "Internal") != "Internal":
                invalid(f"slide {number} relationship {rid!r} is not internal", rel_part)
            target = rel.get("Target", "")
            uri = urlsplit(target)
            if (not uri.path or uri.scheme or uri.netloc or uri.query or uri.fragment
                    or "\\" in target or any(ord(c) < 32 for c in target)):
                invalid(f"slide {number} has an invalid internal target {target!r}", rel_part)
            joined = uri.path.lstrip("/") if uri.path.startswith("/") else "ppt/" + uri.path
            resolved = posixpath.normpath(joined)
            if resolved == ".." or resolved.startswith("../"):
                invalid(f"slide {number} target escapes the package", rel_part)
            # A relationship URI may encode a space/non-ASCII character that
            # the ZIP member spells literally. Archive preflight disallows
            # ambiguous encoded/decoded member aliases and traversal names.
            decoded = unquote(resolved, errors="strict")
            part = next((p for p in (resolved, decoded) if p in self.pkg.parts), None)
            if part is None:
                invalid(f"slide {number} target {target!r} is missing", rel_part)
            if part in seen_parts:
                invalid(f"slide part {part!r} is listed more than once")
            seen_parts.add(part)
            tree = self.pkg.tree(part)
            if tree is None or tree.tag != _p("sld"):
                invalid(f"slide {number} has an unreadable or unsupported slide root", part)
            result.append(part)
        return result

    def read(self) -> Deck:
        slide_parts = self._slide_parts()
        shapes: list[Shape] = []
        features = {
            "entries": len(self.pkg.parts),
            "slides": len(slide_parts),
            "presentation_order_entries": len(slide_parts),
            "plain_text_shapes": 0,
            "unread_text_shapes": 0,
            "grouped_shapes": 0,
            "grouped_text_shapes": 0,
            "tables": 0,
            "smartart": 0,
            "charts": 0,
            "fields": 0,
            "vertical_text_shapes": 0,
            "rotated_shapes": 0,
            "master_layout_text_shapes": 0,
        }

        for name in self.pkg.parts:
            if not name.startswith(("ppt/slideLayouts/", "ppt/slideMasters/")):
                continue
            tree = self.pkg.tree(name)
            if tree is None:
                continue
            features["master_layout_text_shapes"] += sum(
                1 for sp in tree.iter(_p("sp"))
                if sp.find(f'{_p("nvSpPr")}/{_p("nvPr")}/{_p("ph")}') is None
                if any((node.text or "").strip() for node in sp.iter(_a("t")))
            )

        for slide_no, part in enumerate(slide_parts, 1):
            tree = self.pkg.tree(part)
            if tree is None:
                continue
            features["grouped_shapes"] += len(list(tree.iter(_p("grpSp"))))
            features["tables"] += len(list(tree.iter(_a("tbl"))))
            features["fields"] += len(list(tree.iter(_a("fld"))))
            for graphic in tree.iter(_a("graphicData")):
                uri = (graphic.get("uri") or "").lower()
                if "diagram" in uri:
                    features["smartart"] += 1
                if "chart" in uri:
                    features["charts"] += 1
            for sp in tree.iter(_p("sp")):
                txbody = sp.find(_p("txBody"))
                has_text = txbody is not None and any(
                    (node.text or "").strip() for node in txbody.iter(_a("t"))
                )
                if any(parent.tag == _p("grpSp") for parent in sp.iterancestors()):
                    if has_text:
                        features["grouped_text_shapes"] += 1
                    continue
                if has_text:
                    features["plain_text_shapes"] += 1
                nv_ph = sp.find(f'{_p("nvSpPr")}/{_p("nvPr")}/{_p("ph")}')
                ph_idx = nv_ph.get("idx") if nv_ph is not None else None
                ph_type = (nv_ph.get("type") or "body") if nv_ph is not None else ""
                cnv = sp.find(f'{_p("nvSpPr")}/{_p("cNvPr")}')
                name = (cnv.get("name") if cnv is not None else "") or "unnamed"

                geom = self._shape_geometry(sp, part, ph_idx, ph_type)
                if geom is None:
                    if has_text:
                        features["unread_text_shapes"] += 1
                    continue
                left, top, width, height, rot = geom
                if rot:
                    features["rotated_shapes"] += 1

                insets, wrap, autofit, scale, reduction, anchor, vertical = \
                    self._body_properties(txbody)
                if vertical and has_text:
                    features["vertical_text_shapes"] += 1
                txbody_lst = txbody.find(_a("lstStyle")) if txbody is not None else None
                style_chain = (
                    self._placeholder_chain(part, ph_idx, ph_type)
                    if nv_ph is not None else [self.pres_default_style]
                )
                style_chain = [c for c in style_chain if c is not None]

                paragraphs: list[Paragraph] = []
                if txbody is not None:
                    for ap in txbody.findall(_a("p")):
                        ppr = ap.find(_a("pPr"))
                        level = _int(ppr, "lvl", 0) or 0
                        runs: list[Run] = []
                        for ar in ap:
                            if ar.tag == _a("r"):
                                t_el = ar.find(_a("t"))
                                text = t_el.text or "" if t_el is not None else ""
                                size, face, bold, italic = self._effective_run_props(
                                    ar.find(_a("rPr")), ppr, txbody_lst,
                                    style_chain, level, part)
                                runs.append(Run(text, size, face, bold, italic))
                            elif ar.tag == _a("br"):
                                _, face, _, _ = self._effective_run_props(
                                    ar.find(_a("rPr")), ppr, txbody_lst,
                                    style_chain, level, part)
                                runs.append(Run("\n", DEFAULT_SIZE_PT, face, False, False))
                        mult, exact, before, after = self._paragraph_spacing(
                            ppr, txbody_lst, style_chain, level)
                        latin_break = False
                        sources = [ppr]
                        for src in [txbody_lst, *style_chain]:
                            if src is None:
                                continue
                            sources.extend([self._lvl_props(src, level),
                                            src.find(_a("defPPr"))])
                        for source in sources:
                            if source is not None and source.get("latinLnBrk") is not None:
                                latin_break = _bool(source, "latinLnBrk")
                                break
                        paragraphs.append(Paragraph(
                            runs, level, mult, exact, before, after,
                            _int(ppr, "marL", 0) or 0, latin_break))

                shapes.append(Shape(
                    name=name, slide=slide_no, left=left, top=top,
                    width=width, height=height, rotation=rot,
                    paragraphs=paragraphs, insets=insets, wrap=wrap,
                    autofit=autofit, font_scale=scale,
                    line_space_reduction=reduction, anchor=anchor,
                    is_placeholder=nv_ph is not None,
                    placeholder_type=ph_type if nv_ph is not None else "",
                    vertical_text=vertical,
                ))

        themes = {i: dict(self._slide_themes[part])
                  for i, part in enumerate(slide_parts, 1) if part in self._slide_themes}
        # Legacy single-theme summary: only fonts common to all resolved slides.
        # Measurements use the per-slide maps, never this diagnostic summary.
        common = dict(next(iter(themes.values()))) if themes else {}
        common = {k: v for k, v in common.items()
                  if all(fonts.get(k) == v for fonts in themes.values())}
        return Deck(self.path, self.slide_w, self.slide_h, shapes,
                    common, features, themes)


# ------------------------------------------------------------------- layout
@dataclass
class LayoutResult:
    """What the text actually needs, versus what the shape gives it."""

    lines: int
    text_height_pt: float
    box_height_pt: float
    widest_line_pt: float
    box_width_pt: float
    confident: bool
    #: False when no font metrics were available for any run, so the numbers
    #: above are meaningless. A caller must report "could not check" rather
    #: than "nothing wrong" - the distinction the first version got wrong.
    measured: bool = True
    notes: list[str] = field(default_factory=list)

    @property
    def vertical_overflow_pt(self) -> float:
        return max(0.0, self.text_height_pt - self.box_height_pt)

    @property
    def vertical_overflow_ratio(self) -> float:
        if self.box_height_pt <= 0:
            return 0.0
        return self.text_height_pt / self.box_height_pt

    @property
    def horizontal_overflow_pt(self) -> float:
        return max(0.0, self.widest_line_pt - self.box_width_pt)


def _metrics_for(run: Run) -> Metrics | None:
    try:
        return load_metrics(run.font, run.bold, run.italic)
    except Exception:
        return None


@dataclass
class _Piece:
    """One measurable fragment of text, carrying the run it came from."""

    text: str
    run: Run
    width_pt: float
    is_space: bool
    metrics: Metrics
    size_pt: float


def _split_runs(para: Paragraph, scale: float,
                notes: list[str]) -> tuple[list[_Piece], bool]:
    """Break a paragraph into word-sized pieces, each measured with its own face."""
    pieces: list[_Piece] = []
    confident = True
    for run in para.runs:
        if not run.text:
            continue
        m = _metrics_for(run)
        if m is None:
            notes.append(f"no font metrics for {run.font!r}")
            confident = False
            continue
        if not m.face.trustworthy:
            confident = False
            if m.face.note and m.face.note not in notes:
                notes.append(m.face.note)
        size = run.size_pt * scale
        for token in _WORD_TOKENS.split(run.text):
            if not token:
                continue
            pieces.append(_Piece(
                token, run, m.text_width_pt(token, size), token.isspace(), m, size
            ))
    return pieces, confident


def _build_lines(pieces: list[_Piece], max_width_pt: float,
                 wrap: bool, notes: list[str], *,
                 latin_line_break: bool = False) -> list[list[_Piece]]:
    """Greedy word wrap over pieces from mixed runs.

    Wrapping has to be run-aware: a paragraph whose first run is 32pt and whose
    second is 12pt wraps at different points than either size alone would, and
    each resulting line's height comes from the tallest run *on that line*.
    """
    # A formatting run boundary is not a word boundary. Keep adjacent fragments
    # together for normal wrap, then retain their individual metrics/heights
    # when an overlong word has to break by character.
    groups: list[list[_Piece]] = []
    for piece in pieces:
        if (groups and not piece.is_space and not groups[-1][-1].is_space):
            groups[-1].append(piece)
        else:
            groups.append([piece])

    lines: list[list[_Piece]] = []
    current: list[_Piece] = []
    width = 0.0

    def finish():
        nonlocal current, width
        while current and current[-1].is_space:
            current.pop()
        lines.append(current)
        current, width = [], 0.0

    for group in groups:
        first = group[0]
        group_width = sum(p.width_pt for p in group)
        if first.text == "\n":
            finish()
            continue
        if not wrap or width + group_width <= max_width_pt + 1e-9:
            current.extend(group)
            width += group_width
            continue
        if first.is_space:
            # Discard a trailing space without eagerly emitting the line: a
            # following hard break must not manufacture a second blank line.
            continue

        # With latinLnBrk=false (Office's default), move the word to a fresh
        # line first. PowerPoint still breaks a word wider than that WHOLE line.
        if not latin_line_break and current:
            finish()
        if group_width <= max_width_pt + 1e-9 and not latin_line_break:
            current.extend(group)
            width = group_width
            continue
        token = "".join(p.text for p in group)
        if not _LATIN_TOKEN.fullmatch(token):
            reason = "character wrapping outside basic Latin letters/digits is not modelled"
            if reason not in notes:
                notes.append(reason)
            current.extend(group)
            width += group_width
            continue

        # Linear in the token length, including legacy pair kerning. Repeated
        # measurement of growing prefixes would make a long token quadratic.
        for piece in group:
            start, fragment_width, previous = 0, 0.0, None
            m = piece.metrics
            factor = piece.size_pt / m.upem
            for offset, ch in enumerate(piece.text):
                cp = ord(ch)
                advance = m.advance(cp) * factor
                kern = m.kerning.get((previous, cp), 0) * factor if previous is not None else 0.0
                candidate_width = width + advance + kern
                if (current or offset > start) and candidate_width > max_width_pt + 1e-9:
                    if candidate_width <= max_width_pt * (1 + EMERGENCY_WRAP_TOLERANCE):
                        reason = "character-wrap boundary is within 5% measurement tolerance"
                        if reason not in notes:
                            notes.append(reason)
                    if offset > start:
                        current.append(_Piece(piece.text[start:offset], piece.run,
                                              fragment_width, False, m, piece.size_pt))
                    finish()
                    start, fragment_width, kern = offset, 0.0, 0.0
                width += advance + kern
                fragment_width += advance + kern
                previous = cp
            if start < len(piece.text):
                current.append(_Piece(piece.text[start:], piece.run,
                                      fragment_width, False, m, piece.size_pt))

    if current or not lines or pieces[-1].text == "\n":
        while current and current[-1].is_space:
            current.pop()
        lines.append(current)
    return lines


def layout_shape(shape: Shape) -> LayoutResult | None:
    """Lay the shape's text out and report what it needs.

    Returns None when there is nothing to measure.
    """
    if not shape.has_text or shape.vertical_text:
        return None

    box_w_pt = shape.usable_width_emu / EMU_PER_POINT
    box_h_pt = shape.usable_height_emu / EMU_PER_POINT
    scale = shape.font_scale if shape.autofit == "normAutofit" else 1.0

    total_h = 0.0
    total_lines = 0
    widest = 0.0
    confident = True
    notes: list[str] = []
    paragraphs_with_text = 0
    paragraphs_measured = 0

    for i, para in enumerate(shape.paragraphs):
        if not para.runs:
            continue
        if para.text.strip():
            paragraphs_with_text += 1
        pieces, ok = _split_runs(para, scale, notes)
        confident = confident and ok
        if not pieces:
            continue
        paragraphs_measured += 1

        avail_w = max(0.0, box_w_pt - para.bullet_indent_emu / EMU_PER_POINT)
        notes_before = len(notes)
        lines = _build_lines(pieces, avail_w, shape.wrap, notes,
                             latin_line_break=para.latin_line_break)
        if len(notes) != notes_before:
            confident = False

        para_h = 0.0
        for line in lines:
            sizes = [p.run.size_pt * scale for p in line if not p.is_space]
            if not sizes:
                sizes = [p.run.size_pt * scale for p in line] or [DEFAULT_SIZE_PT]
            # DrawingML: the tallest run on the line sets that line's height,
            # at a flat 1.2x - see DRAWINGML_LINE_SPACING.
            line_h = max(sizes) * DRAWINGML_LINE_SPACING * para.line_spacing
            if para.line_spacing_pt:
                line_h = para.line_spacing_pt
            if shape.line_space_reduction:
                line_h *= (1.0 - shape.line_space_reduction)
            para_h += line_h
            widest = max(widest, sum(p.width_pt for p in line) + box_w_pt - avail_w)

        para_h += para.space_after_pt
        if i > 0:
            para_h += para.space_before_pt   # no space above the first paragraph

        total_h += para_h
        total_lines += len(lines)

    measured = paragraphs_measured > 0 or paragraphs_with_text == 0
    return LayoutResult(total_lines, total_h, box_h_pt, widest, box_w_pt,
                        confident, measured, notes)


def read_deck(path: str | Path, *,
              limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> Deck:
    return DeckReader(path, limits).read()
