# `fix` on every DOCX in the repository

[`ooxml-integrity fix`](../../docs/fix.md) makes three repairs: anchor-replies
(`CMT005` on a reply whose parent comment is anchored), renumber-revisions
(`REV001`) and content-type (`PKG010` on a part declared by an `Override`). This
record runs it on every DOCX in the repository that has one of the three
findings, and records what it repaired, what it refused and why, and what the
re-check found.

## Construction

`python research/fix_evidence.py evaluate --output evidence/fix-repairs/results.json`
checks every `.docx` under `corpus/`, `runs/`, `demo/` and `evidence/`: 1,380
paths, 849 distinct files by content. The 51 distinct files (58 paths) that have
`CMT005`, `REV001` or `PKG010` go to `fix()`; the five with `PKG010` also have
`CMT005`. Each runs against its source when the repository records one, which
all but the two Word-check variants of a Codex capture have:

- the review-history benchmark's tasks;
- the protocols of the two earlier benchmarks;
- the agent runs (`corpus/base.docx`);
- the docx-beta, docx-revisions and comment-story manifests.

Each file is fixed twice into a temporary directory, to check that the output
is deterministic. For a review-history capture that was repaired, the
benchmark's oracle evaluates the input and the copy.

[`results.json`](results.json) has, per file:

- the paths with those bytes, its hash and its source;
- the status and exit code;
- every change (part, element, XPath, old → new) and every refusal reason;
- the re-check: findings removed and added, `compare(input, output)`, what
  `compare(source, ·)` gained, and which ZIP members changed;
- the output hash, the determinism result and, for benchmark captures, the
  oracle's verdicts.

The hashes come from checker 0.6.0 (this change), Python 3.12.8, lxml 6.1.3 and
zlib 1.2.12. The output hash depends on the zlib that compresses the edited
part; everything else does not.

## Results

| Documents | files (paths) | repaired | anchor-replies | renumber-revisions | content-type | refused |
|---|---:|---:|---:|---:|---:|---:|
| review-history benchmark captures | 25 (30) | 17 | 13 | 4 | 5 | 9 comments in 8 files |
| docx-benchmark-boundaries, adeu split captures | 10 (11) | 10 | | 10 | | |
| docx-revisions, seeded `duplicate-id` | 1 | 1 | | 1 | | |
| docx-beta, seeded orphan comments | 9 | | | | | 9 |
| comment stories, lost anchors | 2 | | | | | 2 |
| agent runs, `t4_fast_*` | 2 (3) | | | | | 2 |
| `PKG010` Word check, variants of a Codex K5-S1 capture | 2 | 1 | 1 | | | 1 |
| **All** | **51 (58)** | **29** | **14** | **15** | **5** | **23 comments in 22 files** |

- **Every repair passed the re-check:**
  - the targeted finding is gone, and `check()` reports nothing new;
  - only `word/document.xml` changed, and `[Content_Types].xml` where
    content-type applied; every other ZIP member was copied as stored;
  - `compare(source, output)` gains nothing that `compare(source, input)`
    lacked, beyond the declared count increases.
- **`compare(input, output)` reports exactly what each repair adds:**
  - renumber-revisions and content-type: nothing.
  - anchor-replies: `FID002` INFO comment anchors +1. On the 7 S2 outputs it
    also reports character style references +1, because the reply's
    reference run copies the parent's `CommentReference` style, as Word's
    own reply runs do.
- **content-type and anchor-replies together** on the five Codex `K5-S1`
  captures:
  - in `[Content_Types].xml`, only the `commentsExtended` `Override`'s value
    changes, from `application/vnd.ms-word.commentsExtended+xml` to the
    `wordprocessingml` type;
  - the re-check removes `PKG010` and the `CMT005` and adds nothing.
    Against `corpus/base.docx` the copy gains nothing.
- **Every refusal names a precondition that does not hold:**
  - 22 top-level comments are "not a reply". Nothing links them to a parent,
    and their anchor position is lost.
  - python-docx-setter's `K1-S2` reply (both repeats are one file) "replies to
    comment 2, which is not anchored".
- **Deterministic:** a second run wrote the same bytes for all 51 files.
- **Oracle:** for all 17 repaired review-history captures, the verdict is the
  same before and after:
  - Codex (with its content type corrected), OpenCode, adeu: completed and
    preserved.
  - docx-mcp and docxengine `K5-S2`: preserved but still incomplete. Their
    new comment on "sixty days" stays unanchored; fix does not complete an
    edit.
  - Two of the 17, docx-mcp-1 and -2, were superseded by
    [amendment 005](../review-history-benchmark/amendments/005-runner-fixes.json)
    and are not scored, but are still in the repository.
