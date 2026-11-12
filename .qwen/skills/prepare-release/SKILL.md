---
name: prepare-release
description: Prepare a release candidate of ooxml-integrity on a branch, following docs/releasing.md, and stop before anything is tagged or published.
disable-model-invocation: true
---

# Prepare a release candidate

Only the maintainer starts this, with the version number: `/prepare-release 0.10.1`.
`docs/releasing.md` is the authority; read its "Prepare" section before step 1.
This skill covers preparation only. **Do not create or push a tag, do not
publish to PyPI or the MCP Registry, do not merge.** Those are the maintainer's
steps.

1. **Check the starting point.** `main` is up to date and its CI is green; the
   version is not on PyPI and the tag does not exist
   (`git tag -l vVERSION`, `gh release view vVERSION`). Create the branch
   `release/VERSION`.
2. **Version in four places:** `pyproject.toml`,
   `src/ooxml_integrity/__init__.py`, and both `version` fields of `server.json`.
3. **Changelog and notes.** A new section at the top of `CHANGELOG.md` and a
   new `docs/releases/VERSION.md`, written from `git log vPREVIOUS..HEAD` and
   the merged pull requests. Describe every new or changed finding, severity
   change and baseline migration, as `docs/compatibility.md` requires. Notes of
   earlier releases are not edited.
4. **Rule tables.** New codes in `docs/rules.md`, and its "These tables
   describe" line pointed at the new notes.
5. **Action pins** in `.github/workflows/release.yml` to the new tag. Public
   examples in the README, the configuration guide and the demo stay on the
   published tag until the release is out.
6. **Evidence.** Save current metrics to a new file, never over an old one:

   ```sh
   mkdir -p evidence/releases/VERSION
   .venv/bin/python research/build_docx_evidence.py evaluate --output evidence/releases/VERSION/docx-beta.json
   ```
   Look at `evidence/releases/` for the files the previous release recorded and
   record the same set.
7. **Build and smoke-test.** Build the wheel and sdist, run
   `twine check --strict`, install each into a fresh environment and run
   `research/release_smoke.py --version VERSION` from the repository root.
8. **Verify.** Run the `verify-change` skill and the reference-deck assertion
   (`.venv/bin/python research/assert_deck.py corpus/deck.pptx`).
9. **Stop and report.** List what changed, what ran, what was not run (the
   browser suite, other platforms), and the steps that remain for the
   maintainer: the pull request, the tag, the publication checks, the public
   pins and the MCP Registry.
