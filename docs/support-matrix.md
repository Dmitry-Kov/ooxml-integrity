# Support matrix

This page describes the checks the current implementation actually performs.
The unit of support is the row in the tables below, not the whole file format.
OOXML is large, and reading a part successfully does not mean that every
construct in that part was validated.

## What the statuses mean

| status | meaning |
| --- | --- |
| **Supported** | The stated condition is checked directly. The status applies only to the parts, elements and preconditions named in the row. |
| **Partial** | A useful check exists, but only for a named subset, or its verdict depends on the producer, renderer, installed fonts or another stated limitation. |
| **Not checked** | The checker makes no claim about this surface. The package may still be opened or parsed while this content receives no semantic or layout check. |

**No findings does not mean that every surface in a file was checked.** It means
that no finding was produced by the supported and partial checks that applied to
that file. Content listed as **Not checked**, and unsupported variants within a
**Partial** row, may still be broken, missing or rendered differently.
The current CLI does not emit a complete inventory of unsupported constructs it
encountered, so absence of an "unsupported" finding is not evidence of coverage.

## DOCX self-consistency

The DOCX inspector works on Transitional WordprocessingML namespaces. Unless a
row says otherwise, the Word-specific checks below inspect matching descendants
of the main document part, `word/document.xml`.

### Package and relationships

| surface | status | current scope |
| --- | --- | --- |
| ZIP/package readability | **Supported** | Reports a missing file, an invalid ZIP and a corrupt ZIP member. |
| XML well-formedness | **Supported** | Parses every package member whose name ends in `.xml` or `.rels` and reports XML syntax errors. This is not schema validation. |
| DTDs and XML entities | **Supported** | OOXML parts are parsed with DTD loading, entity expansion and network access disabled. A part containing a `DOCTYPE` is rejected. |
| Archive resource budgets | **Supported** | Before member decompression, enforces configurable limits for entry count, compressed archive bytes, total and per-entry expanded bytes, and per-entry compression ratio. The declared EOCD count and archive byte size are checked before the ZIP central directory is loaded. Defaults and measurements are documented in [archive resource limits](archive-limits.md). |
| Package part names | **Supported** | Rejects absolute, traversal-like, backslash-separated and otherwise non-canonical member names, plus names that collide after percent-decoding and OPC's ASCII-case-insensitive comparison. This is package-name validation, not malware scanning. |
| Content-type coverage | **Partial** | Requires `[Content_Types].xml`, checks that package members are covered by an extension default or part override, and requires a default for `.rels`. It does not verify that a declared content type is the correct one for the part. |
| Root office-document relationship | **Partial** | Requires `_rels/.rels` to contain an `officeDocument` relationship with a non-empty, non-external target, and the package-wide target check requires that target to exist. The Word semantic checks still require the conventional `word/document.xml`; the relationship target and that hard-coded main part are not cross-validated as one entry point. |
| Internal relationship targets | **Supported** | Checks `_rels/.rels` and every successfully parsed companion `*_rels/*.rels` present in the package. Every internal relationship must have a non-empty target that resolves to an existing package member. A malformed relationship part receives `XML001`; its targets cannot then be inspected. External targets are not fetched or tested. |
| Relationship references from XML | **Partial** | For each parseable XML source part, checks Transitional relationship attributes `r:id`, `r:embed` and `r:link` against that part's companion relationship set; a referenced id with no companion part does not resolve. Other relationship-bearing attributes and Strict OOXML namespaces are not covered. |
| Unused relationships | **Partial** | Emits informational `REL003` findings for explicit relationships unused by a parseable XML source part. Root relationships and known package-level/implicit relationship types are excluded. This is a diagnostic, not a proof that every declared relationship is necessary. |
| Full ECMA-376 schema validation | **Not checked** | The project does not bundle or run the complete OOXML XSD set. |
| Strict OOXML | **Not checked** | Strict namespace variants are not recognised by the Word-specific rules or by relationship-reference scanning. |
| Encryption, signatures and broader package security | **Not checked** | Encryption validity, digital signatures, macros, embedded-object safety, external-link safety and malware are outside the current scope. Resource budgets constrain ZIP expansion but do not make the checker a malware scanner. |

