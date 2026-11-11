# Applied to other projects

Findings from the corpus and the [review-history benchmark](../evidence/review-history-benchmark/README.md)
were filed upstream, each with a self-contained reproduction. adeu fixed two
and docx-cli three; the others are open.

| Project | Finding | Status |
|---|---|---|
| [adeu](https://github.com/dealfluence/adeu/issues/137) | comment reference run carried `rStyle="CommentReference"` with no such style defined | fixed in 3.0.3; the reference document from this corpus was adopted as an upstream fixture |
| [python-docx](https://github.com/python-openxml/python-docx/issues/1604) | `paragraph.text` setter detaches comment anchors created through 1.2's comment API and existing footnote references | open; [PR #1605](https://github.com/python-openxml/python-docx/pull/1605) restored the comment anchors but was closed unmerged by its author on 2026-11-09; [PR #1645](https://github.com/python-openxml/python-docx/pull/1645) (opened 2026-11-10) keeps comment anchors when assigning `Paragraph.text`; footnotes and revisions remain outside its scope |
| [python-docx](https://github.com/python-openxml/python-docx/issues/1609) | `add_comment()` references the `CommentReference` style without defining it | open |
| [anthropics/skills](https://github.com/anthropics/skills/issues/1733) | the docx skill's `validate.py` passes a file whose comment is present in `comments.xml` but anchored to nothing — it checks marker → comment, not the reverse | open; [PR #1734](https://github.com/anthropics/skills/pull/1734) awaits maintainer review |
| [sontanon/docx-mcp](https://github.com/sontanon/docx-mcp/issues/4) | offer of labelled pairs; question about the policy of rejecting inputs that already carry revisions | open |
| [docx-cli](https://github.com/kklimuk/docx-cli/issues/12) | any write turns numeric character references such as `&#8226;` into literal text; Word shows `&#8226;` instead of a bullet | fixed in 0.27.0 (PR #14); in the [post-release recheck](../evidence/review-history-recheck/README.md) no S1 output has the literal bullet (0.26.0: all 28) |
| [docx-cli](https://github.com/kklimuk/docx-cli/issues/13) | `replace --track` inside another author's pending insertion credits the new text to that author, and misses the target next to a nested deletion | fixed in 0.27.0 (PRs #19, #20); in the [recheck](../evidence/review-history-recheck/README.md) both tracked K4 edits are preserved |
| [docx-cli](https://github.com/kklimuk/docx-cli/issues/22) | an untracked `replace` inside another author's pending insertion that holds a nested deletion replaces the wrong span | fixed in 0.28.0 (PR #21); in the [recheck](../evidence/review-history-recheck/README.md) the untracked K4 edit on S2 is completed and preserved (0.27.0: incomplete and damaged) |
| [docxengine](https://github.com/ruwadgroup/docxengine/issues/1) | a new comment writes `w14:paraId` into a comments part that does not declare `w14`; Word reports unreadable content | open |
| [docxengine](https://github.com/ruwadgroup/docxengine/issues/2), [SecurityRonin/docx-mcp](https://github.com/SecurityRonin/docx-mcp/issues/21) | a reply has no anchor in the document, and Word does not display it | open |
| [Codex](https://github.com/openai/codex/issues/53077) | replying to a comment, the code the model generated declares `commentsExtended` with a content type Word refuses (`PKG010`), and anchors the reply nowhere (`CMT005`) | open |

Fixture contributions merged upstream: [adeu #138](https://github.com/dealfluence/adeu/pull/138)
(comment projection across LibreOffice, Word for Mac and Word for Windows) and
[adeu #140](https://github.com/dealfluence/adeu/pull/140) (revision projection and
accept/reject). Preparing them surfaced a Python/TypeScript namespace-serialization
mismatch in adeu's own consistency suite
([#139](https://github.com/dealfluence/adeu/issues/139), fixed in 3.0.4).

## In use upstream

Since [adeu #156](https://github.com/dealfluence/adeu/pull/156) (merged
2026-09-29), adeu's test suite installs `ooxml-integrity`, pinned to 0.4.8 since
[adeu #161](https://github.com/dealfluence/adeu/pull/161) (merged 2026-10-05);
the pin is `0.8.1` as of 2026-11-11. For each shared cross-platform scenario it
applies the edits, runs `check()` on the output and `compare()` against the
input, and fails on error-level findings. The two accept/reject scenarios
declare the revision-count changes they request as expectations with `expect()`.