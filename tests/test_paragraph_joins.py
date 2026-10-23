"""A paragraph boundary in a story, comment or note reads as a space.

The loss rules compare the words of a comment, a note or a header story, not
its paragraphs. Through 0.8.1 a comment, footnote or endnote body joined its
paragraphs with nothing between them: "First." and "Second." read
"First.Second.", and an edit that reflowed them into one paragraph, "First.
Second.", was reported as a lost comment (FID004, an error) although no word
changed. A header read its paragraphs apart, but the paragraphs of a text box
in it were read twice, once glued to the paragraph holding the box, so the
same reflow inside a text box changed the story (FID007). Which paragraph a
word stands in is FID014's to report, as information.
"""
from __future__ import annotations

from lxml import etree

from conftest import ROOT, read_part, repack
from ooxml_integrity import Severity, compare
from ooxml_integrity.fidelity import _bodies, _story_text, note_revision_inventory

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
COMMENTS = "word/comments.xml"
FOOTNOTES = "word/footnotes.xml"
HEADER = "word/header1.xml"
COMMENT = "<w:p><w:r><w:t>Confirm this figure against the source table before circulation.</w:t></w:r></w:p>"
FOOTNOTE = "<w:r><w:t xml:space=\"preserve\"> Measured across the reference corpus, Q2 2026.</w:t></w:r></w:p>"


def paragraphs(*texts: str) -> str:
    return "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{t}</w:t></w:r></w:p>" for t in texts)


def with_comment(tmp_docx, path, *texts):
    comments = read_part(tmp_docx, COMMENTS)
    assert COMMENT in comments
    return repack(tmp_docx, path, {COMMENTS: comments.replace(COMMENT, paragraphs(*texts)).encode()})


def with_footnote(tmp_docx, path, first, *rest):
    footnotes = read_part(tmp_docx, FOOTNOTES)
    assert FOOTNOTE in footnotes
    text = f"<w:r><w:t xml:space=\"preserve\"> {first}</w:t></w:r></w:p>" + paragraphs(*rest)
    return repack(tmp_docx, path, {FOOTNOTES: footnotes.replace(FOOTNOTE, text).encode()})


def with_header(tmp_docx, path, body):
    header = read_part(tmp_docx, HEADER)
    start = header.index("<w:p>")
    end = header.index("</w:hdr>")
    return repack(tmp_docx, path, {HEADER: (header[:start] + body + header[end:]).encode()})


def text_box(*texts: str) -> str:
    """A paragraph holding a VML text box, as Word writes one in a header."""
    return ('<w:p><w:r><w:t>Letterhead</w:t></w:r>'
            '<w:r><w:pict><v:shape xmlns:v="urn:schemas-microsoft-com:vml" style="width:200pt;height:40pt">'
            f'<v:textbox><w:txbxContent>{paragraphs(*texts)}</w:txbxContent></v:textbox>'
            '</v:shape></w:pict></w:r><w:r><w:t>Office</w:t></w:r></w:p>')


def errors(findings):
    return [(f.code, f.extra.get("body")) for f in findings if f.severity is Severity.ERROR]


def test_a_two_paragraph_comment_reflowed_into_one_is_not_lost(tmp_docx, tmp_path):
    source = with_comment(tmp_docx, tmp_path / "source.docx",
                          "Confirm this figure.", "Check the source table.")
    reflowed = with_comment(tmp_docx, tmp_path / "reflowed.docx",
                            "Confirm this figure. Check the source table.")
    assert compare(source, reflowed) == []
    assert compare(reflowed, source) == []


def test_a_changed_word_in_a_reflowed_comment_is_still_a_loss(tmp_docx, tmp_path):
    source = with_comment(tmp_docx, tmp_path / "source.docx",
                          "Confirm this figure.", "Check the source table.")
    changed = with_comment(tmp_docx, tmp_path / "changed.docx",
                           "Confirm this figure. Check the target table.")
    assert errors(compare(source, changed)) == [
        ("FID004", "Confirm this figure. Check the source table.")]


def test_two_paragraphs_read_as_two_words_not_one(tmp_docx, tmp_path):
    """Joining the paragraphs "Confirm this" and "figure." into "Confirm
    thisfigure." joins two words: the comment the reviewer wrote is gone."""
    source = with_comment(tmp_docx, tmp_path / "source.docx", "Confirm this", "figure.")
    joined = with_comment(tmp_docx, tmp_path / "joined.docx", "Confirm thisfigure.")
    spaced = with_comment(tmp_docx, tmp_path / "spaced.docx", "Confirm this figure.")
    assert errors(compare(source, joined)) == [("FID004", "Confirm this figure.")]
    assert compare(source, spaced) == []


def test_a_two_paragraph_footnote_reflowed_into_one_is_not_lost(tmp_docx, tmp_path):
    source = with_footnote(tmp_docx, tmp_path / "source.docx",
                           "Measured across the reference corpus,", "Q2 2026.")
    reflowed = with_footnote(tmp_docx, tmp_path / "reflowed.docx",
                             "Measured across the reference corpus, Q2 2026.")
    findings = compare(source, reflowed)
    assert errors(findings) == []
    # Which paragraph the words stand in is still reported, as information.
    assert {(f.code, f.severity) for f in findings} == {("FID014", Severity.INFO)}