The package-wide relationship checks cover missing targets and the named
relationship attributes in headers, footers and other XML parts. They do not
extend the Word semantic checks below to those parts.

### WordprocessingML structures

| surface | status | current scope |
| --- | --- | --- |
| Styles | **Partial** | Checks paragraph, run and table style references found in `word/document.xml`; also checks `basedOn`, `next` and `link` references in `word/styles.xml`. It does not compare style definitions with a source or predict rendered formatting. |
| Numbering | **Partial** | Checks `numId -> abstractNumId -> abstractNum` resolution and referenced levels for numbering found in `word/document.xml`. Numbering used in other package parts is not inspected semantically. |
| Footnotes | **Partial** | Checks footnote references in `word/document.xml` against `word/footnotes.xml` and reports non-housekeeping footnotes with no reference in that main part. It does not lay out or render footnotes. |
| Comments | **Partial** | Checks range starts, range ends and comment references in `word/document.xml` against `word/comments.xml`. Modern comment threads, replies, resolved state and people metadata are not validated semantically. |
| Tracked changes | **Partial** | Checks revision-id collisions and `w:t`/`w:delText` use inside insertions and deletions in `word/document.xml`, including legal nested revisions. It does not judge whether an edit should have been tracked, or validate author/date metadata and every revision type. |
| Tables | **Partial** | Checks that tables in `word/document.xml` have `tblGrid` and compares each direct row's effective cell span with the grid width. Merges, layout, widths, borders and rendered appearance are not otherwise validated. |
| Content controls | **Partial** | Checks that `w:sdt` elements in `word/document.xml` contain `w:sdtPr` and `w:sdtContent`. Bindings, custom XML, field semantics and displayed values are not checked. |
| Edge whitespace | **Partial** | Reports `w:t` nodes in `word/document.xml` with leading or trailing whitespace but no `xml:space="preserve"`. It does not perform general text normalisation checks. |
| Images, charts and embedded objects | **Partial** | Package-wide relationship checks can detect a missing internally related part when it is referenced through a covered attribute. Image/chart content, dimensions, cropping, accessibility and rendering are not checked. |
| Headers and footers | **Partial** | Their XML and relationships receive package-wide syntax and relationship checks. Their styles, numbering, comments, revisions, tables, text and visual layout are not checked by the main-story semantic rules. |
| Document layout and pagination | **Not checked** | Page count, line and page breaks, clipping, overlap, font substitution and Word rendering are not predicted. |
| Fields, equations, citations and bibliography semantics | **Not checked** | These may be parsed as XML, but their correctness and displayed values are not evaluated. |

## DOCX fidelity against a source

Fidelity checks run only when an edited DOCX is checked with `--against` or
through `compare(source, edited)`. They report structural loss; they do not
decide whether the requested prose or business change was correct.
An unreadable source produces `FID000` as an error, so the default threshold
cannot report success without the requested comparison.

| surface | status | current scope |
| --- | --- | --- |
| Main-document construct counts | **Supported** | Compares counts of comment and footnote references, insertions, deletions, content controls, drawings, tables, hyperlinks, paragraph and character style references, numbered-list properties and table-header markers among all descendants of `word/document.xml`. Loss and addition are reported separately. |
| Comment, footnote and endnote bodies | **Supported** | Compares normalised body text as a multiset, independent of item ids. Whitespace-only reflow is ignored; losing one of two identical bodies is still detected. |
| Main-document text volume | **Partial** | Reports when concatenated descendant `w:t` text in `word/document.xml` falls below 95% of the source length. This is a coarse loss detector, not a semantic diff. |
| Identifier preservation | **Not checked** | Legitimate renumbering is allowed. Except for self-consistency rules such as revision-id collision, fidelity does not require ids to remain unchanged. |
| Header/footer and other-part fidelity | **Not checked** | Apart from the comment, footnote and endnote body comparison named above, text and constructs in `word/header*.xml`, `word/footer*.xml`, glossary parts and other package parts are not compared with the source as fidelity surfaces. |
| Style, numbering, settings and relationship fidelity | **Not checked** | Definitions and package graphs are checked for some forms of self-consistency, but they are not compared source-to-output for semantic equivalence. |
| Media and embedded-part fidelity | **Not checked** | The comparison does not prove that images, charts, embedded files or custom XML retained the same bytes or meaning. |
| Intended edits and semantic correctness | **Not checked** | A structurally intact file can still contain the wrong amount, name, clause, slide text or other business content. |

