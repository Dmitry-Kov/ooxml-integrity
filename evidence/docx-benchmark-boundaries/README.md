# DOCX boundary benchmark v1.1

**140 actual local operations completed on 2026-09-13.** Three harder edits and
an open/save control were run on five synthetic sources derived from the existing
revision corpus. The small public-API python-docx adapter succeeds throughout;
adeu preserves the requested content but emits repeated deletion IDs in the
split-format scenario; the fixed local model fails to execute all three edit tasks.
This characterizes these adapters/prompts, not entire libraries or model families.

The [protocol](PROTOCOL.md), [input hashes](protocol.json) and
[exact prompts](prompts.json) were fixed before capture. Original v1 is preserved
in local commit `22481ed` and [its own report](../docx-benchmark/README.md).
Neither old corpus (220 labelled pairs or 30 revision pairs) is counted below.

## Method and results

The five original revision DOCX files remain unchanged. Derived inputs split
EDITBEFORE into bold EDIT and italic BEFORE, and give the last table cell a unique
TABLEBEFORE marker. Each operation starts from its source, not a prior output.
The split edit requests bold DONE + italic AFTER; the comment edit changes delivery
to payment within the anchored sentence; the table edit changes TABLEBEFORE to
TABLEAFTER. Only the table profile has old revisions inside the edited cell;
the other four have revisions elsewhere. All have a comment and footnote reference.

Independent checks combine the unchanged XML revision oracle with a bounded
package/character-format comparison at the target paragraph. Existing revisions,
comment positions, notes, other wording, formatting, relationships and binary parts
are protected. New tracked edits are checked in both their original and current
views. `ooxml-integrity` 0.4.1 is then run separately, with no configuration or rule
changes. No Word rendering or visual identity is measured.

Two captures per deterministic adapter; three agent trials per source/task.
Counts are operations on five documents, not 140 independent documents.

| Pipeline / task | Attempts | Task completed | Full protocol pass | Status and checker interpretation |
| --- | ---: | ---: | ---: | --- |
| adeu SDK / save | 10 | 10 | 10 | All ok; no ERROR/WARN |
| adeu SDK / split formats | 10 | 10 | 0 | All ok; repeated new deletion ID, REV001 in all 10 |
| adeu SDK / comment | 10 | 10 | 10 | All ok; anchors and footnote retained |
| adeu SDK / table | 10 | 10 | 10 | All ok; old cell revisions retained |
| python-docx v2 / save | 10 | 10 | 10 | All ok; no ERROR/WARN |
| python-docx v2 / split formats | 10 | 10 | 10 | All ok; both formats retained |
| python-docx v2 / comment | 10 | 10 | 10 | All ok; anchors and footnote retained |
| python-docx v2 / table | 10 | 10 | 10 | All ok; old cell revisions retained |
| local agent / save | 15 | 15 | 15 | Actual Document open/save; no ERROR/WARN |
| local agent / split formats | 15 | 0 | 0 | Execution error, no output; preservation/checker not evaluated |
| local agent / comment | 15 | 0 | 0 | Execution error, no output; preservation/checker not evaluated |
| local agent / table | 15 | 0 | 0 | Execution error, no output; preservation/checker not evaluated |

Full pass requires successful execution, completed task, protected content and
raw revision integrity checks. **No loss of pre-existing content was observed in
any of the 95 produced DOCX outputs.** Adeu's 10 split outputs fail solely because
two new deletion fragments share an ID. The independent raw XML check sees the
same fact as REV001. Adeu intentionally supports shared IDs for logical revision
groups; whether REV001 is too strict for these fragments, or they cause a practical
Word problem, remains unresolved. Do not call these files corrupt or count them
as unconditional true positives. [BND-001](ISSUES.md) contains the exact reproduction.

Each source has two pre-existing REL003 INFO findings. Adeu edits also have FID002
INFO for added review markup; these are expected additions, not losses. There are
no other actionable findings. Missing agent outputs are execution failures, not
checker false negatives. All 140 input files remained unchanged.

## Concrete pipelines and variation

* **adeu-sdk-boundaries-v1:** adeu 3.0.4, Python 3.12.14, lxml 6.1.3. Documented
  RedlineEngine/ModifyText/save_to_stream, strict match, partial false, defaults
  except author Evidence Editor. Split-format replacement uses documented Markdown
  `**DONE**_AFTER_`. Parameters, package versions and implementation hashes are in
  every capture receipt.
* **python-docx-targets-v2:** python-docx 1.2.0, Python 3.12.14, lxml 6.1.3.
  Select the declared paragraph or cell using public properties and set only the
  target Run.text values. This task-aware adapter explicitly supports the two-run
  marker; v1's single-body-run adapter was narrower. It does not use paragraph.text,
  cell.text, private XML edits or checker feedback.
* **local-agent-boundaries-v1:** existing Ollama.app 0.30.7 on Apple M4 Pro,
  qwen2.5-coder:7b Q4_K_M, digest
  `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`.
  Temperature 0, seeds 101/102/103, context 8192, maximum prediction 4096,
  think false; one response and one sandbox execution, no repair/retry. Same
  Python/library versions as the public adapter. Full model/template/runtime
  declaration precedes all 60 calls. No paid API or document upload was used.

