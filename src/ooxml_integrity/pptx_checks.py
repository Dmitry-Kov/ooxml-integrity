"""
Checks for .pptx decks: text that does not fit, shapes that collide, shapes
that hang off the slide.

Thresholds here are not guesses. They come from `research/calibrate_pptx.py`,
which renders every shape of the reference deck one at a time with LibreOffice
and compares the prediction against the extracted glyph positions:

    line pitch   median 0.05%, worst 0.06%   (uniform-size paragraphs, n=12)
    line count   23/24 exact, 1 off by one

The single miss is instructive and sets `BORDERLINE`: that shape's first line
filled its box to within **0.6%**, and the renderer broke a word earlier than
the prediction did. Advance widths alone cannot resolve a margin that thin -
GPOS kerning and shaping, which are not applied here, move a line's width by a
fraction of a percent. So anything within a few percent of the boundary is
reported as borderline rather than as overflow, and the caller is told why.
"""
from __future__ import annotations

from pathlib import Path

from .archive import DEFAULT_ARCHIVE_LIMITS, ArchiveLimits, PackageIssue
from .finding import ERROR, INFO, WARN, Finding
from .fonts import EMU_PER_POINT, measurement_available
from .pptx_layout import Deck, Shape, layout_shape, read_deck

#: Within this fraction of the box, a verdict is not resolvable from advance
#: widths - see the module docstring. Measured, not chosen.
BORDERLINE = 0.05

#: Ignore overlaps smaller than this fraction of the smaller shape's area.
#: Decks routinely have decorative shapes touching by a hair on purpose.
OVERLAP_TOLERANCE = 0.02

#: A shape may hang this far past the slide edge before it is worth reporting;
#: bleed of a few points is a design choice, half a shape is not.
OFFCANVAS_TOLERANCE_EMU = 12700 * 2   # 2pt


def _where(shape: Shape) -> str:
    return f"slide{shape.slide}/{shape.name}"


def check_measurable(deck: Deck) -> list[Finding]:
    """Can this machine measure text at all?

    This check exists because of a real bug. The first version looked for fonts
    only through `fc-match`. On macOS, which ships no fontconfig, it found
    nothing, every measurement was skipped, and a deck with seven overflowing
    shapes was reported as having no text problems - a clean bill of health from
    a checker that had not checked anything.

    A tool that cannot run its own check has to say so. Reporting "nothing
    wrong" in that situation is the same silent-failure class this project
    exists to catch.
    """
    ok, detail = measurement_available()
    if ok:
        return []
    return [Finding(
        "PPT000", ERROR,
        "text measurement is unavailable on this machine, so overflow was NOT "
        f"checked - only geometry (overlap, off-canvas) was. {detail}",
    )]


def check_text_overflow(deck: Deck) -> list[Finding]:
    """Does each shape's text fit the box it was given?"""
    out: list[Finding] = []
    # If measurement is unavailable machine-wide, check_measurable already said
    # so once. Repeating it per shape buries the geometry findings under noise.
    machine_wide, _ = measurement_available()
    for shape in deck.shapes:
        result = layout_shape(shape)
        if result is None:
            continue
        if not result.measured:
            if machine_wide:
                # fonts work in general, so this shape specifically failed -
                # worth naming
                out.append(Finding(
                    "PPT000", ERROR,
                    "no font metrics were available for any run, so this shape's "
                    "text was not measured" + (
                        "; " + "; ".join(result.notes) if result.notes else ""),
                    _where(shape)))
            continue

        # spAutoFit means the box grows to the text, so overflow is not a defect.
        if shape.autofit == "spAutoFit":
            continue

        ratio = result.vertical_overflow_ratio
        confident = result.confident
        note = ("; " + "; ".join(result.notes)) if result.notes else ""

        if ratio > 1.0 + BORDERLINE:
            over_pt = result.vertical_overflow_pt
            msg = (f"text needs {result.text_height_pt:.0f}pt in a "
                   f"{result.box_height_pt:.0f}pt box - "
                   f"{over_pt:.0f}pt too tall ({(ratio - 1) * 100:.0f}% over), "
                   f"{result.lines} line(s)")
            if shape.autofit == "normAutofit" and shape.font_scale >= 1.0:
                # PowerPoint stores the shrink it applied. No scale means either
                # it never opened the file, or the writer did not compute one -
                # so what a viewer sees depends on the renderer.
                out.append(Finding(
                    "PPT005", WARN,
                    f'{msg}; the shape asks for shrink-to-fit but carries no '
                    f'stored fontScale, so the result depends on the renderer',
                    _where(shape)))
            elif confident:
                out.append(Finding("PPT001", ERROR, msg + note, _where(shape)))
            else:
                out.append(Finding(
                    "PPT001", WARN,
                    msg + " - but the declared font is not available, so this is "
                          "an estimate" + note,
                    _where(shape)))
        elif ratio > 1.0:
            out.append(Finding(
                "PPT002", WARN,
                f"text fills {ratio * 100:.0f}% of its box - within measurement "
                f"tolerance of overflowing, so it may or may not fit depending "
                f"on the renderer and the installed font" + note,
                _where(shape)))

        # wrap off: a long line runs out the side however tall the box is
        if not shape.wrap and result.horizontal_overflow_pt > 0:
            over = result.horizontal_overflow_pt
            if over > result.box_width_pt * BORDERLINE:
                out.append(Finding(
                    "PPT003", ERROR if confident else WARN,
                    f"word wrap is off and the longest line is "
                    f"{result.widest_line_pt:.0f}pt in a "
                    f"{result.box_width_pt:.0f}pt box - {over:.0f}pt runs "
                    f"outside the shape" + note,
                    _where(shape)))
    return out