## PPTX layout

The PPTX reader currently models slide-level `p:sp` shapes with a `p:txBody`.
It does not run the DOCX package inspector over a presentation.

### Text and geometry

| surface | status | current scope |
| --- | --- | --- |
| Slide size and slide parts | **Partial** | Reads `p:sldSz` and numbered `ppt/slides/slideN.xml` parts, with built-in defaults when slide size is absent. Slides are ordered by the number in the part name rather than by the presentation's `p:sldIdLst`. |
| Plain text shapes | **Supported** | Reads ungrouped slide-level `p:sp` geometry, text-body insets, wrapping, vertical anchor metadata, paragraphs, ordinary `a:r` runs and hard `a:br` breaks. The vertical anchor is retained but does not change the fit calculation. |
| Placeholder inheritance | **Partial** | Resolves missing shape geometry from a matching layout placeholder and resolves text properties through shape, layout, master, presentation defaults and the first theme. Complex or ambiguous placeholder chains have no separate coverage claim. |
| Effective font size and family | **Partial** | Resolves run and paragraph defaults, list styles, placeholder styles, master text styles, presentation defaults and major/minor theme faces for the properties implemented. East Asian and complex-script theme faces are treated as the corresponding major/minor family rather than shaped separately. |
| Word wrapping and hard breaks | **Partial** | Uses greedy word wrapping and explicit hard breaks. A token wider than a whole line is not broken by character in this model. Fields (`a:fld`), hyphenation, language-specific breaking, tabs and advanced shaping are not modelled. |
| Vertical text overflow | **Supported** | For measured `p:sp` text, compares calculated text height with the usable text-box height and reports clear or borderline overflow. Mixed run sizes, paragraph spacing, insets and stored line-space reduction are included within the implemented model. |
| No-wrap horizontal overflow | **Supported** | Reports a measured line that exceeds the usable width when word wrap is disabled. Horizontal excess with wrapping enabled, including an unbreakable long token, does not produce `PPT003`. |
| Borderline fit | **Supported** | Width/height results within the 5% tolerance band are reported as renderer-dependent rather than as authoritative overflow. |
| Off-slide geometry | **Partial** | Checks the unrotated rectangle of each read `p:sp`, with a 2pt tolerance. Other shape classes and the transformed bounds of rotated or grouped shapes are not covered. |
| Shape overlap | **Partial** | Checks axis-aligned overlap between two text-bearing, unrotated `p:sp` shapes and ignores intersections below 2% of the smaller rectangle. Z-order, transparency, clipping, visual glyph bounds and non-text shapes are not considered. |
| Rotated shapes | **Partial** | Rotation is read. Rotated shapes are excluded from overlap checks, and rotation is not applied to off-slide bounds. Text-direction and transformed-layout effects are not modelled. |
| Grouped shapes | **Not checked** | Nested `p:sp` elements may be encountered, but group coordinate transforms are not composed; findings for grouped geometry are therefore outside the supported surface. |
| PowerPoint tables | **Not checked** | Text and geometry in `p:graphicFrame/a:tbl` are not read by the layout model. |
| SmartArt and charts | **Not checked** | Diagram and chart text, generated layout and related data are not measured. |
| Pictures, connectors, media and embedded objects | **Not checked** | Their bounds, overlap, clipping, relationships and content are not checked by `check_pptx`. |
| Master/layout-only objects | **Not checked** | Layout and master parts are consulted for placeholder inheritance, but objects that appear only on a master or layout are not independently checked for fit or geometry. |
| Vertical and non-horizontal text | **Not checked** | DrawingML vertical-text modes, text rotation within a body and other non-horizontal layout are not modelled. |

### Fonts and autofit

