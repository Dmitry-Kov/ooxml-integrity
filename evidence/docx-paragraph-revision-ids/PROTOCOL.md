# Unreleased paragraph revision ID regression gate

This is a current-checker re-evaluation of existing saved outputs, not a new
editor/model run. Historical input/output hashes, labels, captures and receipts
are immutable. Native observations and the narrow code exception are described
in [scope and evidence](../../docs/paragraph-revision-ids.md).

Retain the preceding FID009 and FID010 expectations. For all 168 saved benchmark
and Word output pairs, require exactly the former ordered findings and all their
fields, allowing only these declared suffix replacements on the named codes:

- `REV001`: remove the categorical Word unreadable-content claim; retain the
  ID, occurrence count, ERROR severity and location.
- `FID002`: remove the assertion that only colliding IDs make an addition
  defective; retain construct labels, before/after counts and INFO severity.

The exact old/new suffixes are in [expectations.json](expectations.json). No
finding addition/removal, severity, location, count or other field change is
permitted. The 45 attempts without an output remain unevaluated. Changed pair
IDs are recorded explicitly; the evaluator must not discard all messages or
pretend wording is unchanged. Existing adjacent content collisions remain errors.

This declaration was added after the old gate rejected the first changed
message. A complete local comparison found only 80 FID002 and 10 REV001 message
changes across 40 of the 168 pairs. This is a declared diagnostic update, not
a predeclared editor experiment or a relabeling of outcomes.

Run from the repository root with the development environment:

```sh
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs --output tmp/new-paragraph-id-review.json
python research/build_docx_evidence.py evaluate --output tmp/new-paragraph-id-corpus.json
python research/replay_frozen_docx.py
python -m pytest -ra
```

Use fresh output paths; receipts refuse overwrite. The previous note-revision
directory remains valid for its original code/message contract and intentionally
rejects the new wording. No historical evidence is updated to make it pass.
