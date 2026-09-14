# adeu pilot feedback: local regression protocol

Recorded before changing the checker, 2026-09-14. Starting commit: `5aa06b7`.
External report: [Git-Uzair, adeu #140, 14 September 2026](https://github.com/dealfluence/adeu/pull/140#issuecomment-5661945776).

The reporter used adeu 3.0.4, Windows and ooxml-integrity 0.4.1 on HUD
Handbook 4000.1, revised 2025-11-26: six tracked editing operations, nine Word
revisions and one comment. They report successful edits/Word opening, a cp1252
stdout crash, CMT004 for a related `word/comments1.xml`, shared paragraph-mark
revision IDs, 258,568 baseline TXT001 warnings, and approximately 144/200 second
single/pair checks. These are external observations, not local measurements.
Neither the exact source/output pair nor its hashes accompanied the comment.

## Local checks

1. Build small synthetic variants of the existing `corpus/base.docx`. Preserve
   every ZIP member except the explicitly changed XML/name/content-type and
   relationship entries. This is a checker regression study, not an editor run.
2. CLI: add a Unicode text excerpt and invoke human/JSON output with redirected
   `PYTHONIOENCODING=cp1252:strict`, `PYTHONUTF8=0`. Check complete output and
   normal threshold exit status; JSON must round-trip the exact Unicode text.
   This simulates stream encoding on macOS, not a native Windows capture.
3. Comments: rename the comments part through the standard relationship.
   Retained bodies must not produce CMT004/FID004. Changed bodies and missing
   definitions must still be detected, including with a misleading unlinked
   `word/comments.xml`. Check coverage as well as finding codes. Malformed or
   ambiguous relationships must not yield a clean comparison.
4. Whitespace: distinguish XML whitespace from non-breaking Unicode spaces and
   test inherited `xml:space` with a nearer override. Preserve warnings for
   unprotected ordinary edge spaces. Do not infer Word rendering from XML alone.
5. Profile a deterministic synthetic document with many paragraphs and edge
   spaces before/after any performance correction. Preserve every warning and
   its location when only performance changes. No timing assertion in tests.

Keep existing evidence, labels, captures and frozen checker receipts unchanged.
Run targeted/full tests and both original evidence evaluators. Record findings
and limitations in a separate report here. Do not change REV001 merely on the
reported Word acceptance behavior; the paragraph-mark ID case needs separate
evidence and specification analysis. Do not send a reply or publish a release.
