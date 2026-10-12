"""Run content every text rule reads the same way (`runtext`).

A non-breaking hyphen is a visible "-", a soft hyphen shows nothing, a tab or
a break separates words, a symbol is its character code. FID014's paragraphs,
FID013's replacements and the story, comment and note bodies of the loss
rules read these alike, so a character one rule sees is not invisible to
another: `non` + `w:noBreakHyphen` + `compete` replaced by `noncompete` was no
change to FID014 in 0.8.0.
"""
from __future__ import annotations

import zipfile

from lxml import etree

from conftest import read_part, repack
from ooxml_integrity import compare
from ooxml_integrity.fidelity import _bodies, _story_text, note_revision_inventory
from ooxml_integrity.paragraphs import paragraph_text
from ooxml_integrity.replacements import replacements
from ooxml_integrity.runtext import shown

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"

#: Every character element once, between pieces of text.
RUN = ('<w:r><w:t>non</w:t><w:noBreakHyphen/><w:t>compete</w:t><w:softHyphen/><w:t>ly</w:t>'
       '<w:tab/><w:t>a</w:t><w:ptab w:relativeTo="margin" w:alignment="right" w:leader="none"/>'
       '<w:t>b</w:t><w:br/><w:t>c</w:t><w:cr/><w:t>d</w:t>'
       '<w:sym w:font="Wingdings" w:char="F0FC"/></w:r>')
READ = "non-competely a b c d"


def xml(text: str):
    return etree.fromstring(text.replace("<w:root>", f'<w:root xmlns:w="{W_NS}">'))


