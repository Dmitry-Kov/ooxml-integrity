# Instructions for coding agents

`ooxml-integrity` checks `.docx` and `.pptx` files after automated editing. It
is research-alpha: what it claims is limited to what `evidence/` measured.
[CONTRIBUTING.md](CONTRIBUTING.md) is the full guide; this file is the short
version an agent needs on every task.

## Commands

```sh
.venv/bin/python -m pytest                      # full suite, about two minutes
.venv/bin/python -m pytest tests/test_cli.py    # one area while working
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
```

All three must pass before a change is reported as done.

## How to work

- Work on a branch. Never commit on `main`.
- Do not push, tag, open or merge a pull request, or publish anything unless
  the maintainer asked for that step in this session.
- Keep a change focused. Fix what was asked; report other problems you notice
  instead of fixing them in the same change.
- A behaviour change needs a regression test, with a clean control where one
  makes sense. Assert document semantics, codes and severity, not copied output.
- No attribution or co-author lines in commit messages or pull requests.
- Report what ran, what failed and what was skipped. Say "not verified" for
  anything you did not run. A green checker result does not prove a document
  is correct.

## Rules of the code

- Fail closed. A check that cannot run is an ERROR (`INT001`, `FID000`,
  `PKG009`), never a silent pass.
- Rule codes are stable. A different kind of check gets a new code; an existing
  code keeps its documented purpose. Severity follows the consequence for the
  reader of the document.
- Parse XML with `xmlutil.fromstring` and read packages with
  `archive.read_package`. Never call `etree.fromstring` on package bytes
  directly: the safe parser and the archive limits are the security boundary.
- The checker makes no network or model calls and does not render documents.
- Runtime dependencies are `lxml` and `fonttools`. Do not add one.
- The package runs on Python 3.9: keep `from __future__ import annotations`,
  and use no syntax or standard-library API newer than 3.9.

## Evidence

- Every number in the README, the docs and the changelog has a source under
  `evidence/`. Do not write a number you did not read there or measure now.
- Historical records are immutable: receipts, labels, captures, frozen
  protocols and their hashes. A new measurement goes into a new file.
- Do not relabel expected results to make a metric pass. Known misses and
  false alarms stay listed.
- State the scope of a claim: which documents, which tool versions, which
  build of Word. Say what was not measured.

## Leave alone

- `tmp/`, `drafts/`, `PILOT_*.md`, `AUDIT_PLAN.md`: local, outside Git.
- Version numbers, tags, the Action pins and `CHECKER_VERSION` in
  `demo/worker.js`: they change only in the [release procedure](docs/releasing.md).
- `research/review_history_oracle.py` and everything under
  `evidence/review-history-benchmark/` that the frozen protocol hashes.