def test_a_changed_word_in_a_reflowed_footnote_is_still_a_loss(tmp_docx, tmp_path):
    source = with_footnote(tmp_docx, tmp_path / "source.docx",
                           "Measured across the reference corpus,", "Q2 2026.")
    changed = with_footnote(tmp_docx, tmp_path / "changed.docx",
                            "Measured across the reference corpus, Q3 2026.")
    assert errors(compare(source, changed)) == [
        ("FID005", "Measured across the reference corpus, Q2 2026.")]


def test_a_two_paragraph_header_reflowed_into_one_is_not_a_changed_story(tmp_docx, tmp_path):
    source = with_header(tmp_docx, tmp_path / "source.docx",
                         paragraphs("Reference Agreement", "Draft 7"))
    reflowed = with_header(tmp_docx, tmp_path / "reflowed.docx",
                           paragraphs("Reference Agreement Draft 7"))
    changed = with_header(tmp_docx, tmp_path / "changed.docx",
                          paragraphs("Reference Agreement Draft 8"))
    assert errors(compare(source, reflowed)) == []
    assert errors(compare(source, changed)) == [("FID007", "Reference Agreement Draft 7")]


def test_a_text_box_in_a_header_is_read_once_apart_from_its_paragraph(tmp_docx, tmp_path):
    """0.8.1 read the box's paragraphs into the paragraph holding the box,
    glued ("LetterheadLine 1Line 2Office"), and then once more on their own."""
    source = with_header(tmp_docx, tmp_path / "source.docx", text_box("Line 1", "Line 2"))
    reflowed = with_header(tmp_docx, tmp_path / "reflowed.docx", text_box("Line 1 Line 2"))
    changed = with_header(tmp_docx, tmp_path / "changed.docx", text_box("Line 1 Line 3"))
    assert _story_text(etree.fromstring(read_part(source, HEADER).encode())) == (
        "Letterhead Line 1 Line 2 Office")
    assert errors(compare(source, reflowed)) == []
    assert errors(compare(source, changed)) == [("FID007", "Letterhead Line 1 Line 2 Office")]


def _part(kind: str, body: str) -> bytes:
    return f'<w:{kind}s xmlns:w="{W_NS}"><w:{kind} w:id="1">{body}</w:{kind}></w:{kind}s>'.encode()


def test_every_body_reader_reads_a_paragraph_boundary_as_a_space():
    two = paragraphs("First.", "Second.")
    for kind in ("comment", "footnote", "endnote"):
        part = f"word/{kind}s.xml"
        [(body, original, _)], _ = _bodies({part: _part(kind, two)}, part, kind)
        assert body == original == "First. Second."
    for kind in ("footnote", "endnote"):
        part = f"word/{kind}s.xml"
        assert list(note_revision_inventory({part: _part(kind, two)}).notes) == [
            (part, "First. Second.")]


def test_a_reflowed_note_keeps_its_tracked_revision_comparable(tmp_docx, tmp_path):
    """FID010 groups notes by text. A reflowed note read differently, so its
    revisions were skipped as "changed text"; now they are compared."""
    insertion = ('<w:ins w:id="7" w:author="Reviewer" w:date="2026-10-01T00:00:00Z">'
                 '<w:r><w:t>Q2 2026.</w:t></w:r></w:ins>')
    footnotes = read_part(tmp_docx, FOOTNOTES)

    def note(path, body):
        return repack(tmp_docx, path, {FOOTNOTES: footnotes.replace(FOOTNOTE, body).encode()})

    source = note(tmp_path / "source.docx",
                  '<w:r><w:t xml:space="preserve"> Measured across the reference corpus,</w:t></w:r>'
                  f'</w:p><w:p>{insertion}</w:p>')
    reflowed = note(tmp_path / "reflowed.docx",
                    '<w:r><w:t xml:space="preserve"> Measured across the reference corpus, </w:t></w:r>'
                    f'{insertion}</w:p>')
    accepted = note(tmp_path / "accepted.docx",
                    '<w:r><w:t xml:space="preserve"> Measured across the reference corpus, </w:t></w:r>'
                    '<w:r><w:t>Q2 2026.</w:t></w:r></w:p>')
    assert errors(compare(source, reflowed)) == []
    assert [(f.code, f.extra["tag"]) for f in compare(source, accepted)
            if f.code == "FID010"] == [("FID010", "ins")]


def test_story_text_reads_the_same_with_or_without_a_paragraph_holding_nothing():
    root = etree.fromstring(f'<w:hdr xmlns:w="{W_NS}">{paragraphs("A")}<w:p/>{paragraphs("B")}</w:hdr>')
    assert _story_text(root) == "A B"


def test_fix_quotes_a_reply_of_two_paragraphs_as_the_loss_rules_read_it(tmp_path):
    from ooxml_integrity.fix import fix
    source = ROOT / "evidence/review-history-benchmark/captures/docx-mcp-3/K5-S2-comment.docx"
    reply = '<w:p w14:paraId="1C4295B9" w14:textId="77777777">'
    comments = read_part(source, COMMENTS)
    assert comments.count(reply) == 1
    # Word links a reply through the paraId of its last paragraph.
    variant = repack(source, tmp_path / "two-paragraph-reply.docx", {COMMENTS: comments.replace(
        reply, f"{paragraphs('See clause 4.')}{reply}").encode()})
    report = fix(variant, tmp_path / "fixed.docx")
    assert report.status == "repaired"
    assert '("See clause 4. Schedule 1 now defines it.")' in report.repaired[0].detail
