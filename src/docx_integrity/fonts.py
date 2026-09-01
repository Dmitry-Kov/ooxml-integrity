"""
Font resolution and text measurement.

The honest framing first, because it governs the whole design:

**Exact overflow detection is impossible in principle.** The font a slide is
rendered with depends on what is installed where it is opened. A deck that
declares Calibri renders in Calibri on Windows, in Carlito on most Linux boxes,
and in whatever the substitution chain lands on elsewhere. Metric-compatible
substitutes (Carlito for Calibri, Liberation Sans for Arial) match advance
widths closely but not to the last unit.

So this module does not claim to say "this text overflows". It measures with the
best available face and reports how far past the boundary the text goes, which
lets the caller separate "3% over, could be a substitution artefact" from
"40% over, broken on every machine".

Measurement uses advance widths from the font's own tables. No rendering, no
rasterising, no image comparison.

Two known sources of error, both stated rather than hidden:

* **Kerning.** Only the legacy ``kern`` table is read. Most modern fonts,
  Carlito and the Liberation family included, carry kerning in ``GPOS``, which
  is not parsed here. For Latin body text the effect on a line's width is
  typically well under one percent, but it is not zero.
* **Shaping.** Ligatures, contextual alternates and complex scripts are not
  applied. For Latin text at office sizes this is negligible; for Arabic,
  Devanagari or heavily-ligatured display faces it is not, and measurements
  there should not be trusted.
"""
from __future__ import annotations

import contextlib
import functools
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@contextlib.contextmanager
def _quiet_fonttools():
    """Silence fontTools while reading system fonts.

    Plenty of shipped faces have small table irregularities that fontTools
    reports on stderr - macOS system fonts produce lines like "144733 extra
    bytes in post.stringData array". They are harmless for advance widths, and
    a user checking a deck should not see them.
    """
    log = logging.getLogger("fontTools")
    previous = log.level
    log.setLevel(logging.ERROR)
    try:
        yield
    finally:
        log.setLevel(previous)

#: OOXML geometry is in English Metric Units.
EMU_PER_INCH = 914400
EMU_PER_POINT = 12700
POINTS_PER_INCH = 72

#: Metric-compatible clones: designed to stand in for the declared family at
#: the same widths. Close enough to act on, but NOT identical - measured.
#:
#: Carlito against real Calibri, both read with this module, 18pt:
#:
#:     digits "0123456789 EUR 44,500.00"     202.376953  vs  202.376953   0.000%
#:     bold caps A-Z                         265.772461  vs  265.069336  -0.265%
#:     caps A-Z                              259.171875  vs  258.451172  -0.278%
#:     "The Supplier shall maintain ..."     444.682617  vs  443.188477  -0.336%
#:     pangram                               326.276367  vs  324.685547  -0.488%
#:     lowercase a-z                         213.372070  vs  212.132812  -0.581%
#:
#: Digits match exactly - tabular figures are built to. Letters do not: Carlito
#: runs 0.26-0.58% wider. Two things follow. The substitution error is the same
#: order as the GPOS-kerning gap, so `pptx_checks.BORDERLINE` at 5% covers both
#: comfortably. And the error has a direction: measuring Calibri text with
#: Carlito OVERSTATES width, so it leans toward a false overflow report rather
#: than a missed one - the safe direction for a checker.
#:
#: Measured on a Mac with Microsoft 365 installed, since neither font is present
#: on a machine that has the other; the comparison needs both.
METRIC_SUBSTITUTES: dict[str, tuple[str, ...]] = {
    "calibri": ("Carlito",),
    "cambria": ("Caladea",),
    "arial": ("Liberation Sans", "Arimo"),
    "helvetica": ("Liberation Sans", "Arimo"),
    "times new roman": ("Liberation Serif", "Tinos"),
    "courier new": ("Liberation Mono", "Cousine"),
    "georgia": ("Gelasio",),
}

