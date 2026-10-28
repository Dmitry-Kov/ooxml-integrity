# Review-history benchmark: post-release recheck

Post-hoc evidence, kept outside the frozen evaluation. docx-cli 0.27.0
(released 2026-10-11) and adeu 3.0.7 (released 2026-10-05) ran every task of
the [review-history benchmark](../review-history-benchmark/README.md) again on
2026-10-11, and docx-cli 0.28.0 (released 2026-10-27) on 2026-10-28, two
captures each, as the frozen evaluation captured docx-cli 0.26.0 and adeu
3.0.6. The question is narrower than the benchmark's: did the upstream fixes
for the defects reported from the benchmark remove the damage it recorded?

## Why it is separate

The protocol pins one version of each tool, its image and its adapter before
the first capture, and an amendment is made before the captures it affects. A
new release is a different tool version, so its outputs cannot join the frozen
counts. Nothing under `evidence/review-history-benchmark/` changes: protocol,
tasks, sources, oracle, evaluator, adapters, runners, captures, amendments and
`evaluation.json` are as frozen, and `verify` passed before every capture here.
The benchmark's results still describe docx-cli 0.26.0 and adeu 3.0.6.

## What ran

| Tool | Package | Image |
| --- | --- | --- |
| docx-cli 0.27.0 | npm `bun-docx` 0.27.0, tag `v0.27.0` (`11bc599`), tarball sha256 `4003b973…` | `ooxml-bench-docx-cli:0.27.0` (`sha256:0ad0358c…`) on the frozen base `oven/bun@sha256:e10577f0…` |
| docx-cli 0.28.0 | npm `bun-docx` 0.28.0, tag `v0.28.0` (`3c616a9`), tarball sha256 `11c6e900…` | `ooxml-bench-docx-cli:0.28.0` (`sha256:ac9c4308…`) on the same base |
| adeu 3.0.7 | tag `v3.0.7` (`096baa8`), its `python/` directory with `uv.lock` sha256 `9d5a0427…` | `ooxml-bench-adeu:3.0.7` (`sha256:b4c16f89…`) on the frozen base `python@sha256:f77ac9e4…`, uv 0.12.20 |

Each image is built as the frozen one was, from
[docx-cli-0.27.0.Dockerfile](../../research/review_history_tools/docx-cli-0.27.0.Dockerfile),
[docx-cli-0.28.0.Dockerfile](../../research/review_history_tools/docx-cli-0.28.0.Dockerfile)
and [adeu-3.0.7.Dockerfile](../../research/review_history_tools/adeu-3.0.7.Dockerfile);
[tools.json](tools.json) has the hashes, image ids and the exact build commands.
The network was used only while building. Every attempt ran in its own
container with the frozen flags (`--network none --user 65534:65534 --cap-drop ALL
--security-opt no-new-privileges`, the source read-only), through the
benchmark's own adapter and runner, unchanged; only the image name differs.
[research/review_history_recheck.py](../../research/review_history_recheck.py)
points the adapter at the new image and writes the captures under
[captures/](captures/) with the same receipts as the frozen ones.

**Control.** Before a release's captures, the image of the version before it
ran once through this same path ([control.json](control.json)): on 2026-10-11
the images the frozen captures used (same image ids), against those captures,
and on 2026-10-28 docx-cli 0.27.0's image, against its recheck captures. All
30 attempts of each control had the recorded status and the same oracle facts
as both recorded captures: docx-cli 0.26.0 and 0.27.0 each wrote 26 of their 28
outputs byte for byte (the two K5 outputs differ as the two recorded repeats
do), adeu 3.0.6 differs only in the dates it stamps. A difference below comes
from the release, not from the harness.

**Evaluation.** The benchmark's oracle and evaluator, unchanged, score the
recheck captures and the two frozen captures of the previous version alike.
The checker axis uses the current checker, `ooxml-integrity` 0.8.4 from this
repository's `src/` (the commit is in [results.json](results.json)): `check` on
the output and `compare` against the source, no configuration, an output
counted as flagged when it has an ERROR or WARN the source does not. It
scores the captures made on 2026-10-11 exactly as the 0.7.0 checker did then;
only the version label in their records changed. The frozen evaluation's own
checker axis (0.4.6) stays in `evaluation.json`; `results.json` repeats it for
the frozen captures as `frozen_detection`.

## Results

