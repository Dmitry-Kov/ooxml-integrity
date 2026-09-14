# local-agent-v1 — prepared, NOT RUN

The fixed scenario is a single model response producing one Python program,
followed by one execution. It is a constrained agent pipeline, not an interactive
coding assistant benchmark. No model was invoked to edit these fixtures here.
The specified local runtime (`ollama`) is absent from PATH; no local model weights
or approved external model endpoint were supplied. The current coding session is
not counted as a benchmark model run.

Prerequisites for a later run: install Ollama and obtain `qwen2.5-coder:7b` locally
(the model download is a separate resource decision). Use a Python 3.12 environment
with python-docx 1.2.0 and lxml 6.1.3. Before generating any output, record
`ollama --version`, `/api/tags`' full model digest and `/api/show`'s model details,
template and parameters in the run receipt. Tags can move: freeze that digest
before capture and refuse a different digest on reproduction. No model digest is
invented for this unexecuted scenario.

For each of five pinned sources, both operations, and seeds 101, 102, 103:

1. Create a fresh directory inside `tmp/docx-benchmark-agent/`, copy only that
   source as `input.docx`, and verify its protocol SHA-256. Do not expose prior
   outputs, benchmark results, checker code or the independent oracle.
2. Send the system/user messages below to local `http://127.0.0.1:11434/api/chat`,
   model `qwen2.5-coder:7b`, `stream: false`, `think: false`, options
   `temperature: 0`, `seed: SEED`, `num_ctx: 8192`, `num_predict: 4096`.
   Save the exact request JSON and complete response JSON, model digest,
   elapsed time, token counts and all effective runtime defaults. Use the same
   declared Ollama build and model digest for all 30 attempts. Do not use a
   remotely configured host or substitute a cloud model.
3. Save the response message content verbatim as `edit.py`; if it is fenced,
   remove only one outer Markdown code fence and record both raw and extracted
   hashes. Do not repair the script. Execute once as `PYTHON edit.py` with that
   fresh directory as cwd, no network and a 60-second timeout, retaining stdout,
   stderr and return code. This needs an isolated execution environment with
   only this work directory writable. Refusal, invalid code, timeout and missing
   output are outcomes, not invitations to retry.
4. Keep `output.docx`, script, logs, request and response even on failure; hash
   all retained artifacts. Record status (`ok`, `rejected`, `error`), source,
   operation, seed, exact command and tool/runtime/model versions per attempt.
5. Only after all attempts finish, evaluate each existing output locally:
   `PYTHON research/docx_benchmark.py inspect --source SOURCE --output OUTPUT --action save|edit --adapter local-agent-v1`.
   Run from the repository root. Missing-output attempts remain errors with
   null completion/preservation/detection; include all 30 attempts in the table.
   Require three attempts for each source/action, including failures; report
   trial variation, never just the best result. Package the model/runtime
   declaration and artifacts with these JSON evaluations in a new receipt.

System message (exact):

```text
You write one standalone Python program for a local DOCX editing task. Return only Python source, with no explanation. Read input.docx and write output.docx in the current directory. You may use the Python standard library, python-docx 1.2.0 and lxml 6.1.3. Do not use network access, subprocesses, other files, or external services. The input contains existing comments and pending tracked changes. Preserve all existing review content, authors, dates, formatting, relationships and other document content. Do not accept or reject existing changes. If you cannot perform the task, raise a clear exception. Do not use an integrity checker.
```

User message for `save` (exact):

```text
Open input.docx and serialize it to output.docx without editing it. A file copy is not an open/save operation. Preserve all package content and existing comments and tracked changes.
```

User message for `edit` (exact):

```text
In input.docx replace the unique current-text marker EDITBEFORE with EDITAFTER exactly once, then save as output.docx. The marker is wholly within an ordinary text-only run in a body paragraph beside pending revisions. Change nothing else. The new replacement may be untracked. If you create a tracked replacement, use Evidence Editor as its author and preserve all earlier changes.
```

This recipe is prepared, not validated with Ollama or generated scripts. Its
runtime/digest and isolation setup must be completed before execution; those
missing prerequisites must not be reported as failed model attempts.