#: Substitutes that merely *look* similar. Widths will differ, sometimes by a
#: lot, so a measurement taken with one of these is an estimate. Keeping this
#: separate from METRIC_SUBSTITUTES is the difference between a number you can
#: act on and a number that reads as precise but is not.
SIMILAR_SUBSTITUTES: dict[str, tuple[str, ...]] = {
    "verdana": ("DejaVu Sans",),
    "tahoma": ("DejaVu Sans",),
    "segoe ui": ("Open Sans", "Noto Sans", "DejaVu Sans"),
    "trebuchet ms": ("Fira Sans", "DejaVu Sans"),
    "garamond": ("EB Garamond", "Liberation Serif"),
    "palatino linotype": ("TeX Gyre Pagella", "Liberation Serif"),
    "century gothic": ("URW Gothic", "DejaVu Sans"),
}

#: Used when nothing better is found, so measurement degrades rather than fails.
#: Ordered by how likely each is to exist, per platform, and every entry is a
#: normal Latin sans - a measurement taken with one of these is wrong, but
#: wrong in a way proportional to the text, which a random system face is not.
LAST_RESORT = (
    "DejaVu Sans", "Liberation Sans", "FreeSans",          # Linux
    "Helvetica", "Helvetica Neue", "Arial", "Geneva",      # macOS
    "Segoe UI", "Tahoma", "Verdana",                       # Windows
)


class FontUnavailable(Exception):
    """No usable face could be found at all - measurement cannot proceed."""


@dataclass(frozen=True)
class ResolvedFace:
    """Which file was actually used to measure, and how confident that makes us."""

    requested: str
    path: Path
    family: str
    #: "exact"    the declared family itself was found - widths are right
    #: "metric"   a metric-compatible clone - widths are right
    #: "similar"  a visually similar face - widths are an estimate
    #: "fallback" something unrelated - widths are a guess
    match: str

    @property
    def trustworthy(self) -> bool:
        """Can a caller act on a measurement taken with this face?"""
        return self.match in ("exact", "metric")

    @property
    def note(self) -> str:
        return {
            "exact": "",
            "metric": f"measured with {self.family}, metric-compatible with "
                      f"{self.requested}",
            "similar": f"{self.requested} is not installed; measured with "
                       f"{self.family}, which is similar but NOT "
                       f"metric-compatible - treat the number as an estimate",
            "fallback": f"{self.requested} is not installed and has no known "
                        f"substitute; measured with {self.family} - widths are "
                        f"a guess",
        }[self.match]


