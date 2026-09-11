# Effective PowerPoint run properties

For ordinary `a:r` text in parsed slide shapes, the reader resolves font size,
Latin family, bold and italic independently. An explicit size and family do
not stop the search for inherited bold or italic. For example, a run with
`sz="1800"` and `Arial`, but no `b` or `i`, inherits both flags from a list
default with `b="1" i="1"`: the result is 18pt Arial Bold Italic.

The first definition of **each property** wins in the existing candidate chain:

1. The run's `a:rPr`.
2. The paragraph's `a:pPr/a:defRPr`.
3. The active level's `a:lvlNpPr/a:defRPr` in the shape's `a:lstStyle`.
4. Matching layout and then master placeholder list styles at that level.
5. The master text style for the placeholder class at that level.
6. Presentation defaults at that level.

For non-placeholder shapes, the chain goes from the shape's list style directly
to presentation defaults. Unset size defaults to 18pt; an unset family or a theme
token resolves through the [owning master's theme](pptx-master-themes.md).
Unset bold and italic default to false only after the chain is exhausted.
Explicit `0` or `false` overrides a lower-priority `1` or `true`; resolving one
flag never supplies a value for the other.

This is the existing level-specific property model, not the full DrawingML
style cascade. `a:defPPr` run-property fallbacks, shape-style `a:fontRef`, complex
or ambiguous placeholder matching, fields and script-specific shaping are
outside this claim. The change concerns ordinary runs; hard-break formatting
and placeholder selection retain their existing behaviour. The resolved flags
are passed to font discovery and measurement, subject to the installed-face and
substitution limits in the [support matrix](support-matrix.md).

## Regression evidence

[Run-property tests](../tests/test_pptx_run_properties.py) use controlled XML in a
copy of the committed master-theme package. They cover paragraph, shape list,
layout placeholder, master placeholder, master text style and presentation
defaults at levels 1 and 3. They also check explicit false at every overriding
level, properties split across different levels, themed family resolution,
unset defaults and non-placeholder shapes.

[Collection tests](../tests/test_font_collections.py) exercise the complete path
from inherited flags to selected font member, loaded advance tables, layout,
findings and CLI JSON/coverage. The fixtures generate original synthetic TTC and
CFF-based OTC fonts with deliberately different advances. For `ABCD` at 10pt,
wrap off and zero insets:

| Inherited style | Regular width used before the fix | Correct width | Box width | Correct result |
| --- | ---: | ---: | ---: | --- |
| Regular control | 12pt | 12pt | 18pt | No finding |
| Bold | 12pt | 24pt | 18pt | `PPT003` ERROR |
| Italic | 12pt | 8pt | 10pt | No finding; removes the false overflow |
| Bold Italic | 12pt | 28pt | 18pt | `PPT003` ERROR |

These are font-table and parser regressions, not new Office render observations.
The existing native Office fixtures remain separate regression controls.
Correcting the selected face can add or remove overflow findings in affected
presentations. Rule codes, severity thresholds, report schemas and font
substitution confidence classes are unchanged.
