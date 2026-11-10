"""One comment, one range and one reference (CMT007).

The closed python-docx PR #1605 kept comment anchors when `Paragraph.text` is
assigned by marking the new run again for every `commentRangeStart` the
paragraph had. For a comment spanning two paragraphs, setting the first wrote a
second `commentRangeEnd` and `commentReference` while the second paragraph
kept its own. Every start still had an end and a reference, so `CMT001` to
`CMT003` passed, and against the source only `FID002` INFO counted one more
anchor.
"""
from __future__ import annotations

import json

import pytest
from conftest import ROOT, read_part, repack, run_cli

from ooxml_integrity import Severity, check, compare, introduced
from ooxml_integrity.cli import EXIT_FINDINGS
from ooxml_integrity.introduced import REASON

DOC = "word/document.xml"
HEADER = "word/header1.xml"
HEADER_SOURCE = ROOT / "evidence" / "docx-comment-stories" / "sources" / "header-anchor.docx"
START = '<w:commentRangeStart w:id="1"/>'
END = '<w:commentRangeEnd w:id="1"/>'
REFERENCE = '<w:r><w:commentReference w:id="1"/></w:r>'
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"


def _findings(path):
    return [(f.code, f.part) for f in check(path)]


def _messages(path):
    return [f.message for f in check(path) if f.code == "CMT007"]


def _before_section(doc: str, paragraph: str) -> bytes:
    """The body with one more paragraph before its final w:sectPr."""
    assert doc.count("<w:sectPr") == 1
    return doc.replace("<w:sectPr", paragraph + "<w:sectPr").encode()


def _pr1605_edit(tmp_path):
    """A comment over two paragraphs, then paragraph 0's text set as #1605 did."""
    docx = pytest.importorskip("docx")
    if not hasattr(docx.document.Document, "add_comment"):
        pytest.skip("python-docx before 1.2 cannot add comments")
    from docx.oxml.ns import qn

    document = docx.Document()
    first = document.add_paragraph("First paragraph of the clause.")
    second = document.add_paragraph("Second paragraph of the clause.")
    document.add_comment(runs=[first.runs[0], second.runs[0]],
                         text="Spans both", author="Reviewer")
    source = tmp_path / "span.docx"
    document.save(source)

    document = docx.Document(source)
    paragraph = document.paragraphs[0]
    ids = [int(e.get(qn("w:id")))
           for e in paragraph._p.iter(qn("w:commentRangeStart"))]
    paragraph.clear()
    run = paragraph.add_run("First paragraph of the clause, reworded.")
    for i in ids:
        run.mark_comment_range(run, i)
    edited = tmp_path / "edited.docx"
    document.save(edited)
    return source, edited


def test_pr1605_setter_on_a_spanning_comment_is_an_error(tmp_path):
    source, edited = _pr1605_edit(tmp_path)
    assert not [f for f in check(source) if f.code.startswith("CMT")]
    found = [f for f in check(edited) if f.code.startswith("CMT")]
    assert [(f.code, f.severity, f.part) for f in found] == [
        ("CMT007", Severity.ERROR, DOC)]
    assert found[0].message == (
        "comment id=0 is marked more than once: 2 commentRangeEnd, "
        "2 commentReference - a comment has one range and one reference, "
        "so its anchor is ambiguous")


def test_pr1605_setter_fails_the_default_gate_against_its_source(tmp_path):
    source, edited = _pr1605_edit(tmp_path)
    result = run_cli("check", str(edited), "--against", str(source),
                     "--no-config", "--json")
    assert result.returncode == EXIT_FINDINGS, result.stdout + result.stderr
    codes = {f["code"] for f in json.loads(result.stdout)["files"][0]["findings"]}
    assert {"CMT007", "FID002"} <= codes


def _introduced(source, edited):
    """(CMT007 messages --introduced reports, [(set aside, why)])."""
    new, inherited = introduced(check(edited) + compare(source, edited), source)
    return ([f.message for f in new if f.code == "CMT007"],
            [(f.message, why) for f, why in inherited if f.code == "CMT007"])


def _references(tmp_docx, target, times, edit=lambda doc: doc):
    doc = read_part(tmp_docx, DOC)
    assert doc.count(REFERENCE) == 1
    return repack(tmp_docx, target,
                  {DOC: edit(doc.replace(REFERENCE, REFERENCE * times)).encode()})


def test_introduced_keeps_the_pr1605_repeat(tmp_path):
    source, edited = _pr1605_edit(tmp_path)
    new, inherited = _introduced(source, edited)
    assert len(new) == 1 and inherited == []