All three agent repeats emitted the same script for each task (four unique scripts,
15 copies of each). Save uses Document(input) followed by doc.save, despite its
function being named copy_docx. Split wrongly searches for one run both bold and
italic; comment uses nonexistent Paragraph.comments; table sets invalid lxml tag
`w:t`. These are errors of the frozen generated scripts, not sandbox restrictions
or evidence that the library lacks support. Scripts were retained without repair.
Temperature-zero repeats are not independent editing strategies.

Both deterministic captures agree for all 20 source/task pairs per adapter on
status, task completion, independent assessment, checker findings and normalized
package hashes. Raw ZIP bytes differ across runs; raw hashes remain recorded.
See [repeat-adeu.json](repeat-adeu.json),
[repeat-python-docx.json](repeat-python-docx.json) and [review.json](review.json).

## Reproduce

Run from the repository root. Existing local environments are used below. A fresh
checkout needs Python 3.12.14 and the [pinned adeu environment](../docx-benchmark/capture-requirements.txt);
the isolated model/script environment needs python-docx 1.2.0, lxml 6.1.3 and
typing_extensions 4.16.0. The checkout development environment provides pytest and
the checker dependencies. The editor/model capture processes do not invoke the checker.

Replay **all saved evidence**, hashes, independent assessments and repeats without
Ollama, an editor run or network access:

```sh
.venv/bin/python research/review_docx_boundaries.py
.venv/bin/python -m pytest tests/test_docx_boundaries.py --basetemp tmp/boundaries-tests -ra
```

The supported replayer compares canonical JSON: the frozen evaluator returns
Python tuples for duplicate-ID facts, which are arrays in saved JSON. Its original
per-adapter `verify` helper compares those types directly and rejects adeu receipts
for that representation mismatch. `review_docx_boundaries.py` fixes the replay
comparison only; original evaluations, protocol, harness and results are unchanged.
The first failing replay test is retained in validation-boundaries.txt; final
validation includes the corrected replay.

Fresh deterministic captures (choose new, nonexistent directories):

```sh
tmp/e1/adeu-env/bin/python research/docx_boundaries.py capture \
  --adapter adeu-sdk-boundaries-v1 --directory tmp/boundaries-adeu-fresh
.venv/bin/python research/docx_boundaries.py evaluate tmp/boundaries-adeu-fresh

tmp/benchmark-runtime/python-env/bin/python research/docx_boundaries.py capture \
  --adapter python-docx-targets-v2 --directory tmp/boundaries-python-fresh
.venv/bin/python research/docx_boundaries.py evaluate tmp/boundaries-python-fresh
```

For a fresh agent run, follow [the local runtime startup instructions](../docx-benchmark/LOCAL_RUNTIME.md)
with the existing app and repo-local model store, then:

```sh
tmp/benchmark-runtime/python-env/bin/python research/capture_docx_boundaries_agent.py prepare \
  --python "$PWD/tmp/benchmark-runtime/python-env/bin/python" \
  --runtime-receipt tmp/benchmark-runtime/installation-existing.json \
  --directory tmp/boundaries-agent-fresh

tmp/benchmark-runtime/python-env/bin/python research/capture_docx_boundaries_agent.py capture \
  --directory tmp/boundaries-agent-fresh --work-root tmp/boundaries-agent-work-fresh

.venv/bin/python research/capture_docx_boundaries_agent.py evaluate \
  --directory tmp/boundaries-agent-fresh
```

The referenced installation receipt describes this machine. On another machine,
record its actual runtime/binary/settings and sandbox preflight; do not reuse that
receipt as a new observation. A changed runtime or model digest is a new cohort.
The service started for this capture was stopped after all calls finished; the
user's original Ollama model store was left intact.

## Validation and limits

The final suite passed **828 tests, with 7 expected font-related skips**;
[validation.json](validation.json) records commands and evidence hashes.
Validation receipts record local sandbox import/save and
blocked outside reads/writes/network/child-process probes, unchanged source
reconstruction, replay of both boundary captures and all 70 v1 operations, and
old 220-pair / 30-pair corpus evaluations with zero label mismatches.
No production checker, old corpus, v1 evidence, top-level README, AUDIT_PLAN or
pilot instructions were changed. No push, external issue or maintainer message.

Five related synthetic sources, one edit per file, one small local model and
one-response scripting are narrow evidence. Rendering, repair dialogs, selecting
or accepting/rejecting revision groups, interactive agents, broader documents,
Office saves of these outputs and external pilots are unmeasured.

Known checker misses remain explicit in [ISSUES.md](ISSUES.md). A new **seeded**
formatting-loss example is separate from the real editor table; it shows that a
quiet checker cannot certify formatting preservation. Prior payload/footnote/anchor
misses are inherited fault-injection evidence, not new editor defects. Next useful
work is the focused REV001/Word compatibility check and an external pilot, before
expanding this benchmark again. Sharing these results requires the owner's decision.
