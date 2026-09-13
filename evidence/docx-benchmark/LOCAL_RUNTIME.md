# Running the declared local model pipeline

The machine already had Ollama.app **0.30.7** in `/Applications`. The initial
PATH-only availability check missed it. The benchmark uses that existing binary;
it does not require a replacement app. The earlier `AGENT.md` and protocol are
immutable pre-run declarations, so their original unavailable status is retained
as historical context. Current observed results belong in the main report.

`qwen2.5:7b-instruct` was already present in the user's default Ollama store.
The declared benchmark model is **qwen2.5-coder:7b**, so its additional 4.7 GB of
Q4_K_M weights were downloaded into this repository's ignored local directory:
`tmp/benchmark-runtime/models`. The old model/store were left intact.
Model digest:
`dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`.

The isolated Python environment is `tmp/benchmark-runtime/python-env`: Python
3.12.14, python-docx 1.2.0, lxml 6.1.3 and typing_extensions 4.16.0.
The runtime installation receipt, effective model template/parameters, runtime
sampling defaults, all request bodies and the full 30-case inventory are pinned
in [declaration.json](agent-local-1/declaration.json) before the first model task.
The infrastructure smoke prompt was only “Reply with OK only.”, excluded from
model task results. No input DOCX or document content is sent outside loopback.

## Start the existing service

Run from the repository root in a separate terminal. If another Ollama service
already owns port 11434, inspect it first; do not terminate another user's job.

```sh
OLLAMA_HOST=127.0.0.1:11434 \
OLLAMA_MODELS="$PWD/tmp/benchmark-runtime/models" \
OLLAMA_NO_CLOUD=1 \
OLLAMA_NUM_PARALLEL=1 \
OLLAMA_MAX_LOADED_MODELS=1 \
OLLAMA_CONTEXT_LENGTH=8192 \
OLLAMA_KEEP_ALIVE=30m \
/Applications/Ollama.app/Contents/Resources/ollama serve
```

The existing default model store is not reassigned globally; these environment
settings belong only to this service process. For a fresh checkout, create the
Python environment using a Python 3.12.14 interpreter and install the three
pinned packages above. Download the model with the same local service running:

```sh
OLLAMA_HOST=127.0.0.1:11434 /Applications/Ollama.app/Contents/Resources/ollama pull qwen2.5-coder:7b
```

Verify the tag digest against the declaration before attempting reproduction;
a moving tag is not an immutable model pin. A different runtime, digest or
platform must be recorded as a new cohort. The one-off setup downloaded an
unused portable Ollama 0.34.0 before discovering the existing app; it fetched
weights, then was stopped. It generated no benchmark response. The installation
correction is retained in the run declaration.

## Fresh run and replay

The [capture runner](../../research/capture_docx_agent.py) reads exact prompts
from frozen `AGENT.md`. `prepare` records the installed model/runtime and all
30 requests before `capture` starts. Choose new, nonexistent directories:

```sh
tmp/benchmark-runtime/python-env/bin/python research/capture_docx_agent.py prepare \
  --python "$PWD/tmp/benchmark-runtime/python-env/bin/python" \
  --directory tmp/agent-fresh \
  --runtime-receipt tmp/benchmark-runtime/installation-existing.json

tmp/benchmark-runtime/python-env/bin/python research/capture_docx_agent.py capture \
  --directory tmp/agent-fresh --work-root tmp/docx-benchmark-agent/fresh

.venv/bin/python research/capture_docx_agent.py evaluate --directory tmp/agent-fresh
.venv/bin/python research/capture_docx_agent.py verify --directory tmp/agent-fresh
```

For a different machine/build, produce a new installation receipt with observed
binary hash, versions, server settings and a sandbox preflight result; do not
copy the machine-specific receipt and present it as a fresh observation.
Replaying the saved capture needs no model or Ollama:

```sh
.venv/bin/python research/capture_docx_agent.py verify \
  --directory evidence/docx-benchmark/agent-local-1
```

Scripts run exactly once through macOS `sandbox-exec`, with a 60-second timeout,
no network, no child processes, no credentials in their environment, access to
only their own working files plus read-only Python/system runtime files, and
writes restricted to the working directory (and `/dev/null`). Ancestor directory
traversal/listing is permitted; other documents, prior results and checker files
are unreadable. This is a measured macOS isolation setup, not a cross-platform
or adversarial sandbox certification. Portable/Linux execution is untested.

A response may lose document content, fail to execute, time out or omit the
output. Keep all attempts. Evaluate only after all 30 requests finish; do not
repair scripts, retry failed model requests or feed checker findings back to the
model. All raw replies, extracted scripts, logs, output files and hashes are
retained per attempt. No-op scripts also need review for the declared open/save
requirement; an identical-file copy does not fulfill it.
