# Review-history benchmark — wave 1

When a tool makes an ordinary edit to a DOCX that already carries comments,
other authors' pending revisions and notes, what survives, and does
`ooxml-integrity` report what does not? The [protocol](PROTOCOL.md) and its
[30 task declarations](tasks.json) were frozen in [protocol.json](protocol.json)
before the first capture. Two sources: S1 is `corpus/base.docx`; S2 is a review
record [written by Word for Mac](sources/README.md). Wave 1 ran seven tools and
a reference control on 2026-09-30 and 2026-10-01, two captures each. Counts are
attempts on two documents, not independent documents.

## Results

| Tool | Ran | Unsupported | Rejected | Completed | Preserved | Damaged outputs: checker finding on the damaged construct |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| reference control | 60 | 0 | 0 | 60 | 60 | none damaged |
| python-docx `Run.text =` | 28 | 32 | 0 | 20 | 28 | none damaged |
| python-docx `Paragraph.text =` / `_Cell.text =` | 28 | 32 | 0 | 18 | 14 | 14 of 14 |
| adeu 3.0.6 | 34 | 24 | 2 | 30 | 30 | 4 of 4 (K6, see below) |
| docx-cli 0.26.0 | 56 | 4 | 0 | 46 | 18 | 8 of 38 |
| Office-Word-MCP-Server 1.1.11 | 24 | 36 | 0 | 12 | 18 | 4 of 6 |
| docx-mcp 0.7.4 | 36 | 4 | 20 | 34 | 36 | none damaged |
| docxengine 1.0.0 | 40 | 0 | 20 | 32 | 34 | 2 of 6 |

*Unsupported* is an operation the tool has no interface for; *rejected* is the
tool refusing with its own message. *Completed* and *Preserved* count the
attempts that ran. The last column counts outputs with a preservation failure
and, of those, the outputs where the checker (0.4.6, the published wheel)
reported an ERROR or WARN from a rule that concerns a damaged category. The
protocol's primary rule counts any new ERROR/WARN; [evaluation.json](evaluation.json)
has both, and every finding.

## What the tools did

**python-docx** has no tracked changes, replies or note API. Its setter path
loses comment anchors and footnote references and overwrites a pending header
revision it cannot see; the run path preserves everything where the old text
is a whole run. It does not see text inside `w:ins`, so K4 is saved unchanged.

**adeu** completes and preserves all 11 tracked replacements it ran, including
inside another author's insertion next to a third author's nested deletion,
and K5 with a threaded reply. Plain replacements are unsupported by design. It
refused K7h on S2 as ambiguous (`Consulting Services` is also the document
title). It resolves a same-author deletion and insertion forming one
replacement as a single unit, by design; both K6 targets are halves of such
pairs, so K6 is not completed as declared and `FID001` fires as it does on any
resolution. Inside another author's insertion it keeps one `w:id` on both
fragments (`REV001`, the BND-001 class).

**docx-cli** completes most tasks, with three kinds of damage the checker does
not report (the first two confirmed in Word for Mac, [word check](word-check/README.md)):

- On every S1 output it rewrites `w:lvlText w:val="&#8226;"` in
  `numbering.xml` as `&amp;#8226;`, so the bullet becomes the literal text
  `&#8226;`.
- Inside another author's insertion (K4) the new text lands in that insertion
  without the editor's wrapper, so it reads as the other author's. On S2, next
  to Reviewer B's nested deletion, the edit also deletes the wrong span
  (` The Client may` instead of `disputed amount`).
- A tracked note edit (K7n) deletes the whole note text and inserts the whole
  new text. Nothing is lost, but the tracked deletion is wider than the edit.

Replacing header text applies directly even with `--track`, as the tool
documents; on S2 that overwrites Reviewer A's pending revision (detected:
`FID007`, `FID008`).

