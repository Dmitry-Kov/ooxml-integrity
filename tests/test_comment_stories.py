"""Comments anchored outside the main story.

A comment's range and reference may be written in a header, footer, footnote
or endnote that the main part relates. Such a comment is not orphaned; a range
still pairs within one story, and an unrelated part is not a story.
"""
from __future__ import annotations

import json
import sys
import zipfile

from conftest import ROOT, read_part, repack

from ooxml_integrity import check
from ooxml_integrity.comments import story_parts
from ooxml_integrity.coverage import coverage_for

sys.path.insert(0, str(ROOT))
from research import comment_story_evidence as evidence  # noqa: E402

HEADER = "word/header1.xml"
DOC = "word/document.xml"
SOURCE = evidence.EVIDENCE / "sources" / "header-anchor.docx"
LOST = evidence.EVIDENCE / "outputs" / "header-anchor-lost-anchor.docx"
START = '<w:commentRangeStart w:id="1"/>'


def _findings(path):
    return sorted((f.code, f.part) for f in check(path))


def _comments_coverage(path):
    return next(i for i in coverage_for(path, []).items if i.id == "docx.comments")


def test_labelled_pairs_match_their_labels():
    totals = evidence.evaluate()["totals"]
    assert totals == {"pairs": 4, "tp": 3, "fp": 0, "fn": 0, "label_mismatches": 0}


def test_labelled_pairs_rebuild_byte_identically(tmp_path):
    manifest = evidence.build(tmp_path)
    assert manifest == json.loads(evidence.MANIFEST.read_text())
    for built in sorted(tmp_path.rglob("*.docx")):
        relative = built.relative_to(tmp_path)
        assert built.read_bytes() == (evidence.EVIDENCE / relative).read_bytes(), relative


def test_story_references_count_in_comment_coverage():
    assert _comments_coverage(SOURCE).reason == (
        "evaluated 2 reference(s) and 2 definition(s)")


def test_a_range_split_across_stories_is_still_malformed(tmp_path):
    document = read_part(SOURCE, DOC)
    assert document.count("<w:r><w:t>EUR 12,000</w:t></w:r>") == 1
    split = repack(SOURCE, tmp_path / "split.docx", {
        HEADER: read_part(SOURCE, HEADER).replace(START, "").encode(),
        DOC: document.replace("<w:r><w:t>EUR 12,000</w:t></w:r>",
                              START + "<w:r><w:t>EUR 12,000</w:t></w:r>").encode(),
    })
    assert _findings(split) == [
        ("CMT001", DOC), ("CMT002", HEADER), ("CMT003", DOC)]


def test_an_undefined_reference_in_a_header_names_the_header(tmp_path):
    header = read_part(SOURCE, HEADER).replace(
        "</w:p>", '<w:r><w:commentReference w:id="9"/></w:r></w:p>', 1)
    out = repack(SOURCE, tmp_path / "undefined.docx", {HEADER: header.encode()})
    assert _findings(out) == [("CMT004", HEADER)]


def test_an_unrelated_part_with_anchors_is_not_a_story(tmp_path):
    out = repack(LOST, tmp_path / "unrelated.docx", {
        "word/header9.xml": read_part(SOURCE, HEADER).encode()})
    assert _findings(out) == [("CMT005", "word/comments.xml")]


def test_an_unreadable_story_leaves_orphans_undecided(tmp_path):
    out = repack(SOURCE, tmp_path / "unreadable.docx", {HEADER: b"<w:hdr"})
    assert [code for code, _ in _findings(out)] == ["XML001"]
    coverage = _comments_coverage(out)
    assert coverage.status.value == "skipped"
    assert coverage.reason.startswith(HEADER + " could not be safely parsed")


def test_story_parts_follow_the_main_part_relationships():
    with zipfile.ZipFile(SOURCE) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    assert story_parts(parts, DOC) == [
        DOC, "word/footnotes.xml", "word/header1.xml", "word/footer1.xml"]
