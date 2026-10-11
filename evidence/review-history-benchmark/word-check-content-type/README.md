# Word refuses Codex's K5-S1 outputs over one content type

**A post-hoc finding, not part of the [frozen evaluation](../README.md).** Word
for Mac 16.113.4 (16.113.26100421) on macOS 27.0.1 refused all five Codex
K5-S1 outputs on 10 October 2026: "Word found unreadable content", and after
**No**, "Word experienced an error trying to open the file". Codex declared
their `word/commentsExtended.xml` as `application/vnd.ms-word.commentsExtended+xml`
instead of
`application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml`.
With only that string changed, Word opens the file. The frozen oracle counts all
five outputs as correct, and no released checker rule reported the cause. The
unreleased `PKG010` now reports it
([rule and corpus run](../../docx-content-types/README.md)).

## How it was found

The refusals came from the Word check of the fixability survey for
`ooxml-integrity fix`. Its protocol was written before the first file was opened
and covered prototype repairs of 18 benchmark outputs. The five Codex S1 files
were among them: Word refused each one, both as captured and with the
prototype's reply repair. The variants below were made afterwards, from codex-2's
capture, to find the cause. They change one thing each, and every other ZIP entry
is the same, byte for byte, with the same order, names, compression and
timestamps. Each file was opened alone with `open -a "Microsoft Word"`; no
repair mode was chosen, no preference changed, and nothing was saved.

| File | Change from `captures/codex-2/K5-S1-comment.docx` | Word |
| --- | --- | --- |
| the five captures (`codex-1` … `codex-5`) | none | refused |
| [d4](variants/d4-codex-2-K5-S1-no-commentsExtended.docx) | `commentsExtended` part, its relationship and its content type removed | opens |
| [d6](variants/d6-codex-2-K5-S1-ct-fixed.docx) | only the `commentsExtended` content type changed to the `wordprocessingml` one | opens; Word lists three comments, and the reply is not among them |
| [d7](variants/d7-codex-2-K5-S1-anchored-ct-fixed.docx) | d6's change, and the reply anchored at its parent's range | opens; the reply in A. Counsel's thread |
| control: `corpus/base.docx` | — | opens |

d6 shows the cause. The reply is not shown there because Codex left it without an
anchor in the document (`CMT005`, as in the frozen evaluation). d7 anchors it the
way the prototype `fix` does, and Word then shows it in its parent's thread
([screenshot](screens/d6-d7-thread.png): d6 left, d7 right). The checker reports
nothing on d6 except that `CMT005`, and nothing at all on d7. `ooxml-integrity
fix` now writes d7 byte for byte from codex-2's capture itself, with its
content-type and anchor-replies repairs ([record](../../fix-repairs/README.md)).

[observations.json](observations.json) records, for each file, the SHA-256,
Word's prompts with the choice made, the comments and revisions Word's object
model listed, and what the margin showed. The five captures' hashes match the
frozen captures. The prototype's repaired copies are not stored; only their
hashes and Word's prompts are.

## Limits

- One Word build, one capture's variants. Word for Windows and Word on the web
  were not checked.
- Only `commentsExtended` was varied. The other relationship types `PKG010`
  reads were not opened in Word with a wrong content type.
- The operator was a computer-use agent driving Word through AppleScript, with
  the maintainer's permission. It was not blind to the expectations. Word's
  object model has no reply link, so threading was read from the screenshot.
- On every open, an installed Adobe PDF add-in raised a Visual Basic error. It
  was dismissed with **End**; it is unrelated to the documents.
- Only the margin crop is stored; the full-window screenshots also showed
  unrelated windows.