| Tool | Captures | Ran | Unsupported | Rejected | Completed | Preserved | Damaged | damaged with a new ERROR/WARN | Correct with a new ERROR/WARN |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| docx-cli 0.26.0 | frozen | 56 | 4 | 0 | 46 | 18 | 38 | 36 | 4 |
| docx-cli 0.27.0 | recheck | 56 | 4 | 0 | 48 | 44 | 12 | 10 | 14 |
| docx-cli 0.28.0 | recheck | 56 | 4 | 0 | 50 | 46 | 10 | 10 | 14 |
| adeu 3.0.6 | frozen | 34 | 24 | 2 | 30 | 30 | 4 | 4 | 4 |
| adeu 3.0.7 | recheck | 34 | 24 | 2 | 30 | 30 | 4 | 4 | 4 |

Every task where some version is not completed, preserved and free of new
findings; each cell is completion, the damaged fact categories, and the
current checker's new ERROR/WARN codes, and a task is marked with the releases
whose cell differs from the version before. Both captures of a version agree
on every task. Tasks not listed were completed and preserved with no new
finding by every version, or are unsupported by all (K0 for docx-cli, plain
replacements for adeu), or refused by all (adeu's K7h on S2).

| docx-cli task | 0.26.0 | 0.27.0 | 0.28.0 |
| --- | --- | --- | --- |
| K1-S1-tracked (changed in 0.27.0) | completed; damaged: list_item; `TXT002` | completed; preserved; - | completed; preserved; - |
| K1-S1-plain (changed in 0.27.0) | completed; damaged: list_item; `TXT002` | completed; preserved; - | completed; preserved; - |
| K2-S1-tracked (changed in 0.27.0) | completed; damaged: list_item; `TXT002` | completed; preserved; - | completed; preserved; - |
| K2-S1-plain (changed in 0.27.0) | completed; damaged: list_item; `TXT002` | completed; preserved; - | completed; preserved; - |
| K3-S1-tracked (changed in 0.27.0) | completed; damaged: list_item; `TXT002` | completed; preserved; - | completed; preserved; - |
| K3-S1-plain (changed in 0.27.0) | completed; damaged: list_item; `TXT002` | completed; preserved; - | completed; preserved; - |
| K4-S1-tracked (changed in 0.27.0) | completed; damaged: attribution, list_item; `FID011`, `TXT002` | completed; preserved; - | completed; preserved; - |
| K4-S1-plain (changed in 0.27.0) | completed; damaged: list_item; `FID009`, `TXT002` | completed; preserved; `FID009` | completed; preserved; `FID009` |
| K4-S2-tracked (changed in 0.27.0) | incomplete; damaged: paragraph_current, revision; `FID011` | completed; preserved; - | completed; preserved; - |
| K4-S2-plain (changed in 0.28.0) | incomplete; damaged: paragraph_current, revision; - | incomplete; damaged: paragraph_current, revision; - | completed; preserved; - |
| K5-S1-comment (changed in 0.27.0) | completed; damaged: list_item; `STY001`, `TXT002` | completed; preserved; `STY001` | completed; preserved; `STY001` |
| K6-S1-resolve (changed in 0.27.0) | completed; damaged: list_item; `FID001`, `TXT002` | completed; preserved; `FID001` | completed; preserved; `FID001` |
| K6-S2-resolve | completed; preserved; `FID001` | completed; preserved; `FID001` | completed; preserved; `FID001` |
| K7h-S1-tracked (changed in 0.27.0) | incomplete; damaged: list_item, paragraph, paragraph_current, story, story_current; `FID007`, `TXT002` | incomplete; damaged: paragraph, paragraph_current, story, story_current; `FID007` | incomplete; damaged: paragraph, paragraph_current, story, story_current; `FID007` |
| K7h-S1-plain (changed in 0.27.0) | completed; damaged: list_item; `FID007`, `TXT002` | completed; preserved; `FID007` | completed; preserved; `FID007` |
| K7h-S2-tracked | incomplete; damaged: paragraph, paragraph_current, revision, story, story_current; `FID007`, `FID008` | incomplete; damaged: paragraph, paragraph_current, revision, story, story_current; `FID007`, `FID008` | incomplete; damaged: paragraph, paragraph_current, revision, story, story_current; `FID007`, `FID008` |
| K7h-S2-plain | incomplete; damaged: paragraph, paragraph_current, revision, story, story_current; `FID007`, `FID008` | incomplete; damaged: paragraph, paragraph_current, revision, story, story_current; `FID007`, `FID008` | incomplete; damaged: paragraph, paragraph_current, revision, story, story_current; `FID007`, `FID008` |
| K7n-S1-tracked (changed in 0.27.0) | completed; damaged: attribution, list_item; `FID013`, `TXT002` | completed; damaged: attribution; `FID013` | completed; damaged: attribution; `FID013` |
| K7n-S1-plain (changed in 0.27.0) | completed; damaged: list_item; `FID005`, `TXT002` | completed; preserved; `FID005` | completed; preserved; `FID005` |
| K7n-S2-tracked | completed; damaged: attribution; `FID013` | completed; damaged: attribution; `FID013` | completed; damaged: attribution; `FID013` |
| K7n-S2-plain | completed; preserved; `FID005` | completed; preserved; `FID005` | completed; preserved; `FID005` |

| adeu task | 3.0.6 | 3.0.7 |
| --- | --- | --- |
| K4-S1-tracked | completed; preserved; `REV001` | completed; preserved; `REV001` |
| K4-S2-tracked | completed; preserved; `REV001` | completed; preserved; `REV001` |
| K6-S1-resolve | incomplete; damaged: paragraph_current, revision; `FID001` | incomplete; damaged: paragraph_current, revision; `FID001` |
| K6-S2-resolve | incomplete; damaged: paragraph, paragraph_current, revision; `FID001` | incomplete; damaged: paragraph, paragraph_current, revision; `FID001` |

## What changed

**docx-cli 0.27.0: damaged outputs fall from 38 to 12.** The literal
bullets are gone, and so is the tracked edit credited to another author inside
that author's insertion; both were reported from the benchmark. No damage
class appeared.

- **Bullets as the text `&#8226;` (S1) are gone: [PR #14](https://github.com/kklimuk/docx-cli/pull/14),
  for [issue #12](https://github.com/kklimuk/docx-cli/issues/12).** 0.26.0
  wrote `w:lvlText w:val="&amp;#8226;"` into `numbering.xml` on all 28 S1
  outputs, so Word showed the literal text `&#8226;` instead of the bullet. 0.27.0
  writes it on none. 24 S1 outputs are now preserved; the other four keep
  the damage described below. The 0.4.6 checker has no rule for it; the
  current one reports `TXT002` on all 28.
- **A tracked edit inside another author's insertion (K4) is credited to the
  editor and lands on the right span: [PR #20](https://github.com/kklimuk/docx-cli/pull/20)
  (with [#19](https://github.com/kklimuk/docx-cli/pull/19)), for
  [issue #13](https://github.com/kklimuk/docx-cli/issues/13).** 0.26.0 left
  the new text inside the other author's insertion with no wrapper of its own;
  on S2, next to Reviewer B's nested deletion of `any `, it also deleted
  ` The Client may` instead of `disputed amount`. 0.27.0 deletes exactly the old
  text as `Benchmark Editor`, puts the new text in the editor's own `w:ins` and
  splits the other author's insertion around it. Character by character, the
  ownership of both K4 tracked paragraphs equals the reference control's, which
  records the edit as Word does. The current checker's `FID011` (0.4.6: nothing)
  fired on all four 0.26.0 outputs and on none of 0.27.0's.

Unchanged in 0.27.0:

- **A direct edit next to the nested deletion (K4-S2 plain) still edits the
  wrong span**. Neither the 0.4.6 checker nor any loss rule of the current
  one reports it; 0.8.0's `FID014` does when the caller expects the
  text the edit was asked to produce, as the
  [fourth reading](../review-history-benchmark/expectations/README.md#fourth-reading-the-text-the-edit-was-asked-to-produce)
  of the frozen captures shows. The output is byte for byte 0.26.0's: ` The Client may` becomes
  `disputed sum` and `disputed amount` stays. Issue #13 reported the tracked
  command only. On that issue's own `nested-deletion.docx`, 0.27.0's `replace`
  without `--track` still replaces `The Client may ` with `disputed sum`, while
  `replace --track` now writes the expected markup
  ([nested-deletion-0.27.0.json](nested-deletion-0.27.0.json)). Reported upstream as
  [docx-cli#22](https://github.com/kklimuk/docx-cli/issues/22), fixed in 0.28.0
  (below).
- **A tracked note edit (K7n) still deletes and reinserts the whole note
  text.** Nothing is lost, but the tracked deletion is wider than the edit;
  `FID013` reports it on all four outputs of both versions. Not reported
  upstream.
- **`headers set --text --track` applies directly**, as the tool documents:
  the tracked K7h task is incomplete on both sources, and on S2 both modes
  overwrite Reviewer A's pending header revision (`FID007`, `FID008`).
- [PR #18](https://github.com/kklimuk/docx-cli/pull/18)'s new warning covers
  whole-paragraph `edit --at pN`, which the benchmark's mapping does not use;
  no attempt printed it.
- Apart from these, the only output difference is serialization: on S1,
  0.27.0 declares `w14` and `mc:Ignorable` on `comments.xml` (a changed part,
  not a loss). Every S2 output except the tracked K4 and the K5 comments
  (new random ids) is byte for byte 0.26.0's: 24 of 56.

Correct outputs with a new finding rise from 4 to 14 only because ten S1
outputs are no longer damaged: their findings are the requested change
itself (`FID009` for the plain K4 edit, `FID001` for K6, `FID007` and `FID005`
for the plain header and note edits), which the
[declared expectations](../review-history-benchmark/expectations/README.md)
treat as expected, and `STY001` on S1, where the new comment references a
`CommentReference` style S1 does not define, a true report outside the
benchmark's scope.

**docx-cli 0.28.0: the direct edit next to the nested deletion lands on the
requested words; damaged outputs fall from 12 to 10.**
[PR #21](https://github.com/kklimuk/docx-cli/pull/21), for
[issue #22](https://github.com/kklimuk/docx-cli/issues/22) (reported from this
recheck) and the maintainer's [#16](https://github.com/kklimuk/docx-cli/issues/16),
makes an untracked `replace` cut another author's insertion in place, nested
wrappers included, instead of splitting it.

- **K4-S2 plain is completed and preserved in both captures.** 0.28.0 replaces
  `disputed amount` with `disputed sum` inside Reviewer A's insertion, which
  keeps its one `w:id`, and leaves Reviewer B's deletion of `any ` as it was.
  The output has the reference control's oracle facts; the new run lacks the
  `w:rsidR` and `w:rsidRPr` the reference control keeps, which no fact
  records. Without configuration the checker reports no new ERROR or WARN on
  either version's output; with the fourth reading's expectations, 0.27.0's
  fails them (`EXP001`, the expected `FID014` does not occur) and 0.28.0's
  matches.
- On issue #13's `nested-deletion.docx`, `replace` without `--track` now gives
  `Fees are due. The Client may withhold disputed sum.`, and `replace --track`
  writes 0.27.0's markup ([nested-deletion-0.28.0.json](nested-deletion-0.28.0.json)).
- Nothing else changed. 50 of the 56 outputs are byte for byte 0.27.0's; the
  four K5 comment outputs have its oracle facts and differ as the two repeats
  do (new random ids). The K7n and K7h results above are 0.27.0's.
  [PR #23](https://github.com/kklimuk/docx-cli/pull/23) (table cell margins) and
  [#25](https://github.com/kklimuk/docx-cli/pull/25) (one grammar for size
  flags) change no output here.

**adeu 3.0.7: nothing changed.** Every attempt has 3.0.6's status,
completion, preservation and new codes, and each of the 17 outputs has the
same oracle facts as 3.0.6's apart from the dates adeu stamps. 3.0.7's engine
changes (tabs across run splits, [#157](https://github.com/dealfluence/adeu/issues/157);
rejecting a paragraph-mark deletion, [#158](https://github.com/dealfluence/adeu/issues/158);
comment dates, [#159](https://github.com/dealfluence/adeu/issues/159)) change
no fact these tasks record. Inside another author's insertion (K4) it still
keeps one `w:id` on both halves of the split insertion (`101` on S1, `12` on
S2), reported as `REV001`, which `ooxml-integrity fix` renumbers
([fix record](../fix-repairs/README.md)); K6 still resolves a same-author replacement pair
as one unit, by design; K7h on S2 is still refused as ambiguous.

## Reproduce

Without Docker, re-deriving status, completion, preservation and the probes
from the committed outputs:

```sh
python -m pytest tests/test_review_history_recheck.py
```

With Docker, building the images as [tools.json](tools.json) records, then,
for the latest release of a tool (`--version` names another):

```sh
python research/review_history_recheck.py control docx-cli
python research/review_history_recheck.py capture docx-cli 1
python research/review_history_recheck.py capture docx-cli 2
python research/review_history_recheck.py nested-deletion
python research/review_history_recheck.py evaluate --checker .venv/bin/python
python research/review_history_recheck.py table
```

`control` runs the version before the release. `capture` refuses to run when
the frozen benchmark has drifted or the image is not the recorded one, and
never writes into the frozen captures.

## Limits

Two sources, one build of each image, and the frozen task mapping: a fix in a
command the mapping does not call is not exercised. The outputs of this recheck
were not opened in Word; the [Word check](../review-history-benchmark/word-check/README.md)
of the damage classes stands for 0.26.0. The checker is a later version than
the frozen evaluation's, so its counts are not the benchmark's.
