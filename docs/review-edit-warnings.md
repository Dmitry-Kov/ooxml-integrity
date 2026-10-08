# Suspected escaping, insertion attribution and wide replacements

These warnings ask for review of a concrete XML observation. They do not
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

## FID013: a tracked replacement wider than the change

0.5.1. `compare(source, edited)` reads, in the main document, each
effective header/footer slot and the conventional footnote and endnote parts,
every paragraph's deleted and inserted text in document order. A deletion and
an insertion by one author that touch, with no other text between them, are a
tracked replacement. Only replacements the edit added are read: neither
revision's kind, author and effective date occurs in the same story of the
source, the rule `FID012` uses.

Words are separated by whitespace, as a reader sees them. The unchanged words
are those the deleted and inserted text share at their start and at their
end: words the replacement could have left out. FID013 reports WARN when they
are at least four and outnumber the words that change on the longer side, with
the story, author, both counts and both texts. In the review-history benchmark
docx-cli edits a footnote by deleting its whole text and inserting it again
with one phrase changed: six unchanged words around one to three changed ones.
A reviewer sees those six words struck through and added again under the
editor's name, and the change is hard to find; accepting still gives the right
text, so no other rule reports it.

The profile is deliberately narrow:

- A replaced phrase that keeps a word or two of itself (`ten business days`
  becoming `fifteen business days`) is below the threshold, and so is a
  rewritten sentence that keeps its first words but changes most of the rest:
  a real agent's rewrite in `runs/t5_rewrite_bare` keeps four words and
  changes nine. Words shared in the middle of the two texts do not count,
  since a rewrite can reuse `the` and `of` by chance.
- A replacement split by unchanged text between its deletion and insertion is
  two replacements, each judged alone. Moves, deletions and insertions by
  different authors, and revisions reusing a source context are not read.
- A person who selects a sentence and types it again with one word changed
  produces the same markup; the rule cannot tell who made the edit. WARN asks
  the caller to look. A pipeline that deliberately replaces whole sentences can
  declare it with an [expectation](configuration.md#changes-the-edit-was-asked-to-make)
  or turn the rule off with a reason.

Among the 1,051 labelled pairs this repository compares (producer corpus,
existing revisions, saved editor outputs, agent runs and the review-history
benchmark; of its 1,062 labelled pairs, nine have a missing header part and
two a comments part no parser reads, so `compare()` does not run on them), FID013 fires on the four docx-cli note edits only; no correct
benchmark output has one ([analysis](../evidence/review-history-benchmark/expectations/README.md#tracked-replacements-wider-than-the-change)).
