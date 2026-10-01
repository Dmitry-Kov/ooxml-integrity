# Review-history benchmark — wave 1: python-docx and adeu

When a tool makes an ordinary edit to a DOCX that already carries comments,
other authors' pending revisions and notes, what survives, and does
`ooxml-integrity` report what does not? The [protocol](PROTOCOL.md) and its
[30 task declarations](tasks.json) were frozen in [protocol.json](protocol.json)
before the first capture. Two sources: S1 is `corpus/base.docx`; S2 is a review
record [written by Word for Mac](sources/README.md). Wave 1 runs python-docx
1.2.0 on two paths and a reference control (2026-09-30), and adeu 3.0.6 in its
own container ([amendment 2](amendments/002-adeu.json), 2026-10-01), two
captures each. Counts below are attempts on two documents, not independent
documents.

## Results

| Adapter | Attempts | Unsupported | Completed | Preserved | Pass | Checker (0.4.6) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| reference control | 60 | 0 | 60 | 60 | 60 | 44 clean, 16 false alarms |
| python-docx `Run.text =` | 60 | 32 | 20 of 28 | 28 of 28 | 20 | 22 clean, 6 false alarms |
| python-docx `Paragraph.text =` / `_Cell.text =` | 60 | 32 | 18 of 28 | 14 of 28 | 6 | 14 detected, 0 missed, 10 clean, 4 false alarms |
| adeu 3.0.6 | 60 | 24 (+2 rejected) | 30 of 34 | 30 of 34 | 30 | 26 clean, 4 false alarms, 4 detected |

*Unsupported* is what the tool has no API for: for python-docx tracked
replacements, K6 (accept/reject) and K7n (note bodies); for adeu every plain
replacement, because adeu writes only tracked changes. *Completed* and *Preserved* count the
attempts that ran. The checker column is the protocol's primary, per-output
rule: a preservation failure is detected if the checker reports any new ERROR
or WARN; an output without one is a false alarm if it does.

Per task, identical in both captures:

| Task (plain mode) | Setter path | `Run.text` path |
| --- | --- | --- |
| K1 phrase in a commented range | loses the comment anchor (S1 also the footnote reference); detected: `CMT005`, `FID001`, `FTN002` | preserved |
| K2 table cell with a comment | `_Cell.text =` loses the anchor; detected: `CMT005`, `FID001` | preserved |
| K3 sentence with a footnote | loses the footnote reference; detected: `FID001`, `FTN002` | preserved |
| K4 inside another author's insertion | not completed: python-docx does not see text inside `w:ins`, so the document is saved unchanged | same |
| K5 reply and new comment | not completed: no replies; `add_comment` anchors the whole run | same |
| K7h header (S2: next to a pending revision) | S2: overwrites the pending `3`/`4` revision it cannot see; detected: `FID007`, `FID008` | preserved |

The setter path is what tutorials and MCP wrappers use; the damage the source
reading predicted is confirmed, and the checker caught all 14 damaged outputs.
The run path preserves everything where the old text is a whole run.

## adeu 3.0.6

adeu completes and preserves every tracked replacement it ran - inside commented
ranges, a commented table cell, a sentence with a footnote, inside another
author's insertion next to a third author's nested deletion, in the S1 header
and in both footnotes - and K5 with a threaded reply and a comment-only edit.
It refused K7h on S2 with an ambiguity error and a list of both matches:
`Consulting Services` occurs in the header and in the document title. The task
file checked uniqueness only within the header, so this is a correct refusal of
the structured call, not a failure.

K6 is not completed as declared. adeu resolves a same-author deletion and
insertion that form one replacement as a single unit, by design (its
`AI_CONTEXT.md`, "Replacement Pairs Resolve as ONE Unit"; the projection marks
them "pairs with Chg:N"). Both K6 targets turned out to be halves of such pairs:
rejecting S1's deletion of `EUR 40,000` also rejected the paired insertion
`EUR 44,500`, and accepting S2's insertion `forty-five` also accepted the
deletion of `thirty`. Word resolves the halves separately, so the outputs differ
from the declared texts; under adeu's own model nothing unrequested happened.
The checker's `FID001` on these outputs counts as a detection under the frozen
rule, but it fires on every resolution, including the reference control's.

Inside another author's insertion (K4), adeu splits that insertion into two
fragments that keep one `w:id`. Text, authorship and dates are intact, so the
oracle records no loss; the checker's `REV001` reports the ID collision, the
same class as BND-001, which Word for Mac opened without a repair prompt in the
[earlier follow-up](../docx-word-id-followup/README.md). Under the frozen rule
it counts as a false alarm.

## Checker false alarms on correct edits

The reference control performs every task correctly (60 of 60 pass), so every
checker finding on it is a false alarm under the frozen rule:

| Task | Finding | Cause |
| --- | --- | --- |
| K6 accept/reject (S1, S2) | `FID001` ERROR | intentional resolution lowers the revision count; there is no contract for requested revision removal yet |
| K7h header, plain (S1, S2) | `FID007` ERROR | an untracked header edit is reported as a lost story; the same untracked edit in the body is not reported |
| K7n footnote, plain (S1, S2) | `FID005` ERROR | likewise for a note body |
| K7h header, tracked (S2) | `FID007` ERROR | the header already had a pending revision; 0.4.6 keeps the exact match for such items |
| K4 inside an insertion, plain (S1) | `FID009` ERROR | a requested direct edit changes another author's pending insertion text |

The python-docx false alarms are the same `FID007` on plain header edits, and
`STY001` WARN on S1's K5: `add_comment` references the character style
`CommentReference`, which S1 does not define. That warning is true, but style
definitions are outside this benchmark's scope, so the frozen rule counts it as
a false alarm.

## Method

The [oracle](../../research/review_history_oracle.py) reads each package into
review facts (comments, anchors, threads, resolution, people, revisions with
author, date, nesting and payload, notes, header/footer stories, paragraphs,
lists, content controls, tables, hyperlinks, images, settings, other parts) and
never imports the checker. The [evaluator](../../research/review_history_benchmark.py)
scores status, completion, preservation (the oracle's report minus what the
task declares, and inside the edited paragraph a character-by-character check
of revision ownership) and the checker, run from an environment installed from
the exact public 0.4.6 wheel. Before any capture, the oracle was checked on 27
seeded mutations and no-op controls, and the evaluator on the reference
control and nine negative controls; amendment 1 added two more controls.

[Amendment 1](amendments/001-incomplete-edits.json) corrects the evaluator after
the first evaluation and before any result was reported: an unchanged target
paragraph (python-docx K4) had been scored as damage instead of an incomplete
task. Protocol text, tasks, sources, adapters and captures are unchanged.

Repeats agree fact for fact except the dates the tools stamp: python-docx's new
comment and adeu's new revisions and comments carry the save time. Each attempt has an exclusive receipt under
`captures/<adapter>-<repeat>/receipts/`; `evaluation.json` holds every result,
including the checker's full findings.

## Limits

Two sources and one version of each tool. Formatting, layout and rendering are
not compared. No output has yet been opened in Word; the protocol's native check
of one representative output per loss class is still to come. The structured
call names the old text only, so a tool that searches the whole document can
refuse a target that is unique only within its story. Agents and the remaining
wave-1 tools (docx-cli, Office-Word-MCP-Server, docx-mcp, docxengine) run later,
each in its own container and after its own approval.

```sh
python research/review_history_benchmark.py verify
python research/review_history_benchmark.py evaluate-all --checker PATH/TO/0.4.6/python
python -m pytest tests/test_review_history_oracle.py tests/test_review_history_benchmark.py
```
