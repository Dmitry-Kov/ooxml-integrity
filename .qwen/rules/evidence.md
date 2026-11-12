---
description: Evidence records are historical and are not rewritten
paths:
  - 'evidence/**'
  - 'research/review_history_oracle.py'
  - 'research/build_docx_evidence.py'
  - 'research/replay_frozen_docx.py'
---

You are touching the project's evidence.

- A record that exists is history. Do not edit receipts, labels, captures,
  `results.json` files, frozen protocols, amendments or the hashes they pin.
  `research/review_history_oracle.py` is hash-pinned too: a changed byte is drift.
- A new measurement goes into a new file or a new directory, with the command
  that produced it, the date, and the versions of the checker and of every
  tool it ran.
- Do not use `build_docx_evidence.py evaluate --write` to relabel old metrics
  with a new checker version. Save current metrics with `--output NEW_PATH.json`.
- Known misses and false alarms stay listed. If the checker now disagrees with
  a label, report the disagreement; do not change the label.
- A README here states what was measured and, under "Limits", what was not.
  Keep both when you add to one.
- After a change under `evidence/` or to an evaluator, run:

  ```sh
  .venv/bin/python research/build_docx_evidence.py evaluate
  .venv/bin/python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs
  ```
