# Word for Mac check of the prototype repairs — declared before opening

Written 2026-10-10 before the first file was opened. 18 pairs, each the original
capture and the prototype's repaired copy, byte copies in a local `in/` folder
(not published; [README](README.md) says how to rebuild them). One file open at a time, original first; opened with `open -a "Microsoft Word"`,
no repair mode chosen in advance, no preference changed, nothing saved; each
document closed with `close active document saving no`. Prompts are recorded with
the choice made (repair prompt: No). The Adobe PDFMaker VBA error that appears on
open/close on this Mac is dismissed with Return and is not attributed to the file.

What is recorded per file: Word's prompts; the comments Word's object model lists
(author, text, anchor text); the revisions it lists (type, author, text); a window
screenshot; for anchor-replies, whether the reply is shown in its parent's thread.
For renumber-revisions: each revision accepted alone, then (after reopening) each
rejected alone, counting the revisions left after each step; then closed unsaved.

Declared expectations:

- anchor-replies, original: opens without a prompt; the reply by Benchmark Editor is
  not shown (as in word-check files 4 and 5).
- anchor-replies, repaired: opens without a prompt; the reply is shown in the thread
  of its parent, at the parent's text (S1 "Effective Date", S2 "Completion Date").
- renumber-revisions, original and repaired: open without a prompt; Word lists the
  same revisions for both; in the repaired copy each revision is accepted or rejected
  alone. For the original, whether one accept/reject also takes the other half of the
  split insertion that shares its id is recorded as observed (no expectation).

| # | repair | original | repaired | SHA-256 original | SHA-256 repaired |
|---|---|---|---|---|---|
| 1 | renumber-revisions | `01-adeu-1-K4-S1-tracked-K4-S1-tracked--orig.docx` | `01-adeu-1-K4-S1-tracked-K4-S1-tracked--fixed.docx` | `9ae24f934fdb7e0d…` | `84ce42dfebcd9fc9…` |
| 2 | renumber-revisions | `02-adeu-1-K4-S2-tracked-K4-S2-tracked--orig.docx` | `02-adeu-1-K4-S2-tracked-K4-S2-tracked--fixed.docx` | `e3260958a52f2684…` | `e2c5d1e4e4f8efcc…` |
| 3 | renumber-revisions | `03-adeu-2-K4-S1-tracked-K4-S1-tracked--orig.docx` | `03-adeu-2-K4-S1-tracked-K4-S1-tracked--fixed.docx` | `183baa85d98ba34e…` | `f1ccf22ff23bb7b2…` |
| 4 | renumber-revisions | `04-adeu-2-K4-S2-tracked-K4-S2-tracked--orig.docx` | `04-adeu-2-K4-S2-tracked-K4-S2-tracked--fixed.docx` | `fe6c72e9a898e047…` | `cc390eff1afe6518…` |
| 5 | anchor-replies | `05-codex-1-K5-S1-comment-K5-S1-comment--orig.docx` | `05-codex-1-K5-S1-comment-K5-S1-comment--fixed.docx` | `486966298c2b252f…` | `32b694d6a7d971b5…` |
| 6 | anchor-replies | `06-codex-2-K5-S1-comment-K5-S1-comment--orig.docx` | `06-codex-2-K5-S1-comment-K5-S1-comment--fixed.docx` | `e03f4cc2cef4e8ba…` | `2b7611830e2e6126…` |
| 7 | anchor-replies | `07-codex-3-K5-S1-comment-K5-S1-comment--orig.docx` | `07-codex-3-K5-S1-comment-K5-S1-comment--fixed.docx` | `d331ea03253147c0…` | `00597ef5c5aa4f82…` |
| 8 | anchor-replies | `08-codex-3-K5-S2-comment-K5-S2-comment--orig.docx` | `08-codex-3-K5-S2-comment-K5-S2-comment--fixed.docx` | `17493a820911dca5…` | `9608c64960266d3d…` |
| 9 | anchor-replies | `09-codex-4-K5-S1-comment-K5-S1-comment--orig.docx` | `09-codex-4-K5-S1-comment-K5-S1-comment--fixed.docx` | `29f0e33e840b43d9…` | `55da57a188537d36…` |
| 10 | anchor-replies | `10-codex-5-K5-S1-comment-K5-S1-comment--orig.docx` | `10-codex-5-K5-S1-comment-K5-S1-comment--fixed.docx` | `b7fefc7a142cd830…` | `a4329a652e1f4724…` |
| 11 | anchor-replies | `11-docx-mcp-3-K5-S2-comment-K5-S2-comment--orig.docx` | `11-docx-mcp-3-K5-S2-comment-K5-S2-comment--fixed.docx` | `f909351d2d871656…` | `7826ff3275bc2d77…` |
| 12 | anchor-replies | `12-docx-mcp-4-K5-S2-comment-K5-S2-comment--orig.docx` | `12-docx-mcp-4-K5-S2-comment-K5-S2-comment--fixed.docx` | `f797872a792b6dd4…` | `400a310f8f4426c2…` |
| 13 | anchor-replies | `13-docxengine-1-K5-S2-comment-K5-S2-comment--orig.docx` | `13-docxengine-1-K5-S2-comment-K5-S2-comment--fixed.docx` | `01869cba76c924b9…` | `98208febaba0126b…` |
| 14 | anchor-replies | `14-docxengine-2-K5-S2-comment-K5-S2-comment--orig.docx` | `14-docxengine-2-K5-S2-comment-K5-S2-comment--fixed.docx` | `01869cba76c924b9…` | `98208febaba0126b…` |
| 15 | anchor-replies | `15-opencode-qwen-1-K5-S1-comment-K5-S1-comment--orig.docx` | `15-opencode-qwen-1-K5-S1-comment-K5-S1-comment--fixed.docx` | `09e63af78b496555…` | `2827096a8d79f141…` |
| 16 | anchor-replies | `16-opencode-qwen-1-K5-S2-comment-K5-S2-comment--orig.docx` | `16-opencode-qwen-1-K5-S2-comment-K5-S2-comment--fixed.docx` | `1895f2035f04d182…` | `9c5d66cdf8374ca6…` |
| 17 | renumber-revisions | `17-revisions-seeded_defect--duplicate-id--orig.docx` | `17-revisions-seeded_defect--duplicate-id--fixed.docx` | `f879520276a04a46…` | `a542906235c7d0e9…` |
| 18 | renumber-revisions | `18-public-libreoffice--tdf157011_ins_del_empty_cols--orig.docx` | `18-public-libreoffice--tdf157011_ins_del_empty_cols--fixed.docx` | `7c737a45db1ed60f…` | `dab8618a7b2d1584…` |

Full hashes: `inputs.json`.
