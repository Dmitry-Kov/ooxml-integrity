# Review-history benchmark with declared expectations

A later analysis of the frozen captures, not part of the [frozen evaluation](../README.md).
It asks how many of the checker's findings on correct edits are only the
changes the task asked for, and whether declaring those changes costs any
detection. The checker is this checkout's, run once as is and once with
expectations; the oracle's verdicts (completed, preserved) are read from
[evaluation.json](../evaluation.json), not recomputed. Status `ok` attempts of
both waves are included; superseded captures are not.

Expectations are derived only from each task's declaration and its source, the
way a caller who asked for the edit would write them
([script](../../../research/review_history_expectations.py)):

| Task | Expectation |
| --- | --- |
| K6 accept/reject | `FID001` with the insertion and deletion counts the named revisions remove (required) |
| K7h plain | `FID007` for the edited header story (required) |
| K7n plain | `FID005` with the edited footnote's source text (required) |
| K4 plain | `FID009` with the edited insertion's text, allowed but not required: `FID009` does not read an insertion holding a nested deletion |

Every other task declares none. [results.json](results.json) has every attempt.

| Tool | Correct outputs | flagged without | flagged with | Damaged outputs | caught without | caught with | Incomplete | flagged without | flagged with |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| reference control | 60 | 14 | 0 | 0 | | | 0 | | |
| python-docx `Run.text =` | 20 | 4 | 0 | 0 | | | 8 | 2 | 2 |
| python-docx setters | 6 | 2 | 0 | 14 | 14 | 14 | 8 | 2 | 2 |
| adeu 3.0.6 | 30 | 4 | 4 | 4 | 4 | 4 | 0 | | |
| docx-cli 0.26.0 | 18 | 4 | 0 | 38 | 34 | 34 | 0 | | |
| Office-Word-MCP-Server 1.1.11 | 8 | 0 | 0 | 6 | 4 | 6 | 10 | 0 | 6 |
| docx-mcp 0.7.4 | 34 | 12 | 0 | 0 | | | 2 | 2 | 2 |
| docxengine 1.0.0 | 32 | 6 | 0 | 6 | 2 | 4 | 2 | 2 | 2 |
| Claude Code, Opus 5.5 | 150 | 35 | 0 | 0 | | | 0 | | |
| Codex, gpt-6.1-sol | 150 | 41 | 6 | 0 | | | 0 | | |
| OpenCode, Qwen3.8 27B | 29 | 8 | 2 | 1 | 1 | 1 | 0 | | |
| **All** | **537** | **130** | **12** | **69** | **59** | **63** | **30** | **8** | **14** |

*Flagged* and *caught* mean a new ERROR or WARN on that output, the frozen
protocol's rule; `EXP001` counts.

- **Correct outputs.** The 12 still flagged are true reports outside the
  oracle's scope: replies with no anchor in the document (`CMT005`, Codex and
  OpenCode), which Word for Mac does not display ([word check](../word-check/README.md));
  adeu's repeated revision id (`REV001`); an undefined `CommentReference` style
  (`STY001`, Codex). No correct output gained an `EXP001`.
- **Damaged outputs.** None that was caught is missed with expectations. Four
  more are caught: Office-Word-MCP-Server and docxengine edited the document
  title instead of the requested header on S2, so the expected `FID007` did not
  occur (`EXP001`). Still missed: docx-cli's plain K4 and tracked K7n on S2,
  and docxengine's tracked K7h on S2. A tracked task declares no expectation
  in this reading, because a correct tracked edit draws no error; see the
  third reading below.
- **Incomplete outputs.** Office-Word-MCP-Server returns `ok` for header and
  note tasks it cannot perform; six of those are now flagged, because the
  requested change is missing.

## Third reading: tracked edits in the right place

0.4.9's `FID012` lists, as INFO, the tracked changes an edit added, per
story, kind and author. The third reading keeps the expectations above and
adds, for every tracked replacement, `FID012` with the editor as author in the
task's story (`document`, `header/default` or `footnotes`), required.

| | Without | With 0.4.8 expectations | Also expecting `FID012` |
| --- | ---: | ---: | ---: |
| Correct outputs flagged (of 537) | 130 | 12 | 12 |
| Damaged outputs caught (of 69) | 59 | 63 | 65 |

The two added catches are docxengine's tracked edit of the document title
instead of the requested header on S2, in both captures: its new revisions are
in `document`, so the expected `FID012` for `header/default` does not occur. No
correct output gains an `EXP001`. Still missed: docx-cli's plain K4 and tracked
K7n on S2, which change the right story in the wrong way.

## Limits

An expectation states which change is allowed, not what the result must look
like: `FID007` for a header accepts any change to that header's text. Only one
source per document type, two documents in all; the counts are attempts, not
independent documents.

```sh
python research/review_history_expectations.py
```
