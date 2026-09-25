# Compatibility and upgrades

This policy describes the public interfaces of the research-alpha `0.x`
releases. A compatible report format does not promise identical findings:
correcting a missed defect can make an existing CI job fail. Check the
[0.4.3 release notes](releases/0.4.3.md) before changing a version pin.

## What a release can change

| Change | Release handling |
| --- | --- |
| Fix a missed defect, false alarm, severity assignment or resource-limit bypass | May ship in a patch release. Release notes must describe affected inputs, changed findings or thresholds, and any action needed. |
| Add a rule, optional report field or coverage identifier | Consumers must tolerate additions. New findings can affect a gate; document them in the changelog. |
| Remove or rename a public CLI/API field, change its type, or repurpose a rule code | An incompatible interface change needs explicit release notes and migration guidance; during `0.x`, normally use the next minor release. |
| Change coverage/Doctor schema meaning or baseline identity incompatibly | Increment the corresponding format version and document migration, independently of the package version. |

Security fixes may require rejecting previously accepted inputs in a patch.
Document that restriction and its reason. Do not silently reuse a published
package version or replace a release tag; see the [release procedure](releasing.md).

For example, `0.4.1` reports undefined styles even when `word/styles.xml` is
absent. A file that passed `0.4.0` can now produce `STY001` and exit `1`.
The same patch changes undefined *character* styles from error to warning;
those alone pass the default error threshold. These are finding changes with
unchanged CLI exits and JSON field types. Baseline v2 remains compatible.

The 0.4.2 [FID001 coalescence correction](../evidence/docx-fid001-coalescence/README.md)
can remove an ERROR when a lower inline revision-wrapper count is explained by
preserved content. Such a pair can change from exit 1 to exit 0. Codes, remaining
severities, report fields, coverage and baseline v2 identities are unchanged;
no baseline regeneration is required. An obsolete baseline entry may remain
unused. This does not authorize accepting revisions or certify a clean document.

## Rule codes, severity and exit status