| surface | status | current scope |
| --- | --- | --- |
| Installed TrueType/OpenType metrics | **Partial** | Measures advances from `cmap`/`hmtx` and legacy `kern` tables in discoverable font files. Standalone TTF/OTF faces are the direct path; TTC/OTC collections are indexed, but selection of the intended face within a collection has not been separately validated. No renderer is launched. |
| Exact installed face | **Supported** | An exact family match is treated as trustworthy for the implemented advance-width model. This does not add GPOS/GSUB shaping. |
| Metric-compatible substitution | **Partial** | Known substitutes are treated as trustworthy. Only the Calibri/Carlito pair has direct cross-machine measurements in this repository; other declared pairs have not received the same validation. |
| Similar or last-resort substitution | **Partial** | A measurement is still attempted, but the result is marked as an estimate through `PPT007`; affected overflow severity is reduced when the face is not trustworthy. |
| No usable fonts | **Supported** | Emits `PPT000` instead of reporting a clean text-layout result. Geometry checks can still run. |
| Embedded fonts | **Not checked** | Fonts embedded in a presentation are not loaded from the package by the layout model. |
| Kerning and shaping | **Partial** | Legacy `kern` pairs are applied. GPOS kerning, GSUB substitution, ligature shaping, bidirectional layout and complex-script shaping are not implemented. |
| Stored `normAutofit` result | **Partial** | Applies stored `fontScale` and `lnSpcReduction`. If shrink-to-fit is requested but no scale is stored, `PPT005` reports renderer dependence. |
| `spAutoFit` grow-shape behaviour | **Not checked** | Shapes requesting grow-to-fit are skipped by the overflow finding logic. Current PowerPoint-for-Mac evidence shows that the box was not recomputed merely by opening the file, so no clean verdict should be inferred for this mode. |

### Presentation integrity and fidelity

| surface | status | current scope |
| --- | --- | --- |
| PPTX ZIP readability and resource budgets | **Supported** | A missing file or unreadable ZIP produces `PKG000` or `PKG002`; the same `PKG007` resource budgets and `PKG008` name checks used for DOCX run before PPTX parts are loaded. |
| POTX and PPSX routing | **Partial** | The CLI sends `.potx` and `.ppsx` through the same reader, but the committed corpus and renderer evidence cover `.pptx` only. |
| PPTX XML/package/relationship integrity | **Not checked** | `check_pptx` follows the relationships it needs for layout but does not validate the complete OPC graph, content types or well-formedness of every XML part. |
| Fidelity against a source PPTX | **Not checked** | An explicit `--against` emits `FID000` as an error with `comparison was NOT performed`; layout checks still run, but the default CLI result cannot pass without the requested comparison. |
| Notes, comments, transitions and animations | **Not checked** | Their presence, integrity and preservation are not evaluated. |
| Semantic correctness | **Not checked** | Correct text, numbers, chart data, reading order, accessibility and presentation intent are outside the current checks. |

## Producer and platform evidence

Evidence applies to the committed reference corpus. It is not a general
compatibility claim for every file produced by the named application.

| surface | evidence present | evidence not yet present |
| --- | --- | --- |
| DOCX corpus | One byte-reproducible synthetic package containing styles, numbering, footnotes, comments, tracked revisions, content controls, a table, an image, a hyperlink, header and footer; six clean and two defective real agent edit outputs. | A varied corpus of real customer documents and systematic coverage of files authored by multiple Office suites. |
| DOCX observed rendering | The key detached-comment case was inspected in Word for Mac. Twenty mutation cycles were converted by LibreOffice without it reporting the structural losses. | Word for Windows behaviour, Word Online, Google Docs and systematic DOCX checks in ONLYOFFICE. |
| PPTX corpus | One byte-reproducible deck built with `python-pptx`, containing 24 deliberately chosen plain text-shape cases. | Real customer decks, tables, SmartArt, grouped/rotated content, charts and broad producer diversity. |
| PowerPoint evidence | PowerPoint for Mac, Microsoft 365 on Apple Silicon, in editing view: 21 non-excluded reference shapes agreed with the predicted fit and line count. | PowerPoint for Windows, PowerPoint Online, mobile clients and Slide Show mode. |
| Other PPTX renderers | LibreOffice and ONLYOFFICE PDF exports agreed on line count for 23 of 24 reference shapes; the one disagreement is treated as renderer-dependent. | Google Slides and broader decks across renderer versions and platforms. |
| Runtime platforms | The automated test matrix runs the Python package on Linux, macOS and Windows, and on Python 3.9 through 3.13 where applicable. | Running on an operating system does not establish agreement with every Office renderer on that system. |
