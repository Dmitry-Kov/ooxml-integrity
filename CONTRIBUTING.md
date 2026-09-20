# Contributing

Bug reports, small reproductions and focused fixes are welcome. The maintainer
is [Dmitrii Kovalev (@Dmitry-Kov)](https://github.com/Dmitry-Kov).
Use the [feedback form](https://github.com/Dmitry-Kov/ooxml-integrity/issues/new?template=checker-feedback.yml)
for useful findings, false alarms, missed defects and setup problems; propose
larger changes in a [GitHub issue](https://github.com/Dmitry-Kov/ooxml-integrity/issues/new)
before building them. Follow [SECURITY.md](SECURITY.md) for sensitive security reports.

## Make a finding reproducible

Include the checker version or commit, generator/editor version, OS/Python or
browser, exact command, finding codes and expected/actual behavior. Record any
config, baseline, failure threshold and font setup. For a fidelity result,
retain both the original and edited file and explain the intended changes,
including deliberate acceptance/rejection of revisions. Explain how the defect
was independently verified; a green checker result alone cannot establish that
a document is correct.

Prefer a minimal synthetic DOCX/PPTX or a script that creates it. Share only
material you may publish, and review package metadata, comments, tracked-change
authors, hidden parts and report excerpts. A short description is enough to
start; private documents are not required. Record the exact Office/producer
version and operation for native saves or renders. Do not label a generated
fixture as an Office capture.

## Development setup

From a clone of this repository, use Python 3.9+ (3.12 matches the cross-platform
CI jobs) and create a virtual environment:

```sh
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on macOS/Linux or
`.venv\Scripts\activate.bat` in Windows Command Prompt, then run:

```sh
python -m pip install -e ".[dev]"
python -m ooxml_integrity --version
python -m ooxml_integrity doctor --json
python -m pytest
```

PPTX tests need usable fonts. The [CI workflow](.github/workflows/ci.yml) installs
Carlito, Caladea and Liberation on Linux/macOS and checks the resolved families;
Windows runners have Office-compatible system fonts. Use that workflow's font
checks to diagnose local differences. Report any skipped tests and their reasons;
a font-dependent skip is not evidence that the layout check passed. Ordinary
tests and the committed DOCX evidence evaluators do not need Office installed.

To work on one area, run its existing tests, for example:

```sh
python -m pytest tests/test_cli.py tests/test_policy.py tests/test_baseline_identity.py
```

Add a regression for a behavioral fix, including a clean/boundary case where
useful. Assert the intended document semantics and relevant codes, severity or
coverage, rather than merely copying implementation output. Documentation-only
changes need checked links and runnable examples; they do not require tests
that assert the prose verbatim.

## Evidence, browser and distributions

When touching DOCX evidence or its evaluators, run:

```sh
python research/build_docx_evidence.py evaluate
python research/review_revision_text.py --evidence-dir evidence/docx-paragraph-revision-ids --saved-outputs
```

The current revision gate keeps the original labels and allows only the finding
changes and exact diagnostic replacements declared in the
[paragraph-revision follow-up](evidence/docx-paragraph-revision-ids/PROTOCOL.md).
`python research/replay_frozen_docx.py` verifies historical expectations against
their archived checker. Running `research/revision_evidence.py evaluate` directly
uses the active checker and original labels; after FID009/FID010 it intentionally
reports two mismatches, the former known misses. The review command's default
evidence directory retains the FID009-only contract; use the explicit current
directory above. The previous note-revision contract still requires the former
message wording; it is retained as historical evidence. Do not rewrite historical
receipts to match a changed checker.

Read the [producer corpus](evidence/docx-beta/README.md) and
[existing-revision corpus](evidence/docx-revisions/README.md) before changing
fixtures or labels. Preserve provenance and hashes. Retain known misses and
false alarms explicitly; do not relabel expected behavior to make metrics pass.
Separate renderer observations, synthetic mutations, and checker results, and
keep accuracy claims limited to the measured corpus and scope.

For demo/runtime changes, follow the [real browser checks](tests/browser/README.md):
Node 24+, Chromium, both the published package and a checkout-wheel preview.
The Python adapter tests alone do not exercise the browser runtime. Use the
isolated preview directory; keep the public demo pinned to a published package.
Record failures or startup timeouts rather than treating them as passes.

For packaging changes, build both distributions and validate metadata:

```sh
python -m pip install build twine
python -m build
python -m twine check --strict dist/*
```

Then install each into a fresh environment and run
`python research/release_smoke.py --version 0.4.1`, replacing the version with
the candidate's actual version. Run it from the repository root using the
fresh environment's Python. The [distribution workflow](.github/workflows/distributions.yml)
also exercises the exact built wheel in Pyodide and retains the receipts.

## Submit a pull request

Use a branch and keep the change focused. Explain the concrete problem, the
resulting behavior, how it was verified and any remaining limitations. Include
reproduction steps for a fix, and say which tests ran, failed or were skipped.
Run `git diff --check` before committing. Keep temporary reports, private pilot
notes and credentials out of the PR.

For user-visible changes, update the changelog and relevant support/coverage
documentation. Review [compatibility](docs/compatibility.md): call out new or
removed findings, severity changes, schema changes and baseline migration,
including gate changes in a patch release. Version numbers, release tags and
demo pins are updated as part of the [release procedure](docs/releasing.md).
Opening a PR does not publish a release. Submit contributions under the
project's [MIT license](LICENSE).
