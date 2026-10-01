# Suspected escaping and insertion attribution

These two warnings ask for review of a concrete XML observation. They do not
infer the editor's intent, automatically repair a document, or establish that a
document is corrupt. They are new checker behavior; the frozen 0.4.6 benchmark
receipts and their original metrics remain unchanged.

## TXT002: literal numeric punctuation/symbol spellings

`check()` scans parsed `w:t` and `w:delText` values in the main document and its
related headers, footers, footnotes and endnotes, plus `w:lvlText/@w:val` in
conventional `word/numbering.xml`. A literal `&#8226;` or `&#x2013;` remaining
**after XML decoding** usually means the producer escaped a numeric reference
twice. Word then receives the reference spelling as text or as the list marker.
Normal XML `&#8226;` decodes to `•` and produces no warning.

Only syntactically complete references to valid Unicode punctuation or symbol
characters are in scope. Numeric references to letters, whitespace, controls,
surrogates and out-of-range values do not produce this warning. It inspects
individual values; an entity spelling divided across text nodes is a gap.
Comments, field instructions, custom XML, Strict WordprocessingML, nonstandard
numbering-part locations and rendering are outside this check.

A document teaching XML syntax may deliberately contain these strings. Parsed
text cannot establish that intent, so TXT002 is WARN and explicitly calls it
possible double escaping. The existing rule configuration can ignore TXT002 in
such workflows; there is no automatic replacement. `docx.literal-entities`
coverage counts the inspected text/numbering values and names unreadable parts.

## FID011: surplus text under an existing insertion context

`compare(source, edited)` groups supported pending main-story `w:ins` text by
revision kind, author and effective date (`w16du:dateUtc` takes precedence over
`w:date`). It projects the edited character record with newly introduced
insertion contexts rejected and new deletion wrappers removed: the projection
that, since [#40](https://github.com/Dmitry-Kov/ooxml-integrity/pull/40), lets a
tracked comment, note or header/footer edit match its source item.
Revision IDs, run splitting and wrapper splitting/coalescence do not identify
an edit.

If the projected group preserves all source characters in their original
order **and** contains additional characters, those additional characters carry
the source insertion attribution without a distinct new insertion context.
FID011 reports WARN with that author/date and the additional text. For example,
an old insertion `indemnity insurance` by Counsel becomes a nested new deletion
by Editor followed by ordinary runs containing `liability insurance`: the old
words remain after rejecting Editor's deletion, and the new words still belong
to Counsel's insertion. A proper new nested insertion by Editor is rejected by
the projection and produces no FID011.

The profile is deliberately narrow:

- Source insertions must be nonempty direct paragraph children containing
  ordinary text runs with complete author/date metadata. Existing nested text
  deletions retain their own character states. The empty insertion Word puts
  in an inserted paragraph's mark or row properties, and proofing, bookmark,
  comment-range and rendered-page-break markers, hold no text and are ignored.
  Nested source insertions, moves, property history, fields, tabs, breaks and
  other non-text content make their context group ineligible. Unsupported
  edited content also skips its group. In the public corpora of
  [docs/real-world-corpora.md](real-world-corpora.md), 57 of the 85 author/date
  groups in the 38 documents with main-story insertions qualify; most of the
  rest have no date.
- Removed, altered or reordered source text/context is skipped. FID011 only
  witnesses preserved source text plus surplus; FID009 and other existing
  checks retain their own separate scopes. Surplus inside a pre-existing nested
  deletion context also skips the group; the warning concerns surplus carrying
  the outer insertion context alone.
- Context groups are joined in document order. The rule does not establish
  paragraph location, individual wrapper identity, formatting, task correctness
  or who actually performed the new edit. Redistribution between identical
  contexts and equal-length replacements can be missed. With repeated
  characters, the reported `additional_text` is one greedy subsequence surplus
  witness, not a unique reconstruction of the edit's original boundaries.
- A deliberate continuation by the same author or a new wrapper reusing the
  same author/date is indistinguishable from accidental attribution. WARN asks
  the caller to check intent. Distinct date spellings are not normalized; a
  metadata change can make a group ineligible even when the times are equivalent.
- Headers, footers, comments and notes are outside FID011. Comparison is bounded
  by the package limits, and extraction/projection/subsequence accounting is
  linear in the inspected text; it does not run a general edit-distance diff.

`docx.fidelity.insertion-attribution` counts assessed source insertion wrappers.
No source insertions gives `not-present`; all eligible wrappers assessed gives
`checked`; a mixture of assessed and skipped groups gives `estimated`; none
assessed gives `skipped` with the reason. No requested/successful comparison also
gives `skipped`. `checked` refers to this narrow witness, not attribution safety.

Both new WARN codes can change gates using `--fail-on warn` or a rule override;
the default error-only gate does not fail solely because of these warnings.
Coverage identifiers are additive under schema version 1. Existing baseline
entries, rule codes and historical evidence remain unchanged.
FID011 baseline identities hash author/date, the source-text digest and the
additional text, so acknowledging one warning does not hide a different
insertion context or addition and does not write that content into a baseline.
