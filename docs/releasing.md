# Release procedure

A release publishes a tested package and its tag. Capability claims should
continue to reflect the documented evidence: publishing a version does not
establish that every public-beta adoption gate has been met. Keep capability
scope fixed while preparing a release.

## Prepare

1. Update `pyproject.toml`, `src/ooxml_integrity/__init__.py`, the changelog,
   versioned release notes, and current Action examples. Keep historical evidence
   unchanged. Explain every incompatible change, including baseline migration.
2. Update the public Action pins in `.github/workflows/release.yml` to the new
   tag. These jobs test the same pinned ref a consumer would use, with no
   source/version override. They must not resolve to a local working copy or
   the current PyPI version.
3. Run all tests, the DOCX evidence evaluator and the reference-deck assertion.
   Build wheel and sdist; validate with `twine check --strict`; install each in a
   fresh environment and run `research/release_smoke.py --version VERSION`.
   Run the [real browser suite](../tests/browser/README.md) against that candidate
   wheel in an isolated preview. Keep the public demo on the existing published
   version; the preview generator must not change `demo/worker.js`.
4. Commit, push `main`, and wait for all jobs in `CI` on that exact commit.

## One-time publisher setup

Configure a PyPI Trusted Publisher for project `ooxml-integrity`:

- Owner: `Dmitry-Kov`
- Repository: `ooxml-integrity`
- Workflow: `release.yml`
- GitHub environment: `pypi`

The environment should permit release tags only. The publish job alone receives
`id-token: write`; the build and pinned-Action jobs do not receive PyPI credentials.
The separate GitHub Release job receives `contents: write` only after publication.
The official [PyPI publisher setup](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
and [publishing guide](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
describe this token-free workflow. Never put API tokens in the repository or logs.

## Publish and verify

1. Confirm the version does not already exist on PyPI and the tag is absent.
2. Create an annotated `vVERSION` tag on the tested commit and push that tag.
3. `Release` requires matching package/tag versions and green source CI, builds
   once, checks both fresh installations, and exercises the remote pinned Action's
   clean/findings/usage-error/JSON/SARIF/baseline paths.
4. Only after both verification jobs pass, upload those exact files to PyPI with
   Trusted Publishing and attestations. Then create a GitHub Release containing
   the same wheel, sdist and SHA-256 checksums.
5. Check the published PyPI metadata and hashes, then install the exact version
   from public PyPI into a fresh environment and run the smoke test once more.
   Verify the GitHub Release points to the tested tag and contains both files.
6. Update `CHECKER_VERSION` in `demo/worker.js` in a separate PR after the package
   is available. The default browser suite must now install that exact version
   from public PyPI and pass, as must the checkout-wheel preview suite. Record
   the package/runtime/browser versions and page revision in `demo/VALIDATION.md`.
   Merge the pin update only after those checks pass; Pages repeats both suites
   on the deployed commit before uploading the public demo.

Do not overwrite a published tag or attempt to reuse a PyPI version. A failure
before upload can be retried after correcting its prerequisite. If upload
succeeded and only GitHub Release creation failed, rerun that failed job; do not
re-upload. Manual workflow dispatch must select the release tag, not `main`.
An incorrect published package needs a new version. Where justified, the faulty
release can be yanked after explicit review; do not delete or silently replace it.
