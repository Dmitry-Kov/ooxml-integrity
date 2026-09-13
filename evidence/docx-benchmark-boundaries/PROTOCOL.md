# DOCX boundary benchmark v1.1 — declared before capture

Question: do three precisely scoped edits preserve existing review content and
formatting? This is a separate extension of frozen benchmark v1 (`22481ed`),
not a replacement for it or an editor/model ranking.

## Inputs and tasks

Derive five inputs deterministically from the five unchanged revision sources.
Change only two ordinary text locations: split `EDITBEFORE` into bold `EDIT` and
italic `BEFORE` in body paragraph 3; replace the final ordinary table-cell word
`review` with the unique `TABLEBEFORE`. Retain all other bytes outside document.xml
and all existing review markup. Original and derived hashes are in protocol.json.
Only the table profile has pending revisions inside the edited cell; the other
four provide table-edit controls with revisions elsewhere. No new review markup
is seeded in these inputs.

Run each task on a fresh copy of each derived source:

| Task | Exact operation | Target |
| --- | --- | --- |
| save | Open and serialize, no edits; copying is not completion | Whole file |
| split | `EDITBEFORE` → `DONEAFTER`, exactly once | Body paragraph 3; `DONE` stays bold, `AFTER` stays italic |
| comment | `Review the delivery terms.` → `Review the payment terms.`, exactly once | Body paragraph 6, inside comment 1; preserve full-sentence anchor and trailing comment/footnote references |
| table | `TABLEBEFORE` → `TABLEAFTER`, exactly once | First table, row 2, column 2; preserve ordinary formatting and adjacent old revisions |

No acceptance/rejection or other wording changes. Untracked replacement is
allowed; new tracked text must use author `Evidence Editor`. Adeu requires a
tracked replacement. New revision IDs/dates may vary; existing ones may not.
For split, adeu receives documented Markdown `**DONE**_AFTER_` to specify the two
formats explicitly. Plain-text replacement would leave format allocation vague.

## Protected content and bounded independent assessment

All other current text, old revision payloads/authors/dates/nesting, comment
bodies and positions, note bodies/references, paragraph/cell/table boundaries,
formatting, numbering, relationships, metadata and binary assets are protected.
Reuse the unchanged revision XML oracle and v1 package normalizations: expanded
names; ignore ZIP/XML serialization metadata, namespace prefixes/declarations,
attribute order, insignificant XML whitespace, relationship/content-type entry
order, explicit default TargetMode Internal. Permit only core modified,
lastModifiedBy and revision metadata changes, recording them separately.

In the ONE target paragraph for an edit, compare ordinary text character by
character with run attributes, text attributes (except xml:space) and rPr attached
to each character. Thus a plain text run can split/coalesce without masking a
format change. Only there, an empty rPr equals absent rPr, and b/i val=1/true/on
equals the default true when val is omitted. Other properties remain exact.
Nontext runs, old revision wrappers, anchors and all other nodes
remain exact ordered XML signatures. Empty text-only runs may be omitted there;
nontext runs may not. Outside that paragraph use strict v1 package signatures.
No visual equivalence or general semantic diff is claimed.

Recognize new direct-child insertion/deletion wrappers only in that target
paragraph, with author Evidence Editor, a new ID, allowed id/author/date attributes
(and matching dateUtc), containing only ordinary text runs/rPr. Preserve both
views: removing new deletions/unwrapping new insertions must give the declared
new text/formats; removing new insertions/unwrapping new deletions must recover
the original paragraph. This allows a full-span pair or smaller fragment pairs
without allowing changed deletion history. Run the independent revision oracle
on the projected current view; also check raw invalid text/duplicate IDs. Old
revisions remain wrapped and checked. Output without the edit may pass preservation
but never task completion. New wording with changed required formatting is a
preservation failure, even if lexical replacement completed. Residual differences
are undeclared changes to inspect, not automatic proof of corrupt DOCX.

Score status (ok/unsupported/rejected/error), lexical task completion, preservation
and checker detection separately. Overall requires all three successful axes.
Check task completion at its declared location, independently of unrelated losses.
Run unconfigured checker check(output)+compare(source,output), retain all findings
and source baselines. Map actionable findings to observed losses manually; warning
counts are not quality scores. No-edit failures without collateral loss are not
checker fidelity false negatives. Inspect generated save scripts for open/save.

## Frozen pipelines and inventory

* adeu-sdk-boundaries-v1: adeu 3.0.4, Python 3.12.14. Same documented SDK and
  protection defaults as v1: RedlineEngine(BytesIO, author), one ModifyText strict,
  regex false, comment null, process_batch(partial=False), save_to_stream.
* python-docx-targets-v2: python-docx 1.2.0, lxml 6.1.3. Public Document.paragraphs,
  tables/rows/cells/paragraphs/runs. Select the declared paragraph/cell. For split,
  require adjacent runs exactly `EDIT` and `BEFORE`, set their Run.text to `DONE`
  and `AFTER`. Otherwise require one matching ordinary run and replace only that
  run's text. Save with Document.save. Unsupported shape raises before saving.
  No paragraph.text/cell.text setter, private XML editing or checker feedback.
  This task-aware adapter is deliberately limited to these fixtures.
* local-agent-boundaries-v1: existing Ollama.app 0.30.7, qwen2.5-coder:7b digest
  dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364.
  Reuse v1 system/save prompt; three edit prompts in prompts.json describe only
  task and preservation, not an API recipe. One generated Python script, one
  sandbox execution, no repairs/retries/checker feedback. Python 3.12.14 with
  python-docx 1.2.0/lxml 6.1.3. Temperature 0, seeds 101/102/103, context 8192,
  max prediction 4096, think false. Runtime declaration precedes model calls.

Two deterministic captures per adapter: 5 × 4 × 2 × 2 = 80 operations.
Three agent attempts per source/task: 5 × 4 × 3 = 60 operations. Retain failures
and every repetition; identical scripts are not independent strategies. Compare
normalized packages/status/assessment/checker findings for deterministic repeats.
Keep original hashes, commands, parameters, dependency/source hashes, timestamps,
raw logs, model requests/responses and immutable receipts. Capture precedes
checker evaluation. Protocol/source/harness drift is an error.

Local execution only. No paid model calls, document uploads, new integrations,
rendering or checker-rule changes. Synthetic test defects and prior 220 pairs
are separate from these 140 real operations. Reproducibility means replay of saved
bytes plus fresh local captures; a different machine/model is a new cohort.

API basis (checked before capture): [python-docx Run.text](https://python-docx.readthedocs.io/en/latest/api/text.html#docx.text.run.Run.text),
[adeu 3.0.4 SDK](https://github.com/dealfluence/adeu/blob/v3.0.4/python/README.md),
and installed 3.0.4 ModifyText schema documenting strict matches and Markdown.
