# DOCX preservation benchmark v1 — declared before fresh runs

Question: does a small specified edit preserve comments, pending revisions and
other package content? This is a fixture-specific adapter comparison, not a
library/model ranking or a visual fidelity assessment.

## Inputs and tasks

Use the five unchanged `../docx-revisions/sources/{basic,nested,table,notes,stories}.docx`
files. `protocol.json` pins their SHA-256 hashes, the base Git commit, the existing
oracle and this protocol. Each has one ordinary body run containing `EDITBEFORE`,
in the third body paragraph beside pending insertions 101 and 103. The comment
and its footnote reference are in a different paragraph. Profiles add nested,
table-cell, footnote and header/footer revisions. No new source is generated.

For every source, perform both operations in a fresh editor instance:

* `save`: open and serialize to a new DOCX without editing; copying the file is
  not this control.
* `edit`: replace the unique current-text marker `EDITBEFORE` with `EDITAFTER`
  exactly once. Change no other wording and do not accept/reject old revisions.
  The replacement may be untracked, or one deletion/insertion pair authored
  `Evidence Editor`. Adeu's declared mode requires this new tracked pair;
  python-docx's declared mode requires an untracked replacement.

## Protected content and success

Preserve all pre-existing revision payloads, authors, dates and nesting in every
XML story, all other current text, comment definitions and anchor positions,
notes and their references, tables/cell boundaries/widths, styles, numbering,
section properties, relationships and binary parts. Do not remove or add parts.

Reuse `research/revision_evidence.py`'s independent XML facts/oracle, without
changing it or the production checker. Add only a bounded package comparison:
compare expanded XML names, attributes, text and child order, plus binary bytes.
Ignore ZIP metadata, XML declarations, namespace prefixes/declarations, attribute
order, insignificant XML whitespace, relationship/content-type entry ordering
and an explicit relationship `TargetMode="Internal"` versus its default omission.
Record core `modified`, `lastModifiedBy`, `revision` metadata changes separately;
these three fields may change, all other metadata remains protected.

In the third body paragraph only, undo a new exact marker revision pair for the
protected-content comparison, normalize old/new marker text to the old marker,
and coalesce adjacent text-only runs with equal run formatting. Normalize
`xml:space` on those runs only. Existing revision wrappers remain protected;
other run content, formatting and anchor positions remain protected. This is
not an algorithm for arbitrary paragraph rewrites or relationship renumbering.
A residual difference is an undeclared change requiring inspection, not automatic
proof that the file is corrupt. No post-run broadening of these allowances.

Assess four independent axes per attempt:

1. Adapter status: `ok`, `unsupported` (target outside this adapter's scope),
   `rejected` (tool reports a refused operation), `error`, or `not_run`.
2. Task completion: valid output exists and marker counts/current text establish
   the requested operation. For adeu edits, also require the new tracked pair.
   Missing replacement never passes merely because the checker is quiet.
3. Preservation: old revision payloads and protected structures/text/package
   have no undeclared losses or changes. Normalize the target separately so a
   missing edit alone is not mislabeled collateral loss.
4. Checker: run unconfigured `check(output)` plus `compare(source, output)`;
   retain all raw findings and distinguish ERROR/WARN from INFO additions.
   Run the same checks on each source first. Report defect detection only when
   a finding corresponds to an independently established defect; warning counts
   alone are not quality scores. A task failure with no loss is not a fidelity FN.

Overall success requires `ok`, completed task and preserved protected content.
No-op control completion requires actual adapter open/save, plus unchanged marker;
all other preservation is scored separately. Rendering and visual identity are
unmeasured. The strict package comparison also protects unused assets, but their
presence does not measure how a renderer uses them.

## Pipelines and repetitions

* `adeu-sdk-v1`: published `adeu==3.0.4`, Python 3.12. Load `RedlineEngine` from
  `BytesIO`, author `Evidence Editor`; defaults retain all protection gates.
  Save with `save_to_stream()`. Edit with exactly one `ModifyText` (strict match,
  regex false, comment null), `process_batch(partial=False)`, then save.
* `python-docx-run-v1`: `python-docx==1.2.0`. `Document(input)`, find the sole
  matching direct body `paragraph.runs` item, assign only its `Run.text` after
  one replacement, then `Document.save(output)`. No paragraph/cell text setter,
  private XML manipulation or monkeypatch. Missing/ambiguous run is unsupported.
  Scope is the pinned text-only target run, not arbitrary drawings/fields or a
  marker split across runs. `Run.text` replaces other content inside its run.
* `local-agent-v1`: fixed single-response Python-script generation scenario in
  `AGENT.md`; no checker feedback, retries or cherry-picking. Three fresh trials
  per source and operation, seeds 101/102/103. No execution unless the specified
  local model/runtime is available. No paid API or remote document upload.

Run both deterministic adapters twice (two captures of 10 attempts each) to
verify reproducibility. Report each capture separately: repeats are not new
independent documents. Compare task/preservation/findings and normalized package
hashes across captures. Raw ZIP hashes may differ because of timestamps/new
revision dates; keep raw bytes and every hash rather than rewriting captures.

## Evidence and interpretation

Freeze this protocol and inputs before fresh adapter outputs. Capture start/end
UTC, versions, installed distribution/source hashes, command and parameters,
source/output SHA-256, raw tool statistics, errors and logs. Evaluate outputs
separately after capture; retain full independent oracle details and checker
findings. Refuse overwriting receipts/outputs and fail verification on drift.

The old 220 labelled pairs and the 30-pair revision tranche are background and
checker regression data, not these editor runs. Synthetic fault-injection tests
of this benchmark/oracle must stay separate from real adapter results. Record
new checker gaps separately; do not change checker rules or labels to improve
the table. Conclusions concern only these versions, adapters, inputs and task.

## API references checked before capture

* [python-docx 1.2.0 Run.text](https://python-docx.readthedocs.io/en/latest/api/text.html#docx.text.run.Run.text)
  and the installed 1.2.0 docstrings: run content replacement preserves run formatting.
* [Adeu 3.0.4 Python SDK](https://github.com/dealfluence/adeu/blob/v3.0.4/python/README.md#the-python-sdk)
  and installed 3.0.4 package README/METADATA, engine signatures and model defaults.

The references document API use; preservation conclusions come from local outputs.