def docx(path, body):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   f'<Override PartName="/word/document.xml" ContentType="{MAIN}"/></Types>')
        z.writestr("_rels/.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                   'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml",
                   f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
    return path


def test_each_character_element_reads_as_the_standard_shows_it():
    root = xml(f"<w:root><w:p>{RUN}</w:p></w:root>")
    [paragraph] = root.iter(W + "p")
    assert paragraph_text(paragraph, "current") == READ


def test_a_tab_stop_and_a_symbol_without_a_code_are_not_text():
    root = xml('<w:root><w:p><w:pPr><w:tabs><w:tab w:val="left" w:pos="720"/></w:tabs></w:pPr>'
               '<w:r><w:sym w:font="Symbol" w:char="zz"/><w:sym w:font="Symbol"/>'
               '<w:sym w:font="Symbol" w:char="D800"/><w:tab/></w:r></w:p></w:root>')
    stop = next(root.iter(W + "tabs"))[0]
    assert shown(stop) is None
    assert [shown(n) for n in root.iter(W + "sym")] == ["", "", ""]
    assert shown(next(root.iter(W + "r"))[-1]) == "\t"


def test_story_comment_and_note_bodies_read_what_paragraphs_read():
    header = xml(f"<w:root><w:p>{RUN}</w:p></w:root>")
    assert _story_text(header) == _story_text(header, original=True) == READ
    comments = (f'<w:comments xmlns:w="{W_NS}"><w:comment w:id="1" w:author="A">'
                f'<w:p>{RUN}</w:p></w:comment></w:comments>').encode()
    [(body, original, _)], _ = _bodies({"word/comments.xml": comments}, "word/comments.xml",
                                       "comment")
    assert body == original == READ
    notes = (f'<w:footnotes xmlns:w="{W_NS}"><w:footnote w:id="1">'
             f'<w:p>{RUN}</w:p></w:footnote></w:footnotes>').encode()
    assert list(note_revision_inventory({"word/footnotes.xml": notes}).notes) == [
        ("word/footnotes.xml", READ)]


def test_a_deleted_tab_or_hyphen_is_read_only_with_the_deletion_rejected():
    root = xml('<w:root><w:p><w:r><w:t>non</w:t></w:r>'
               '<w:del w:id="1" w:author="A" w:date="2026-10-01T00:00:00Z">'
               '<w:r><w:noBreakHyphen/><w:tab/></w:r></w:del>'
               '<w:ins w:id="2" w:author="A" w:date="2026-10-01T00:00:00Z">'
               '<w:r><w:sym w:font="Wingdings" w:char="F0FC"/></w:r></w:ins>'
               '<w:r><w:t>compete</w:t></w:r></w:p></w:root>')
    [paragraph] = root.iter(W + "p")
    assert paragraph_text(paragraph, "current") == "noncompete"
    assert paragraph_text(paragraph, "original") == "non- compete"
    assert _story_text(root) == "noncompete"
    assert _story_text(root, original=True) == "non- compete"


def test_a_hyphen_the_edit_removed_is_a_changed_paragraph(tmp_path):
    source = docx(tmp_path / "source.docx",
                  '<w:p><w:r><w:t>non</w:t><w:noBreakHyphen/>'
                  '<w:t>compete obligation</w:t></w:r></w:p>')
    joined = docx(tmp_path / "joined.docx",
                  "<w:p><w:r><w:t>noncompete obligation</w:t></w:r></w:p>")
    [f] = [f for f in compare(source, joined) if f.code == "FID014"]
    assert (f.extra["before"], f.extra["after"]) == ("non-compete obligation",
                                                     "noncompete obligation")
    # The same hyphen typed as U+002D reads the same: no change of text.
    typed = docx(tmp_path / "typed.docx",
                 "<w:p><w:r><w:t>non-compete obligation</w:t></w:r></w:p>")
    assert [f for f in compare(source, typed) if f.code == "FID014"] == []
    # A soft hyphen shows nothing unless the line breaks at it.
    soft = docx(tmp_path / "soft.docx",
                '<w:p><w:r><w:t>non</w:t><w:softHyphen/><w:t>compete obligation</w:t></w:r></w:p>')
    assert [f for f in compare(soft, joined) if f.code == "FID014"] == []


def test_a_replaced_symbol_is_a_changed_paragraph(tmp_path):
    def checkbox(code):
        return (f'<w:p><w:r><w:sym w:font="Wingdings" w:char="{code}"/>'
                '<w:t xml:space="preserve"> Approved</w:t></w:r></w:p>')
    [f] = [f for f in compare(docx(tmp_path / "a.docx", checkbox("F0A8")),
                              docx(tmp_path / "b.docx", checkbox("F0FE")))
           if f.code == "FID014"]
    assert (f.extra["before"], f.extra["after"]) == (" Approved", " Approved")


def test_a_hyphen_lost_in_a_comment_or_header_is_a_lost_body(base_docx, tmp_path):
    comment = "<w:t>Defined term must match the definitions schedule.</w:t>"
    hyphenated = "<w:t>Defined term must match the definitions</w:t><w:noBreakHyphen/><w:t>schedule.</w:t>"
    header = "<w:t>Reference Agreement - Draft 7</w:t>"
    source = repack(base_docx, tmp_path / "source.docx", {
        "word/comments.xml": read_part(base_docx, "word/comments.xml")
        .replace(comment, hyphenated).encode(),
        "word/header1.xml": read_part(base_docx, "word/header1.xml")
        .replace(header, "<w:t>Reference</w:t><w:noBreakHyphen/><w:t>Agreement</w:t>").encode(),
    })
    edited = repack(source, tmp_path / "edited.docx", {
        "word/comments.xml": read_part(source, "word/comments.xml")
        .replace("<w:noBreakHyphen/>", "").encode(),
        "word/header1.xml": read_part(source, "word/header1.xml")
        .replace("<w:noBreakHyphen/>", "").encode(),
    })
    found = {f.code: f for f in compare(source, edited)}
    assert found["FID004"].extra["body"] == "Defined term must match the definitions-schedule."
    assert found["FID007"].extra["body"] == "Reference-Agreement"


def test_replacement_words_are_separated_by_tabs_and_breaks_and_joined_by_hyphens():
    for separator in ("<w:tab/>", "<w:ptab/>", "<w:br/>", "<w:cr/>"):
        root = xml('<w:root><w:p><w:del w:id="1" w:author="A" w:date="d"><w:r>'
                   f'<w:delText>one</w:delText>{separator}<w:delText>non</w:delText>'
                   '<w:noBreakHyphen/><w:softHyphen/><w:delText>compete</w:delText></w:r></w:del>'
                   '<w:ins w:id="2" w:author="A" w:date="d"><w:r>'
                   f'<w:t>one</w:t>{separator}<w:t>non</w:t><w:noBreakHyphen/><w:t>competing</w:t>'
                   '</w:r></w:ins></w:p></w:root>')
        [item] = replacements(root)
        assert (item.deleted.split(), item.inserted.split()) == (
            ["one", "non-compete"], ["one", "non-competing"]), separator


def test_a_tab_between_a_deletion_and_an_insertion_separates_them():
    root = xml('<w:root><w:p><w:del w:id="1" w:author="A" w:date="d"><w:r>'
               '<w:delText>old</w:delText></w:r></w:del><w:r><w:tab/></w:r>'
               '<w:ins w:id="2" w:author="A" w:date="d"><w:r><w:t>new</w:t></w:r></w:ins>'
               '</w:p></w:root>')
    assert replacements(root) == []
    # A soft hyphen shows nothing, so it does not.
    root = xml('<w:root><w:p><w:del w:id="1" w:author="A" w:date="d"><w:r>'
               '<w:delText>old</w:delText></w:r></w:del><w:r><w:softHyphen/></w:r>'
               '<w:ins w:id="2" w:author="A" w:date="d"><w:r><w:t>new</w:t></w:r></w:ins>'
               '</w:p></w:root>')
    [item] = replacements(root)
    assert (item.deleted, item.inserted) == ("old", "new")
