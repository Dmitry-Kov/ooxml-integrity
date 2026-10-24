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

A `path` glob is matched segment by segment against the file's path as given
on the command line. `*`, `?` and `[...]` match within one segment; `**` as a
whole segment matches any number of segments, including none; a pattern
ending in `/` covers everything under that directory, and `*` alone every
file. So `out/**/accepted/*.docx` covers `out/accepted/a.docx` and
`out/2026/q3/accepted/a.docx`, but not `out/a/accepted/old/a.docx`, and
`**/final.docx` covers `final.docx` at any depth but not `draft-final.docx`.
Backslashes count as separators, so a config written on Windows reads the
same elsewhere.

0.8.1 narrows patterns with `**`. Up to 0.8.0 such a pattern was matched
against the whole path at once, so its other `*` crossed separators too:
`out/**/accepted/*.docx` also covered `out/a/accepted/nested/file.docx`, and
`**/final.docx` also covered `draft-final.docx`; `**` inside a segment
(`**.docx`) crossed them as well, and a leading `.` was dropped from paths and
patterns (`hidden/*.docx` covered `.hidden/a.docx`). An `ignore` or `expect`
entry written with such a pattern now covers fewer files. A finding an
over-broad `ignore` hid can now appear and fail the run; on the files an
`expect` entry no longer applies to, its finding is no longer marked expected,
and a missing one no longer raises `EXP001`.

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
`extra`, which `check --json` prints for every finding. The fidelity findings an
expectation usually names carry these:

| code | `extra` keys | values |
| --- | --- | --- |
| `FID001`, `FID002` | `tag`, `before`, `after` | `tag` is the counted element: `commentReference`, `footnoteReference`, `ins`, `del`, `sdt`, `drawing`, `tbl`, `hyperlink`, `pStyle`, `rStyle`, `numPr`, `tblHeader`; the counts are numbers |
| `FID003` | `before`, `after`, `tracked_deleted` | main-document text lengths in characters; `tracked_deleted`, when present, the text the edit kept as new tracked deletions |
| `FID004`-`FID006` | `body`, `author`, `lost`, `in_source` | `body` is the comment, footnote or endnote text, whitespace-normalised |
| `FID007` | `story_kind`, `variant`, `body`, `lost`, `in_source` | `header` or `footer`; `default`, `first` or `even` |
| `FID008` | `story_kind`, `variant`, `tag`, `before`, `after` | as `FID007`, with a `tag` as for `FID001` |
| `FID009`, `FID010` | `tag`, `body`, `lost`, `in_source` | `tag` is `ins` or `del`; `body` the revision text |
| `FID011` | `author`, `date`, `source_text_sha256`, `additional_text`, `additional_characters` | the earlier insertion's author and date, the text added under them |
| `FID012` | `story`, `tag`, `author`, `count` | `story` is `document`, `header/default` (and the other slots), `footnotes` or `endnotes`; `tag` is `ins`, `del`, `moveFrom` or `moveTo` |
| `FID013` | `story`, `author`, `unchanged_words`, `changed_words`, `deleted`, `inserted` | `story` as for `FID012` |
| `FID014` (0.8.0) | `story`, `change`, `before`, `after`, `before_original`, `after_original` | `story` as for `FID012`; `change` is `changed`, `added` or `removed`; the texts are the paragraph with tracked changes accepted (`before`, `after`) and rejected (`*_original`), whitespace normalised |

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

A correct tracked edit loses nothing, so it draws no error to expect. To check
that it landed where it was asked to, expect `FID012`, the INFO finding that
lists the tracked changes an edit added, per story (`document`, a header or
footer slot such as `header/default`, `footnotes`, `endnotes`), kind and author:

```toml
[[expect]]
code = "FID012"
reason = "the pipeline revises the header as Benchmark Editor, tracked"
match = { story = "header/default", author = "Benchmark Editor" }
```

A tracked edit made anywhere else leaves this unmatched and fails with `EXP001`.

Where the result is known, expect the text itself. `FID014`, an INFO finding
(0.8.0), lists every paragraph whose text the edit changed, with
the text before and after, tracked changes accepted and rejected. Declare the
paragraph the edit was asked to change as it read (`before`), the text it was
asked to produce (`after`), and that it was changed in place
(`change = "changed"`), with the text as `FID014` reads it: runs of spaces,
tabs and breaks as one space, none at either end, a non-breaking hyphen as
`-`, a soft hyphen as nothing:

```toml
[[expect]]
code = "FID014"
reason = "the task replaces 'disputed amount' with 'disputed sum'"
match = { story = "document", change = "changed", before = "Fees are payable within forty-five days of receipt of a valid invoice. The Client may withhold disputed amount.", after = "Fees are payable within forty-five days of receipt of a valid invoice. The Client may withhold disputed sum." }
```

An edit of another span or no edit at all leaves this unmatched and fails
with `EXP001`, and so does an edit of another paragraph. `after` alone is not
enough: it accepts any changed paragraph that ends up with that text. Given
`Pay within 30 days.` followed by `Legacy clause.`, an edit that leaves the
first alone and rewrites the second into `Pay within 60 days.` matches
`after = "Pay within 60 days."`; with `before = "Pay within 30 days."` it
fails. `change = "changed"` requires the paragraph to stand where it stood: an
edit that splits it, merges it with a neighbour, or deletes it and adds
another is listed as paragraphs removed and added, and fails. In the
review-history benchmark this expectation caught the two damaged outputs no
other rule or expectation reported: a tool rewrote the wrong words inside
another reviewer's pending insertion and lost nothing.

What the match cannot tell:

- **Repeated paragraphs.** `before` names a paragraph by its text, not its
  place. Where two paragraphs read the same, an edit of either matches. Add
  `where`, the paragraph's number in the edited story as `FID014` reports it
  (`where = "document/p12"`), when the paragraphs before it do not change.
- **Numbering.** That number counts every paragraph of the story, empty ones
  included, so an edit that adds or removes a paragraph earlier shifts it.
  Automatic list numbers (`1.`, `(a)`) are not paragraph text: renumbering a
  list is no `FID014` change and cannot be expected this way.
- **Other changes.** The match says the named paragraph changed as asked, not
  that nothing else did. Every other changed paragraph is still listed as
  `FID014` INFO, which does not fail the default gate. To fail on those too,
  raise the rule: with `FID014 = "error"` under `[severity]`, each paragraph
  change no expectation names is an error, and the expected one is still
  listed as expected.

## Findings in the pull request, not in a log

```yaml
- uses: Dmitry-Kov/ooxml-integrity@v0.8.2
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