def test_introduced_sets_aside_a_repeat_the_source_had(tmp_docx, tmp_path):
    source = _references(tmp_docx, tmp_path / "source.docx", 2)
    assert read_part(source, DOC).count("governs") == 1
    edited = _references(tmp_docx, tmp_path / "edited.docx", 2,
                         lambda doc: doc.replace("governs", "covers"))
    new, inherited = _introduced(source, edited)
    assert new == []
    assert inherited == [(_messages(source)[0], REASON)]


def test_introduced_reports_a_repeat_the_edit_made_worse(tmp_docx, tmp_path):
    source = _references(tmp_docx, tmp_path / "source.docx", 2)
    edited = _references(tmp_docx, tmp_path / "edited.docx", 3)
    new, inherited = _introduced(source, edited)
    assert [m.split(" - ")[0] for m in new] == [
        "comment id=1 is marked more than once: 3 commentReference"]
    assert inherited == []


@pytest.mark.parametrize("marker,kind", [
    (START, "commentRangeStart"),
    (END, "commentRangeEnd"),
    (REFERENCE, "commentReference"),
], ids=["start", "end", "reference"])
def test_each_marker_written_twice_is_reported(tmp_docx, tmp_path, marker, kind):
    doc = read_part(tmp_docx, DOC)
    assert doc.count(marker) == 1
    out = repack(tmp_docx, tmp_path / "twice.docx",
                 {DOC: doc.replace(marker, marker * 2).encode()})
    assert _findings(out) == [("CMT007", DOC)]
    assert _messages(out) == [
        f"comment id=1 is marked more than once: 2 {kind} - a comment has one "
        "range and one reference, so its anchor is ambiguous"]


def test_a_whole_second_anchor_lists_every_marker(tmp_docx, tmp_path):
    doc = read_part(tmp_docx, DOC)
    anchor = START + "<w:r><w:t>EUR 12,000</w:t></w:r>" + END
    assert doc.count(anchor) == 1
    out = repack(tmp_docx, tmp_path / "again.docx",
                 {DOC: _before_section(doc, f"<w:p>{anchor}{REFERENCE}</w:p>")})
    assert _findings(out) == [("CMT007", DOC)]
    assert _messages(out)[0].startswith(
        "comment id=1 is marked more than once: 2 commentRangeStart, "
        "2 commentRangeEnd, 2 commentReference - ")


def test_a_repeat_in_a_header_names_the_header(tmp_path):
    assert check(HEADER_SOURCE) == []
    header = read_part(HEADER_SOURCE, HEADER)
    assert header.count(REFERENCE) == 1
    out = repack(HEADER_SOURCE, tmp_path / "header.docx",
                 {HEADER: header.replace(REFERENCE, REFERENCE * 2).encode()})
    assert _findings(out) == [("CMT007", HEADER)]


def _text_box(choice: str, fallback: str) -> str:
    """A paragraph holding a text box written as Word writes one: twice."""
    return (
        f'<w:p><w:r><mc:AlternateContent xmlns:mc="{MC}" xmlns:wps="{WPS}" '
        'xmlns:v="urn:schemas-microsoft-com:vml">'
        f'<mc:Choice Requires="wps"><wps:txbx><w:txbxContent>{choice}'
        '</w:txbxContent></wps:txbx></mc:Choice>'
        '<mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent>'
        f'{fallback}</w:txbxContent></v:textbox></v:shape></w:pict></mc:Fallback>'
        '</mc:AlternateContent></w:r></w:p>')


def _boxed_comment(tmp_docx, tmp_path, choice_reference=REFERENCE):
    doc = read_part(tmp_docx, DOC)
    for marker in (START, END, REFERENCE):
        assert doc.count(marker) == 1
        doc = doc.replace(marker, "")
    boxed = f"<w:p>{START}<w:r><w:t>Boxed</w:t></w:r>{END}{{}}</w:p>"
    box = _text_box(boxed.format(choice_reference), boxed.format(REFERENCE))
    return repack(tmp_docx, tmp_path / "box.docx", {DOC: _before_section(doc, box)})


def test_a_text_box_copy_in_the_fallback_is_not_a_second_anchor(tmp_docx, tmp_path):
    out = _boxed_comment(tmp_docx, tmp_path)
    assert read_part(out, DOC).count(START) == 2
    assert _findings(out) == []


def test_a_repeat_inside_one_branch_is_reported(tmp_docx, tmp_path):
    out = _boxed_comment(tmp_docx, tmp_path, choice_reference=REFERENCE * 2)
    assert _findings(out) == [("CMT007", DOC)]
    assert _messages(out)[0].startswith(
        "comment id=1 is marked more than once: 2 commentReference - ")
