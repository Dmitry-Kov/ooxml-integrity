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

Everything here is geometry and table lookups. No rendering.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .fonts import EMU_PER_POINT, Metrics, load_metrics
from .xmlutil import fromstring as parse_xml

#: split on whitespace but keep it, so word boundaries survive
_WORD_TOKENS = re.compile(r"(\s+)")

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

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as z:
            self.parts = {n: z.read(n) for n in z.namelist()}
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
            resolved = f"{d}/{target}" if d else target
            resolved = re.sub(r"/\./", "/", resolved)
            while "/../" in resolved:
                resolved = re.sub(r"[^/]+/\.\./", "", resolved, count=1)
            out[rel.get("Id")] = resolved.lstrip("/")
        return out

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

    def __init__(self, path: str | Path):
        self.pkg = _Package(path)
        self.path = Path(path)
        pres = self.pkg.tree("ppt/presentation.xml")
        sz = pres.find(_p("sldSz")) if pres is not None else None
        self.slide_w = _int(sz, "cx", DEFAULT_SLIDE_W)
        self.slide_h = _int(sz, "cy", DEFAULT_SLIDE_H)
        self.pres_default_style = (
            pres.find(_p("defaultTextStyle")) if pres is not None else None
        )
        self.theme_fonts = self._theme_fonts()

    # ------------------------------------------------------------------ theme
    def _theme_fonts(self) -> dict[str, str]:
        """+mj-lt / +mn-lt from the first theme, which is what shapes reference."""
        out = {"major": "Calibri Light", "minor": "Calibri"}
        theme_part = next(
            (n for n in self.pkg.parts if n.startswith("ppt/theme/theme")), None
        )
        t = self.pkg.tree(theme_part) if theme_part else None
        if t is None:
            return out
        scheme = t.find(f'.//{_a("fontScheme")}')
        if scheme is None:
            return out
        for key, tag in (("major", "majorFont"), ("minor", "minorFont")):
            node = scheme.find(_a(tag))
            latin = node.find(_a("latin")) if node is not None else None
            if latin is not None and latin.get("typeface"):
                out[key] = latin.get("typeface")
        return out

    def _resolve_typeface(self, name: str | None) -> str:
        if not name:
            return self.theme_fonts["minor"]
        if name in ("+mn-lt", "+mn-ea", "+mn-cs"):
            return self.theme_fonts["minor"]
        if name in ("+mj-lt", "+mj-ea", "+mj-cs"):
            return self.theme_fonts["major"]
        return name

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

    def _effective_run_props(self, rpr, ppr, txbody_lst, style_chain, level: int):
        """Walk the chain for size, family, bold, italic - first hit wins."""
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
            if size_pt is not None and typeface is not None:
                break
        return (
            size_pt if size_pt is not None else DEFAULT_SIZE_PT,
            self._resolve_typeface(typeface),
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
        if bodypr is not None:
            wrap = (bodypr.get("wrap") or "square") != "none"
            anchor = bodypr.get("anchor") or "t"
            if bodypr.find(_a("normAutofit")) is not None:
                na = bodypr.find(_a("normAutofit"))
                autofit = "normAutofit"
                scale = _pct(na, "fontScale", 1.0) or 1.0
                reduction = _pct(na, "lnSpcReduction", 0.0) or 0.0
            elif bodypr.find(_a("spAutoFit")) is not None:
                autofit = "spAutoFit"
        return insets, wrap, autofit, scale, reduction, anchor

    def read(self) -> Deck:
        slide_parts = sorted(
            (n for n in self.pkg.parts
             if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)),
        )
        shapes: list[Shape] = []

        for slide_no, part in enumerate(slide_parts, 1):
            tree = self.pkg.tree(part)
            if tree is None:
                continue
            for sp in tree.iter(_p("sp")):
                nv_ph = sp.find(f'{_p("nvSpPr")}/{_p("nvPr")}/{_p("ph")}')
                ph_idx = nv_ph.get("idx") if nv_ph is not None else None
                ph_type = (nv_ph.get("type") or "body") if nv_ph is not None else ""
                cnv = sp.find(f'{_p("nvSpPr")}/{_p("cNvPr")}')
                name = (cnv.get("name") if cnv is not None else "") or "unnamed"

                geom = self._shape_geometry(sp, part, ph_idx, ph_type)
                if geom is None:
                    continue
                left, top, width, height, rot = geom

                txbody = sp.find(_p("txBody"))
                insets, wrap, autofit, scale, reduction, anchor = \
                    self._body_properties(txbody)
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
                                    style_chain, level)
                                runs.append(Run(text, size, face, bold, italic))
                            elif ar.tag == _a("br"):
                                runs.append(Run("\n", DEFAULT_SIZE_PT,
                                                self.theme_fonts["minor"],
                                                False, False))
                        mult, exact, before, after = self._paragraph_spacing(
                            ppr, txbody_lst, style_chain, level)
                        paragraphs.append(Paragraph(
                            runs, level, mult, exact, before, after,
                            _int(ppr, "marL", 0) or 0))

                shapes.append(Shape(
                    name=name, slide=slide_no, left=left, top=top,
                    width=width, height=height, rotation=rot,
                    paragraphs=paragraphs, insets=insets, wrap=wrap,
                    autofit=autofit, font_scale=scale,
                    line_space_reduction=reduction, anchor=anchor,
                    is_placeholder=nv_ph is not None,
                    placeholder_type=ph_type if nv_ph is not None else "",
                ))

        return Deck(self.path, self.slide_w, self.slide_h, shapes,
                    self.theme_fonts)


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
                token, run, m.text_width_pt(token, size), token.isspace()
            ))
    return pieces, confident


def _build_lines(pieces: list[_Piece], max_width_pt: float,
                 wrap: bool) -> list[list[_Piece]]:
    """Greedy word wrap over pieces from mixed runs.

    Wrapping has to be run-aware: a paragraph whose first run is 32pt and whose
    second is 12pt wraps at different points than either size alone would, and
    each resulting line's height comes from the tallest run *on that line*.
    """
    lines: list[list[_Piece]] = []
    current: list[_Piece] = []
    width = 0.0

    for piece in pieces:
        if piece.text == "\n":
            lines.append(current)
            current, width = [], 0.0
            continue
        if not wrap or width + piece.width_pt <= max_width_pt or not current:
            current.append(piece)
            width += piece.width_pt
            continue
        # does not fit: break, dropping a space that would start the new line
        while current and current[-1].is_space:
            width -= current.pop().width_pt
        lines.append(current)
        if piece.is_space:
            current, width = [], 0.0
        else:
            current, width = [piece], piece.width_pt

    lines.append(current)
    return lines


def layout_shape(shape: Shape) -> LayoutResult | None:
    """Lay the shape's text out and report what it needs.

    Returns None when there is nothing to measure.
    """
    if not shape.has_text:
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
        lines = _build_lines(pieces, avail_w, shape.wrap)

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
            widest = max(widest, sum(p.width_pt for p in line))

        para_h += para.space_after_pt
        if i > 0:
            para_h += para.space_before_pt   # no space above the first paragraph

        total_h += para_h
        total_lines += len(lines)

    measured = paragraphs_measured > 0 or paragraphs_with_text == 0
    return LayoutResult(total_lines, total_h, box_h_pt, widest, box_w_pt,
                        confident, measured, notes)


def read_deck(path: str | Path) -> Deck:
    return DeckReader(path).read()
