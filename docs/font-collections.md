# Font collections: face selection and Office evidence

P1 item 2 is closed for **static TTC/OTC member-index propagation**. The chosen
member now survives discovery, substitution grading, Latin-coverage checks,
caching and metric loading. This is not full variable-font or weight matching.

## Failure and contract

A collection is one file containing several faces. Previously, the directory
index recorded a member number but resolution discarded it and metric loading
always read member zero. There was a second fault: closing the first lazy
member closed the stream shared by the others, preventing subsequent name
reads. Keeping the collection open until enumeration finishes fixes discovery;
preferring canonical Regular/Bold/Italic names prevents later Light/Heavy
members from displacing them. Preferred subfamily names are used when present.
See the upstream [TTCollection implementation](https://fonttools.readthedocs.io/en/latest/_modules/fontTools/ttLib/ttCollection.html)
and the [TTFont `fontNumber` parameter](https://fonttools.readthedocs.io/en/latest/ttLib/ttFont.html).

`ResolvedFace.face_index` is a zero-based member number, defaulting to zero for
standalone fonts and existing four-argument construction. The metric loader
opens that member, including when the family was substituted. Coverage caches
include both path and member number; metrics remain keyed by requested family,
bold and italic. `doctor --json` exposes `face_index` for each successful font
probe; the human capability detail also identifies the measurement face.

Fontconfig discovery requests the [file, family and index properties](https://fontconfig.pages.freedesktop.org/fontconfig/fontconfig-user.html).
Malformed indices are not guessed as zero: discovery may instead use the
directory scanner. Encoded named variable-font instances are rejected as
unavailable rather than masking off their variation selection. FreeType
[uses the high bits for named-instance selection](https://freetype.org/freetype2/docs/reference/ft2-face_creation.html);
measuring the base member would not honour that request. Invalid collection
members also fail instead of silently loading member zero.

## Renderer evidence

- Renderer: **Microsoft PowerPoint for Mac 16.112.3**, macOS Apple Silicon,
  observed locally on 2026-09-06.
- Input: [`corpus/pptx-font-collections.pptx`](../corpus/pptx-font-collections.pptx),
  SHA-256 `ec1c455f3d9b01007dc2a32c21940a1e9e655555046bc785d6780397ee1fb265`.
- Native **File → Export → PNG → Save Every Slide**, 960 × 540. All six PNGs
  were inspected individually at full size. No repair prompt, input edits or
  resave. These are Office exports, not the fixture-authoring tool's renders.
- Installed `/System/Library/Fonts/Times.ttc`: Regular 0, Bold 1, Italic 2,
  Bold Italic 3. The checker resolves these faces exactly on the evidence host.
- [Provenance, font/fixture/image hashes and measured advances](calibration/font-collections/evidence.json).
  The synthetic fixture and renders use the project's MIT licence. No font
  binaries or personal document content are redistributed.

Each slide has one native text box, authored with `@oai/artifact-tool` and
validated for package integrity, geometry, font policy and import before
opening it in PowerPoint. The blue outline is the actual shape boundary.
Times is explicitly 24pt, wrap/autofit are off, insets are zero and height is
60pt throughout. Intentional horizontal overflow is preserved.

| Slide / render | Face / member | Text | Box width | Measured advance | Office observation / expected finding |
|---|---|---|---:|---:|---|
| [1](calibration/font-collections/Slide1.png) | Regular / 0 | 20 × r | 180pt | 159.84pt | clean |
| [2](calibration/font-collections/Slide2.png) | Bold / 1 | 20 × r | 180pt | 213.05pt | overflows; `PPT003` ERROR |
| [3](calibration/font-collections/Slide3.png) | Bold / 1 | 20 × r | 240pt | 213.05pt | clean |
| [4](calibration/font-collections/Slide4.png) | Italic / 2 | 10 × W | 212pt | 199.92pt | clean |
| [5](calibration/font-collections/Slide5.png) | Bold Italic / 3 | 20 × r | 172pt | 186.80pt | overflows; `PPT003` ERROR |
| [6](calibration/font-collections/Slide6.png) | Bold Italic / 3 | 20 × r | 220pt | 186.80pt | clean |

These are checker advance measurements, **not pixel-derived Office widths**.
All six renders show one line and agree on overflow versus fit. Running the
preceding checker, commit `a66ae3b`, on this exact input yields only a false
`PPT003` on slide 4 (member-zero width 226.52pt). It misses slides 2 and 5
(member-zero width 159.84pt). The fix removes that false positive and detects
both defects; all four clean controls remain free of WARN/ERROR findings.

## Confidence, regression coverage and remediation

No rule codes, severity thresholds or substitution grades change. `PPT003`
still requires more than 5% horizontal excess for ERROR with trustworthy
metrics; the two defects exceed that threshold by 18.36% and 8.60%. Approximate
substitution still reduces severity to WARN. Selecting the correct face also
affects wrapping and `PPT001` height estimates; it does not turn unsupported
layout or text shaping into checked coverage.

Cross-platform tests create original empty-outline TrueType TTC and **CFF OTC**
collections with different advances, vertical metrics and character coverage
per member. They cover nonzero regular/styled members, cache isolation, all
substitution routes, Fontconfig indices, malformed/unsupported indices,
preferred names and standalone-font compatibility. A separate synthetic
collection with approximate advance ratios exercises all six committed slide
geometries through the full checker without requiring proprietary fonts.
These synthetic tests are **not additional Office observations**. Fixture
geometry, declared styles and all image hashes are pinned in the suite.

For a reported overflow, widen the text box or reduce the text/font size and
check the result in the target renderer. When machines disagree, compare the
installed font build and selected member, not just the family name. Missing
or unsuitable fonts should be corrected before suppressing a layout finding.

## Limits

Office evidence covers one Mac build and one static TTC. CFF OTC loading is
covered synthetically, not by an OTC-specific Office render. Windows/web
rendering, independent review, arbitrary weights, synthesized missing styles,
variable axes/named instances, embedded fonts, GPOS and complex shaping remain
outside this change. Font discovery and the overall metric-support row remain
**Partial**. The original reference DOCX/PPTX corpus is unchanged.
