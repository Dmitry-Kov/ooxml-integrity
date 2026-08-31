# Agent run outputs

Each file is the result of one real agent run: its own copy of `../corpus/base.docx`,
one task phrased the way a user would phrase it, and no hint about how to edit.
Tooling choice was the variable being measured. See the main README for the table.

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

The pair to look at is `t2_pres` and `t4_fast_table`: the same table edits, one
with the reviewer's comment intact and tracked changes, one with the comment
silently detached and the edits untracked. That pair is the screenshot in
`../docs/word-comparison.png`.

Check any of them:

```bash
cd .. && python3 -c "
from inspect_docx import inspect, ERROR, WARN
from fidelity import compare
for f in inspect('runs/t4_fast_table/agreement.docx'):
    if f.sev in (ERROR, WARN): print(f.sev, f.code, f.msg)
for f in compare('corpus/base.docx', 'runs/t4_fast_table/agreement.docx'):
    print(f['sev'], f['code'], f['msg'])
"
```

## A note on `settings.xml`

These files were produced by agents editing a version of `base.docx` that had no
`word/settings.xml`, so they originally opened in Word's **Compatibility Mode**.
That is cosmetic — it does not affect any defect shown here — but it invites a
distracting question, so the part was added afterwards with `add_settings.py`.

It was added at the package level, not through Word's own "Convert" button:
Convert re-serialises the whole document and can itself alter tracked changes and
comment anchors, which would have destroyed the evidence these files carry.

`add_settings.py` asserts, on every run, that every pre-existing part is
byte-identical afterwards and that only `[Content_Types].xml` and
`word/_rels/document.xml.rels` gain one line each. The inspector's verdict on
each file is unchanged: `t2_pres` clean, `t4_fast_table` still reporting the
orphaned comment.

```bash
python3 add_settings.py runs/*/agreement.docx   # idempotent
```
