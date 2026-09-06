# Research notes

The experiments, measurements and evidence behind
[`ooxml-integrity`](../README.md). The README says what the tool does; this
document says why it exists and how its claims were checked. Read
[Limitations](#limitations) before citing any number here.

## The finding

Two agents were given the same document — a services agreement carrying tracked
changes from counsel and two reviewer comments — and the same task: update three
figures in the milestone table.

One agent was given no budget constraint. It read the raw XML, noticed the fee
sat inside counsel's unaccepted insertion, and wrapped its own edits as tracked
changes under a separate author. The other was told it was a routine edit and to
be quick. It used `python-docx`.

Opened side by side in Word:

![Word for Mac, both files open side by side. Left: the fast agent's output, with
two comments in the pane. Right: the careful agent's output, with five comments
including the reviewer's, and the table edits shown as tracked changes.](word-comparison.png)

*Left: fast agent. Right: careful agent. Look at the comment panes — the fast
agent's file is missing M. Reviewer entirely — and at the colour of the table
figures: blue and underlined on the right, plain black on the left.*

|                                  | fast agent                        | careful agent                     |
| -------------------------------- | --------------------------------- | --------------------------------- |
| Reviewer comment in margin       | **absent**                        | present, anchored to the figure   |
| Table edits                      | **untracked** (0 `w:ins`, 0 `w:del`) | tracked (9 `w:ins`, 2 `w:del`) |
| Word warning on open             | **none**                          | none                              |
| Word count                       | 118                               | 118                               |
| Comments shown in pane           | 2                                 | 5                                 |

Two defects, and Word reports neither.

**First.** The reviewer comment *"Confirm this figure against the source table
before circulation"* is gone from the margin. Its text is still sitting in
`word/comments.xml` — it is simply anchored to nothing. The warning to check that
number vanished at the moment the number changed.

**Second, and worse.** All three edits went in *untracked*, in a document
explicitly under review. Three changes to commercial terms bypass the redline
entirely.

Same word count. Same layout. Same page count. No naive check distinguishes them.

### Why `python-docx` does this

Comment anchors live *between* runs, not inside them:

```xml
<w:p>
  <w:commentRangeStart w:id="1"/>
  <w:r><w:t>EUR 12,000</w:t></w:r>
  <w:commentRangeEnd w:id="1"/>
  <w:r><w:commentReference w:id="1"/></w:r>
</w:p>
```

Assigning `paragraph.text` drops every run and creates one new run. The anchors
go with them:

```xml
<w:p><w:r><w:t>EUR 14,000</w:t></w:r></w:p>
```

The result is schema-valid, renders correctly, and opens without complaint. The
same mechanism eats footnote references, character-style runs and tracked-change
markup.

---


## How accurate is the deck model?

`research/calibrate_pptx.py` renders every shape of the
reference deck one at a time with LibreOffice, extracts the position of every
glyph, and compares:

| | agreement |
|---|---|
| line pitch (uniform-size paragraphs, n=12) | median **0.05%**, worst **0.06%** |
| line count (24 shapes) | **23/24** exact, 1 off by one |

And against **real PowerPoint**, which is the renderer that settles it: every one
of the 21 checkable shapes got the verdict the tool predicted, with the line count
exact on all 21 - including the shape whose widest line fills 99.2% of its box,
where a disagreement was most likely. The checker and PowerPoint were reading the
same `Calibri.ttf` out of the PowerPoint app bundle, so this is a statement about
the layout model and not about font substitution. Predictions were generated
before the deck was opened; method, per-shape table and limits are in
[`docs/powerpoint-validation.md`](powerpoint-validation.md).

That check also turned up something the tool gets wrong in the other direction:
PowerPoint recomputes **neither** autofit mode when it opens a file. A deck with
`normAutofit` and no stored `fontScale` displays broken text until someone edits
the shape, and `spAutoFit` does not grow its box either - which the tool currently
treats as a warning and as nothing at all, respectively. See the validation notes
for what would settle the severities.

Two findings came out of that calibration and neither could have been guessed:

**Line spacing in DrawingML is a flat 1.2 x font size, not the font's metrics.**
Rendering the same string in Calibri, Arial, Times New Roman, Courier New,
Cambria and Verdana at 12pt and 20pt gives a pitch of exactly 1.2000 x size in
every case, while those faces' own `ascender + descender + lineGap` ratios range
from 0.80 to 1.22. Deriving line height from font metrics - correct for Word body
text - was producing a consistent +1.7% error until this was measured.

**At the margin, the renderers do not agree with each other.** The single
line-count disagreement is `FIT_mixed_run_sizes`, whose widest line fills
**99.2%** of its box. It was tempting to write that off as this model's
precision limit - advance widths cannot resolve a margin that thin, since GPOS
kerning and shaping are not applied - and that is what this document used to say.
Measuring a third engine says otherwise:

| | `FIT_mixed_run_sizes` | how it was measured |
|---|---|---|
| this model | **2 lines** | `layout_shape` |
| PowerPoint for Mac | **2 lines** | rendered, read from the outlined deck ([method](powerpoint-validation.md)) |
| LibreOffice | **3 lines** | `calibrate_pptx.py`, glyph positions from the PDF |
| ONLYOFFICE | **3 lines** | same script, same measurement code |

Two engines on each side of one string. No amount of measuring settles that -
the shape genuinely lays out differently in different renderers, so no verdict
about it can be authoritative. That is exactly what a borderline band is for:
anything within a few percent of the boundary is reported as borderline
(`PPT002`) rather than as overflow, and `pptx_checks.BORDERLINE` is now
justified by three engines disagreeing rather than by one measurement of ours.

ONLYOFFICE is also the tightest confirmation of the 1.2 constant available:
every uniform-size shape matched the predicted pitch to **0.000026% median,
0.00012% worst** - floating-point noise in the PDF, nothing more. LibreOffice's
0.05% is its own; whether that is rounding on export or a marginally different
pitch cannot be told from a PDF. Reproduce with
`research/compare_renderers.py`.

**How good is a metric-compatible substitute, exactly?** This is the one claim
that cannot be checked on a single machine - Calibri and Carlito are almost
never both installed - so it was measured across two: Carlito on Linux against
real Calibri from Microsoft 365 on macOS, both read by this module at 18pt.

| sample | Carlito | Calibri | delta |
|---|---|---|---|
| digits `0123456789 EUR 44,500.00` | 202.376953 | 202.376953 | **0.000%** |
| bold caps A–Z | 265.772461 | 265.069336 | −0.265% |
| caps A–Z | 259.171875 | 258.451172 | −0.278% |
| clause text | 444.682617 | 443.188477 | −0.336% |
| pangram | 326.276367 | 324.685547 | −0.488% |
| lowercase a–z | 213.372070 | 212.132812 | −0.581% |

Digits match to the last unit — tabular figures are designed to. Letters do not:
Carlito runs **0.26–0.58% wider**. So "metric-compatible" means close enough to
act on, not identical, and this document used to overclaim it.

Two consequences worth stating. The substitution error is the same order as the
GPOS-kerning gap, so the 5% `BORDERLINE` threshold covers both with room. And it
has a direction: measuring Calibri text with Carlito *overstates* width, so it
leans toward reporting an overflow that is not there rather than missing one —
the safe direction for a checker.

**A limit that cannot be engineered away.** Which font a deck renders with still
depends on what is installed where it is opened, so the checker says what it
measured with:

```
[INFO ] PPT007  Segoe UI is not installed and has no known substitute; measured
                with DejaVu Sans - widths are a guess. 1 shape(s) affected;
                overflow verdicts for them are estimates
```

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

Both fixtures rebuild byte-identical, which is what makes `git diff` a usable
assertion in CI. `assert_deck.py` compares the whole multiset of finding codes
rather than the exit code, because a machine with no usable fonts reports the
same layout problems as warnings and exits 0 — an exit-code check would call
that a pass, which is the exact failure this tool exists to catch.

`libreoffice` on `PATH` is needed for the rendering check. Total runtime is a
couple of minutes, most of it LibreOffice.

`research/add_settings.py` injects `word/settings.xml` into an existing package
without touching anything else — see `runs/README.md` for why that exists.

The reference document is assembled part-by-part rather than with `python-docx`,
because `python-docx` cannot create most of what needs testing: footnotes,
comments, tracked changes, content controls. It carries named paragraph and
character styles, multi-level numbering, two footnotes, two comments, three
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
report precision/recall per measured rule and producer; unmeasured rules and
limitations of the captured builds/web session remain explicit instead of
inheriting the measured rules' score.

---

## What each verification approach catches

`ok` means "no problem found" — i.e. the defect was **missed**.

```
defect introduced by the agent          well-   schema  render   inspector   fidelity
                                        formed          (LO)                 vs source
python-docx: open and save, no edit     ok      ok      ok       ok          ok
python-docx: paragraph.text = ...       ok      ok      ok       2 found     5 losses
LLM edits a value in raw XML            ok      ok      ok       ok          ok
LLM clones a block for "one more clause ok      ok      ok       1 found     3 losses
LLM reformatted the XML                 ok      ok      ok       5 found     ok
LLM deleted a para holding a footnote a  ok      ok      ok       1 found     3 losses
LLM renamed a style, left refs dangling ok      ok      ok       4 found     ok
round-trip through markdown             ok      ok      ok       ok          12 losses

Real defects introduced: 6
  missed by well-formed check:  6/6
  missed by schema validation:  6/6
  missed by PDF rendering:      6/6
  caught by this prototype:     6/6
```

Rows one and three are controls — genuinely clean edits, correctly reported clean.

The render column is the interesting one. Rendering is the current state of the
art: [Anthropic's official `pptx` skill](https://github.com/anthropics/skills/blob/main/skills/pptx/SKILL.md)
converts through LibreOffice to PDF, rasterises the pages, and hands the images
to a subagent to inspect for overlap and overflow. On this defect class its
detection rate is zero — not because it looks badly, but because none of these
defects are visible in a picture.

### Two questions, not one

A document stripped of every style, footnote and revision is *perfectly
self-consistent*. The markdown round-trip row proves it: the inspector finds
nothing wrong, and the file has lost 100% of its styles, numbering, footnotes,
comments, revisions, content controls, tables and images.

So there are two questions, and both are needed:

- **Self-consistency** — do the internal references resolve? (`inspect_docx.py`)
- **Fidelity** — what was lost relative to the source? (`fidelity.py`)

Nothing I could find does the second.

---

## Real agent runs, including the result that went against me

The mutators above are hand-written. That makes them a demonstration, not a
benchmark — so eight real agent runs were done instead. Each agent got its own
copy of the document, a task phrased the way a user would phrase it, and no hint
about how to edit. Tooling choice was the variable being measured.

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

**Six careful runs produced zero structural defects.** All six independently
declined `python-docx` — several said outright that it cannot round-trip tracked
changes — went to raw XML with targeted replacements, and wrapped their edits as
tracked changes with separate authorship. Two spotted that the fee sat inside
counsel's pending insertion and built correct `w:ins > w:del` nesting for it.

So the claim "agents corrupt documents" is **wrong as stated**, and I am not
making it. The honest claim is narrower:

> The variance between agents is total, and it is invisible. Same task, same
> document, same day: one pipeline produces a correct multi-author redline, the
> other silently detaches the reviewer's warning. Nothing downstream can tell
> which one you got.

That is a benchmarking and CI problem more than a linting problem. The useful
question is not "is this file broken" but "which of my document pipelines is
safe".

The obvious objection — *just use a better agent* — has a cost answer. The
careful runs spent 67–86k tokens and 18–29 tool calls on a two-line edit. Nobody
pays that for routine work at volume, so routine work will keep taking the cheap
path. And the fast agent did not report a problem, because it did not know it had
caused one.

### The agent runs also found three bugs in the checker

Worth stating plainly, because it is the main argument for running real agents
rather than writing mutators:

| code     | was                                                        | now                                                                                              |
| -------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `REV003` | any `w:delText` inside `w:ins` flagged as a defect          | `w:ins > w:del` nesting is legal and means "inserted by one author, deleted by another". Tests the *nearest* revision ancestor now |
| `PKG005` | zip directory entries (`word/`, `docProps/`) flagged as uncovered parts | skipped — not OPC parts, and Word tolerates them                                    |
| `FID002` | any increase in construct count flagged as duplication      | an agent may legitimately add a clause. Real duplication is caught by colliding ids (`REV001`) |

For a linter, precision matters more than recall: one that cries wolf on a valid
file gets switched off. Regression after the fix is clean — all six hand-written
defects still caught, zero false positives across the eight agent runs.

---

## Accumulation

Twenty successive edit cycles, following the round-trip design of
[DELEGATE-52](https://arxiv.org/abs/2604.15597) but measuring at the file level
rather than semantically:

- Footnotes and comment anchors drop to **50%** on the *first* cycle and stay
  there. The loss is irreversible; later edits do not restore it.
- Tracked changes grow to **233%** through duplicated revision ids.
- An error introduced at cycle 3 survives to cycle 20.
- LibreOffice converts all twenty versions without a single complaint.

---

## Limitations

Read these before citing any number in this document or in the README.

- **The 50-source beta evidence tranche is synthetic.** It covers six document
  classes and five producers, but not customer document
  distributions, other Office builds/web sessions, or an independently supplied
  generator. Its 100% figure applies only to the 14 measured rules; the
  per-rule report names every unmeasured DOCX rule.
- **Schema validation is approximated.** The full ECMA-376 XSDs are not bundled;
  `compare_detectors.py` checks namespaces and root elements. For these
  mutations the verdict matches what a real XSD gives — every one is
  schema-legal, because they break referential integrity rather than grammar —
  but swap in a real validator before quoting the schema column.
- **Structural evidence is not visual accuracy.** DOCX evidence includes real
  saves through Word for Mac, Word for Windows and LibreOffice, plus actual
  Word Online edits. The web capture includes supplementary page inspection
  through a local LibreOffice render. Neither that review nor the structural
  scores establish general visual fidelity; systematic ONLYOFFICE DOCX
  behaviour remains untested.
- **Neighbouring tools are described from their documentation, not from
  running them.** `OfficeCLI` and `docx-mcp` are summarised in Prior work from
  their own READMEs and command help. Before quoting any comparison, run them.
- **`OfficeCLI` not compared.** Its `validate` command is schema-only by its own
  documentation, and `view issues` covers text overflow, contrast, alt text and
  inconsistent fonts — no overlap with the defects here. That should be confirmed
  by running it, which I have not done.
- **Eight agent runs is a small sample**, on one document, with one task family,
  on one day. The careful/fast split is suggestive, not established.
- **The PowerPoint check is one build on one platform.** 21 of 21 shapes agreed,
  with every line count exact (`docs/powerpoint-validation.md`), but that is
  PowerPoint for Mac in the editing view, read from screenshots. Windows and
  Slide Show mode are untested.
- **Only the Carlito/Calibri pairing has been measured** (see the table above).
  The other entries in `METRIC_SUBSTITUTES` — Caladea/Cambria, Liberation
  Sans/Arial, Liberation Serif/Times New Roman, Liberation Mono/Courier New,
  Gelasio/Georgia — are taken on their designers' word and should get the same
  treatment.
- **No GPOS kerning or shaping.** Only the legacy `kern` table is read. This is
  the ~1% precision limit described above, and it makes measurements for
  complex scripts and heavily-ligatured display faces untrustworthy.
- **Font discovery is best-effort.** `fc-match` is used where fontconfig exists;
  otherwise the standard font directories are scanned. A machine with neither
  gets a `PPT000` error saying overflow was not checked - which is the point,
  but it does mean the text checks are only as good as the fonts installed.
- **The mutators are controlled regression evidence, not behavioural
  prevalence evidence.** They prove how labelled defects score on fixed
  producer bytes; they do not estimate how often an agent introduces those
  defects. The eight agent runs are still the only behavioural sample.

---

## Prior work

- [DELEGATE-52](https://arxiv.org/abs/2604.15597) — Laban, Schnabel, Neville
  (Microsoft Research, 2026). Frontier models corrupt ~25% of document content
  over long delegated workflows; agentic tool use does not help. Measures
  *semantic* degradation. This repo is the file-level complement — the structural
  half nobody has published.
- [python-pptx #973](https://github.com/scanny/python-pptx/issues/973) and four
  sibling issues — text autofit is unimplementable without text metrics. Root
  cause of most "the AI deck looks broken" reports.
- [Python-Redlines](https://github.com/JSv4/Python-Redlines) — its README
  documents an unfixed revision-id collision that makes Word report "unreadable
  content". Mutator `C2_copyclause` reproduces that defect class.
- [Office-o-tron](https://github.com/DEVSDMF/office-o-tron) and other OOXML
  validators — answer "is this schema-valid", not "will Word render this
  correctly".
- [adeu](https://github.com/dealfluence/adeu), safe-docx, docx-redline-js — the
  small ecosystem of tools attempting faithful docx editing. None ships a
  conformance suite, so nobody can say which of them is safe.
- [docx-mcp](https://github.com/sontanon/docx-mcp) — the closest overlap, and
  worth being precise about. It is a redlining *engine*: it applies AI-generated
  changes as tracked changes and comments, and ships `validate` and `audit`
  commands that check annotation-id isolation, comment integrity and package
  consistency. So the self-consistency half of this repo is not unique. Two
  things differ. It has no source-to-output comparison, which is where the
  defects that leave a self-consistent file live. And it *rejects* documents that
  already contain `w:ins` / `w:del` — which is exactly the case this repo is
  about, a contract already carrying counsel's unaccepted changes.

---

## Where this is going

The gap I set out to test is real: no existing tool answers "is this
agent-produced document safe to send". But the agent runs reframed it. The value
is less in catching broken files after the fact and more in **ranking pipelines
before you trust them** — which argues for a public benchmark across the docx
editing tools and agent harnesses, run on a real corpus, with a reproducible
method.

That is what I would like to build next, and it needs a corpus. If you have
document workflows where an agent edits files that someone else then reviews, I
would like to hear what breaks for you.

