# Boundary observations and checker limits

## BND-001 — repeated deletion ID after the split-format edit

**Real captured output; protocol failure, practical impact unresolved.**
Adeu 3.0.4 with the frozen SDK adapter completes EDITBEFORE → DONEAFTER and
preserves the two requested formats, comments/notes and all previous revisions.
It emits two adjacent new `w:del` elements with the same ID (one for bold EDIT,
one for italic BEFORE). The new insertion contains both correctly formatted runs.
All five sources show this in both captures (10 operations, five documents).

For [basic-split.docx](captures/adeu-1/basic-split.docx), both deletions have ID 104;
the insertion has ID 105. Other profiles use 203, 402, 503 and 303 for the repeated
deletions. IDs differ with the maximum pre-existing revision ID in the input.
The raw independent revision oracle lists the duplicate. `check()` reports
`REV001` ERROR for precisely that ID; the other findings are INFO. No content,
formatting, anchor, old-review-record or package-part loss was established.

The frozen protocol inherited the original corpus's unique-ID check, so these
operations fail its full preservation/integrity criterion. That is **not proof
of a Word repair dialog or data loss**. The installed adeu source explicitly
reuses IDs to group logical changes (track_insert docstring and track_delete_run
reuse_id calls). Whether these particular adjacent fragments should trigger a
hard checker error needs separate review. Treat this as a compatibility question,
not an established upstream corruption bug or an unconditional checker TP.
The checker message's claim about an unreadable-content warning has not been
observed on these files. No checker rule was changed during this benchmark.

One-pair replay, without running an editor:

```sh
PYTHONPATH=src .venv/bin/python -m ooxml_integrity check \
  evidence/docx-benchmark-boundaries/captures/adeu-1/basic-split.docx \
  --against evidence/docx-benchmark-boundaries/sources/basic.docx --no-config --json
```

This exits 1 because of REV001. Fresh SDK capture and independent evaluation:

```sh
tmp/e1/adeu-env/bin/python research/docx_boundaries.py capture \
  --adapter adeu-sdk-boundaries-v1 --directory tmp/boundaries-adeu-fresh
.venv/bin/python research/docx_boundaries.py evaluate tmp/boundaries-adeu-fresh
```

A separate follow-up should check a copy in a named Word build, retain any repair
log and resulting package, and review revision-group ID semantics before deciding
whether to report an adeu issue or improve REV001. Opening successfully alone does
not establish normative conformance. This Office follow-up was not run here.

## BND-002 — model execution failures

**Real generated scripts, not artificially damaged DOCX files.** The fixed local
model is given the declared tasks without API instructions or checker feedback.
Observed script failures include searching for a single run that is both bold
and italic, using a nonexistent `Paragraph.comments` property, and assigning the
unexpanded lxml tag name `w:t`. These are errors of this one-response script
pipeline. They do not establish that python-docx cannot perform the task; the
public-API v2 adapter performs all three edits. Exact errors, responses and scripts
are retained per attempt. No repair attempt, changed prompt or alternative model
is included in the score. Final counts and variation are in the main report.

## Checker blind spots: synthetic evidence, excluded from editor results

[seeded-bold-loss.docx](diagnostics/seeded-bold-loss.docx) deliberately performs
the exact split replacement, then removes bold from DONE. The independent
comparison reports a formatting difference while the checker emits no ERROR/WARN.
[The receipt](diagnostics/seeded-bold-loss.json) records hashes and both assessments.
This is a deliberately introduced defect, not an observed loss from adeu or the
local agent. The checker is not a general run-formatting preservation checker.

Earlier known misses remain: count-neutral replacement of an old insertion's
payload, stripping a footnote insertion while retaining text, and moving a comment
start anchor with unchanged marker counts/definitions. See
[v1 known gaps](../docx-benchmark/KNOWN_GAPS.md). The first two came from the old
revision fault-injection cohort, the anchor example from v1 diagnostics. They are
not new failures among these real boundary operations.
