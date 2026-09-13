# Small DOCX edit-preservation benchmark

**Local result, 13 September 2026:** all three measured pipelines completed the
marker replacement and preserved the protected contents of all five synthetic
sources. There are **70 actual open/save or edit/save operations**: 40 from two
deterministic adapters (20 primary attempts and 20 repetitions), plus 30 fresh
local model requests with one script execution each. No unintended loss was
found in these outputs under the frozen
protocol. This does not establish visual identity or a general library ranking.

Question: **do comments, pending tracked changes and the rest of the content
survive a small specified DOCX edit?**

## Method

[PROTOCOL.md](PROTOCOL.md) and [protocol.json](protocol.json) were frozen before
fresh outputs. Protocol SHA-256:
`8c19d04394357abc540795bcfe97c375849619dc7e36a90f8e7a9b0b9202daa6`.
The base checkout is `63633c2e13bacb0a8dd3118cfc02b65586a5536d`.
The original README, plans, 220 labelled beta pairs, 30 revision pairs and checker
source were preserved; those old pairs are not counted in this comparison.

The inputs are the unchanged `basic`, `nested`, `table`, `notes`, `stories`
DOCX files in [the revision corpus](../docx-revisions/sources). Every source has
comments, a footnote and revisions by multiple authors; profiles add nested,
table, note and header/footer revisions. Each has one `EDITBEFORE` marker in an
ordinary text-only body run, beside existing insertions. The two tasks are a
real open/serialize control and exactly one `EDITBEFORE` → `EDITAFTER` replacement.

The [harness](../../research/docx_benchmark.py) assesses task completion separately
from unrelated revision/text/structure loss using the existing independent XML
oracle plus a bounded package comparison. The latter protects anchor positions,
formatting, table cells, relationships and binary assets as well. Only declared
serialization differences, core modification metadata and the requested edit
are normalized. Actual XML/binary bytes, hashes and full checker findings are
retained. This is a fixture-specific structural check, with no visual rendering.

## Actual results

Each `5/5` column is five source/action attempts in one capture. All five profiles
pass individually; per-case results are linked below. Success requires an `ok`
operation, completed task and preserved protected content.

| Adapter and operation | Task completed, capture 1 / 2 | Protected content preserved, capture 1 / 2 | Unsupported / rejected / error, total | ERROR/WARN, total |
| --- | --- | --- | --- | --- |
| adeu-sdk-v1, save | 5/5 / 5/5 | 5/5 / 5/5 | 0 / 0 / 0 | 0 |
| adeu-sdk-v1, tracked edit | 5/5 / 5/5 | 5/5 / 5/5 | 0 / 0 / 0 | 0 |
| python-docx-run-v1, save | 5/5 / 5/5 | 5/5 / 5/5 | 0 / 0 / 0 | 0 |
| python-docx-run-v1, untracked edit | 5/5 / 5/5 | 5/5 / 5/5 | 0 / 0 / 0 | 0 |
| local-agent-v1, save (3 trials/source) | 15/15, separate cohort | 15/15 | 0 / 0 / 0 | 0 |
| local-agent-v1, edit (3 trials/source) | 15/15, separate cohort | 15/15 | 0 / 0 / 0 | 0 |

There is no observed preservation difference on this task. Adeu adds the requested
new deletion/insertion pair; python-docx makes an untracked replacement. All old
revision payloads/authors/dates/nesting, comments/anchors, notes, other text and
protected package content survive. Two pre-existing REL003 INFO findings occur
on every source and output. Adeu edits also receive two FID002 INFO findings for
the new tracked constructs. These expected additions are not losses or defects.
There are no independently established pipeline defects against which to measure
checker sensitivity; zero ERROR/WARN is **not a recall or quality score**.

The concrete python-docx adapter uses the documented `Run.text` setter only on
the single matching run. This says nothing about `Paragraph.text`, `Cell.text`,
rewriting a document, or editing inside pre-existing revisions. The target shares
a paragraph with revisions but does not touch their text or the comment range.
This deliberately easy nearby edit cannot discriminate all editor workflows.

The local agent also chose a run-local replacement, using the private
`run._element.text` property. This measured script is not an endorsement of that
private API. All save scripts call `Document()` and `Document.save()`, fulfilling
the open/serialize control despite the generated function's name `copy_docx`.
At temperature 0, seeds 101/102/103 produced one unique save script and one unique
edit script across all five profiles: the 30 attempts are reproducibility
observations, not 30 independent editing strategies. See the
[agent evaluation](agent-local-1/evaluation.json) and [script review](agent-local-1/review.json).

