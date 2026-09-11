# Support matrix

This page describes what the current checker can assess. Each table row defines
the scope of one check, including the parts and constructs it reads. A package
can be read successfully while some of its content remains unchecked.

## What the statuses mean

| status | meaning |
| --- | --- |
| **Supported** | The stated condition is checked directly. The status applies only to the parts, elements and preconditions named in the row. |
| **Partial** | A useful check exists, but only for a named subset, or its verdict depends on the producer, renderer, installed fonts or another stated limitation. |
| **Not checked** | The checker makes no claim about this surface. The package may still be opened or parsed while this content receives no semantic or layout check. |

When a file has no findings, none of the supported or partial checks that ran
found a problem. Content listed as **Not checked**, and unsupported variants
within a **Partial** row, may still be broken, missing or rendered differently.

Use `check ... --coverage` for a per-file inventory. It distinguishes a
supported surface that was checked, a supported surface that was not present,
an estimated result, a check that was skipped with a reason, and a recognised
construct that is unsupported. The default human view shows only confidence
gaps; `--coverage-details` shows every item, and `--json` adds the complete
machine-readable block. See [coverage and doctor](coverage.md).

## DOCX self-consistency

The DOCX inspector works on Transitional WordprocessingML namespaces. Unless a
row says otherwise, the Word-specific checks below inspect matching descendants
of the main document part, `word/document.xml`.

### Package and relationships

| surface | status | current scope |
| --- | --- | --- |
| ZIP/package readability | **Supported** | Reports a missing file, an invalid or unsupported ZIP layout and a corrupt ZIP member. The supported single-disk ZIP/ZIP64 profile is defined in [archive resource limits](archive-limits.md). |
| XML well-formedness | **Supported** | Parses every package member whose name ends in `.xml` or `.rels` and reports XML syntax errors. This is not schema validation. |
| DTDs and XML entities | **Supported** | OOXML parts are parsed with DTD loading, entity expansion and network access disabled. A part containing a `DOCTYPE` is rejected. |
| Archive resource budgets | **Supported** | Before allocating the ZIP index, checks archive bytes, central-directory bytes, declared and actual entry counts, and consistent directory/trailer bounds using fixed-size reads. Before member decompression, enforces total and per-entry expanded-byte limits and per-entry compression ratios. The same limits apply to DOCX, PPTX and both comparison inputs. Defaults, supported ZIP layout and measurements are documented in [archive resource limits](archive-limits.md). |
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
| Styles | **Partial** | Checks paragraph, run and table style references found in `word/document.xml`, including when `word/styles.xml` is missing. Undefined `pStyle`/`tblStyle` references are `STY001` errors because they can carry numbering and structure; undefined `rStyle` references are `STY001` warnings, including comment reference marks. An absent styles part without main-document references is not a finding by itself. A malformed or unsafe styles part receives `XML001`; style resolution is skipped without a cascade of undefined-reference findings. Undefined `basedOn`, `next` and `link` references in readable `word/styles.xml` are `STY002` warnings. It does not compare style definitions with a source or predict rendered formatting. |
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

Fidelity checks run when an edited DOCX is checked with `--against` or through
`compare(source, edited)`. They look for structural loss. The requested wording
or business change still needs its own review. An unreadable source produces
`FID000` as an error, which prevents a successful result at the default
threshold when the requested comparison could not run.

