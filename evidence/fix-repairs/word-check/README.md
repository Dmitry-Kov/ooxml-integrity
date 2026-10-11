# Word for Mac check of the repaired copies: the record

The raw record behind the [Word for Mac and LibreOffice](../README.md#word-for-mac-and-libreoffice)
summary of `fix`. Word for Mac 16.113.4 (build 26100421) on macOS 27.0.1,
2026-10-10, during the fixability survey that preceded `fix`: 18 pairs of an
original and the survey prototype's repaired copy, opened one file at a time,
plus four controls and the single-change variants of a Codex output that
isolated the content type Word refuses. The procedure and the expectations were
written before the first file was opened.

| File | What it holds |
| --- | --- |
| [PROTOCOL.md](PROTOCOL.md) | the procedure and the declared expectations, with each pair's hashes |
| [inputs.json](inputs.json) | per pair: the original capture, the repair, both SHA-256, the changes the repair made |
| [observations.json](observations.json) | per file: opened or not, Word's prompts and the choice made, the comments and revisions Word's object model lists, and for renumber-revisions each revision accepted alone and rejected alone; the controls and diagnostics |
| [verdicts.json](verdicts.json) | whether each reply is shown in its parent's thread, read from the window screenshots |
| [meta.json](meta.json) | Word and macOS versions, how files were opened, prompts and environment dialogs |
| [wcheck.py](wcheck.py), [wread.applescript](wread.applescript) | the automation that opened each file and recorded the above |

## Results

| | original | repaired |
| --- | ---: | ---: |
| renumber-revisions, 6 pairs: Word opens without a prompt | 6/6 | 6/6 |
| same revisions (type, author, text); each of 51 accepted alone and rejected alone gives the same result | | 6/6 (102/102 actions) |
| anchor-replies, 12 pairs: Word opens without a prompt | 7/12 | 7/12 |
| Word lists the reply, and shows it in its parent's thread | 0/7 | 7/7 |

The five pairs Word did not open are the Codex K5-S1 outputs, refused for a
content type before and after the reply was anchored; that finding is recorded
in the [content-type Word check](../../review-history-benchmark/word-check-content-type/README.md),
whose variant d7 Word opened with the reply in its thread.

## What is not published, and how to rebuild it

- **The copies.** `in/` and `fixed_from` name the survey's working folders,
  which were not committed. The originals are the captures `inputs.json` names.
  `ooxml-integrity fix` writes 12 of the 18 repaired copies byte for byte:
  their `fixed_sha256` here equals `output_sha256` in
  [results.json](../results.json). The five Codex K5-S1 copies differ, because
  `fix` also corrects their content type, which the prototype did not; from
  codex-2 it writes d7. The 18th original is a LibreOffice test file from the
  public corpora, not in this repository.
- **The screenshots.** They captured Word's window and the screen around it,
  so only what they show is recorded here (`verdicts.json`). The margin crop of
  the content-type check is published with that check.

To repeat the check, copy the two scripts to a working folder, put the pairs
in it and run `python3 wcheck.py FILE LABEL [--revisions]` for one file at a
time; it writes `obs/LABEL.json` and screenshots next to the script.