@functools.lru_cache(maxsize=256)
def _fc_match(pattern: str) -> tuple[str, str] | None:
    """Ask fontconfig for a file. Returns (path, family) or None."""
    if not shutil.which("fc-match"):
        return None
    try:
        r = subprocess.run(
            ["fc-match", "-f", "%{file}\t%{family}", pattern],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if r.returncode != 0 or "\t" not in r.stdout:
        return None
    path, _, family = r.stdout.partition("\t")
    if not path or not Path(path).exists():
        return None
    return path, family.split(",")[0].strip()


#: Where fonts live when there is no fontconfig to ask. macOS has none by
#: default, and Windows has none at all.
#:
#: This exists because the first version relied on `fc-match` alone. On a Mac it
#: found nothing, every measurement was skipped, and the checker reported a deck
#: with seven overflowing shapes as having no text problems at all - the exact
#: silent-failure class this project was built to catch. The lesson is in
#: `_index_font_dirs` and in `check_measurable`.
FONT_DIRS = (
    # Microsoft Office fonts first: when Office is installed these are the real
    # Calibri, Cambria and Segoe UI, which beat any substitute. Microsoft 365 on
    # macOS keeps them in a group container rather than in a font directory,
    # which is why a plain /Library/Fonts scan misses them.
    "~/Library/Group Containers/UBF8T346G9.Office/FontCache",
    "/Library/Fonts/Microsoft",
    "/Applications/Microsoft Word.app/Contents/Resources/DFonts",
    "/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts",
    # macOS
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
    "~/Library/Fonts",
    # Windows
    "C:/Windows/Fonts",
    "~/AppData/Local/Microsoft/Windows/Fonts",
    # Linux, for the case where fontconfig is absent but fonts are not
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "~/.fonts",
    "~/.local/share/fonts",
)

_FONT_EXTS = (".ttf", ".otf", ".ttc", ".otc")


@functools.lru_cache(maxsize=1)
def _index_font_dirs() -> dict[str, tuple[str, int]]:
    """family name (lowercased) -> (file path, font number within the file).

    Built by reading each face's `name` table, because a filename is not a
    family name: HelveticaNeue.ttc holds several families, and
    'Times New Roman' lives in Times.ttc on macOS. Scanning is deferred until
    fontconfig has already failed, and the result is cached for the process.
    """
    from fontTools.ttLib import TTCollection, TTFont

    index: dict[str, tuple[str, int]] = {}

    def record(family: str, path: str, number: int, bold: bool, italic: bool):
        """The only writer of `index` - both the plain and the composed key.

        They used to be written in two places, and the dot-prefix guard was
        only on this one. macOS system faces walked in through the other door:
        `.sf ns mono` was correctly rejected while `.sf ns mono:italic` was
        indexed, so an internal system face was still reachable for any italic
        run. Caught on the macOS runner, by the regression test written for
        the original `.aqua kana` bug.
        """
        key = family.strip().lower()
        if not key:
            return
        # Dot-prefixed names are macOS internal system faces (.aqua kana,
        # .SF NS, .Helvetica Neue DeskInterface). They are not document fonts
        # and must never be picked as a fallback.
        if key.startswith("."):
            return
        # prefer the regular face for a family; styled ones also get their own
        # composed key, which never overwrites one already recorded
        if key not in index or not (bold or italic):
            index[key] = (path, number)
        if bold or italic:
            index.setdefault(key + _style_key(bold, italic), (path, number))

    def faces(path: Path):
        try:
            with _quiet_fonttools():
                if path.suffix.lower() in (".ttc", ".otc"):
                    coll = TTCollection(str(path), lazy=True)
                    for i, f in enumerate(coll.fonts):
                        yield f, i
                    return
                yield TTFont(str(path), lazy=True, fontNumber=0), 0
        except Exception:
            return

    for raw in FONT_DIRS:
        d = Path(raw).expanduser()
        if not d.is_dir():
            continue
        try:
            candidates = [p for p in d.rglob("*") if p.suffix.lower() in _FONT_EXTS]
        except OSError:
            continue
        for path in candidates:
            for font, number in faces(path):
                try:
                    name_table = font["name"]
                    family = (name_table.getBestFamilyName() or "")
                    subfamily = ""
                    rec = name_table.getDebugName(2)
                    if rec:
                        subfamily = rec.strip().lower()
                    bold = "bold" in subfamily
                    italic = "italic" in subfamily or "oblique" in subfamily
                    record(family, str(path), number, bold, italic)
                except Exception:
                    continue
                finally:
                    try:
                        font.close()
                    except Exception:
                        pass
    return index


@functools.lru_cache(maxsize=512)
def _has_latin_coverage(path: str) -> bool:
    """Does this face actually carry basic Latin? A CJK or symbol font does not,
    and measuring English text with one produces nonsense."""
    from fontTools.ttLib import TTFont

    try:
        with _quiet_fonttools():
            font = TTFont(path, lazy=True, fontNumber=0)
            cmap = font.getBestCmap()
            font.close()
    except Exception:
        return False
    probe = "AaEeIiNnOoSsTt 0123456789.,"
    return all(ord(c) in cmap for c in probe)


def _style_key(bold: bool, italic: bool) -> str:
    return {(False, False): "", (True, False): ":bold",
            (False, True): ":italic", (True, True): ":bold:italic"}[(bold, italic)]


def _dir_match(family: str, bold: bool, italic: bool) -> tuple[str, str] | None:
    """Look a family up in the scanned directories. Returns (path, family)."""
    index = _index_font_dirs()
    if not index:
        return None
    key = family.strip().lower()
    for candidate in (key + _style_key(bold, italic), key):
        hit = index.get(candidate)
        if hit:
            return hit[0], family.strip()
    return None


def _locate(family: str, bold: bool, italic: bool) -> tuple[str, str] | None:
    """fontconfig first because it honours the system's own substitution rules;
    a directory scan second, for macOS and Windows where there is none."""
    hit = _fc_match(family + _style_suffix(bold, italic))
    if hit:
        return hit
    return _dir_match(family, bold, italic)


def _style_suffix(bold: bool, italic: bool) -> str:
    if bold and italic:
        return ":bold:italic"
    if bold:
        return ":bold"
    if italic:
        return ":italic"
    return ""


@functools.lru_cache(maxsize=512)
def resolve_face(family: str, bold: bool = False, italic: bool = False) -> ResolvedFace:
    """Find a font file for a declared family, and say how good the match is."""
    requested = (family or "").strip() or "Calibri"
    suffix = _style_suffix(bold, italic)
    key = requested.lower()

    metric_ok = {s.lower() for s in METRIC_SUBSTITUTES.get(key, ())}
    similar_ok = {s.lower() for s in SIMILAR_SUBSTITUTES.get(key, ())}

    first = _locate(requested, bold, italic)
    if first:
        path, got = first
        if got.lower() == key:
            return ResolvedFace(requested, Path(path), got, "exact")
        # something substituted for us. Grade what it chose rather than
        # assuming its choice was metric-compatible.
        if got.lower() in metric_ok:
            return ResolvedFace(requested, Path(path), got, "metric")
        if got.lower() in similar_ok:
            return ResolvedFace(requested, Path(path), got, "similar")

    for candidate in METRIC_SUBSTITUTES.get(key, ()):
        found = _locate(candidate, bold, italic)
        if found and found[1].lower() == candidate.lower():
            return ResolvedFace(requested, Path(found[0]), found[1], "metric")

    for candidate in SIMILAR_SUBSTITUTES.get(key, ()):
        found = _locate(candidate, bold, italic)
        if found and found[1].lower() == candidate.lower():
            return ResolvedFace(requested, Path(found[0]), found[1], "similar")

    for candidate in LAST_RESORT:
        found = _locate(candidate, bold, italic)
        if found:
            return ResolvedFace(requested, Path(found[0]), found[1], "fallback")

    if first:  # whatever turned up first, better than nothing
        return ResolvedFace(requested, Path(first[0]), first[1], "fallback")

    # Last resort before giving up: anything usable from the scanned dirs, so a
    # machine with fonts but no fontconfig still measures.
    #
    # "Usable" matters. Sorting the index alphabetically and taking the first
    # entry picked `.aqua kana` on macOS - a dot-prefixed internal Japanese
    # system face - and measured English text with it. Dot-prefixed families are
    # excluded at index time now, and the pick prefers a face with real Latin
    # coverage over whatever happens to sort first.
    index = _index_font_dirs()
    if index:
        for family in sorted(index):
            if family.startswith("."):
                continue
            path, _ = index[family]
            if _has_latin_coverage(path):
                return ResolvedFace(requested, Path(path), family, "fallback")

    raise FontUnavailable(
        f"no usable font file for {requested!r}. Searched fontconfig "
        f"(fc-match {'found' if shutil.which('fc-match') else 'NOT installed'}) "
        f"and these directories: "
        + ", ".join(str(Path(d).expanduser()) for d in FONT_DIRS
                    if Path(d).expanduser().is_dir())
        + ". Text measurement cannot run without at least one font file."
    )


def measurement_available() -> tuple[bool, str]:
    """Can text be measured on this machine at all?

    Callers use this to report "could not check" rather than "nothing wrong",
    which is the distinction the first version of this module got wrong.
    """
    try:
        face = resolve_face("Calibri")
    except FontUnavailable as e:
        return False, str(e)
    return True, f"measuring with {face.family} ({face.path})"


@dataclass
class Metrics:
    """Advance widths and vertical metrics for one face, in font units."""

    face: ResolvedFace
    upem: int
    ascender: int
    descender: int          # positive number of units below the baseline
    line_gap: int
    widths: dict[int, int]  # codepoint -> advance width
    default_width: int
    kerning: dict[tuple[int, int], int]

    # -------------------------------------------------------------- geometry
    def advance(self, codepoint: int) -> int:
        return self.widths.get(codepoint, self.default_width)

    def text_width_units(self, text: str, *, kern: bool = True) -> int:
        total = 0
        prev: int | None = None
        for ch in text:
            cp = ord(ch)
            total += self.advance(cp)
            if kern and prev is not None and self.kerning:
                total += self.kerning.get((prev, cp), 0)
            prev = cp
        return total

    def text_width_pt(self, text: str, size_pt: float, *, kern: bool = True) -> float:
        return self.text_width_units(text, kern=kern) * size_pt / self.upem

    def line_height_pt(self, size_pt: float) -> float:
        """Single-spaced line height, from the face's own vertical metrics."""
        return (self.ascender + self.descender + self.line_gap) * size_pt / self.upem

    def ascent_pt(self, size_pt: float) -> float:
        return self.ascender * size_pt / self.upem


@functools.lru_cache(maxsize=128)
def load_metrics(family: str, bold: bool = False, italic: bool = False) -> Metrics:
    """Read one face's tables. Cached: opening a TTF is the expensive part."""
    from fontTools.ttLib import TTFont

    face = resolve_face(family, bold, italic)
    # The whole body stays inside the quiet block: TTFont is lazy, so tables are
    # parsed at first access, not at construction. Wrapping only the constructor
    # let the `kern` table's "subtable longer than defined" warning through when
    # it was read further down.
    with _quiet_fonttools():
        font = TTFont(str(face.path), fontNumber=0, lazy=True)

        upem = font["head"].unitsPerEm
        hmtx = font["hmtx"]
        cmap = font.getBestCmap()

        widths: dict[int, int] = {}
        for cp, name in cmap.items():
            try:
                widths[cp] = hmtx[name][0]
            except KeyError:
                continue

        # Vertical metrics: prefer OS/2 typo metrics, which is what layout
        # engines use when USE_TYPO_METRICS is set; fall back to hhea. Note that
        # DrawingML ignores all of this - see pptx_layout.DRAWINGML_LINE_SPACING.
        ascender = descender = line_gap = 0
        os2 = font.get("OS/2")
        if os2 is not None and getattr(os2, "sTypoAscender", 0):
            if bool(getattr(os2, "fsSelection", 0) & (1 << 7)):
                ascender = os2.sTypoAscender
                descender = abs(os2.sTypoDescender)
                line_gap = getattr(os2, "sTypoLineGap", 0)
        if not ascender:
            hhea = font["hhea"]
            ascender = hhea.ascender
            descender = abs(hhea.descender)
            line_gap = hhea.lineGap

        kerning: dict[tuple[int, int], int] = {}
        kern_table = font.get("kern")
        if kern_table is not None:
            name_to_cp = {}
            for cp, name in cmap.items():
                name_to_cp.setdefault(name, cp)
            for subtable in getattr(kern_table, "kernTables", []):
                for (left, right), value in getattr(subtable, "kernTable", {}).items():
                    lcp, rcp = name_to_cp.get(left), name_to_cp.get(right)
                    if lcp is not None and rcp is not None:
                        kerning[(lcp, rcp)] = value

        space = widths.get(0x20) or round(upem * 0.25)
        font.close()
    return Metrics(face, upem, ascender, descender, line_gap, widths, space, kerning)


# ---------------------------------------------------------------- line breaking
_WORD_SPLIT = re.compile(r"(\s+)")


def wrap_text(text: str, metrics: Metrics, size_pt: float, max_width_pt: float,
              *, kern: bool = True) -> list[str]:
    """Greedy word wrap, the algorithm every office renderer uses.

    A word longer than the line is broken by character rather than allowed to
    run off, which is what PowerPoint does with wrap on.
    """
    if max_width_pt <= 0:
        return [text] if text else []

    lines: list[str] = []
    for hard_line in text.split("\n"):
        if not hard_line:
            lines.append("")
            continue
        current = ""
        for token in _WORD_SPLIT.split(hard_line):
            if not token:
                continue
            candidate = current + token
            if metrics.text_width_pt(candidate, size_pt, kern=kern) <= max_width_pt:
                current = candidate
                continue
            if token.isspace():
                # trailing space that does not fit is dropped, as in a renderer
                continue
            if current.strip():
                lines.append(current.rstrip())
                current = ""
            # the token itself may still be too wide for a whole line
            if metrics.text_width_pt(token, size_pt, kern=kern) <= max_width_pt:
                current = token
                continue
            chunk = ""
            for ch in token:
                if metrics.text_width_pt(chunk + ch, size_pt, kern=kern) > max_width_pt:
                    if chunk:
                        lines.append(chunk)
                    chunk = ch
                else:
                    chunk += ch
            current = chunk
        lines.append(current.rstrip())
    return lines


def emu_to_pt(emu: float) -> float:
    return emu / EMU_PER_POINT


def pt_to_emu(pt: float) -> int:
    return round(pt * EMU_PER_POINT)