**Office-Word-MCP-Server** has no tracked changes, replies or note editing.
`format_table_cell_text` loses the commented cell's anchor (K2, detected:
`CMT005`), as found on 2026-09-23. `search_and_replace` does not search headers,
and on S2 it replaced `Consulting Services` in the document title instead of
the header (not reported: the checker does not compare body text).

**docx-mcp** preserves everything it ran. It addresses paragraphs by
`w14:paraId`, which it does not assign, so it rejects every paragraph-level
task on S1 (generated without paraIds), and it refuses to edit inside another
author's insertion ("accept or reject the insertion first"). Its new comment
anchors a whole paragraph and its reply has no anchor in the document (K5 not
completed; `CMT005` reports the reply as invisible in Word).

**docxengine** searches only body paragraphs: it rejects the table cell (K2),
S1's header and both sources' notes, and on S2 it edited the document title
instead of the header (not reported). Adding a comment to S1's classic comments part
writes `w14:paraId` without declaring the namespace, so `comments.xml` is not
well-formed although its own pre-save validation passed (detected: `XML001`,
`CMT004`, `CMT006`). Like docx-mcp, its K5 reply has no document anchor.

## Checker false alarms on correct edits

The reference control (60 of 60 pass) shows what the frozen rule counts as a
false alarm: `FID001` on requested accept/reject (K6), `FID007`/`FID005` on
requested untracked header and note edits, `FID007` on a tracked header edit
next to a pending revision (corrected after 0.4.6 in #40), and `FID009` on a
requested direct edit inside another author's insertion. Tools that perform
these tasks get the same findings. Three counted false alarms are true reports
outside this benchmark's scope: `STY001` on S1, where python-docx's new comment
references a `CommentReference` style S1 does not define (docx-cli does the
same, on outputs already damaged), `REV001` for
adeu's repeated revision id, and `CMT005` for replies with no document anchor
(docx-mcp, docxengine), which Word for Mac indeed does not display
([word check](word-check/README.md)).

## Amendments

Seven amendments, each before the captures it affects and before any result was
reported; protocol text, tasks, sources and the oracle never changed.
[1](amendments/001-incomplete-edits.json): an unchanged target paragraph is an
incomplete task, not damage. [2](amendments/002-adeu.json) and
[3](amendments/003-wave1-tools.json): declare adeu and the four other tools,
their images, locks and task mappings. [4](amendments/004-malformed-packages.json):
a part no XML parser accepts makes the package damaged. [5](amendments/005-runner-fixes.json)
and [6](amendments/006-docx-cli-note-text.json): two adapter errors - note text
handled wrongly for each tool's API, and docx-cli's tracking switched off only
for body edits; the affected captures are kept, marked superseded and left out
of the evaluation. [7](amendments/007-relative-checker-paths.json): the checker
runs with repository-relative paths, so no local directory enters its messages.

## Method

The [oracle](../../research/review_history_oracle.py) reads each package into
review facts and never imports the checker; the
[evaluator](../../research/review_history_benchmark.py) scores status,
completion, preservation (the oracle's report minus what the task declares,
and inside the edited paragraph a character-by-character check of revision
ownership) and the checker. Before any capture the oracle was checked on 27
seeded mutations and no-op controls, and the evaluator on the reference control
and nine negative controls; the amendments added three more controls. Every
third-party tool ran in its own container per attempt: base image by digest,
dependencies from a hashed lock or a SHA-256-checked bundle, no network, user
65534, all capabilities dropped. Repeats agree fact for fact except the dates
adeu, docx-mcp and python-docx stamp.

## Limits

Two sources and one version of each tool. Formatting, layout and rendering are
not compared. Only one output per damage class was opened in Word, in one
build of Word for Mac ([word check](word-check/README.md)). The structured call names the old text only, so a tool that searches the
whole document can refuse a target that is unique only within its story. Agents
are wave 2.

```sh
python research/review_history_benchmark.py verify
python research/review_history_benchmark.py evaluate-all --checker PATH/TO/0.4.6/python
python -m pytest tests/test_review_history_oracle.py tests/test_review_history_benchmark.py
```