def check_offcanvas(deck: Deck) -> list[Finding]:
    """Shapes extending past the slide edge."""
    out: list[Finding] = []
    tol = OFFCANVAS_TOLERANCE_EMU
    for shape in deck.shapes:
        sides = []
        if shape.left < -tol:
            sides.append(f"{-shape.left / EMU_PER_POINT:.0f}pt past the left edge")
        if shape.top < -tol:
            sides.append(f"{-shape.top / EMU_PER_POINT:.0f}pt past the top edge")
        if shape.right > deck.slide_width + tol:
            sides.append(f"{(shape.right - deck.slide_width) / EMU_PER_POINT:.0f}pt "
                         "past the right edge")
        if shape.bottom > deck.slide_height + tol:
            sides.append(f"{(shape.bottom - deck.slide_height) / EMU_PER_POINT:.0f}pt "
                         "past the bottom edge")
        if not sides:
            continue
        # A shape entirely outside the slide is usually deliberate scratch
        # content; one straddling the edge is usually a mistake.
        fully_outside = (
            shape.right <= 0 or shape.bottom <= 0
            or shape.left >= deck.slide_width or shape.top >= deck.slide_height
        )
        out.append(Finding(
            "PPT004", INFO if fully_outside else WARN,
            ("shape sits entirely outside the slide" if fully_outside
             else "shape extends " + ", ".join(sides))
            + (" - content will be cut off" if not fully_outside else
               " and will not be visible"),
            _where(shape)))
    return out


def check_overlap(deck: Deck) -> list[Finding]:
    """Text-bearing shapes covering one another."""
    out: list[Finding] = []
    by_slide: dict[int, list[Shape]] = {}
    for s in deck.shapes:
        by_slide.setdefault(s.slide, []).append(s)

    for slide, shapes in sorted(by_slide.items()):
        withtext = [s for s in shapes if s.has_text and s.rotation == 0]
        for i, a in enumerate(withtext):
            for b in withtext[i + 1:]:
                ox = min(a.right, b.right) - max(a.left, b.left)
                oy = min(a.bottom, b.bottom) - max(a.top, b.top)
                if ox <= 0 or oy <= 0:
                    continue
                area = ox * oy
                smaller = min(a.width * a.height, b.width * b.height)
                if smaller <= 0 or area / smaller < OVERLAP_TOLERANCE:
                    continue
                pct = area / smaller * 100
                out.append(Finding(
                    "PPT006", WARN if pct < 50 else ERROR,
                    f"overlaps {b.name!r} over {pct:.0f}% of the smaller shape "
                    f"({ox / EMU_PER_POINT:.0f}x{oy / EMU_PER_POINT:.0f}pt) - "
                    "both carry text, so one will obscure the other",
                    f"slide{slide}/{a.name}"))
    return out


def check_font_availability(deck: Deck) -> list[Finding]:
    """Report once per missing family, not once per shape."""
    from .fonts import resolve_face

    seen: dict[str, list[str]] = {}
    for shape in deck.shapes:
        for para in shape.paragraphs:
            for run in para.runs:
                if not run.text.strip():
                    continue
                try:
                    face = resolve_face(run.font, run.bold, run.italic)
                except Exception:
                    continue
                if not face.trustworthy:
                    seen.setdefault(run.font, [])
                    if _where(shape) not in seen[run.font]:
                        seen[run.font].append(_where(shape))
    out: list[Finding] = []
    for family, shapes in sorted(seen.items()):
        face = resolve_face(family)
        out.append(Finding(
            "PPT007", INFO,
            f"{face.note}. {len(shapes)} shape(s) affected; overflow verdicts "
            f"for them are estimates",
            shapes[0] if len(shapes) == 1 else f"{len(shapes)} shapes"))
    return out


CHECKS = (check_measurable, check_text_overflow, check_offcanvas,
          check_overlap, check_font_availability)


def check_pptx(path: str | Path, *,
               limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS) -> list[Finding]:
    """Inspect one .pptx for layout defects. Returns every finding."""
    try:
        deck = read_deck(path, limits=limits)
    except FileNotFoundError:
        return [Finding("PKG000", ERROR, f"file not found: {path}")]
    except PackageIssue as e:
        return [Finding(e.code, ERROR, str(e), part=e.part)]
    except Exception as e:
        return [Finding("PKG002", ERROR, f"could not read as a .pptx package: {e}")]

    out: list[Finding] = []
    for fn in CHECKS:
        try:
            out.extend(fn(deck))
        except Exception as e:
            out.append(Finding("INT001", WARN, f"check {fn.__name__} raised: {e}"))
    return out
