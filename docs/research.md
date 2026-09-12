# Research notes

These notes describe the experiments behind
[`ooxml-integrity`](../README.md), including the results that led me to change
the checker. The measurements apply to the recorded documents, fonts and
application builds. The [limitations](#limitations) section gives that scope
in more detail.

The later [existing-revision evidence](../evidence/docx-revisions/README.md)
records 27 additional pairs without changing the original beta corpus. It
separates actual adeu/Word Online edits, seeded defects and accept/reject
characterization, and retains two preservation false negatives explicitly.

## The finding

The starting point was a services agreement with tracked changes from counsel
and two reviewer comments. In the pair shown below, two agents received copies
of that document and a request to update three figures in the milestone table.

The run labelled `careful` had no budget constraint and was asked not to disturb
anything else. It read the XML, noticed that the fee was inside counsel's
unaccepted insertion, and recorded its own edits under a separate author.
The `fast` run was asked to be quick and used `python-docx`. These labels
describe the runs; they are not established categories of agent behaviour.

Opened side by side in Word:

![Word for Mac, both files open side by side. Left: the fast agent's output, with
two comments in the pane. Right: the careful agent's output, with five comments
including the reviewer's, and the table edits shown as tracked changes.](word-comparison.png)

*The fast run is on the left. Its comment pane has no entry from M. Reviewer,
and the edited figures are plain black. The careful run is on the right, with
the reviewer's comment present and the figures blue and underlined.*

|                                  | fast agent                        | careful agent                     |
| -------------------------------- | --------------------------------- | --------------------------------- |
| Reviewer comment in margin       | **absent**                        | present, anchored to the figure   |
| Table edits                      | **untracked** (0 `w:ins`, 0 `w:del`) | tracked (9 `w:ins`, 2 `w:del`) |
| Word warning on open             | **none**                          | none                              |
| Word count                       | 118                               | 118                               |
| Comments shown in pane           | 2                                 | 5                                 |

Word opened both files without a warning. In the fast run, the comment
*"Confirm this figure against the source table before circulation"* remained
in `word/comments.xml`, but no longer had an anchor in the document. It was
therefore missing from the margin beside the edited number.

The three edits were also untracked, so a reviewer following the redline
would not see them as changes to the contract. Word count, page count and
the visible page layout did not reveal these losses.

### Why `python-docx` does this

Comment range markers are siblings of the text runs. A separate run contains
the comment reference:

```xml
<w:p>
  <w:commentRangeStart w:id="1"/>
  <w:r><w:t>EUR 12,000</w:t></w:r>
  <w:commentRangeEnd w:id="1"/>
  <w:r><w:commentReference w:id="1"/></w:r>
</w:p>
```

Assigning `paragraph.text` replaces the paragraph's contents with a new run.
The range markers and reference are removed:

```xml
<w:p><w:r><w:t>EUR 14,000</w:t></w:r></w:p>
```

The replacement still parses as XML and opened normally in Word in this
experiment. It can also remove footnote references, character-style runs and
tracked-change markup from the paragraph. A full XSD validation was not part
of this experiment; the comparison below used a namespace/root-element check.

---


## How accurate is the deck model?

`research/calibrate_pptx.py` renders each shape of the reference deck separately
with LibreOffice, extracts glyph positions from the PDF, and compares the
measured line pitch and count with the model:

| | measurement error or agreement |
|---|---|
| line pitch (uniform-size paragraphs, n=12) | median **0.05%**, worst **0.06%** |
| line count (24 shapes) | **23/24** exact, 1 off by one |

I also checked the deck in PowerPoint for Mac. All 21 checkable shapes matched
the predicted verdict and line count, including the shape whose widest line
fills 99.2% of its box. The checker and PowerPoint used the same `Calibri.ttf`
from the PowerPoint app bundle, which removed font substitution as a variable.
Predictions were generated before the deck was opened. The method, per-shape
table and limits are in
[`docs/powerpoint-validation.md`](powerpoint-validation.md).

The same check exposed a remaining question about autofit. In the tested
PowerPoint build, opening a file did not recompute either autofit mode.
`normAutofit` without a stored `fontScale` left text overflowing until the shape
was edited, and `spAutoFit` did not grow its box. The checker warns about the
first condition and has no dedicated finding for the second. The validation
notes describe what further evidence is needed to revisit those severities.

**Default line pitch measured 1.2 times the font size.** The same string in
Calibri, Arial, Times New Roman, Courier New, Cambria and Verdana at 12pt and
20pt gave a pitch of 1.2000 times the size in each test. The fonts' own
`ascender + descender + lineGap` ratios ranged from 0.80 to 1.22. My earlier
calculation used those font metrics and produced a consistent +1.7% error.

**Renderers disagreed near the width limit.** The one line-count disagreement
was `FIT_mixed_run_sizes`, whose widest line fills **99.2%** of its box. I
initially attributed it to the model's precision: advance widths alone omit
GPOS kerning and shaping. Checking another renderer changed that explanation:

| | `FIT_mixed_run_sizes` | how it was measured |
|---|---|---|
| this model | **2 lines** | `layout_shape` |
| PowerPoint for Mac | **2 lines** | rendered, read from the outlined deck ([method](powerpoint-validation.md)) |
| LibreOffice | **3 lines** | `calibrate_pptx.py`, glyph positions from the PDF |
| ONLYOFFICE | **3 lines** | same script, same measurement code |

The model agrees with PowerPoint for this shape, while LibreOffice and
ONLYOFFICE put it on an extra line. A single verdict would therefore depend
on which renderer the user opens. This is a reason to treat measurements
near the limit with care. The checker uses a 5% tolerance: predicted vertical
overflow within that band produces `PPT002`; horizontal overflow must exceed
5% of the box width to produce `PPT003`.

ONLYOFFICE gave the closest line-pitch match in this comparison:
**0.000026% median error and 0.00012% worst error** across uniform-size shapes.
Those differences are small enough to be consistent with numerical rounding.
LibreOffice's median error was 0.05%; the PDF measurements alone cannot show
whether it came from export rounding or a slightly different pitch. The
comparison can be repeated with `research/compare_renderers.py`.

**Font substitution introduces a separate measurement error.** I compared
Carlito on Linux with Calibri from Microsoft 365 on macOS, reading both fonts
with this module at 18pt:

| sample | Carlito | Calibri | (Calibri − Carlito) / Carlito |
|---|---|---|---|
| digits `0123456789 EUR 44,500.00` | 202.376953 | 202.376953 | **0.000%** |
| bold caps A–Z | 265.772461 | 265.069336 | −0.265% |
| caps A–Z | 259.171875 | 258.451172 | −0.278% |
| clause text | 444.682617 | 443.188477 | −0.336% |
| pangram | 326.276367 | 324.685547 | −0.488% |
| lowercase a–z | 213.372070 | 212.132812 | −0.581% |

The digits sample matched exactly; the letter samples differed by
**0.26–0.58%**, using Carlito as the percentage denominator. Negative values
mean Calibri was narrower. An earlier version of these notes described the widths as identical.
The measurements show why that wording needed correcting.

The observed substitution differences fall within the 5% `BORDERLINE` band.
For these samples, substituting Carlito overstates the width of Calibri text
and can produce a false overflow warning. That result applies to the measured
pairing and strings; it does not establish a bound for every substitute font.

The available fonts still depend on the machine that opens the deck. The
checker reports the face it used and marks measurements from an unrelated
fallback as estimates:

```
[INFO ] PPT007  Segoe UI is not installed and has no known substitute; measured
                with DejaVu Sans - widths are a guess. 1 shape(s) affected;
                overflow verdicts for them are estimates
```

## Follow-up checks in 0.4.0

The reference deck exposed the initial layout problems, but it does not cover
all the changes now in the checker. Four later studies use separate synthetic
decks and recorded PowerPoint for Mac exports:

| study | recorded cases | result and remaining scope |
| --- | --- | --- |
| [Long tokens](pptx-long-tokens.md) | 12: 8 clean, 4 defective | Basic Latin character wrapping fixes missed vertical overflow; other scripts and unmodelled breaking remain estimates. |
| [TTC/OTC font collections](font-collections.md) | 6: 4 clean, 2 defective | Retaining the selected font member fixes two omissions and one false positive; named variable instances remain unsupported. |
| [Presentation slide order](pptx-slide-order.md) | 3: 2 clean, 1 defective | Findings follow the presentation's listed slide positions, including hidden slides; custom shows and displayed footer numbering are outside this check. |
| [Owning-master themes](pptx-master-themes.md) | 8: 5 clean, 3 defective | Resolving each slide's own Latin theme fonts fixes three omissions and one false positive; font-scheme overrides remain unsupported. |

These studies test specific fixes. Their case counts are separate from the
original 21-shape PowerPoint comparison, and they do not establish general
layout accuracy on other platforms.

DOCX comparison has also expanded to section-linked headers and footers.
It follows effective `default`, `first` and `even` stories, detects lost text
and tracked constructs, and allows part renumbering and equivalent shared or
split stories. The [support matrix](support-matrix.md) records the exact scope.
Package-wide relationship checks, archive limits and coverage reporting now
make unreadable inputs and checks that could not run visible in the result.

After the package release, a [browser demo](../demo/README.md) was added using
the published checker in a Pyodide worker. It includes DOCX source comparison,
PPTX checks, coverage and `doctor`, with bundled fonts and JSON output.
The [browser validation record](../demo/VALIDATION.md) describes parity checks
and observed browser behaviour. Browser parity is a separate test from Office
renderer accuracy.

## Reproduce the experiment

```bash
pip install -e ".[dev]"
cd research
python build_corpus.py        # build the reference document (byte-reproducible)
python run_experiment.py      # mutators + inspector + 20-cycle accumulation
python compare_detectors.py   # the headline table below

python build_pptx_corpus.py   # build the reference deck (byte-reproducible)
python assert_deck.py ../corpus/deck.pptx   # it still reports its 11 defects

cd ..
python research/build_docx_evidence.py evaluate  # 50 sources, 220 labelled pairs
```

Both fixtures rebuild byte-identically, so CI can check them with `git diff`.
`assert_deck.py` verifies that text measurement is available and compares the
multiset of finding codes. An exit-code check alone can miss a font problem:
when only an unrelated fallback is available, layout findings can be downgraded
to warnings and the command can exit 0 at the default error threshold.

LibreOffice's `soffice` command on `PATH` is needed for the rendering check.
Total runtime is a couple of minutes, most of it LibreOffice.

`research/add_settings.py` adds `word/settings.xml` and its package declarations
while checking that the other parts remain byte-identical. The
[agent-run notes](../runs/README.md) explain why the saved outputs needed it.

The reference document is assembled part-by-part to control the exact XML
used for footnotes, comments, tracked changes and content controls.
It carries named paragraph and character styles, multi-level numbering,
two footnotes, two comments, three
tracked revisions from a named author, a content control, a table with an
explicit `tblGrid` and a header row, an inline image, an external hyperlink, and
header/footer parts.

The versioned [DOCX beta evidence corpus](../evidence/docx-beta/README.md) adds 50
distinct synthetic sources and 220 labelled pairs: 120 clean controls and 100
isolated seeded defects. Ten sources each were actually produced or
opened-and-saved by `python-docx`, LibreOffice, Word for Mac, Word for Windows,
and Word Online. Ten clean pairs preserve real before/after
[Windows Word saves](../evidence/docx-beta/WINDOWS.md); another ten preserve
[observed Word Online edits](../evidence/docx-beta/ONLINE.md), with capture and
sanitisation receipts. Its published
[results](../evidence/docx-beta/RESULTS.md) count exact finding occurrences and
report precision/recall per measured rule and producer. Rules without labels
remain unmeasured, and the report lists the limits of the captured builds and
web session.

---

## What each verification approach catches

These are controlled, hand-written mutations from `research/mutate.py`, separate
from the agent runs below. The table was reproduced on 2026-09-12 with
`compare_detectors.py` against the current checkout. `yes` means that XML parsed,
the main Word document had the expected namespace/root/body, or LibreOffice
created a PDF larger than 1000 bytes. It is not a clean-document verdict.
Full XSD validation and systematic visual review were not performed.

```
controlled edit                         XML     root/   PDF      inspector   fidelity
                                        parses  body    created              vs source
python-docx: open and save, no edit     yes     yes     yes      ok          ok
python-docx: paragraph.text = ...       yes     yes     yes      2 found     5 reports
targeted XML value-edit control         yes     yes     yes      ok          ok
clone clause with revision IDs          yes     yes     yes      1 found     3 reports
reformat XML, lose whitespace markers   yes     yes     yes      5 found     ok
delete paragraph with footnote anchor   yes     yes     yes      1 found     3 reports
rename style, leave dangling refs       yes     yes     yes      4 found     ok
round-trip through markdown             yes     yes     yes      ok          18 reports

Controlled defect cases: 6
  XML parsing succeeded:       6/6
  root/body check passed:      6/6
  PDF creation succeeded:      6/6
  checker reported findings:   6/6
Full XSD validation and systematic visual review: not measured.
```

Rows one and three are clean controls. All six deliberate defect cases have
ERROR or WARN findings from internal inspection, source comparison or both.
The fidelity column counts every comparison report, including INFO additions:
the cloned clause has three such additions, while `REV001` detects the duplicated
revision ID in self-check. The original prototype recorded 12 Markdown losses;
the current comparison has 18 reports, including later text/header/footer rules.

Successful PDF conversion did not distinguish those six cases from the
controls. A page image alone also does not establish whether review anchors
or tracked changes survived an edit. Workflows such as
[Anthropic's `pptx` skill](https://github.com/anthropics/skills/blob/main/skills/pptx/SKILL.md)
use rendering for visual review, but that full workflow was not tested here;
this table cannot supply a detection rate for it.

### Two questions, not one

The markdown round-trip removed all the tracked styles, numbering, footnotes,
comments, revisions, content controls, tables and images from the reference
document. The resulting file had no broken references for the inspector to
report. Comparing it with the source exposed the losses.

That case is why the checker has two operations:

- **Self-consistency:** inspect internal references in one file
  (`src/ooxml_integrity/inspector.py`).
- **Fidelity:** compare supported constructs and text with the source
  (`src/ooxml_integrity/fidelity.py`).

---

## Real agent runs, including the result that went against me

The hand-written mutators reproduce known failure cases. To see which editing
methods agents would choose themselves, I also ran eight tasks on copies of
the reference document. Each request described the desired edit without
prescribing a tool or an XML technique. Some requests added a preservation
instruction or asked the agent to be quick.

| run                             | class   | tool calls | tokens | defects              |
| ------------------------------- | ------- | ---------: | -----: | -------------------- |
| fee + new clause                | careful |         23 |    79k | none                 |
| same, + "don't disturb anything" | careful |        29 |    86k | none                 |
| table edits                     | careful |         29 |    73k | none                 |
| same, + "don't disturb anything" | careful |        22 |    67k | none                 |
| rewrite two paragraphs          | careful |         19 |    68k | none                 |
| same, + "don't disturb anything" | careful |        18 |    74k | none                 |
| **fee, fast**                   | **fast**|      **5** |**36k** | **comment orphaned** |
| **table, fast**                 | **fast**|      **2** |**34k** | **comment orphaned** |

No structural defects were found in the six careful runs. All six used
targeted XML replacements and recorded changes under a separate author.
Several explicitly avoided `python-docx` because of tracked-change handling.
Two correctly nested `w:ins > w:del` where counsel's insertion was still
pending. Both fast runs used `python-docx` and lost a comment anchor.

The six clean runs limit what can be concluded from this experiment. In this
sample, the outcome depended on the editing approach, and opening the file in
Word did not reveal the difference. A larger comparison would need to control
the model, prompt, tool access and budget
before attributing the result to any one of them.

The cost difference is worth measuring too. The careful runs used 67–86k
tokens and 18–29 tool calls for small edits; the fast runs used 34–36k tokens
and 2–5 calls. This sample shows a difference in resource use, but does not
establish how much work is needed to preserve a document reliably.

### The agent runs also found three bugs in the checker

The agent outputs included valid structures that the original checker
incorrectly rejected. Three rules needed changes:

| code     | was                                                        | now                                                                                              |
| -------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `REV003` | any `w:delText` inside `w:ins` flagged as a defect          | `w:ins > w:del` nesting is legal and means "inserted by one author, deleted by another". Tests the *nearest* revision ancestor now |
| `PKG005` | zip directory entries (`word/`, `docProps/`) flagged as uncovered parts | skipped — not OPC parts, and Word tolerates them                                    |
| `FID002` | any increase in construct count flagged as duplication      | an agent may legitimately add a clause. Real duplication is caught by colliding ids (`REV001`) |

These false positives matter for routine use: valid edits should not require
users to suppress a rule. After the fixes, all six deliberately introduced
defect cases were still detected and none of the eight agent outputs produced
a false positive.

---

## Applying the method to other people's tools

The corpus and the checker were only ever measured against my own documents, so
in September 2026 I ran them against third-party tools that edit or validate
DOCX. This section records what came out of it, including the parts where the
tools were fine and I was wrong.

### adeu

adeu projects a DOCX into Markdown, lets a model edit it, and writes the result
back as tracked changes — the closest thing to the workflow this checker is
built for. Running one `ModifyText` with a comment over the reference agreement
and comparing against the source: comment anchors 2 → 3, insertions 2 → 3,
deletions 1 → 2, footnote references, styles and numbering intact. That is the
cleanest round-trip measured here, and worth stating plainly: the tool did not
lose anything.

One finding: the run holding the new `w:commentReference` carried
`rStyle w:val="CommentReference"` while no such style was defined in
`styles.xml`. Word and LibreOffice both accept a dangling `rStyle` silently and
format the mark with the run's default properties, so the reference mark is
simply the wrong size with no warning. Reported as
[adeu #137](https://github.com/dealfluence/adeu/issues/137) and fixed in 3.0.3.
The reference agreement from `corpus/` was adopted upstream as a fixture.

This finding exposed an inconsistency in this checker's own severity rule:
losing something that makes content or an audit trail invisible is an error;
losing appearance is a warning. `STY001` on a comment reference mark reports an
appearance-only loss, so its ERROR severity contradicted that rule. Fixed in
0.4.1: undefined `rStyle` references now
report WARN. Undefined `pStyle` and `tblStyle` references remain ERROR because
paragraph and table styles can carry numbering and structure. With the default
`--fail-on error`, character-style findings no longer fail CI; `--fail-on warn`
still catches them.

Two fixture contributions followed: [#138](https://github.com/dealfluence/adeu/pull/138)
(merged) with comment-projection scenarios from LibreOffice, Word for Mac and
Word for Windows, and [#140](https://github.com/dealfluence/adeu/pull/140)
(merged) with revision projection and accept/reject scenarios built from `runs/`. Preparing
the second set exposed a mismatch in adeu's own cross-platform suite: the Python
engine declares the `w16du` prefix on individual revision elements while the
TypeScript engine declares it on the document root. The namespace-aware trees
are identical; only the serialized snapshot differs. Reported as
[#139](https://github.com/dealfluence/adeu/issues/139) with a self-contained
reproduction script and fixed in 3.0.4.

The four inputs shipped in the second PR came from `runs/t1_bare`,
`runs/t5_rewrite_pres`, `runs/t2_bare` and `runs/t2_pres`, with the revision author
renamed from `Claude` to `Agent` in the three that needed it. Of those four,
only `t1_bare` carries nested `w:ins > w:del`.

### python-docx

`paragraph.text = ...` calls `Paragraph.clear()`, which drops every child of the
paragraph except `w:pPr`. `w:commentRangeStart` and `w:commentRangeEnd` are
paragraph children, not runs, so they go too, along with the run holding
`w:commentReference`. Since 1.2 added `Document.add_comment()`, a library user
can now create a comment and destroy its anchor with two documented calls:

```
before.docx 3 markers, 1 comments
after.docx  0 markers, 1 comments
```

The same applies to `w:footnoteReference` — the footnote body survives in
`footnotes.xml` while the reference in the text disappears — and to any
`w:ins`/`w:del` wrapping the runs. Measured on a real document with the checker:
footnote references 2 → 1, `FTN002` footnote defined but never referenced.

Reported as [#1604](https://github.com/python-openxml/python-docx/issues/1604).
An outside contributor opened
[PR #1605](https://github.com/python-openxml/python-docx/pull/1605) the same day,
collecting the comment ids before `clear()` and re-marking them on the
replacement run. The PR remains open. Verified against 1.2.0: the comment case is fixed, the range
widens to cover the whole replacement text (which is what Word does when a
commented passage is retyped), and footnotes and revisions are still dropped —
so #1604 stays open. The author removed the auto-close from the PR description
to keep that remaining scope open.

A second, pre-existing gap surfaced while checking that PR: `add_comment()`
writes `rStyle w:val="CommentReference"` but never adds the style definition,
which is the same defect found in adeu. Reported separately as
[#1609](https://github.com/python-openxml/python-docx/issues/1609).

### anthropics/skills

The docx skill ships `scripts/office/validate.py`, which runs XSD validation,
checks that comment markers are paired, and — with `--original` — compares
paragraph counts and reports untracked text edits. Run against the `fast` agent
output from the runs recorded here, with the source document supplied:

```
Paragraphs: 22 → 23 (+1)
All validations PASSED!
```

The orphaned comment is not reported. `validate_comment_markers` compares the
set of marker ids against the set of comment ids in one direction only: a marker
pointing at a missing comment is caught, a comment pointed at by nothing is not.
With `--author` it correctly reports the untracked table edits, but still says
nothing about the comment. Reported as
[anthropics/skills #1733](https://github.com/anthropics/skills/issues/1733) with
both documents and a five-line suggested fix. The issue and
[PR #1734](https://github.com/anthropics/skills/pull/1734) remain open; the PR has
not yet received a maintainer review.

A reviewer on that PR argued that the reverse check would flag threaded replies,
claiming they are nested `w:comment` children with no anchors of their own.
A Word-authored file (AppVersion `16.0000`) containing one comment and one Reply
produced a different result:

```
comments.xml:  2 x <w:comment>, zero nested (ids 0 and 1)
document.xml:  commentRangeStart ids [0, 1]
               commentRangeEnd   ids [0, 1]
               commentReference  ids [0, 1]
commentsExtended.xml:
               w15:paraId="57B5BAC5"
               w15:paraId="1E34214A" w15:paraIdParent="57B5BAC5"
```

Both comments are flat siblings and carry all three markers on the same range;
the thread relationship is stored only as `paraIdParent` in
`commentsExtended.xml`. The reverse check therefore does not false-positive on
this thread. The schema also rules out the reviewer's nested example:
`CT_Comment` uses `EG_BlockLevelElts`, whose content model does not include
`comment`, and `w:comment` is declared only inside `CT_Comments`. Nesting one
`w:comment` inside another is not schema-valid. This project's own check reads
direct `w:comment` children with `findall`, so it was never exposed to the
proposed descendant-selection concern; it reports no comment findings on this
Word-authored thread.

This changes an earlier claim in these notes. "Render to PDF and inspect" is not
the whole of what current agent skills do — that skill also validates against
the schema and checks comment markers. It still misses this defect class, but
for a more specific reason than "it only looks at pictures".

### docx-mcp

Its documented `validate` and `audit` commands overlap with the
self-consistency half of this checker, so rather than duplicating that work I
asked in [#4](https://github.com/sontanon/docx-mcp/issues/4) whether the
documented rejection of inputs that already carry `w:ins`/`w:del` is a
deliberate scope boundary, and offered a subset of the labelled pairs as
fixtures. No response yet.

### What this changed about the corpus

The evidence corpus turned out to be narrower than the offer I made in those
issues: all 270 documents under `evidence/docx-beta/` contain zero `w:ins` and
zero `w:del`, because they are producer round-trips of documents that carry
comments and footnotes but no pending revisions. The revision-bearing material
lives in `corpus/base.docx` and the eight agent outputs under `runs/`, and only
`runs/t1_bare` and `runs/t1_pres` contain nested `w:ins > w:del`. Contributions
to other projects were sourced accordingly. Producing pre-redlined pairs
directly from Word for Windows and Word Online remains open work.

---

## Accumulation

I also applied the mutators over twenty successive edit cycles. The repeated
editing setup was inspired by [DELEGATE-52](https://arxiv.org/abs/2604.15597);
this experiment records changes to file structures:

- Footnote references and comment anchors drop to **50%** on the first cycle
  and stay there. None of the later edits restores them.
- Tracked changes grow to **233%** through duplicated revision ids.
- An error introduced at cycle 3 survives to cycle 20.
- LibreOffice converts all twenty versions successfully.

---

## Limitations

The results above have the following limits. They also apply to the numbers
summarised in the README.

- **The 50-source beta evidence corpus is synthetic.** It covers six document
  classes and five producers, but not customer document
  distributions, other Office builds/web sessions, or an independently supplied
  generator. Its 100% figure applies only to the 14 measured rules; the
  per-rule report names every unmeasured DOCX rule.
- **Full schema validation was not run.** The full ECMA-376 XSDs are not bundled;
  `compare_detectors.py` checks the main document's namespace and root element.
  That proxy cannot establish which defects a complete XSD validator would
  detect. A full validator must be run before making that comparison.
- **Structural evidence is not visual accuracy.** DOCX evidence includes real
  saves through Word for Mac, Word for Windows and LibreOffice, plus actual
  Word Online edits. The web capture includes supplementary page inspection
  through a local LibreOffice render. Neither that review nor the structural
  scores establish general visual fidelity; systematic ONLYOFFICE DOCX
  behaviour remains untested.
- **There is no measured comparison with neighbouring tools.** The prior-work
  notes describe documented capabilities. I have not run `OfficeCLI`,
  `docx-mcp` or the other listed tools on this corpus, so these notes cannot
  establish their detection rates or rank their reliability.
- **Eight agent runs is a small sample**, on one document, with one task family,
  on one day. The careful/fast split is suggestive, not established.
- **PowerPoint evidence is limited to the recorded Mac builds.** The original
  21-shape check used editing-view screenshots. The later long-token, font
  collection, slide-order and theme studies added native exports for their
  specific cases. Windows and Slide Show mode remain untested.
- **Only the Carlito/Calibri pairing has been measured** (see the table above).
  The other entries in `METRIC_SUBSTITUTES` — Caladea/Cambria, Liberation
  Sans/Arial, Liberation Serif/Times New Roman, Liberation Mono/Courier New,
  Gelasio/Georgia — rely on the font designers' compatibility claims and still
  need direct measurement.
- **No GPOS kerning or shaping.** Only the legacy `kern` table is read.
  Measurements for complex scripts and heavily-ligatured display faces are
  estimates; the current experiments do not establish a general error bound.
- **Font discovery is best-effort.** `fc-match` is used where fontconfig exists;
  otherwise the standard font directories are scanned. A machine with neither
  gets a `PPT000` error saying text could not be measured. An unrelated fallback
  font produces estimates, so the installed fonts affect the result.
- **The mutators are controlled regression evidence, not behavioural
  prevalence evidence.** They prove how labelled defects score on fixed
  producer bytes; they do not estimate how often an agent introduces those
  defects. The eight agent runs are still the only behavioural sample.

---

## Prior work

- [DELEGATE-52](https://arxiv.org/abs/2604.15597), by Laban, Schnabel and Neville
  (2026), studies document degradation over long delegated workflows across 52
  professional domains. It reports an average loss or corruption of about 25%
  of content for the tested frontier models, with no improvement from agentic
  tool use in its additional experiments. Those are results of that benchmark;
  this repository investigates OOXML structure and source fidelity separately.
- [python-pptx #973](https://github.com/scanny/python-pptx/issues/973) discusses
  the need for text metrics when fitting text to a shape. This is relevant to
  the font resolution and layout measurements used here.
- [Python-Redlines](https://github.com/JSv4/Python-Redlines) generates native
  Word tracked changes from DOCX comparisons. Until 1.0.0 (September 2026) its
  README documented a `WmlComparer` move-markup defect that made Word report
  unreadable content; `C2_copyclause` reproduces that class of defect. 1.0.0
  replaced the comparison engine and states the defect no longer applies. Its
  upgrade notes say revision-bearing inputs now produce different output and
  that the project's fixtures carry no input revisions, so pre-redlined
  documents are untested there by the project's own account. Not measured here.
- OOXML validators such as the [Open XML SDK validator](https://github.com/dotnet/Open-XML-SDK)
  check package or schema conformance. Source-to-output preservation and
  renderer behaviour need separate measurements. (Office-o-tron, cited in
  earlier versions of these notes, is no longer publicly available.)
- [adeu](https://github.com/dealfluence/adeu) — measured; see
  [Applying the method to other people's tools](#applying-the-method-to-other-peoples-tools).
- [docx-mcp](https://github.com/sontanon/docx-mcp) applies edits as tracked
  changes and comments. Its documented `validate` and `audit` commands cover
  annotation IDs, comment integrity and package consistency, which overlap with
  checks here. Its documented input policy rejects existing tracked changes,
  while the reference agreement in this repository deliberately includes
  counsel's pending revisions; that question is open upstream as
  [#4](https://github.com/sontanon/docx-mcp/issues/4).

---

## Where this is going

The next research step I would like to take is a shared comparison of DOCX
editing tools and agent setups. It needs more source documents, labelled
outputs and a method that records the model, prompt, tools and budget for
each run. That would let us study preservation and cost together.

For now, the existing evidence is enough to reproduce particular failures
and keep them covered by regression checks. Examples from workflows where
automated edits are followed by human review would help determine which
documents and operations to add next.
