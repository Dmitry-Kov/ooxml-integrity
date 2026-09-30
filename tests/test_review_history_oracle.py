"""The review-history oracle, checked before any tool runs.

Each seeded mutation damages one kind of review fact in S1 or S2, and the
expected (lost, added, changed) counts below are derived from what the mutation
does to the document, not copied from the oracle's output. No-op controls must
report nothing. The oracle never imports the checker.
"""
from __future__ import annotations

import sys
import zipfile

import pytest
from lxml import etree

from conftest import ROOT

sys.path.insert(0, str(ROOT))
from research import review_history_oracle as oracle  # noqa: E402

W = oracle.W
W15 = oracle.W15
S1 = ROOT / "corpus" / "base.docx"
SOURCES = ROOT / "evidence" / "review-history-benchmark" / "sources"
S2 = SOURCES / "word-review.docx"
DOC, COMMENTS, EXTENDED = "word/document.xml", "word/comments.xml", "word/commentsExtended.xml"


def _write(tmp_path, source, name, edits, *, rename=None):
    with zipfile.ZipFile(source) as z:
        parts = {i.filename: z.read(i) for i in z.infolist()}
    for part, edit in edits.items():
        root = etree.fromstring(parts[part])
        edit(root)
        parts[part] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    for old, new in (rename or {}).items():
        parts[new] = parts.pop(old)
    path = tmp_path / f"{name}.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for part, data in parts.items():
            z.writestr(part, data)
    return path


def _one(root, tag, predicate=lambda e: True):
    [found] = [e for e in root.iter(W + tag) if predicate(e)]
    return found


def _remove(element):
    element.getparent().remove(element)


def _unwrap(element):
    parent, index = element.getparent(), element.getparent().index(element)
    for child in reversed(list(element)):
        parent.insert(index, child)
    parent.remove(element)


def _payload(text):
    return lambda e: oracle.payload(e) == text


def _comment_id(text):
    root = etree.fromstring(zipfile.ZipFile(S2).read(COMMENTS))
    return _one(root, "comment", lambda c: oracle.text(c, "current").strip() == text).get(W + "id")


def _para_id(text):
    root = etree.fromstring(zipfile.ZipFile(S2).read(COMMENTS))
    comment = _one(root, "comment", lambda c: oracle.text(c, "current").strip() == text)
    return comment.findall(W + "p")[-1].get(oracle.W14 + "paraId")


REPLY, FIRST, BUDGET = ("Agreed. Add it to Schedule 1.", "Completion Date is not defined.",
                        "Check this against the approved budget.")


def _drop_anchors(cid, keep_reference=False):
    def edit(root):
        for tag in ("commentRangeStart", "commentRangeEnd") + (() if keep_reference else ("commentReference",)):
            for node in [n for n in root.iter(W + tag) if n.get(W + "id") == cid]:
                target = node.getparent() if tag == "commentReference" else node
                _remove(target)
    return edit


def _unwrap_text(tag, text, *, story=DOC):
    return {story: lambda root: _unwrap(_one(root, tag, _payload(text)))}


def _to_deletion(root):
    node = _one(root, "moveFrom", lambda e: e.getparent().tag != W + "rPr")
    node.tag = W + "del"
    for t in node.iter(W + "t"):
        t.tag = W + "delText"


def _flatten(root):
    inner = _one(root, "del", _payload("any "))
    outer = inner.getparent()
    outer.remove(inner)
    outer.addnext(inner)


def _set_text(tag_text, new):
    def edit(root):
        node = _one(root, "t", lambda t: t.text == tag_text)
        node.text = new
    return edit


def _accept_header(root):
    _remove(_one(root, "del"))
    _unwrap(_one(root, "ins"))


def _untracked_endnote(root):
    note = _one(root, "endnote", lambda n: n.get(W + "type") is None)
    _remove(_one(note, "del"))
    _unwrap(_one(note, "ins"))


def _drop_last_row(root):
    table = _one(root, "tbl")
    _remove(table.findall(W + "tr")[-1])


def _drop_list(root):
    num = [p for p in root.iter(W + "numPr")
           if "insurance" in oracle.paragraph_text(p.getparent().getparent(), "original")]
    _remove(num[0])


def _shift_date(root):
    node = _one(root, "ins", _payload("forty-five"))
    node.set(W + "date", "2026-10-01T00:00:00Z")


def _unwrap_content_control(root):
    sdt = _one(root, "sdt")
    _remove(sdt.find(W + "sdtPr"))
    content = sdt.find(W + "sdtContent")
    _unwrap(sdt)
    _unwrap(content)


def _add_paragraph(root):
    body = root.find(W + "body")
    body.insert(len(body) - 1, etree.fromstring(
        f'<w:p xmlns:w="{oracle.W_NS}"><w:r><w:t>Added clause.</w:t></w:r></w:p>'))


def _empty(tag):
    def edit(root):
        for child in list(root):
            if child.tag == tag:
                root.remove(child)
    return edit


