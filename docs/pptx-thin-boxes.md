# Text boxes no taller than their insets

A `.pptx` text box whose height is no more than its top and bottom insets
leaves no room for text. Through 0.8.3 the checker reported nothing for text in
it: the overflow ratio of a box with no room was taken as 0, which reads as
"fits". A box 0.8pt taller, with almost no room, was reported as overflowing.
0.8.4 closes that gap.

## What is reported

- **Text taller than the shape itself:** `PPT001` ERROR (WARN when font
  metrics or line breaking are approximate). It is drawn outside the shape
  wherever the renderer puts it.
- **Text no taller than the shape:** `PPT001` WARN. When the insets are at least
  as tall as the shape, OOXML moves both insets until they meet; LibreOffice's
  import does the same (tdf#148321). So whether such text is drawn inside the
  shape depends on the renderer, and the message says so.
- Shrink-to-fit without a stored `fontScale` stays `PPT005`, as for any other
  box.

The message names the shape's height and its insets: "text needs 22pt in a
box with no room for text: it is 4.0pt tall and its top and bottom insets take
7.2pt".

## Evidence

[`corpus/pptx-thin-boxes.pptx`](../corpus/pptx-thin-boxes.pptx) is built by
`python research/pptx_thin_boxes.py build`, byte for byte: one 18pt line in
boxes 0, 4, 7.2, 8 and 40pt tall with the default insets (3.6pt top and
bottom), the 4pt box also centred and bottom-anchored and once without insets.
[`evidence.json`](calibration/pptx-thin-boxes/evidence.json) holds each
renderer's glyph positions. PowerPoint for Mac 16.114.1 and LibreOffice
25.8.4.2 both drew the text of every box from 0 to 8pt outside it, below under
`t`, above under `b` and on both sides under `ctr`, and the 40pt box's inside
it. The checker reports exactly the seven boxes drawn outside, all as errors;
before, it reported two of them.

PowerPoint places the text of a box without room by the OOXML rule that
LibreOffice's tdf#148321 import follows: it moves each inset by half their
excess over the height, so the text area is a line `(top - bottom + height) /
2` from the top of the box — 0pt in the 0pt box, 2.0pt in the 4pt box and
3.6pt in the 7.2pt box. The text hangs below that line under `t`, centres on
it under `ctr` and stands on it under `b`. LibreOffice's text boxes put the line
elsewhere (0.5pt in the 4pt box), with the same verdicts.

## On public decks

Over the 605 PPTX files of the [real-world corpora](real-world-corpora.md), 72
findings are new and every other finding is unchanged:

- 2 ERROR in LibreOffice's `tdf165732.pptx`, two Google Slides shapes 10.4pt
  tall with 11.3pt of insets and a 17pt line;
- 70 WARN in LibreOffice's `TextDistancesInsets1`–`3` decks, which test insets
  larger than a 2cm shape with one to three short lines.

## Limits

- One PowerPoint build, on one Mac, with one font. PowerPoint for Windows and
  PowerPoint on the web were not rendered.
- Text no taller than the shape stays a WARN. With PowerPoint's placement
  known, it could be checked against the shape's outline instead; that is not
  done.
- Only the case with no room at all changed. Text that overflows its insets but
  stays inside the shape's outline, in a box with some room, is reported as
  before.
