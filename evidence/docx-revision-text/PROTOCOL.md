# Count-neutral revision text loss

Declared 2026-09-15 before changing the checker. Baseline: merged commit
`83a773cc340a851ecb2a0a4d5a03203ed0945c05` (same checker as `ef6811f`).

Question: can source revision wording disappear while revision counts remain
unchanged, and can we detect that without rejecting Word fragmentation changes?

Primary reproduction: the existing synthetic `replace-unrelated-insertion`
pair in `evidence/docx-revisions`. Reviewer B's `optional` becomes `invented`;
the independent oracle reports loss, while the baseline has only REL003 INFO.
The source/output bytes, original labels and historical results stay unchanged.

Scope of the new check:

- Source comparison only; plain text inside main-part `w:ins` and `w:del`
  directly below a paragraph, assessed separately by revision kind.
- Run splitting, wrapper splitting/coalescence and ID renumbering must not
  become automatic text-loss findings. Existing FID001 coalescence behavior
  remains intact. Added revisions are not themselves defects.
- Start with equal wrapper counts. Compare exact payload occurrences, with
  a conservative fallback to text concatenated across same-kind wrappers when
  boundaries change. A literal occurrence can mask a lost revision's identity;
  this is explicitly not a general semantic diff or revision identity matcher.
- Nested/empty/property/non-text revision structures cause a declared skip for
  that kind. Bound fallback search work and expose incomplete checks in coverage.
- Metadata-only changes, formatting/anchor changes, note/header/footer revision
  text and unequal-count cases remain outside this rule. Existing checks stay
  active. An intentional rewrite/acceptance still needs separate intent review.

Validation: reproduce the original miss before the fix; synthetic insert/delete
substitutions, duplicate wording, run/ID normalization, coalescence compensated
by a new revision, unrelated ordinary edits, unsupported structures and bounded
search; CLI/JSON/SARIF/baseline identity and coverage. Recheck the 168 stored
editor/Word output pairs and all 30 revision pairs without new editor/API runs.
Retain historical receipts and record current differences separately. The old
220-pair corpus is regression evidence, not a new editor comparison.

Do not change REV001 or the note-revision rule in this work. No maintainer
message, paid API, document upload or package release is part of this task.
