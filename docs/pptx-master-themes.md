# Master-specific presentation themes

P1 item 4 is closed for **Latin major/minor fonts resolved through a slide's
own layout and master** in Transitional PresentationML. Text on one master
must not be measured with the font scheme of another master, a notes master,
or whichever theme happens to occur first in the ZIP.

The dependency is `slide → slideLayout → slideMaster → theme`, using typed
internal relationships, not conventional filenames. Microsoft describes the
master's theme relationship in [Working with presentations](https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-presentations)
and master-level text styles in [Working with slide masters](https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-slide-masters).

## Failure and native Office evidence

The preceding checker selected the first `ppt/theme/` part for the whole deck.
That can hide real overflow when the wrong font is narrower, or invent overflow
when it is wider. Neither changing the threshold nor installing more fonts can
repair selection of the wrong declared family.

- Renderer: **Microsoft PowerPoint for Mac 16.112.3**, macOS Apple Silicon,
  observed locally on 2026-09-06.
- Input: [`corpus/pptx-master-themes.pptx`](../corpus/pptx-master-themes.pptx),
  SHA-256 `90f7a5281037910a97bbc4c2fb95cd1a5e44dcb476cd1c020a2619f95751fac5`.
- Opened without a repair prompt, editing or resaving. Native
  **File → Export → PNG → Save Every Slide**, 960 × 540. All eight exported
  PNGs were inspected individually at full size. These are PowerPoint exports,
  not the fixture author's or checker's renders.
- [Provenance, font metadata and pinned fixture/image hashes](calibration/master-themes/evidence.json).
  Fixture and renders are synthetic project MIT material. No font binaries or
  third-party document content are redistributed.

The fixture was authored with `@oai/artifact-tool`, then two master/layout
chains, related font themes and presentation defaults were set in OOXML.
Structural, geometry, font-policy and import checks passed on the exact final
bytes. The native blue outline is a 180 × 60pt text box; text is 24pt, with
wrap/autofit off and zero insets. Labels are separate literal Calibri 30pt text.
All test strings contain 20 lowercase i characters, except slide 3's ten W's.

| Master | Major / heading Latin font | Minor / body Latin font | Related theme part |
|---|---|---|---|
| A | Courier New | Arial | `ppt/master-themes/a.xml` |
| B | Times New Roman | Courier New | `ppt/master-themes/b.xml` |

An unrelated presentation-level `ppt/theme/theme1.xml` declares Arial for both
families. Its conventional name must not make it either master's theme.

| Slide / native render | Font selection | Office result | New finding |
|---|---|---|---|
| [1](calibration/master-themes/Slide1.png) | A minor → Arial | fits | none |
| [2](calibration/master-themes/Slide2.png) | B minor → Courier New | overflows right | `PPT003` ERROR |
| [3](calibration/master-themes/Slide3.png) | B minor → Courier New, ten W's | fits | none |
| [4](calibration/master-themes/Slide4.png) | B major → Times New Roman | fits | none |
| [5](calibration/master-themes/Slide5.png) | A major → Courier New | overflows right | `PPT003` ERROR |
| [6](calibration/master-themes/Slide6.png) | literal Arial on B | fits | none |
| [7](calibration/master-themes/Slide7.png) | A minor again → Arial | fits | none |
| [8](calibration/master-themes/Slide8.png) | inherited minor token on B → Courier New | overflows right | `PPT003` ERROR |

Running commit `d1865a8` on this exact input produces only
`PPT003` ERROR at `slide3/FIT_B_wide`: **three false negatives and one false
positive**. The new reader agrees with all five clean controls and three
defects. The checker's advances on the evidence host are 106.64pt for twenty
i's in Arial, 288.05pt in Courier New, and 133.36pt in Times New Roman.
Ten W's are 144.02pt in Courier New, versus 226.52pt in Arial. These are
font-table calculations, not pixel-derived Office measurements.

## Reader, confidence and rule contract

- An effective `+mn-lt` or `+mj-lt` token uses the owning master's minor or
  major Latin face. An absent family retains the existing minor-theme default,
  now relative to the owner. The implemented run, paragraph, list-style,
  placeholder, master-text-style and presentation-default precedence is
  unchanged. Literal font names still override themes.
- Theme resolution is lazy: literal-font text does not require an otherwise
  unused theme dependency. Resolved themes are cached by part, then associated
  with the actual slide part, so A/B/A slide order cannot leak fonts.
- Missing, ambiguous, external, wrong-type or unreadable required dependencies,
  invalid internal targets/roots, or a missing requested Latin family produce
  `PKG002` ERROR. Reading aborts; no partially measured deck is returned and
  coverage is skipped. There is no first-theme or hard-coded Calibri fallback.
  An unused missing major/minor entry does not block the other face.
- Slide/layout [theme overrides can contain a font scheme](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.themeoverride.fontscheme?view=openxml-3.0.1).
  Full override semantics are **not implemented** here. When themed text
  encounters such a font scheme, the reader explicitly rejects it with
  `PKG002` and says the text was not measured. Valid-root color/effect-only
  overrides do not affect this font choice; their appearance is not checked.
- Existing font availability, substitution confidence and 5% overflow tolerance
  still apply. Correct theme selection does not turn fallback metrics into
  exact metrics: fallback overflow remains WARN/Estimated. These three large,
  exact-or-metric-font overruns qualify for the existing `PPT003` ERROR rule.
  No new code, threshold, baseline format or JSON schema is introduced.
- The Python layout model's `Deck.slide_theme_fonts` contains independent maps
  keyed by one-based presentation position, only for slides that needed theme
  resolution. The legacy `Deck.theme_fonts` diagnostic now contains only entries
  common to those resolved slides; it can be empty for a mixed or literal-only
  deck. Neither diagnostic is a global font source for measuring text.

Regressions cover owner-specific caches, slide reordering, unrelated themes
and ZIP order, relative/absolute/encoded targets, unconventional theme folders,
literal overrides, each implemented inheritance level, hard breaks, reduced
font confidence, missing faces, broken chains and the override boundary. These
mutations are synthetic checks, not additional Office renderer observations.

## Limits and remediation

The observation set covers one Mac Office build, not Windows/web rendering or
independent review. Placeholder inheritance remains Partial. Shape-style
`a:fontRef` selection, full font-scheme overrides, script/language-specific
supplemental fonts, complex-script shaping and Strict PresentationML remain
outside this change. Existing EA/CS token aliases still select the corresponding
Latin major/minor family; this is not native EA/CS font resolution.

For a required dependency error, repair the producer's relationship/theme or
inspect a new copy in PowerPoint; do not guess another master's font. For an
unsupported font-scheme override, a producer can emit an equivalent supported
master theme or explicit fonts and verify the resulting file. For these three
`PPT003` defects, widen the affected box or reduce text/font size. The checker
does not edit presentations. Findings changed by corrected fonts may require
baseline review. The original reference DOCX/PPTX corpus is unchanged.
