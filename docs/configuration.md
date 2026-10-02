# Configuration, suppressions, baselines and CI output

This page explains how to introduce [`ooxml-integrity`](../README.md) into an
existing repository, account for known findings, and show results in pull
request reviews.

Before changing the checker version, read [compatibility and upgrades](compatibility.md)
for report contracts, severity changes and reviewing an existing baseline.

## Adopting it in a repository that already has findings

A repository may already contain findings when you first add the checker to
CI. You can adjust rule severity, ignore a rule on selected paths, or record
existing findings in a baseline. The choice depends on why you want to exclude
the finding.

**Change a rule's severity** when its default does not suit the project. Set
the override in `.ooxml-integrity.toml` (or `[tool.ooxml-integrity]` in
`pyproject.toml`):

```toml
fail-on = "error"

[severity]
PPT006 = "off"      # shapes overlap by design in our template
TXT001 = "error"    # and we care about this one more than the default
```

**Ignore a rule on selected paths** when the exception belongs to a particular
set of files. Each ignore uses a path glob and requires a `reason`, so a later
reviewer can understand why it was added:

```toml
[[ignore]]
code = "PPT004"
path = "decks/social/**"
reason = "these are cropped intentionally for Instagram export"
```

**Create a baseline** when existing findings should be recorded without blocking
new work. Record the current findings, then fail only on new ones:

```bash
ooxml-integrity check "out/**/*.docx" --against templates/master.docx \
    --write-baseline           # writes .ooxml-integrity-baseline.json
git add .ooxml-integrity-baseline.json
```

The baseline records findings before configuration is applied. This keeps old
findings from appearing as new regressions after a configuration change. It
also counts occurrences: a second overflow in a shape that already had one is
still new. Fingerprints exclude the message text because messages contain
measurements such as `needs 118pt in a 48pt box`. A small change in those
measurements should not invalidate the baseline entry.

A check that raised (`INT001`) is never recorded or absorbed: a baseline keeps
a known defect visible to every later run, but a recorded crash would mean the
check silently stops running on that file. To accept one, add an `ignore` with
the reason, ideally a link to the bug report.

The baseline format is versioned. If a newer checker refuses an older baseline,
regenerate it with the same check command and `--write-baseline`; legacy formats
are not accepted when their fingerprints could hide a different new finding.
Version 0.4.0 rejects baseline v1 and writes v2. Review current findings before
regenerating: [0.4.0 migration instructions](releases/0.4.0.md#breaking-change-baseline-v2).

`--show-suppressed` prints what was hidden and why. A full worked config is in
[`docs/example-config.toml`](example-config.toml).

## Changes the edit was asked to make

Some edits remove what `compare()` protects, on purpose: accepting or rejecting
a named revision lowers the revision count (`FID001`), rewriting a header
without tracking changes that story (`FID007`), editing a note's text untracked
changes its body (`FID005`). Declare such a change as an expectation instead of
switching the rule off. A matching finding is listed as expected and does not
fail the run; an expectation that nothing matches is an `EXP001` error, because
the requested change did not happen, or not the way it was declared. A baseline
or a severity override only ever hides; an expectation also checks.

```toml
[[expect]]
code = "FID001"
path = "out/accepted/*.docx"
reason = "the pipeline accepts Counsel's pending insertion"
match = { tag = "ins", before = 2, after = 1 }

[[expect]]
code = "FID007"
reason = "the release step rewrites the draft number in the header"
match = { story_kind = "header", variant = "default" }
```

`match` names values the finding must carry: `part`, `where`, or any key of its
`extra` in the JSON report (`tag`, `before`, `after` for `FID001`;
`story_kind`, `variant`, `body` for `FID007`; `body` for `FID004`-`FID006`).
Values compare as text. `path` is a glob as for `ignore`, `reason` is required,
and `required = false` allows a finding without requiring it, for a change the
checker may or may not report, such as `FID009` for a direct edit inside an
insertion that holds another author's nested deletion. On the command line,
`--expect FID001:tag=ins,before=2,after=1` declares one for every file checked;
values there cannot contain commas. The JSON report lists matched findings under
`expected` with the reason, SARIF marks them suppressed with it, and a baseline
never records or absorbs `EXP001`. In Python, `expect(findings, expectations)`
returns the kept findings, with any `EXP001`, and the expected ones.

An expectation states which change is allowed, not what the result must look
like: `FID007` for a header accepts any change to that header's text. Combined
with the other checks it still caught, in the
[review-history benchmark](../evidence/review-history-benchmark/expectations/README.md),
tools that edited the document title instead of the requested header.

## Findings in the pull request, not in a log

```yaml
- uses: Dmitry-Kov/ooxml-integrity@v0.4.7
  id: docs
  continue-on-error: true
  with:
    files: "out/**/*.docx"
    against: templates/master.docx
    sarif: ooxml-integrity.sarif

- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: ooxml-integrity.sarif

- run: exit ${{ steps.docs.outputs.exit-code }}
```

A SARIF report makes findings available in the pull request review, alongside
the changes that caused them. Suppressed findings remain in the report with
their reasons, so reviewers can also inspect the exceptions.


## Bounded archive processing

DOCX and PPTX inputs are ZIP packages, so the checker applies finite resource
budgets before decompressing their members. The defaults allow 4,096 entries, a
256 MiB archive, 16 MiB central directory, 512 MiB total expanded data,
128 MiB in one expanded member, and a 1,000:1 per-member compression ratio.
Over-budget input is `PKG007`;
unsafe, traversal-like or duplicate normalised part names are `PKG008`.

The same limits cover `check()`, `check_pptx()`, and both files read by
`compare()`. They can be overridden in the project config or with an
`ArchiveLimits` object in the Python API. See [archive resource limits](archive-limits.md)
for the exact order of checks, configuration keys, and reproducible memory/time
measurements.

The [browser demo](../demo/README.md) uses the package's default archive limits
and runs without project configuration, severity overrides or baseline
suppressions. It also limits each input file to 25 MiB and each check to 60
seconds. Use the CLI or Python API when the workload needs custom limits or
repository policy.