Capture receipts/evaluations:
[adeu 1](captures/adeu-1/evaluation.reviewed.json),
[adeu 2](captures/adeu-2/evaluation.reviewed.json),
[python-docx 1](captures/python-docx-1/evaluation.reviewed.json),
[python-docx 2](captures/python-docx-2/evaluation.reviewed.json).
Each directory contains ten raw DOCX outputs, per-attempt receipts,
`started.json`, `capture.json` and the exact capture-harness snapshot. Receipts
record commands, timestamps, options, source/output hashes, installed package
versions, implementation hashes, tool statistics and logs.

[Repeat comparisons](repeat-adeu.json) ([python-docx](repeat-python-docx.json))
show 0/10 semantic/verdict/finding mismatches for each adapter. Raw ZIPs match in
0/10 pairs for each, as expected from save timestamps; the normalized protected
package hashes match in all 20 repeat comparisons. Repetition is a reproducibility
check, not 40 independent documents. The initial evaluator mishandled adeu's new
UTC timestamp attribute; original results are retained and the correction is
[documented separately](KNOWN_GAPS.md#corrected-benchmark-evaluator-issue-not-an-editor-defect).
The protocol and editing algorithms did not change.

The model cohort ran later, **11:05:44–11:07:42 UTC**, through the pre-existing
Ollama.app **0.30.7**, Qwen2.5-Coder 7B (**7.6B, Q4_K_M**) on Apple M4 Pro/Metal.
Digest: `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`.
Its [declaration](agent-local-1/declaration.json) pins prompts, runtime/model
details, Python dependencies, sampling defaults, seeds and all 30 requests before
the first model task. Parameters: `temperature=0`, `num_ctx=8192`,
`num_predict=4096`, `think=false`, one fresh request and one execution per attempt,
60-second script timeout, no feedback, retries or code repair. All raw replies,
scripts, logs, output DOCX and hashes are retained in `agent-local-1/`.

## Versions and reproduction

Captured on macOS 26.6.2 arm64, Python 3.12.14: adeu 3.0.4, python-docx 1.2.0,
lxml 6.1.3, pydantic 2.13.5, diff-match-patch 20241021. Both adapters used the same
existing local environment. API choices follow the
[adeu 3.0.4 SDK](https://github.com/dealfluence/adeu/blob/v3.0.4/python/README.md#the-python-sdk)
and [python-docx 1.2.0 Run.text](https://python-docx.readthedocs.io/en/latest/api/text.html#docx.text.run.Run.text)
documentation; their installed source/METADATA was also inspected.

Evaluation uses **checkout checker 0.4.1**, no config/baseline/ignores. The local
`.venv` distribution metadata still says 0.4.0; the harness explicitly imports
`src/`, verifies its hash and records the actual code version, avoiding that
stale label. Checker evaluation and tests used Python 3.9.6, lxml 6.1.3 and
pytest 8.4.2. Source-level checker hashes are retained in the adapter evaluations;
the agent declaration pins the identical independent evaluator.

From the repository root, replay existing captures (no adeu/model/network needed):

```sh
for capture in adeu-1 adeu-2 python-docx-1 python-docx-2; do
  .venv/bin/python research/docx_benchmark.py verify \
    evidence/docx-benchmark/captures/$capture --result-name evaluation.reviewed.json
done
.venv/bin/python research/docx_benchmark.py compare evidence/docx-benchmark/captures/adeu-1 evidence/docx-benchmark/captures/adeu-2
.venv/bin/python research/docx_benchmark.py compare evidence/docx-benchmark/captures/python-docx-1 evidence/docx-benchmark/captures/python-docx-2
```

For fresh captures on this checkout, the already installed environment is
`tmp/e1/adeu-env/bin/python`. On another machine, create a Python 3.12 environment
and install the pinned [capture requirements](capture-requirements.txt):

```sh
python3.12 -m venv tmp/benchmark-capture-env
tmp/benchmark-capture-env/bin/python -m pip install -r evidence/docx-benchmark/capture-requirements.txt
```

Installation downloads packages, not documents. Exact platform/build reproduction
uses Python 3.12.14 and the recorded macOS architecture; another platform is a new
cohort. Then run, choosing previously nonexistent directories:

```sh
for repeat in 1 2; do
  for adapter in adeu-sdk-v1 python-docx-run-v1; do
    dir="tmp/benchmark-fresh/$adapter-$repeat"
    tmp/benchmark-capture-env/bin/python research/docx_benchmark.py capture --adapter "$adapter" --output-dir "$dir"
    .venv/bin/python research/docx_benchmark.py evaluate "$dir" --result-name evaluation.reviewed.json
  done
done
.venv/bin/python research/docx_benchmark.py compare tmp/benchmark-fresh/adeu-sdk-v1-1 tmp/benchmark-fresh/adeu-sdk-v1-2
.venv/bin/python research/docx_benchmark.py compare tmp/benchmark-fresh/python-docx-run-v1-1 tmp/benchmark-fresh/python-docx-run-v1-2
```

The evaluator needs this project's development environment (`pip install -e
'.[dev]'` in a fresh `.venv` if absent). Fresh outputs and receipts are never
silently overwritten. A run's saved code/protocol/input/output hashes are verified
before replay. An invalid, refused or unsupported operation stays separate from
content success; task completion is measured from output XML, not tool statistics.

## Validation performed

* Full suite after the agent capture: **788 passed, 7 skipped** in 27.12 s;
  [saved log](validation-agent-pytest.txt).
  All skips are existing missing-font tests whose fonts are actually installed.
* Relevant agent/benchmark/revision/Windows-oracle tests: **81 passed**, including
  sandbox enforcement, exact prompts, captured-code identity, task failure versus
  preservation, injected losses, anchor positions, formatting and capture replay.
* Both existing corpus evaluators: **0 label mismatches** (220 beta and 30 revision
  pairs, retained strictly as regression evidence).
* All five saved capture evaluations reproduce; both 10-case adapter repeat
  comparisons match. Capture receipts, all 70 output hashes and fixture-only authors/links
  were checked. Existing tracked files and checker source have no changes;
  whitespace checks and local report links pass.

Exact verification commands and a machine-readable summary are in
[validation-agent.json](validation-agent.json); the earlier
[adapter-only validation](validation.json) is retained. Unit tests invoke no
model; the 30 actual model requests are reported separately. Rendering, Office
and browser checks are not included. Authored-code whitespace checks pass;
raw model replies/scripts retain their original whitespace.

## Limits, checker gaps and the remaining pipeline

No customer documents, independent human review, renderer comparison, general
semantic equivalence, cross-run marker targets, replacement inside revisions,
accept/reject operations, endnotes or move/formatting revisions were measured.
The binary media/external-link parts retained in these fixtures are unused; their
bytes/relationships are protected, but displayed-image/hyperlink editing is not
measured. Namespace-sensitive attribute values and arbitrary OOXML rewrites are
outside the bounded comparator's tested scope. Structurally preserved content
is not a promise of identical layout in Word or another renderer.

[KNOWN_GAPS.md](KNOWN_GAPS.md) separates a newly confirmed **seeded comment-anchor
relocation miss**, two pre-existing seeded checker misses, and the corrected
benchmark evaluator issue. The single diagnostic DOCX is stored under
`diagnostics/`, outside all editor captures. No artificial defect is attributed
to either library. The old 220/30-pair corpora are used only as regression checks.

[AGENT.md](AGENT.md) is the unchanged pre-run scenario declaration; its original
“not run” status is historical. The PATH-only availability check missed an
existing Ollama.app and was corrected before model tasks. The existing app was
used for all 30 tasks; the user's previous `qwen2.5:7b-instruct` model was left
intact. The additional Coder weights and Python environment are local to ignored
`tmp/`. [LOCAL_RUNTIME.md](LOCAL_RUNTIME.md) gives exact startup, fresh-capture
and replay commands, including the measured macOS isolation boundaries. Requests
use the local [chat API](https://docs.ollama.com/api/chat), with the model digest
from the [inventory API](https://docs.ollama.com/api/tags). One unrelated “OK”
infrastructure smoke request is excluded from the 30 attempts. No paid API or
external document transfer occurred.

The measured agent scenario is one-response code generation followed by isolated
execution, without interactive tools or checker feedback. It does not measure a
frontier coding agent session. All three pipelines pass this narrow nearby-edit
task; whether to broaden the task to more challenging edits is a separate scope
decision. Publishing or contacting maintainers also requires a separate decision;
this work made no push, publication or outgoing message.
