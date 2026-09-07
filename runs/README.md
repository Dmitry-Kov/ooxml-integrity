# Agent run outputs

Each file comes from a separate agent run on a copy of `../corpus/base.docx`.
The prompt described an editing task without prescribing a tool or method.
The experiment recorded which approach the agent chose and what survived the
edit. See the main README for the results table.

| file | task | class | result |
|---|---|---|---|
| `t1_bare/agreement.docx` | change the fee, add a clause | careful | clean |
| `t1_pres/agreement.docx` | same, plus "don't disturb anything else" | careful | clean |
| `t2_bare/agreement.docx` | three edits to the milestone table | careful | clean |
| `t2_pres/agreement.docx` | same, plus "don't disturb anything else" | careful | clean |
| `t5_rewrite_bare/agreement.docx` | rewrite two paragraphs for clarity | careful | clean |
| `t5_rewrite_pres/agreement.docx` | same, plus "don't disturb anything else" | careful | clean |
| `t4_fast_fee/agreement.docx` | change the fee, add a clause — "be quick" | **fast** | **comment orphaned** |
| `t4_fast_table/agreement.docx` | three edits to the table — "be quick" | **fast** | **comment orphaned** |

`t2_pres` and `t4_fast_table` show the difference most directly. Both make the
same table edits. In `t2_pres`, the reviewer's comment remains anchored and the
edits are tracked. In `t4_fast_table`, the comment is detached and the edits are
untracked. The screenshot in `../docs/word-comparison.png` shows this pair.

From the repository root, inspect an output and compare it with the source:

```bash
ooxml-integrity check runs/t4_fast_table/agreement.docx --against corpus/base.docx
```

## A note on `settings.xml`

The version of `base.docx` given to the agents had no `word/settings.xml`, so the
outputs originally opened in Word's Compatibility Mode. That label did not
affect the defects studied here. The missing part was added afterwards with
`research/add_settings.py` to remove the Compatibility Mode label.

The script adds the part directly to the package. Word's "Convert" button
re-serialises the whole document and can alter tracked changes and comment
anchors, so using it would risk changing the evidence.

On every run, `research/add_settings.py` verifies that pre-existing parts remain
byte-identical except for `[Content_Types].xml` and
`word/_rels/document.xml.rels`, which each gain one line. The inspector's
verdicts are unchanged: `t2_pres` is clean, and `t4_fast_table` still reports the
orphaned comment.

```bash
python3 research/add_settings.py runs/*/agreement.docx   # idempotent
```
