# Coverage and environment capability

A file can have no findings even when some of its content could not be checked.
Coverage records what the checker evaluated, what it estimated, and what it
could not assess for that file.

## Per-file coverage

Add `--coverage` to an ordinary check:

```bash
ooxml-integrity check edited.docx --against source.docx --coverage
ooxml-integrity check deck.pptx --coverage --json
```

The human output prints one count per status and expands only
`estimated`, `skipped`, and `unsupported` items. `--coverage-details` implies
`--coverage` and also prints `checked` and `not-present` items. When any
confidence gap exists, a file with no findings is described as `no findings in
checked surfaces`, not simply `clean`.

The five statuses are:

| status | meaning |
| --- | --- |
| `checked` | The supported implementation evaluated this surface. |
| `not-present` | The surface was recognised and did not occur in the file. |
| `estimated` | A result was produced with reduced confidence, such as substituted font metrics. |
| `skipped` | A check could not run; `reason` explains the missing precondition or failure. |
| `unsupported` | The file contains, or the user requested, a recognised surface outside the current model. |

Coverage describes confidence and leaves the check exit code unchanged. A
failed requested comparison and unavailable machine-wide PPTX font measurement
already produce error findings (`FID000` and `PPT000`). Skipped or unsupported
informational surfaces appear in coverage without independently failing the
check, so exit codes retain their existing CI meaning.

With `--json`, each file gains this additive block:

```json
{
  "coverage": {
    "schema_version": 1,
    "summary": {
      "checked": 12,
      "not-present": 1,
      "estimated": 0,
      "skipped": 3,
      "unsupported": 2
    },
    "items": [
      {
        "id": "docx.fidelity.main-story",
        "status": "skipped",
        "reason": "source comparison was not requested"
      }
    ]
  }
}
```

All five summary keys are always present. Items always contain `id`, `status`,
and `reason`; `count` is present where a meaningful number of constructs or
package members is available. Coverage is omitted when it was not requested,
so existing JSON consumers retain the previous shape.

### Coverage identifiers

DOCX reports:

- `package.read`, `package.xml`, `package.content-types`, and
  `package.relationships`;
- `docx.styles`, `docx.numbering`, `docx.footnotes`, `docx.comments`,
  `docx.revisions`, `docx.tables`, `docx.content-controls`, and
  `docx.text-whitespace`;
- `docx.header-footer-semantics`, `docx.media-content`, and
  `docx.strict-wordprocessingml`;
- `docx.fidelity.main-story`, `docx.fidelity.note-bodies`, and
  `docx.fidelity.headers-footers`.

`docx.styles` is `checked` when references in `word/document.xml` are evaluated,
including when `word/styles.xml` is missing: those references have no definitions
and receive `STY001` findings. No styles part and no main-document references is
`not-present`, without a finding for the absent part alone. If the styles part
exists but cannot be safely parsed, it receives `XML001` and this surface is
`skipped`, even when the main document has no style references. Its definitions
are unknown; the checker does not emit a cascade of `STY001`/`STY002` findings.
For this skipped case, `count` records the main-document references present,
not references evaluated. The JSON schema and identifiers are unchanged.

When source comparison runs, `docx.fidelity.headers-footers` covers effective
`default`, `first`, and `even` story slots resolved through section
relationships. It is `not-present` only when neither input references any such
story; relationship or part renumbering does not change the status.

PPTX reports:

- `package.read`, `pptx.package-integrity`, and `pptx.slide-order`;
- `pptx.font-metrics`, `pptx.text-overflow`, `pptx.autofit-grow-shape`,
  `pptx.off-slide-geometry`, and `pptx.text-shape-overlap`;
- `pptx.grouped-shapes`, `pptx.tables`, `pptx.smartart`, `pptx.charts`,
  `pptx.fields`, `pptx.rotated-bounds`, `pptx.vertical-text`, and
  `pptx.master-layout-objects`;
- `pptx.fidelity.source`.

`pptx.autofit-grow-shape` is `skipped` when parsed, ungrouped text shapes request
`spAutoFit`, with their number in `count`. Their overflow is **not checked**;
the setting does not establish that the text fits or that a viewer will resize
the box. This reason is reported even when font metrics are unavailable. With
no such text shapes, the item is `not-present`, count zero; empty shapes do not
require an overflow verdict. Groups and shapes without usable geometry retain
their existing coverage limitations.

`pptx.text-overflow.count` excludes grow-shape autofit, as well as vertical text
and shapes without usable geometry. A deck containing only ordinary grow-shape
text has `skipped` overflow coverage, count zero. In a mixed deck, the status
describes the remaining eligible text shapes, and the reason names the excluded
grow-shape count. Font or geometry failures can still make this check `skipped`;
in that case its count is the number of eligible shapes, not completed verdicts.
Font confidence is reported separately and still considers grow-shape text.
Off-slide geometry and text-shape overlap continue to evaluate stored rectangles
where supported; they do not predict geometry after a viewer resizes a shape.
The new coverage identifier is additive under `schema_version: 1`; findings and
exit codes are unchanged.

`pptx.slide-order` is `checked` after the main `p:sldIdLst` resolves, including
hidden slides. An absent/empty list is `not-present`; unlisted parts are not
used as a fallback. A broken listed relationship or slide aborts reading with
`PKG002` and a skipped inventory. Order and layout are then left unchecked.
This does not validate the complete PPTX package graph. See the
[slide-order contract and Office evidence](pptx-slide-order.md).

Font metrics and overflow use families resolved from each slide's owning master
theme. A required theme chain or Latin face that cannot be resolved, or a
slide/layout font-scheme override outside the model, aborts reading with
`PKG002` and a skipped inventory. Layout has not been assessed in that case.
Literal-font text does not require unused theme dependencies. Successful theme resolution
does not upgrade font substitution or shaping confidence. See the
[master-theme contract and native Office evidence](pptx-master-themes.md).

These identifiers and status spellings are machine-facing contracts. New
identifiers may be added; incompatible meaning or schema changes require a new
`schema_version` and release notes.

## `doctor`

Run the environment report separately from a file check:

```bash
ooxml-integrity doctor
ooxml-integrity doctor --json
```

It reports:

- Python implementation, platform, `lxml`, libxml2, and fontTools versions;
- safe XML-parser and bounded-archive capabilities;
- how Calibri, Arial, and Times New Roman resolve on this machine, including
  the selected file and `exact`, `metric`, `similar`, or `fallback`
  confidence;
- checks known to be unavailable in this release.

The three font names provide a small sample of the machine's font setup.
Per-file coverage resolves the faces requested by the deck itself, which may
differ from these probes.

`doctor` exits `0` when all essential capabilities are available, including a
usable exact or metric-compatible font setup. It still exits `0` with status
`degraded` when fonts are usable only as estimates, because file checks will
surface that reduced confidence. It exits `1` when an essential capability is
unavailable, such as having no usable font metrics at all. `doctor --json` uses
`schema_version: 1`; environment-specific paths and version strings are data,
while capability and unavailable-check identifiers are stable.
