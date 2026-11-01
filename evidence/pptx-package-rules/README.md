# The package of a `.pptx`, checked as PowerPoint reads it

**`XML001`, `PKG003`–`PKG005`, `PKG011`, `PKG012`, `REL001`, `REL002` and
`REL004` for `.pptx`, unreleased.** Through 0.8.4 `check_pptx` read only what
the layout checks need: `ppt/presentation.xml` by its name, the slides it lists
and their layouts, masters and themes. A deck without `[Content_Types].xml` or
`_rels/.rels`, with a declaration written twice or a relationship to nothing,
was reported clean; of the 36 variants below it reported one. The package
rules ran on Word documents only, and the coverage report said so
(`pptx.package-integrity: unsupported`).

PowerPoint for Mac 16.114.3 on macOS 27.0.1 treats these defects as Word does.
Every variant whose defect Word refuses PowerPoint refused too: it showed
"PowerPoint found a problem with content in … PowerPoint can attempt to repair
the presentation", and after **Cancel** opened nothing. It opened every
variant Word opens. The rules now run on decks with that wording; two
differences from Word are below.

## The seed

[`powerpoint-seed.pptx`](powerpoint-seed.pptx) is PowerPoint's own:
PowerPoint made a new presentation of two slides,
`python research/pptx_package.py media` added a picture and a hyperlink to
slide 2, and PowerPoint opened that file and saved it under this name,
rewriting every entry. Like Word, PowerPoint writes an `Override` for every
XML part next to an `xml` `Default`.

## Variants

`python research/pptx_package.py build evidence/pptx-package-rules/variants`
writes them from the seed. Each changes, removes or adds one entry, two for
`override-capitals`, `rels-by-override`, `slide-uncovered` and
`custom-xml-namespace`; every other entry keeps its name, order, timestamp,
compression method and content, and the build is byte-for-byte reproducible.
PowerPoint opened each alone on 29 October 2026; nothing was saved.

