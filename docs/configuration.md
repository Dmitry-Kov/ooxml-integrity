# Configuration, suppressions, baselines and CI output

How to run [`ooxml-integrity`](../README.md) in a repository that already has
findings, and how to get the findings into the pull request instead of a log.

## Adopting it in a repository that already has findings

Nobody fixes two hundred findings before they are allowed to gate the next
commit, and a rule that cannot be turned off gets the whole tool turned off
instead. Three mechanisms, deliberately kept separate, because each answers a
different question:

**"This rule is wrong for us."** A severity override in `.ooxml-integrity.toml`
(or `[tool.ooxml-integrity]` in `pyproject.toml`):

```toml
fail-on = "error"

[severity]
PPT006 = "off"      # shapes overlap by design in our template
TXT001 = "error"    # and we care about this one more than the default
```

**"This rule is wrong here."** An ignore, scoped to a path glob. `reason` is
required — a suppression whose justification lives in someone's memory is one
nobody can review a year later:

```toml
[[ignore]]
code = "PPT004"
path = "decks/social/**"
reason = "these are cropped intentionally for Instagram export"
```

**"We know, not today."** A baseline. Record what the repository already reports,
then fail only on what is new:

```bash
ooxml-integrity check "out/**/*.docx" --against templates/master.docx \
    --write-baseline           # writes .ooxml-integrity-baseline.json
git add .ooxml-integrity-baseline.json
```

The baseline records what the *checks* saw, before any config is applied — so
changing the config later cannot make old findings reappear as fake regressions.
It counts occurrences rather than storing a set, so a second overflow in a shape
that had one is still new. And its fingerprints exclude the message, because
messages carry measurements (`needs 118pt in a 48pt box`) and a baseline keyed on
those would go stale the first time anything moved by a point.

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

A failing job puts a message in a log that somebody has to go and open. A SARIF
report puts the finding in the review, where the person who caused it is already
looking. Suppressed findings are still in the report, marked suppressed with
their reason, so the file remains auditable — omitting them would defeat the
point of requiring a reason for every ignore.


## Bounded archive processing

DOCX and PPTX inputs are ZIP packages, so the checker applies finite resource
budgets before decompressing their members. The defaults allow 4,096 entries, a
256 MiB archive, 512 MiB total expanded data, 128 MiB in one expanded member,
and a 1,000:1 per-member compression ratio. Over-budget input is `PKG007`;
unsafe, traversal-like or duplicate normalised part names are `PKG008`.

The same limits cover `check()`, `check_pptx()`, and both files read by
`compare()`. They can be overridden in the project config or with an
`ArchiveLimits` object in the Python API. See [archive resource limits](archive-limits.md)
for the exact order of checks, configuration keys, and reproducible memory/time
measurements.
