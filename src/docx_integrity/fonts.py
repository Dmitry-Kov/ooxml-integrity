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

import functools
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: OOXML geometry is in English Metric Units.
EMU_PER_INCH = 914400
EMU_PER_POINT = 12700
POINTS_PER_INCH = 72

#: Substitutes designed to have IDENTICAL advance widths to the declared
#: family. Text measured with one of these is as good as measured with the
#: original. Each pairing here is a documented metric-compatible clone.
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
LAST_RESORT = ("DejaVu Sans", "Liberation Sans", "FreeSans")


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

    hit = _fc_match(requested + suffix)
    if hit:
        path, got = hit
        if got.lower() == key:
            return ResolvedFace(requested, Path(path), got, "exact")
        # fontconfig substituted for us. Grade what it chose rather than
        # assuming its choice was metric-compatible.
        if got.lower() in metric_ok:
            return ResolvedFace(requested, Path(path), got, "metric")
        if got.lower() in similar_ok:
            return ResolvedFace(requested, Path(path), got, "similar")

    for candidate in METRIC_SUBSTITUTES.get(key, ()):
        found = _fc_match(candidate + suffix)
        if found and found[1].lower() == candidate.lower():
            return ResolvedFace(requested, Path(found[0]), found[1], "metric")

    for candidate in SIMILAR_SUBSTITUTES.get(key, ()):
        found = _fc_match(candidate + suffix)
        if found and found[1].lower() == candidate.lower():
            return ResolvedFace(requested, Path(found[0]), found[1], "similar")

    for candidate in LAST_RESORT:
        hit = _fc_match(candidate + suffix)
        if hit:
            return ResolvedFace(requested, Path(hit[0]), hit[1], "fallback")

    if hit:  # whatever fontconfig gave us first, better than nothing
        return ResolvedFace(requested, Path(hit[0]), hit[1], "fallback")
    raise FontUnavailable(
        f"no usable font file for {requested!r}; install fontconfig and at least "
        "one of: " + ", ".join(LAST_RESORT)
    )


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

    # Vertical metrics: prefer OS/2 typo metrics, which is what layout engines
    # use when USE_TYPO_METRICS is set; fall back to hhea.
    ascender = descender = line_gap = 0
    os2 = font.get("OS/2")
    if os2 is not None and getattr(os2, "sTypoAscender", 0):
        use_typo = bool(getattr(os2, "fsSelection", 0) & (1 << 7))
        if use_typo:
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