- **Beyond the fixability survey:** the 10 adeu captures of the boundaries
  benchmark (`*-split`) were not part of the survey. adeu splits an insertion
  around its edit there too, and they are repaired the same way.
  `evidence/docx-word-id-followup/inputs/adeu-shared-id.docx` has the same
  bytes as one of them.

## Word for Mac and LibreOffice

These results are summarised from the maintainer's fixability survey of
2026-10-10. Its records (protocol, input hashes, screenshots) are outside this
repository, which keeps only what it can reproduce.

**The setup:**
- Microsoft Word for Mac 16.113.4 (build 16.113.26100421) on macOS 27.0.1, and
  LibreOffice 25.8.4.2, headless, outside Docker.
- They opened the survey prototype's repaired copies of 18 files. 17 of the 18
  are files in this repository.

**`fix` writes 12 of those 17 copies byte for byte:**

- For each, the SHA-256 that the Word record gives for the repaired copy equals
  `output_sha256` in `results.json`.
- The other five are the Codex `K5-S1` outputs. The prototype only anchored
  their reply, and Word refused those copies. `fix` now also corrects their
  content type, so it writes other bytes.
- The 18th is LibreOffice's public test file `tdf157011_ins_del_empty_cols.docx`.
  `fix` writes it with the same member contents. Its container differs because
  `fix` keeps the stored bytes of members it did not change, and the prototype
  recompressed them.

**For codex-2, `fix` writes the copy Word opened.** Its output is d7 of the
[content-type Word check](../review-history-benchmark/word-check-content-type/README.md),
byte for byte. Word opened d7 with the reply in its parent's thread. `fix` also
writes d7 from that check's variant d6, a capture with only its content type
corrected. For the other four Codex captures, the `[Content_Types].xml` and the
comment markers `fix` writes are d7's. Their outputs were not opened in Word or
LibreOffice. They differ from d7 only where Codex's own edits differ.

| | original | repaired |
|---|---:|---:|
| renumber-revisions, 6 pairs: Word opens without a prompt | 6/6 | 6/6 |
| same revisions (type, author, text); each of 51 accepted alone and rejected alone gives the same result | | 6/6 (102/102 actions) |
| anchor-replies, 12 pairs: Word opens without a prompt | 7/12 | 7/12 |
| Word lists the reply, and shows it in its parent's thread | 0/7 | 7/7 |
| LibreOffice opens and re-saves | 18/18 | 18/18 |
| the re-saved copy has no finding the re-saved original lacks | | 18/18 |
| LibreOffice keeps the reply when it re-saves | 0/12 | 12/12, threaded in 11 |

Notes on the table:
- **Codex `K5-S1`, the five copies Word does not open.** These are the
  prototype's copies with the reply anchored and nothing else. Word refuses
  them before and after that repair. The cause is not the repair: Codex
  declared `commentsExtended.xml` with the content type
  `application/vnd.ms-word.commentsExtended+xml`. Correcting only that string
  makes Word open the repaired copy with the reply threaded. `PKG010` now
  reports it and content-type repairs it (above).
- **The one LibreOffice reply that is not threaded** is OpenCode's `K5-S1`.
  Its `commentsExtended` root is `commentList`, not `w15:commentsEx`; Word
  threads it, and fix's change list names the non-standard root.
- **Renumbering changes nothing Word shows.** Word already treats halves that
  share an id as separate revisions. The repair gives unique ids for
  conformance and for tools that address a revision by id.

## Limits

- **Few producers, mostly synthetic documents.** The repairs are measured on the
  edit outputs the repository holds: two benchmark contracts, seeded defects,
  and one adeu boundary corpus. Reply placement follows the one convention all
  227 anchored replies in the survey's 656 comment-bearing DOCX have, but 211
  of them descend from one Word-saved source.
- **One build of each office application.** Word for Windows and Word on the web
  were not checked. Thread membership in Word was read from screenshots, because
  its object model has no reply link.
- **Some edit outputs are refused that a person could repair.** Replies
  anchored only in a header or footnote, a reply to a reply, and a reference
  inside a tracked insertion are refused: Word's placement there was not
  observed. None occurs in the repository.

Reproduce with the development environment:

```sh
python research/fix_evidence.py evaluate --output evidence/fix-repairs/results.json
python -m pytest tests/test_fix.py tests/test_repack.py tests/test_fix_evidence.py
```
