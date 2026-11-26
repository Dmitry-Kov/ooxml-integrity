"""Losses in Word comments, notes and effective header/footer representations."""
from pathlib import Path

import pytest
from conftest import ROOT, needs_evidence, read_part, repack
from test_note_revisions import coverage as note_revision_coverage
from test_repeated_comment_markers import _text_box

from ooxml_integrity import Severity, compare

pytestmark = needs_evidence


WORD_REVIEW = ROOT / "evidence/review-history-benchmark/sources/word-review.docx"
TEXT = "<w:p><w:r><w:t>Inside the text box.</w:t></w:r></w:p>"
REFERENCE = '<w:p><w:r><w:commentReference w:id="2"/></w:r></w:p>'


def _with_boxes(destination: Path, part, element, *boxes):
    name = f"word/{part}.xml"
    xml = read_part(WORD_REVIEW, name)
    end = xml.rindex(f"</w:{element}>")
    replacement = xml[:end] + "".join(_text_box(primary, backup) for primary, backup in boxes) + xml[end:]
    return repack(WORD_REVIEW, destination, {name: replacement.encode()})


@pytest.mark.parametrize("part,element,contents,code", [
    ("header1", "hdr", TEXT, "FID007"),
    ("footer1", "ftr", REFERENCE, "FID008"),
    ("comments", "comment", TEXT, "FID004"),
    ("footnotes", "footnote", TEXT, "FID005"),
    ("endnotes", "endnote", TEXT, "FID006"),
], ids=["header-text", "footer-comment-reference", "comment-text", "footnote-text", "endnote-text"])
def test_story_compares_primary_and_fallback_separately(tmp_path, part, element, contents, code):
    primary = _with_boxes(tmp_path / "primary.docx", part, element, (contents, ""))
    backup = _with_boxes(tmp_path / "backup.docx", part, element, ("", contents))
    both = _with_boxes(tmp_path / "both.docx", part, element, (contents, contents))
    reserialized = _with_boxes(tmp_path / "resaved.docx", part, element,
                              (contents, contents.replace("<w:p>", "<w:p >")))
    assert not compare(both, reserialized)

    moved = [f for f in compare(primary, backup) if f.code == code]
    assert [f.severity for f in moved] == [Severity.ERROR]
    assert moved[0].extra.get("branch") != "fallback"

    (lost,) = compare(both, primary)
    assert (lost.code, lost.severity, lost.extra["branch"]) == (code, Severity.WARN, "fallback")


@pytest.mark.parametrize("part,element", [("header1", "hdr"), ("footnotes", "footnote")])
def test_reflowed_fallback_text_boxes_keep_the_same_story_text(tmp_path, part, element):
    first, second = TEXT.replace("Inside the text box.", "First."), TEXT.replace("Inside the text box.", "Second.")
    source = _with_boxes(tmp_path / "source.docx", part, element, (first, first), (second, second))
    reflowed = _with_boxes(tmp_path / "reflowed.docx", part, element, (first, first + second), (second, ""))
    assert not compare(source, reflowed)


def test_nested_backups_keep_their_order_in_a_header(tmp_path):
    first = TEXT.replace("Inside the text box.", "First.")
    second = TEXT.replace("Inside the text box.", "Second.")
    nested = _with_boxes(tmp_path / "nested.docx", "header1", "hdr",
                         (_text_box(first, first) + second, second))
    flat = _with_boxes(tmp_path / "flat.docx", "header1", "hdr",
                       (first, first), (second, second))
    assert compare(nested, flat) == []


@pytest.mark.parametrize("kind", ["ins", "del"])
def test_flattening_only_a_fallback_note_revision_warns(tmp_path, kind):
    revised = TEXT.replace("<w:r>", f'<w:{kind} w:id="4001" w:author="Reviewer"><w:r>').replace(
        "</w:r>", f"</w:r></w:{kind}>")
    if kind == "del":
        revised = revised.replace("w:t>", "w:delText>")
    source = _with_boxes(tmp_path / "source.docx", "footnotes", "footnote", (TEXT, revised))
    edited = _with_boxes(tmp_path / "edited.docx", "footnotes", "footnote", (TEXT, TEXT))
    control = _with_boxes(tmp_path / "resaved.docx", "footnotes", "footnote",
                          (TEXT, revised.replace('w:id="4001"', 'w:id="4002"')))
    assert not compare(source, control)
    (lost,) = compare(source, edited)
    assert (lost.code, lost.severity, lost.extra["tag"]) == ("FID010", Severity.WARN, kind)
    assert lost.extra["branch"] == "fallback"
    assert note_revision_coverage(source, edited).count == note_revision_coverage(WORD_REVIEW, WORD_REVIEW).count + 1


def test_loss_of_a_whole_fallback_comment_definition_is_a_warning(tmp_path):
    part = "word/comments.xml"
    xml = read_part(WORD_REVIEW, part)
    duplicate = ('<mc:AlternateContent><mc:Choice Requires="w14"/><mc:Fallback>'
                 f'<w:comment w:id="923">{TEXT}</w:comment></mc:Fallback></mc:AlternateContent>')
    source = repack(WORD_REVIEW, tmp_path / "with-fallback.docx", {
        part: xml.replace("</w:comments>", duplicate + "</w:comments>").encode(),
    })
    (lost,) = compare(source, WORD_REVIEW)
    assert (lost.code, lost.severity, lost.extra["branch"]) == ("FID004", Severity.WARN, "fallback")
