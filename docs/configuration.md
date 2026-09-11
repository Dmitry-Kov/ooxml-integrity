# Configuration, suppressions, baselines and CI output

This page explains how to introduce [`ooxml-integrity`](../README.md) into an
existing repository, account for known findings, and show results in pull
request reviews.

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

The baseline format is versioned. If a newer checker refuses an older baseline,
regenerate it with the same check command and `--write-baseline`; legacy formats
are not accepted when their fingerprints could hide a different new finding.
Version 0.4.0 rejects baseline v1 and writes v2. Review current findings before
regenerating: [0.4.0 migration instructions](releases/0.4.0.md#breaking-change-baseline-v2).

`--show-suppressed` prints what was hidden and why. A full worked config is in
[`docs/example-config.toml`](example-config.toml).

## Findings in the pull request, not in a log

```yaml
- uses: Dmitry-Kov/ooxml-integrity@v0.4.0
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