#: name -> (source, part edits, expected summary)
MUTATIONS = {
    "drop-reply": (S2, {
        COMMENTS: lambda r: _remove(_one(r, "comment", lambda c: c.get(W + "id") == _comment_id(REPLY))),
        DOC: _drop_anchors(_comment_id(REPLY)),
        EXTENDED: lambda r: _remove(next(e for e in r if e.get(W15 + "paraId") == _para_id(REPLY)))},
        {"comment": (1, 0, 0), "comment_anchor": (1, 0, 0), "comment_date": (1, 0, 0),
         "comment_done": (1, 0, 0), "comment_durable_id": (1, 0, 0), "comment_thread": (1, 0, 0)}),
    "unthread-reply": (S2, {
        EXTENDED: lambda r: next(e for e in r if e.get(W15 + "paraId") == _para_id(REPLY)).attrib.pop(
            W15 + "paraIdParent")},
        {"comment_thread": (1, 0, 0)}),
    "unresolve": (S2, {
        EXTENDED: lambda r: next(e for e in r if e.get(W15 + "paraId") == _para_id(BUDGET)).set(
            W15 + "done", "0")},
        {"comment_done": (0, 0, 1)}),
    "lose-anchor-range": (S2, {DOC: _drop_anchors(_comment_id(FIRST), keep_reference=True)},
                          {"comment_anchor": (0, 0, 1)}),
    "drop-person": (S2, {"word/people.xml": lambda r: _remove(r[0])}, {"person": (1, 0, 0)}),
    "drop-durable-ids": (S2, {"word/commentsIds.xml": _empty(oracle.W16CID + "commentId")},
                         {"comment_durable_id": (3, 0, 0), "comment_date": (0, 0, 3)}),
    # The paragraph's rejected text changes, so its other revisions change context.
    "unwrap-insertion": (S2, _unwrap_text("ins", "forty-five"),
                         {"revision": (1, 0, 3), "paragraph": (1, 1, 0), "paragraph_current": (1, 1, 0)}),
    "accept-deletion": (S2, {DOC: lambda r: _remove(_one(r, "del", _payload("thirty")))},
                        {"revision": (1, 0, 3), "paragraph": (1, 1, 0), "paragraph_current": (1, 1, 0)}),
    "flatten-nested-deletion": (S2, {DOC: _flatten},
                                {"revision": (1, 1, 3), "paragraph": (1, 1, 0),
                                 "paragraph_current": (1, 1, 0)}),
    "move-to-deletion": (S2, {DOC: _to_deletion}, {"revision": (1, 1, 0)}),
    "drop-move-range": (S2, {DOC: lambda r: _remove(_one(r, "moveFromRangeStart"))},
                        {"move_range": (1, 0, 0)}),
    "drop-run-format-change": (S2, {DOC: lambda r: _remove(_one(r, "rPrChange"))}, {"revision": (1, 0, 0)}),
    "drop-bold-keep-change": (S2, {DOC: lambda r: _remove(_one(r, "rPrChange").getparent().find(W + "b"))},
                              {"revision": (0, 0, 1)}),
    "drop-paragraph-format-change": (S2, {DOC: lambda r: _remove(_one(r, "pPrChange"))},
                                     {"revision": (1, 0, 0)}),
    "shift-revision-date": (S2, {DOC: _shift_date}, {"revision": (0, 0, 1)}),
    "untracked-edit-elsewhere": (S2, {DOC: _set_text(
        "Either party may terminate this agreement on sixty days' written notice.",
        "Either party may terminate this agreement on ninety days' written notice.")},
        {"paragraph": (1, 1, 0), "paragraph_current": (1, 1, 0), "revision": (0, 0, 1)}),
    "accept-header-revisions": (S2, {"word/header1.xml": _accept_header},
                                {"revision": (2, 0, 0), "story": (0, 0, 1), "story_current": (1, 1, 0),
                                 "paragraph": (1, 1, 0), "paragraph_current": (1, 1, 0)}),
    "untracked-endnote-edit": (S2, {"word/endnotes.xml": _untracked_endnote},
                               {"revision": (2, 0, 0), "note": (1, 1, 0), "note_current": (1, 1, 0),
                                "note_reference": (1, 1, 0), "paragraph": (1, 1, 0),
                                "paragraph_current": (1, 1, 0)}),
    "drop-endnote-reference": (S2, {DOC: lambda r: _remove(_one(r, "endnoteReference").getparent())},
                               {"note_reference": (1, 0, 0)}),
    "unwrap-content-control": (S2, {DOC: _unwrap_content_control},
                               {"content_control": (1, 0, 0)}),
    "drop-table-row": (S2, {DOC: _drop_last_row},
                       {"table": (0, 0, 1), "paragraph": (3, 0, 0), "paragraph_current": (3, 0, 0)}),
    "unwrap-hyperlink": (S2, {DOC: lambda r: _unwrap(_one(r, "hyperlink"))}, {"hyperlink": (1, 0, 0)}),
    "drop-list-numbering": (S2, {DOC: _drop_list}, {"list_item": (1, 0, 0)}),
    "tracking-off": (S2, {"word/settings.xml": lambda r: _remove(_one(r, "trackRevisions"))},
                     {"setting": (0, 0, 1)}),
    "edit-styles": (S2, {"word/styles.xml": lambda r: next(r.iter(W + "sz")).set(W + "val", "30")},
                    {"part": (0, 0, 1)}),
    "classic-comment-body-lost": (S1, {COMMENTS: lambda r: _remove(r[0])},
                                  {"comment": (1, 0, 0), "comment_anchor": (1, 0, 0),
                                   "comment_date": (1, 0, 0)}),
    "footnote-body-lost": (S1, {"word/footnotes.xml": lambda r: _remove(
        _one(r, "footnote", lambda n: n.get(W + "id") == "2"))},
        {"note": (1, 0, 0), "note_current": (1, 0, 0), "note_reference": (1, 1, 0),
         "paragraph": (1, 0, 0), "paragraph_current": (1, 0, 0)}),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_each_seeded_mutation_is_reported_as_declared(tmp_path, name):
    source, edits, expected = MUTATIONS[name]
    output = _write(tmp_path, source, name, edits)
    assert oracle.summary(oracle.compare(source, output)) == expected


def test_a_changed_image_is_reported(tmp_path):
    path = tmp_path / "image.docx"
    with zipfile.ZipFile(S1) as z, zipfile.ZipFile(path, "w") as out:
        for info in z.infolist():
            data = z.read(info)
            out.writestr(info.filename, data + b"\0" if info.filename.endswith(".png") else data)
    assert oracle.summary(oracle.compare(S1, path)) == {"image": (0, 0, 1), "part": (0, 0, 1)}


def test_dates_can_be_ignored(tmp_path):
    output = _write(tmp_path, S2, "date", {DOC: _shift_date})
    assert oracle.summary(oracle.compare(S2, output, ignore_dates=True)) == {}


@pytest.mark.parametrize("source", [S1, S2], ids=["S1", "S2"])
def test_unchanged_and_repacked_packages_report_nothing(tmp_path, source):
    assert oracle.compare(source, source) == {"lost": {}, "added": {}, "changed": {}}
    repacked = tmp_path / "repacked.docx"
    with zipfile.ZipFile(source) as z, zipfile.ZipFile(repacked, "w", zipfile.ZIP_STORED) as out:
        for info in reversed(z.infolist()):
            out.writestr(info.filename, z.read(info))
    assert oracle.summary(oracle.compare(source, repacked)) == {}


def test_renaming_a_compared_part_is_not_a_change(tmp_path):
    def retarget(root):
        for node in root:
            if node.get("Target") == "header1.xml":
                node.set("Target", "header9.xml")
            if node.get("PartName") == "/word/header1.xml":
                node.set("PartName", "/word/header9.xml")
    output = _write(tmp_path, S2, "renamed", {"word/_rels/document.xml.rels": retarget,
                                              "[Content_Types].xml": retarget},
                    rename={"word/header1.xml": "word/header9.xml"})
    assert oracle.summary(oracle.compare(S2, output)) == {}


def test_word_writes_reviewer_b_on_top_of_reviewer_a():
    """S2's own capture: the second save adds B's record and loses nothing."""
    report = oracle.compare(SOURCES / "review-a.docx", S2)
    assert report["lost"] == {}
    assert oracle.summary(report) == {
        "comment": (0, 1, 0), "comment_anchor": (0, 1, 0), "comment_date": (0, 1, 0),
        "comment_done": (0, 1, 1), "comment_durable_id": (0, 1, 0), "comment_thread": (0, 1, 0),
        "note_current": (0, 0, 1), "paragraph_current": (0, 0, 2), "person": (0, 1, 0),
        "revision": (0, 5, 0)}


def test_python_docx_open_save_is_a_clean_control(tmp_path):
    docx = pytest.importorskip("docx")
    for source in (S1, S2):
        output = tmp_path / f"{source.stem}-saved.docx"
        docx.Document(str(source)).save(str(output))
        assert oracle.summary(oracle.compare(source, output)) == {}


def test_compare_exits_1_on_loss_or_change_and_0_on_addition(tmp_path, capsys):
    lost = _write(tmp_path, S2, "lost", {DOC: lambda r: _remove(_one(r, "rPrChange"))})
    added = _write(tmp_path, S2, "added", {DOC: _add_paragraph})
    assert oracle.summary(oracle.compare(S2, added)) == {"paragraph": (0, 1, 0),
                                                         "paragraph_current": (0, 1, 0)}
    assert oracle.main(["compare", str(S2), str(lost)]) == 1
    assert oracle.main(["compare", str(SOURCES / "review-a.docx"), str(S2)]) == 1
    assert oracle.main(["compare", str(S2), str(added)]) == 0
    capsys.readouterr()


def test_the_oracle_does_not_import_the_checker():
    source = (ROOT / "research" / "review_history_oracle.py").read_text()
    assert "ooxml_integrity" not in source
