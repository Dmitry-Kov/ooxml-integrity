---
name: verify-change
description: Run this project's checks on the current change and report what passed, failed and was not run. Use before saying a task is done, before a commit, and whenever asked to verify, check or test a change in ooxml-integrity.
---

# Verify a change

Run the steps in order. Do not stop at the first failure: finish the list and
report everything.

1. **What changed.** `git status --short` and `git diff --stat`. If the current
   branch is `main`, stop and create a branch first.
2. **Whitespace.** `git diff --check`.
3. **Lint.** `.venv/bin/python -m ruff check .`
4. **Types.** `.venv/bin/python -m mypy`
5. **Tests.** `.venv/bin/python -m pytest -p no:cacheprovider`. The project's
   settings make the output quiet; read the last line for the counts and check
   the exit code. Six skips are expected on a machine with the Office fonts.
6. **Only when files under `evidence/` or an evaluator in `research/` changed:**

   ```sh
   .venv/bin/python research/build_docx_evidence.py evaluate
   .venv/bin/python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs
   ```
7. **Only when Markdown changed:** every relative link and anchor you added or
   moved resolves, and every command in a code block runs as written.
8. **Only when `pyproject.toml`, `action.yml` or the workflows changed:** say
   that packaging and the Action are checked by CI and were not run locally,
   unless you built the wheel and sdist yourself.

## Report

One short list, in this order:

- what ran and its result, with the test counts;
- what failed, with the first lines of the error;
- what was skipped and why;
- what was not verified at all (Python 3.9, Windows, the browser suite, Word).

Do not write "done" or "all checks pass" if any step failed or was not run.