| File | Change | PowerPoint | Finding |
| --- | --- | --- | --- |
| [default-repeated](variants/default-repeated.pptx) | the `xml` `Default` written twice | refused | `PKG011` |
| [default-conflicting](variants/default-conflicting.pptx) | a second `xml` `Default`, `text/xml` | refused | `PKG011` |
| [default-case](variants/default-case.pptx) | a second `Default` for `XML` | refused | `PKG011` |
| [override-repeated](variants/override-repeated.pptx) | slide 2's `Override` written twice | refused | `PKG011` |
| [override-conflicting](variants/override-conflicting.pptx) | a second slide 2 `Override`, `application/xml` | refused | `PKG011` |
| [override-case](variants/override-case.pptx) | a second `Override` for `/PPT/SLIDES/SLIDE2.XML` | refused | `PKG011` |
| [name-plain](variants/name-plain.pptx) | an `Override` for `/ppt/nothere.xml`, which the deck lacks | opens | — |
| [name-space](variants/name-space.pptx), [name-percent](variants/name-percent.pptx), [name-hash](variants/name-hash.pptx) | the same, with `%20`, `%25` or `%23` in it | opens | — |
| [name-letter-upper](variants/name-letter-upper.pptx), [name-letter-lower](variants/name-letter-lower.pptx), [name-digit](variants/name-digit.pptx), [name-tilde](variants/name-tilde.pptx) | the same, escaping an unreserved character | refused | `PKG012` |
| [name-non-ascii](variants/name-non-ascii.pptx), [name-slash](variants/name-slash.pptx), [name-backslash](variants/name-backslash.pptx), [name-malformed](variants/name-malformed.pptx) | the same, escaping `é`, `/` or `\`, or with `%ZZ` | refused | `PKG012` |
| [no-xml-default](variants/no-xml-default.pptx) | the `xml` `Default` removed | opens | — |
| [override-capitals](variants/override-capitals.pptx) | and slide 2's `Override` names `/PPT/SLIDES/SLIDE2.XML` | opens | — |
| [types-missing](variants/types-missing.pptx) | `[Content_Types].xml` removed | refused | `PKG003` |
| [rels-default-missing](variants/rels-default-missing.pptx) | the `rels` `Default` removed | refused | `PKG004` ERROR |
| [rels-by-override](variants/rels-by-override.pptx) | the `rels` `Default` replaced by an `Override` for every relationship part | opens | `PKG004` WARN |
| [png-uncovered](variants/png-uncovered.pptx) | the `png` `Default` removed | refused | `PKG005` |
| [slide-uncovered](variants/slide-uncovered.pptx) | the `xml` `Default` and slide 2's `Override` removed | refused | `PKG005` |
| [relationship-repeated](variants/relationship-repeated.pptx) | slide 2's image relationship written twice | refused | `REL004` |
| [relationship-conflicting](variants/relationship-conflicting.pptx) | a hyperlink relationship added with the image relationship's `Id` | refused | `REL004` |
| [hyperlink-dangling](variants/hyperlink-dangling.pptx) | the hyperlink's `r:id` names an `Id` slide 2 lacks | refused, prompt after the window opened | `REL001` |
| [embed-dangling](variants/embed-dangling.pptx) | the picture's `r:embed` names an `Id` slide 2 lacks | opens; "The picture can't be displayed." | `REL001` |
| [target-missing](variants/target-missing.pptx) | the image relationship targets a part the deck lacks | opens; "The picture can't be displayed." | `REL002` ERROR |
| [thumbnail-missing](variants/thumbnail-missing.pptx) | the thumbnail the package relationships name removed | opens | `REL002` WARN |
| [office-document-missing](variants/office-document-missing.pptx) | the `officeDocument` relationship removed | refused | `REL001` |
| [root-rels-missing](variants/root-rels-missing.pptx) | `_rels/.rels` removed | refused | `REL001` |
| [slide-malformed](variants/slide-malformed.pptx) | slide 2's closing `</p:sld>` removed | refused, prompt after the window opened | `XML001` ERROR (and `PKG002`, as before) |
| [unreferenced-malformed](variants/unreferenced-malformed.pptx) | a malformed `ppt/unused.xml` no relationship reaches | opens | `XML001` WARN |
| [custom-xml-namespace](variants/custom-xml-namespace.pptx) | a custom XML item related from the presentation, its namespace name `$ListId:Shared Documents;` | opens | — ([namespace names](../xml-namespace-names/README.md)) |
| control: `powerpoint-seed.pptx` | — | opens, before and after; 2 slides, the picture, the hyperlink | — |

Unless marked, a finding is an ERROR. [observations.json](observations.json)
records each file's SHA-256, the change, the prompt PowerPoint showed and how
it was answered, what the object model read in decks that opened, and the
findings.

## The rules for a deck

The same rules as for a Word document, with PowerPoint's behaviour in the
message: "PowerPoint asks to repair the presentation" where Word's says it
asks to recover the document. Two differ from Word's:

- **A reference to a missing relationship (`REL001`)** "asks to repair the
  presentation or shows the object as missing": PowerPoint refused the
  hyperlink and showed the picture as a frame reading "The picture can't be
  displayed".
- **A relationship to a missing part (`REL002`)** is a WARN when the part is
  the package thumbnail or a SmartArt drawing, which PowerPoint opens the deck
  without: it draws SmartArt from its data. Any other missing target stays an
  ERROR; a missing picture is drawn as one that can't be displayed.

Not run on decks: `PKG006` and `PKG009`, which read the main part as
WordprocessingML (`read_deck` still reports a Strict deck as `PKG009`),
`PKG010`, whose relationship types are Word's, and `REL003`: PowerPoint relates
slide layouts, masters and properties without naming them in the source part,
so most relationships of a deck would look unused. An archive that cannot be
read is reported as before. The coverage report now marks
`pptx.package-integrity` as checked.

## Public decks

Over the 610 public PPTX, POTX and PPSX files of the
[real-world corpora](../../docs/real-world-corpora.md), findings change in 22
decks, all LibreOffice's or Apache POI's, and only by additions: ERRORs in 5
decks and WARNs in 17. PowerPoint refused each of the five and opened each of
the three WARN decks it was shown, LibreOffice's at commit `382bad999f5d`:

| Deck | Findings | PowerPoint |
| --- | --- | --- |
| `bnc591147.pptx` | 2 `PKG005`: `ppt/media/video.avi` and `audio.mp3` without a content type | refused |
| `n862510_1.pptx`, `predefined-table-style.pptx` | `PKG005`: `ppt/slides/.slide1.xml.swp` | refused |
| `tdf148478_transitionMusic.pptx` | `PKG012`: an `Override` for `/ppt/media/Cort%C3%A1zar.wav`, and `PKG005` for the part it meant | refused |
| `tdf169781.pptx` | 9 `REL001`, 34 `REL002` ERROR | refused |
| `BoldonseFontEmbedded.pptx` | `REL002` WARN: the thumbnail | opens |
| `smartart-autoTxRot.pptx` | 3 `REL002` WARN: SmartArt drawings | opens, with every SmartArt graphic |
| `smoketest.pptx` | `PKG004` WARN: relationship parts declared by `Override` | opens |

The other 14 WARN decks have `PKG004` WARN for the same reason. LibreOffice's
`tdf89927.pptx`, whose custom XML part declares `$ListId:Shared Documents;`,
opened and gets no finding. No finding of a deck in this repository changes.

## Limits

- One PowerPoint build, on one seed deck and nine public decks. PowerPoint for
  Windows and PowerPoint on the web were not checked.
- `REL001` was shown to PowerPoint for a hyperlink, a picture and the package
  entry point; other references, such as charts, OLE objects or embedded
  fonts, keep the rule's wording without a check of their own.
- `.potx` and `.ppsx` files get the same checks; only `.pptx` files were
  opened.
- The operator was Claude Code driving PowerPoint through AppleScript, with the
  maintainer's permission, and was not blind to the expectations. A first pass
  counted a deck whose prompt came after its window opened as opened, and was
  discarded. An installed Adobe PDF add-in raised a Visual Basic error on each
  open, dismissed with **End**; it is unrelated to the decks.
