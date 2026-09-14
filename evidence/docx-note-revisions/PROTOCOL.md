# Revision-presence loss inside notes

Declared 2026-09-15 before checker changes. Baseline is merged PR #16,
`6c075bfabc13cce08703b0ed3af6ce29a37f17e9` (checker source from `beaba45`).

Primary question: can a footnote lose its pending insertion wrapper while
retaining the same words, and can the checker flag that without rejecting note
renumbering or revision-fragment coalescence?

Reuse the original `unwrap-note-insertion` source/output pair and independent
XML oracle. Its source is the synthetic notes profile; the defect was inserted
by a fixture mutator, not observed in an editor. Original bytes and labels stay
unchanged. No new editor/model/API execution or visual equivalence is claimed.

The new check will cover conventional `word/footnotes.xml` and `word/endnotes.xml`:

- Consider direct, non-housekeeping notes. Match groups by part and normalized
  concatenated `w:t` plus `w:delText` in document order, allowing IDs, note order
  and text-run fragmentation to change. This key is textual, not note identity.
- Assess only nonempty text groups with equal note multiplicity in both files.
  Changed/missing text, changed group multiplicity and empty text remain explicit
  gaps; existing note-body loss checks continue unchanged.
- For each group count notes containing at least one `w:ins` or `w:del`,
  separately by kind. Report a decrease in revision-bearing note occurrences.
  Joining two fragments into one inside the same note retains presence.
- A remaining same-kind revision inside that note masks partial removal.
  Repeated note text can mask reassignment of revisions across notes. Reference
  targets, revision payloads/authors/dates/positions, other revision kinds and
  full structural or visual equivalence are outside this rule.
- Track assessed source note/kind occurrences in coverage; malformed note XML
  or an unexpected note-part root cannot become a clean comparison.
- An intentional accept/reject can still remove audit information. The checker
  has no intent input and does not infer authorization from unchanged wording.

Validate insertion/deletion removal in both note kinds, duplicate text, note/revision
renumbering, run splitting, coalescence, nested presence, housekeeping exclusions,
empty/changed groups, malformed parts and intentional acceptance. Retain a test
for partial-removal blindness. Test CLI/JSON/SARIF, baseline multiplicity and
coverage. Re-evaluate all 30 revision pairs, the 168 saved benchmark/Word output
pairs and the original 220-pair regression corpus, with hashes and separate
baseline/current receipts. Only the recorded note miss may gain a finding.

FID001's coalescence guard and FID009's main-document scope are unchanged.
No maintainer message, release, demo pin change or new integration is included.
