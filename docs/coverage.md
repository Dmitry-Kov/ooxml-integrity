# Coverage and environment capability

A finding says that a supported check saw a problem. Coverage answers the
different question: which checks could honestly make a claim about this
particular file?

## Per-file coverage

Add `--coverage` to an ordinary check:

```bash
ooxml-integrity check edited.docx --against source.docx --coverage
ooxml-integrity check deck.pptx --coverage --json
```

The human output stays compact. It prints one count per status and expands only
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

Coverage describes confidence; it does not independently change the check exit
code. A failed requested comparison and unavailable machine-wide PPTX font
measurement already produce error findings (`FID000` and `PPT000`). Skipped or
unsupported informational surfaces remain visible without making every file
fail. Exit codes therefore retain their existing CI meaning.

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

PPTX reports:

- `package.read`, `pptx.package-integrity`, and `pptx.slide-order`;
- `pptx.font-metrics`, `pptx.text-overflow`, `pptx.off-slide-geometry`, and
  `pptx.text-shape-overlap`;
- `pptx.grouped-shapes`, `pptx.tables`, `pptx.smartart`, `pptx.charts`,
  `pptx.fields`, `pptx.rotated-bounds`, `pptx.vertical-text`, and
  `pptx.master-layout-objects`;
- `pptx.fidelity.source`.

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

The three font names are representative probes, not a promise that every face
declared by a future presentation exists. Per-file coverage resolves the faces
actually requested by that deck.

`doctor` exits `0` when all essential capabilities are available, including a
usable exact or metric-compatible font setup. It still exits `0` with status
`degraded` when fonts are usable only as estimates, because file checks will
surface that reduced confidence. It exits `1` when an essential capability is
unavailable, such as having no usable font metrics at all. `doctor --json` uses
`schema_version: 1`; environment-specific paths and version strings are data,
while capability and unavailable-check identifiers are stable.