The unreleased [package correction](real-world-corpora.md#checked-in-word-and-powerpoint)
lowers `XML001` to WARN for a malformed part that no relationship reaches,
which can change exit 1 to 0. Related parts, and packages with an unreadable
relationship part, keep the ERROR. `PKG005` and `PKG002` keep their
severities; their messages now say that Word asks to recover the document
and count the bytes after a ZIP end record. Messages are not part of baseline
fingerprints; codes, parts and baseline v2 identities are unchanged.

The unreleased main-part correction reads the main document part through the
package `officeDocument` relationship. Packages that name it otherwise, such
as docx4j's `word/document22.xml`, change from `PKG006` alone to a full check
and can change exit 1 to 0. A relationship to a part whose root is not
`w:document`, or `officeDocument` relationships to more than one part (new
`REL001`), can change exit 0 to 1; one to a missing part is `PKG006` even when
an unrelated `word/document.xml` exists. Findings in a renamed main part name
it; findings in `word/document.xml` keep their parts and baseline v2
identities. Without a main part, `compare()` raises `ValueError` naming it
instead of `KeyError`, and the CLI still reports `FID000`. Coverage reasons
name the part; schema v1 is unchanged.

The unreleased [comment-story correction](../evidence/docx-comment-stories/README.md)
reads comment ranges and references in the header, footer, footnote and
endnote parts that the main part relates. A comment anchored only there no
longer raises `CMT005`, which can change exit 1 to 0. `CMT001`–`CMT004` in
those parts are new findings that name the part; findings in the main part
keep their parts and baseline v2 identities. An unreadable related story
suppresses `CMT005`, while its `XML001` remains an error, and skips
`docx.comments`. That item's reference count now includes story references;
coverage schema v1 is unchanged.

The 0.4.3 [paragraph revision ID correction](paragraph-revision-ids.md)
removes `REV001` ERROR only for the verified plain whole-paragraph mark/content
pair. Such inputs can change exit 1 to 0 at the default threshold. Other shared
IDs retain their severity; new wording avoids a universal Word repair claim.
`FID002` wording also no longer equates duplication solely with colliding IDs.
No code, report field, coverage schema/count or baseline v2 identity changes.
Messages are excluded from baseline fingerprints, so no regeneration is needed;
an entry for an exempted pair may become unused. Published pins are unchanged.

The 0.4.2 [note-revision correction](../evidence/docx-note-revisions/README.md)
adds `FID010` ERROR when fewer notes retain insertion/deletion presence within
equally populated footnote/endnote text groups. An intentional acceptance can
also remove this audit signal; unchanged words do not establish authorization.
Unexpected roots in conventional note parts now prevent comparison (`FID000`).
These cases can change exit 0 to 1. New `docx.fidelity.note-revisions` coverage
is additive under schema v1; empty/changed groups are explicit gaps. Baseline v2
retains its format and existing identities; FID010 keys distinguish note part,
revision kind, normalized body digest and missing multiplicity. Review any new
finding before accepting it into a baseline. No automatic baseline migration
is performed; package and demo versions are recorded separately.

The 0.4.2 [revision-text correction](../evidence/docx-revision-text/README.md)
adds `FID009` ERROR. With a source and equal same-kind revision counts, loss of
supported main-document literal revision text can change exit 0 to 1 at the
default threshold. It does not infer authorized revision rewrites or acceptance.
The new `docx.fidelity.revision-text` coverage item is additive under schema v1;
unsupported/unequal-count cases and exhausted searches remain explicit gaps.
Baseline v2 keeps its format and all existing identities. The new rule's key
includes insertion/deletion kind, a SHA-256 digest of the original wording and
the missing occurrence count, so accepting one loss cannot hide a greater loss
of the same wording. No migration or automatic regeneration is required; review
new findings before recording a scoped exception. Check the installed version
or demo footer to establish which checker ran.

The 0.4.2 [adeu pilot corrections](../evidence/adeu-pilot-followup/README.md)
can remove false CMT004/FID004 errors for renamed comments parts, expose genuine
FID004 losses in those parts, and add CMT006 ERROR for invalid/ambiguous comments
resolution. Unresolvable fidelity is FID000 rather than a clean comparison.
REL002 no longer rejects ASCII case-equivalent target names. TXT001 no longer
warns for Unicode non-XML spaces alone or inherited preservation. All of these
can change a gate; no existing severity or schema version changed.

CLI stdout JSON now uses ASCII JSON escapes: JSON parsers recover exactly the
same Unicode values. Human stdout/stderr retain the stream encoding and use
backslash escapes for unencodable characters. UTF-8 report files remain UTF-8.
Successful serialization restores the documented exit behavior on legacy streams.
Baseline v2 remains readable. Locations for genuinely lost renamed comments now
name their actual source part, so such entries need review; do not regenerate a
baseline automatically. Existing conventional-part locations and TXT001 paths
are retained.

Use `code`, such as `CMT005`, as the rule identifier. Codes retain their
documented purpose; a different kind of check should receive a different code.
The [rule list](../README.md#what-it-reports-and-how-much-it-covered) and [support matrix](support-matrix.md)
describe current scope. Correcting or extending a rule within that scope can
add or remove findings. Message wording, measurements, finding order, XPath
locations and optional `extra` details are diagnostic data, not stable keys
for a consumer to parse.

Severity is attached to each finding. The same code can have different
severities for different cases: `STY001` is error for an undefined paragraph
or table style, but warning for an undefined character style. Policy can also
override severity or turn a rule off. Read the reported `severity`; do not
infer it from the code alone. Values are `error`, `warn`, and `info`, in that
order of importance.

For an ordinary CLI `check` invocation:

| Exit | Meaning |
| --- | --- |
| `0` | No remaining finding reaches the selected failure threshold. |
| `1` | At least one remaining finding reaches that threshold. JSON/SARIF can still be produced. |
| `2` | A handled usage or configuration error prevented the requested run; a normal JSON report is not guaranteed. |

The default threshold is `error`; `--fail-on warn` also fails on warnings,
and `--fail-on info` includes all three levels. Config can change the default;
an explicit CLI threshold takes precedence. Policy and baseline suppressions
are applied before the exit decision. `--quiet` affects human display only.
A missing named input is a `PKG000` finding, whereas a missing `--against`
source is a usage error. Process crashes or termination are not valid reports.

`--write-baseline` is a separate recording operation: it writes the raw
findings and exits `0` even when they include errors. It returns before normal
JSON, SARIF and coverage output. That exit does not mean the document passed.
`doctor` has its own [capability exit semantics](coverage.md#doctor).

## Machine-readable formats

These versions identify different things:

| Output | Version in 0.4.3 | Meaning |
| --- | --- | --- |
| `check --json` | Top-level `version: "0.4.3"` | Installed checker package version; there is no separate top-level JSON schema version. |
| Per-file coverage | `schema_version: 1` | Coverage shape, statuses and identifier meanings. |
| `doctor --json` | `schema_version: 1` and `version: "0.4.3"` | Capability schema and checker package, respectively. |
| Baseline file | `version: 2` | Counted finding identity format, not the package version. |
| SARIF | `version: "2.1.0"` | SARIF format; `runs[].tool.driver.version` identifies the checker. |

CLI JSON always has `version`, `fail_on`, `config`, `baseline`, and `files`.
`config` and `baseline` are null when unused. Each file has `path`, `summary`,
`worst`, `findings`, and `suppressed`. Summary contains all three severity keys
and counts the retained findings; `worst` is null when there are none.
Suppressed findings are separate and include `suppressed_because`, even without
`--show-suppressed`. A finding has `code`, `severity`, and `message`; empty
`where`, `part`, and `extra` are omitted. New optional fields may be added.

Request `--coverage` (or `--coverage-details`) to add each file's `coverage`.
Otherwise that field is absent. Coverage is computed from the raw check and
does not become complete when policy hides a finding. Its summary counts
inventory items, not a percentage of document correctness; an item's optional
`count` has the meaning documented for that surface. New identifiers may appear
within schema v1. The five status spellings and incompatible-change policy are
defined in [coverage and Doctor](coverage.md). Coverage does not independently
change the exit status.

SARIF uses each finding's code as `ruleId` and maps error/warn/info to
error/warning/note. It retains suppressed results and their reasons. Prefer
each result's `level` over a rule descriptor's default: severity can vary by
finding. Rule descriptors include rules seen in the run, not a complete catalog.
Locations identify the document artifact; they do not provide source-code line
numbers inside its ZIP parts.

Consumers should ignore unknown optional fields and handle unknown codes or
coverage identifiers without discarding their reported severity/status. Check
known schema versions, allow absent optional fields, and avoid assertions on
array order or human message text. An unknown schema should produce a visible
unsupported-format result, not an assumed pass. Store the package version with
the report so a changed result can be traced to the checker that produced it.

The browser demo returns the adapter's JSON response, including its own error
responses; it is not the CLI envelope described above. Its footer identifies
the installed package. See the [demo integration notes](../demo/README.md).

## Configuration and baselines

The CLI discovers `.ooxml-integrity.toml` or the relevant `pyproject.toml`
section by searching upward from the working directory. Use an explicit
`--config PATH`, or `--no-config` for an independent raw comparison. The
[configuration guide](configuration.md) defines overrides, scoped ignores,
archive budgets and baseline use. Unknown top-level or archive config keys are
errors; check a config change against the checker version that will read it.

Baseline v2 counts occurrences of identities based on the input path, rule
code, location (`where`, falling back to `part`), and selected fidelity
discriminators. It excludes message text and severity. Fidelity identities may
include construct tags, story roles and a digest of a lost body; a baseline
does not contain a complete report. Moving a file or changing a reported
location can make a finding new even with the same baseline format. An extra
occurrence beyond its recorded count remains visible.

A baseline is applied only when requested with `--baseline`; creating the
default-named file alone does not activate it. It is written before policy
filtering but applied to findings retained by policy. A matching baseline can
therefore continue suppressing a finding whose severity has changed. Compare
an upgrade without suppressions as well as with the project's normal policy.

Current releases read/write v2 and reject v1 rather than applying its weaker
fidelity identities. Review the raw findings first, then follow the
[v1-to-v2 migration](releases/0.4.0.md#breaking-change-baseline-v2). Regenerating
a baseline accepts the current findings; it does not fix them. Do not regenerate
automatically just to make an upgrade pass.

## Upgrade a CI integration

1. Record the old and candidate package versions, command, config, baseline,
   original/edited pair, and `doctor --json` output. Keep both inputs unchanged.
   For PPTX, record fonts and dependencies too: the same package version can
   measure differently on machines with different font files.
2. Install each version in a separate environment and run the same pair first
   with `--no-config --coverage --json` and no baseline. Compare codes,
   severities, locations and coverage. Review every new, removed or changed
   finding against the intended edit and the release notes.
3. Run again with the normal config, baseline and failure threshold. Review
   suppressions separately; migrate a baseline only when needed and after
   reviewing what it accepts.
4. Update the version pin in a trial branch, retain the reports, and require
   the CI run to finish before adopting the upgrade.

For a published package, pin explicitly, for example
`python -m pip install "ooxml-integrity==0.4.3"`. With the GitHub Action, pin
the Action ref and, when using PyPI, set the `version` input explicitly as in
the [pilot guide](pilot.md#try-it-after-generation-in-ci). The optional `source`
input takes precedence over `version`; with neither override the Action
installs from its selected ref. A checkout of `main` is not a
published release even when it still declares the same package version.

The Python API exported from `ooxml_integrity` is the intended library surface;
the CLI's configuration discovery and baseline filtering are not automatically
applied by `check`, `compare`, or `check_pptx`. Apply policy deliberately when
embedding them. Internal helpers and research scripts are not stable APIs.
The current package requires Python 3.9+; CI tests Python 3.9–3.13 on Linux and
3.12 on Windows/macOS. That matrix does not establish support for every newer
interpreter, Office renderer or font environment.
