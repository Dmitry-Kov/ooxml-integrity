# Rule codes and coverage

Every finding has a stable code and severity, plus a part, shape or XPath
where one can be identified. Losses that hide content or its audit trail are
errors. Losses that affect only appearance are warnings.
Undefined paragraph and table styles remain errors because they can carry
numbering and structure; undefined character styles are warnings.
These tables describe [0.10.0](releases/0.10.0.md). Version `0.4.0` treated undefined character styles
as errors; use `--fail-on warn` to keep them failing after upgrading.

The [README](../README.md) shows the two questions and how to run the checker;
the [support matrix](support-matrix.md) records the exact scope of each rule.

## `.docx`

| code | check |
|---|---|
| `PKG001-008` | OPC package integrity, content types, archive budgets, unsafe part names |
| `PKG009` | 0.4.4: Strict Open XML is not supported, so the Word checks were not run; reported as an error |
| `PKG010` | 0.7.0, ERROR: a part the main document relates is declared with another content type than its relationship type requires, as in Codex's `commentsExtended` parts that Word for Mac refuses; [scope and corpus run](../evidence/docx-content-types/README.md) |
| `PKG011` | 0.8.3, ERROR: a second `Default` for an extension or `Override` for a part name in `[Content_Types].xml`, compared as OPC compares them; Word for Mac refuses the package even when the second repeats the first; [Word check](../evidence/docx-opc-duplicates/README.md) |
| `PKG012` | 0.8.4, ERROR: an `Override` whose part name escapes an unreserved character, a slash, a backslash or a non-ASCII character, or has a `%` that starts no escape, which Word for Mac refuses; [Word check](../evidence/docx-escaped-part-names/README.md) |
| `XML001` | well-formedness of every XML part |
| `REL001-003` | `r:id` / `r:embed` / `r:link` references resolve; targets exist; unreferenced relationships |
| `REL004` | 0.8.3, ERROR: one `Id` on two relationships of the same relationship part, which Word for Mac refuses; [Word check](../evidence/docx-opc-duplicates/README.md) |
| `STY001` | undefined paragraph/table styles: error; undefined character styles: warning |
| `STY002` | undefined `basedOn` / `next` / `link` style references: warning; 0.4.5: `next` / `link` are info |
| `NUM001-004` | `numId` → `w:num` → `abstractNumId` → `w:abstractNum`; `ilvl` defined |
| `FTN001-002` | footnote references resolve; orphaned footnotes |
| `CMT001-006` | Comment ranges/references ↔ the related comments part; unresolved or unreadable comments parts |
| `CMT007` | 0.10.0, ERROR: a second `commentRangeStart`, `commentRangeEnd` or `commentReference` for one comment id in a story, as the closed python-docx [PR #1605](https://github.com/python-openxml/python-docx/pull/1605) wrote when setting the text of the first paragraph of a comment over two; a text box's copy in `mc:Fallback` does not count |
| `REV001-003` | revision-ID collisions outside the verified paragraph-mark/content pair; `w:del` carries `w:delText`, respecting legal `w:ins > w:del` nesting |
| `TBL001-002` | `tblGrid` present; cells per row vs grid columns, accounting for `gridSpan` |
| `SDT001-002` | content-control integrity |
| `TXT001` | XML edge whitespace in runs without effective `xml:space="preserve"` |
| `TXT002` | WARN: literal numeric punctuation/symbol spellings after XML decoding, suggesting double escaping; [scope and intent ambiguity](review-edit-warnings.md) |
| `FID000` | requested source comparison could not run |
| `FID001-003` | losses and additions relative to the source, by construct count (0.10.0: endnote references and section breaks too); drop in text volume |
| `FID004-006` | comment, footnote or endnote text missing from the edited file, allowing for changed ids; 0.4.6: a tracked edit is not a loss |
| `FID007-008` | header/footer story missing or changed untracked (0.4.6); tracked constructs lost from headers/footers |
| `FID009` | 0.4.2: missing literal insertion/deletion text with equal wrapper counts in the supported main-document profile; [limits](../evidence/docx-revision-text/README.md) |
| `FID010` | 0.4.2: fewer notes retain insertion/deletion markup in equally populated footnote/endnote text groups; [limits](../evidence/docx-note-revisions/README.md) |
| `FID011` | WARN: preserved source insertion text plus additional characters under its old author/date context without a distinct new insertion context; [scope and intent ambiguity](review-edit-warnings.md) |
| `FID012` | 0.4.9, INFO: the tracked changes an edit added, per story (body, header/footer slot, notes), kind and author, so an [expectation](configuration.md#changes-the-edit-was-asked-to-make) can require a tracked edit in the right place |
| `FID013` | 0.5.1, WARN: a tracked replacement the edit added deletes and inserts again more unchanged words than it changes (at least four), so a reviewer sees unchanged text struck through and added again; [scope](review-edit-warnings.md#fid013-a-tracked-replacement-wider-than-the-change) |
| `FID014` | 0.8.0, INFO: a paragraph whose text the edit changed, with its text before and after, tracked changes accepted and rejected, so an [expectation](configuration.md#changes-the-edit-was-asked-to-make) can require the text the edit was asked to produce |
| `FID015` | 0.10.0: a bookmark of the source is gone. ERROR when a `REF`, `PAGEREF` or `NOTEREF` field of the edited file still points at it, so Word prints "Error! Reference source not found." or "Error! Bookmark not defined." when fields update; WARN when only an internal link does, or nothing does; a hidden bookmark nothing points at (`_GoBack`, `_Hlk…`) is not reported; [scope and corpus run](../evidence/docx-references/README.md) |
| `FID016` | 0.10.0: fields of the source are gone, per story and kind (`REF`, `TOC`, `PAGE`, …). ERROR for a lost `REF`, `PAGEREF` or `NOTEREF` and when none of a kind is left, else WARN. A field is its kind and the bookmark it points at; switches, the simple or complex form, and fields inside another field's result (the entries of a table of contents) are not compared; [scope and corpus run](../evidence/docx-references/README.md) |
| `INT001` | a check raised and did not complete: error; other checks still run, and coverage reports that check's surface as `skipped` |
| `EXP001` | 0.4.8: a declared expectation (`--expect` or `[[expect]]`) matched no finding, so the requested change did not happen; [expected changes](configuration.md#changes-the-edit-was-asked-to-make) |

## `.pptx`

| code | check |
|---|---|
| `PPT000` | text could not be measured; reported as an error |
| `PKG009` | 0.4.4: Strict Open XML is not supported, so the layout checks were not run; reported as an error |
| `XML001`, `PKG003-005`, `PKG011`, `PKG012`, `REL001`, `REL002`, `REL004` | 0.9.0: the package rules of `.docx`, saying what PowerPoint for Mac does; a missing thumbnail or SmartArt drawing is a `REL002` WARN; [PowerPoint check](../evidence/pptx-package-rules/README.md) |
| `PPT001` | text taller than its box, beyond the measurement tolerance |
| `PPT002` | predicted text height exceeds the box by up to 5% — borderline overflow |
| `PPT003` | line runs outside the usable width: wrap off, or a single overwide glyph |
| `PPT004` | shape extends past the slide edge, or sits entirely outside it |
| `PPT005` | shrink-to-fit requested but no `fontScale` stored — result depends on the renderer |
| `PPT006` | two text-bearing shapes overlap |
| `PPT007` | declared font unavailable; measurements for those shapes are estimates |
| `INT001` | a check raised and did not complete: error; other checks still run, and coverage reports that check's surface as `skipped` |

## Coverage

Use `--coverage` to see the scope of a result. It distinguishes
`checked`, `not-present`, `estimated`, `skipped` and
`unsupported` surfaces per file, and a result with a gap says
`no findings in checked surfaces`, not `clean`. `ooxml-integrity doctor`
reports which measurements are available on the current machine.
See the [support matrix](support-matrix.md) and
[coverage and doctor](coverage.md).