# Comments anchored outside the main story

The unreleased checker no longer reports `CMT005` for a comment whose range
and reference are written in a header, footer, footnote or endnote. Marker
collection read only the main document part, so such a comment was called
orphaned. This false positive was reported, with a comment anchored only in
`word/header1.xml`, in
[anthropics/skills#1734](https://github.com/anthropics/skills/pull/1734#issuecomment-5634228585).

## Construction

`python research/comment_story_evidence.py build` derives two sources from
[`corpus/base.docx`](../../corpus/base.docx). Comment 1 is anchored around
`EUR 12,000` in a table cell there. Its range start, range end and reference
run move around the text of the default header (`header-anchor`) or of footnote
1 (`footnote-anchor`); the cell text stays. Each source has a byte-identical
control and a `lost-anchor` output that removes the moved anchors from that
story while the comment body remains in `comments.xml`. The bytes are
deterministic, and the test suite rebuilds them.

[`manifest.json`](manifest.json) records hashes, mutations and labels. A label
is the exact actionable `(rule, severity, count)` multiset of `check()` on the
output plus `compare()` against its source, scored as in
[the beta corpus](../docx-beta/README.md). The labels follow from the
construction; they were not copied from checker output.

## Results

| pair | label | `26d4514` | unreleased |
| --- | --- | --- | --- |
| `header-anchor-control` | none | `CMT005` (false positive) | none |
| `header-anchor-lost-anchor` | `CMT005`, `FID008` | `CMT005`, `FID008` | `CMT005`, `FID008` |
| `footnote-anchor-control` | none | `CMT005` (false positive) | none |
| `footnote-anchor-lost-anchor` | `CMT005` | `CMT005` | `CMT005` |

[`baseline.json`](baseline.json) was produced by the checker of `26d4514`
(source hash `2b8cc935…`): 3 TP, 2 FP, 0 FN.
[`candidate.json`](candidate.json) by this change: 3 TP, 0 FP, 0 FN. Both record
the checker file hashes, Python, lxml and platform.

The candidate checker leaves every other evaluation unchanged: the 220-pair
beta corpus (100% precision and recall), the 168 saved benchmark and Word
output pairs, the frozen receipts, and all findings on the 1,887 DOCX and 605
PPTX files of the [public corpora](../../docs/real-world-corpora.md), including
their no-op and edit experiments. No file in those corpora anchors a comment
only outside the main story.

## Scope and limits

- The pairs are synthetic, and no Office application opened them. Whether
  Word displays either comment was not checked.
- Stories are the header, footer, footnote and endnote parts that the main
  part relates. Anchors in an unrelated part do not count; text boxes are
  part of the story that contains them.
- A range pairs within one story. A range that starts in the body and ends in
  a header is `CMT001`, `CMT002` and `CMT003`, each naming its part.
- If a related story cannot be parsed, orphans are not decided: that part has
  `XML001`, and `docx.comments` coverage is skipped.
- The source comparison counts comment anchors in the main part (`FID001`) and
  per header/footer story (`FID008`), not in notes. Only `CMT005` detects the
  footnote `lost-anchor` pair.

Reproduce with the development environment:

```sh
python research/comment_story_evidence.py evaluate
python -m pytest tests/test_comment_stories.py
```