| surface | status | current scope |
| --- | --- | --- |
| Main-document construct counts | **Supported** | Compares counts of comment and footnote references, insertions, deletions, content controls, drawings, tables, hyperlinks, paragraph and character style references, numbered-list properties and table-header markers among all descendants of `word/document.xml`. Loss and addition are reported separately. |
| Comment, footnote and endnote bodies | **Supported** | Compares normalised body text as a multiset, independent of item ids. Whitespace-only reflow is ignored; losing one of two identical bodies is still detected. |
| Header/footer story text | **Supported** | Resolves `default`, `first` and `even` header/footer references from every current `w:sectPr` through `word/_rels/document.xml.rels`, including [same-type inheritance from the preceding section](https://learn.microsoft.com/en-us/office/open-xml/word/how-to-replace-the-header-in-a-word-processing-document). Compares normalised descendant `w:t` text as a multiset of effective section slots. Relationship ids and part names may change, and shared parts may be split or merged without a finding. Explicitly referenced empty stories remain distinct because they can suppress an inherited story. Activation through `w:titlePg` and `w:evenAndOddHeaders` is not modelled separately; referenced first/even stories are preserved conservatively even when those display options are off. |
| Header/footer tracked constructs | **Partial** | Within the same effective story slots, compares counts of the constructs listed for main-document fidelity: comments and footnotes, insertions and deletions, content controls, drawings, tables, hyperlinks, style references, numbering and table-header markers. This preserves supported audit/structure signals but is not a semantic comparison of fields, settings, section geometry or rendered appearance. |
| Main-document text volume | **Partial** | Reports when concatenated descendant `w:t` text in `word/document.xml` falls below 95% of the source length. This is a coarse loss detector, not a semantic diff. |
| Identifier preservation | **Not checked** | Legitimate renumbering is allowed. Except for self-consistency rules such as revision-id collision, fidelity does not require ids, relationship ids or header/footer part names to remain unchanged. |
| Other-part fidelity | **Not checked** | Apart from the comment, footnote, endnote, and relationship-referenced header/footer comparisons named above, glossary parts and other package parts are not compared with the source as fidelity surfaces. |
| Style, numbering, settings and relationship fidelity | **Not checked** | Definitions and package graphs are checked for some forms of self-consistency, but they are not compared source-to-output for semantic equivalence. |
| Media and embedded-part fidelity | **Not checked** | The comparison does not prove that images, charts, embedded files or custom XML retained the same bytes or meaning. |
| Intended edits and semantic correctness | **Not checked** | A structurally intact file can still contain the wrong amount, name, clause, slide text or other business content. |

## PPTX layout

The PPTX reader currently models slide-level `p:sp` shapes with a `p:txBody`.
It does not run the DOCX package inspector over a presentation.

### Text and geometry

| surface | status | current scope |
| --- | --- | --- |
| Slide size and main slide order | **Supported** | Reads `p:sldSz` (built-in defaults if absent) and follows `p:sldIdLst` relationships from `ppt/presentation.xml` in Transitional PresentationML. One-based finding positions include hidden slides and do not depend on part names or ZIP order; unlisted parts are excluded. Invalid listed references/roots fail closed with `PKG002`. [Three native PowerPoint observations and regression limits](pptx-slide-order.md). Custom-show playback, footer numbering and relocated/Strict presentation roots are not supported. |
| Plain text shapes | **Supported** | Reads ungrouped slide-level `p:sp` geometry, text-body insets, wrapping, vertical anchor metadata, paragraphs, ordinary `a:r` runs and hard `a:br` breaks. The vertical anchor is retained but does not change the fit calculation. |
| Placeholder inheritance | **Partial** | Resolves missing shape geometry from a matching layout placeholder and resolves text properties through shape, layout, master, presentation defaults and the owning master's theme. Complex or ambiguous placeholder chains have no separate coverage claim. |
| Effective font size and family | **Partial** | Resolves run and paragraph defaults, list styles, placeholder styles, master text styles and presentation defaults for the properties implemented. Shape-style `a:fontRef` selection is not implemented. East Asian and complex-script theme aliases still select the corresponding Latin major/minor family; script-specific supplemental faces and shaping are not resolved. |
| Owning-master Latin theme faces | **Supported, bounded** | Major/minor Latin families follow each slide's typed internal layout → master → theme relationships; literal fonts retain precedence. Unrelated themes and ZIP order do not affect selection. Invalid required dependencies or missing requested faces fail closed with `PKG002` and skipped coverage. Slide/layout font-scheme overrides are explicitly rejected, not modelled; color/effect appearance is not checked. [Eight native PowerPoint observations, inheritance tests and scope](pptx-master-themes.md). |
| Word wrapping and hard breaks | **Partial** | Uses greedy word wrapping, explicit hard breaks and emergency character wrapping of overlong basic Latin letters/digits. Run boundaries do not create word boundaries. Resolves `latinLnBrk` through paragraph and available list-style defaults; when enabled it can use the remaining line width. Insets, resolved paragraph indent, per-run sizes and stored scale participate. [Twelve PowerPoint for Mac observations](pptx-long-tokens.md) document this behaviour. Character boundaries within 5% reduce confidence. Other scripts, punctuation-aware breaking, fields (`a:fld`), hyphenation and tabs remain unmodelled; overwide unsupported tokens are reported as estimates. |
| Text-box height overflow | **Supported** | For measured horizontal `p:sp` text, compares calculated text height with the usable text-box height and reports clear or borderline overflow. Mixed run sizes, paragraph spacing, insets and stored line-space reduction are included within the implemented model. |
| Horizontal overflow | **Supported / Estimated** | `PPT003` reports a measured line beyond the usable width with wrap off, or residual excess after supported character wrapping (e.g. one glyph wider than a whole line). Wrapped long Latin words normally produce extra lines and potentially `PPT001`, not a horizontal defect. More than 5% horizontal excess is required; approximate fonts or unmodelled breaking reduce severity to WARN. |
| Borderline fit | **Supported** | Predicted vertical overflow of up to 5% produces `PPT002`. Horizontal overflow of up to 5% of the box width does not trigger `PPT003`. Measurements near either limit may differ between renderers. |
| Off-slide geometry | **Partial** | Checks the unrotated rectangle of each read `p:sp`, with a 2pt tolerance. Other shape classes and the transformed bounds of rotated or grouped shapes are not covered. |
| Shape overlap | **Partial** | Checks axis-aligned overlap between two text-bearing, unrotated `p:sp` shapes and ignores intersections below 2% of the smaller rectangle. Z-order, transparency, clipping, visual glyph bounds and non-text shapes are not considered. |
| Rotated shapes | **Partial** | Rotation is read. Rotated shapes are excluded from overlap checks, and rotation is not applied to off-slide bounds. Text-direction and transformed-layout effects are not modelled. |
| Grouped shapes | **Not checked** | Group coordinate transforms are not composed. Nested `p:sp` elements are excluded from the plain-shape checks and the group is reported as `pptx.grouped-shapes: unsupported` in coverage output. |
| PowerPoint tables | **Not checked** | Text and geometry in `p:graphicFrame/a:tbl` are not read by the layout model. |
| SmartArt and charts | **Not checked** | Diagram and chart text, generated layout and related data are not measured. |
| Pictures, connectors, media and embedded objects | **Not checked** | Their bounds, overlap, clipping, relationships and content are not checked by `check_pptx`. |
| Master/layout-only objects | **Not checked** | Layout and master parts are consulted for placeholder inheritance, but objects that appear only on a master or layout are not independently checked for fit or geometry. |
| Vertical and non-horizontal text | **Not checked** | DrawingML vertical-text modes, text rotation within a body and other non-horizontal layout are not modelled. Recognised vertical modes are excluded from ordinary overflow measurement and reported as `pptx.vertical-text: unsupported` in coverage output. |

### Fonts and autofit

| surface | status | current scope |
| --- | --- | --- |
| Installed TrueType/OpenType metrics | **Partial** | Measures advances from `cmap`/`hmtx` and legacy `kern` tables in discoverable font files. Static TTC/OTC member indices are preserved from discovery through coverage and metrics, with synthetic TrueType/CFF tests and [six native PowerPoint TTC observations](font-collections.md). Encoded named variable instances are rejected; arbitrary weight matching, GPOS and complex shaping remain outside this model. No renderer is launched by the checker. |
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
| PPTX XML/package/relationship integrity | **Partial** | The main slide list and its referenced slide relationships/roots must be readable and unambiguous before layout runs. `check_pptx` does not validate the complete OPC graph, content types or well-formedness of every XML part; `pptx.package-integrity` therefore remains unsupported in coverage. |
| Fidelity against a source PPTX | **Not checked** | An explicit `--against` emits `FID000` as an error with `comparison was NOT performed`; layout checks still run, but the default CLI result cannot pass without the requested comparison. |
| Notes, comments, transitions and animations | **Not checked** | Their presence, integrity and preservation are not evaluated. |
| Semantic correctness | **Not checked** | Correct text, numbers, chart data, reading order, accessibility and presentation intent are outside the current checks. |

## Producer and platform evidence

The evidence below comes from the committed corpus and recorded observations.
It describes those files and application builds; it does not establish
compatibility with every file from the same producer.

| surface | evidence present | evidence not yet present |
| --- | --- | --- |
| DOCX corpus | One byte-reproducible feature package; six clean and two defective real agent outputs; plus a [versioned synthetic beta tranche](../evidence/docx-beta/README.md) with 50 sources, 220 exactly labelled pairs, six document classes, and ten sources each from `python-docx`, LibreOffice, Word for Mac, Word for Windows and Word Online. Twenty pairs retain actual Windows saves and observed web edits with hashes and independent XML audits. | Customer distributions, other Office builds/web sessions, an independently supplied commercial/internal generator (where available), independent human review of Windows/web labels, and positive labels for rules marked not measured in the [rule-level result](../evidence/docx-beta/RESULTS.md). Synthetic equivalents meet the P0.5 beta scope; client documents and dual human review are optional confidence extensions. |
| DOCX observed rendering | The key detached-comment case was inspected in Word for Mac. Twenty mutation cycles were converted by LibreOffice without it reporting structural losses. [Windows Word](../evidence/docx-beta/WINDOWS.md) opened/saved ten synthetic sources with preserved XML facts. [Word Online](../evidence/docx-beta/ONLINE.md) accepted ten synthetic inputs, confirmed edits/saves, and returned audited downloads; all pages of inputs/downloads received supplementary local LibreOffice visual inspection. | Scored Windows/web visual fidelity, Google Docs and systematic DOCX checks in ONLYOFFICE. |
| PPTX corpus | One byte-reproducible reference deck built with `python-pptx`, containing 24 plain text-shape cases. Four additional synthetic decks cover [long tokens](pptx-long-tokens.md) (12 slides), [font collection members](font-collections.md) (6), [slide order](pptx-slide-order.md) (3), and [master-specific themes](pptx-master-themes.md) (8). | Real customer decks, tables, SmartArt, grouped/rotated content, charts and broad producer diversity. |
| PowerPoint evidence | PowerPoint for Mac, Microsoft 365 on Apple Silicon, in editing view: 21 non-excluded reference shapes agreed with the predicted fit and line count. The four additional decks were opened in PowerPoint for Mac 16.112.3 and all 29 native slide exports were inspected, with results recorded in the linked reports. | PowerPoint for Windows, PowerPoint Online, mobile clients and Slide Show mode; independent review of the four additional decks. |
| Other PPTX renderers | LibreOffice and ONLYOFFICE PDF exports agreed on line count for 23 of 24 reference shapes; the one disagreement is treated as renderer-dependent. | Google Slides and broader decks across renderer versions and platforms. |
| Runtime platforms | The automated test matrix runs the Python package on Linux, macOS and Windows, and on Python 3.9 through 3.13 where applicable. | Running on an operating system does not establish agreement with every Office renderer on that system. |
| Browser runtime | The [browser demo](../demo/README.md) runs the released package in a Pyodide worker, using bundled metric-compatible fonts. [Recorded smoke tests](../demo/VALIDATION.md) with package 0.4.0 and Pyodide 314.0.6 / Python 3.14.2 cover Chrome, Safari, Firefox and the in-app browser on macOS. Local adapter tests compare human and JSON output with the CLI. | Mobile devices, slow-network throttling, browser memory exhaustion, the 60-second worker-termination path and a controlled offline/network trace. Browser execution does not add Office rendering coverage. |
