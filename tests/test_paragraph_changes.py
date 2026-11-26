"""FID014: paragraphs whose text an edit changed, so an expectation can name the result."""
from __future__ import annotations

import json

import pytest
from conftest import ROOT, needs_evidence, read_part, repack, run_cli

from ooxml_integrity import Expectation, Severity, compare, expect
from ooxml_integrity.paragraphs import ParagraphText, paragraph_views
from ooxml_integrity.policy import fingerprint
from ooxml_integrity.xmlutil import fromstring

BENCH = ROOT / "evidence/review-history-benchmark"
S2 = BENCH / "sources/word-review.docx"
ASKED = ("Fees are payable within forty-five days of receipt of a valid invoice. "
         "The Client may withhold disputed sum.")


def _changes(source, edited):
    return [f for f in compare(source, edited) if f.code == "FID014"]


@needs_evidence
def test_the_requested_edit_reads_as_the_task_asks():
    # The reference edit inside Reviewer A's pending insertion.
    [f] = _changes(S2, BENCH / "captures/reference-1/K4-S2-plain.docx")
    assert f.severity is Severity.INFO
    assert (f.extra["story"], f.extra["change"]) == ("document", "changed")
    assert f.extra["before"] == ("Fees are payable within forty-five days of receipt of a "
                                 "valid invoice. The Client may withhold disputed amount.")
    assert f.extra["after"] == ASKED
    # With the tracked changes rejected the paragraph is still the source's.
    assert f.extra["after_original"] == f.extra["before_original"] == (
        "Fees are payable within thirty days of receipt of a valid invoice.")


@needs_evidence
def test_an_edit_of_the_wrong_span_fails_the_expected_text():
    asked = Expectation("FID014", {"story": "document", "after": ASKED},
                        reason="the task asks for this paragraph")
    right = compare(S2, BENCH / "captures/reference-1/K4-S2-plain.docx")
    kept, matched = expect(right, [asked])
    assert [f.code for f, _ in matched] == ["FID014"] and "EXP001" not in {f.code for f in kept}
    # docx-cli 0.26.0 rewrote the start of the insertion instead; nothing was
    # lost, so no other rule reports it.
    wrong = compare(S2, BENCH / "captures/docx-cli-5/K4-S2-plain.docx")
    assert {f.severity for f in wrong} == {Severity.INFO}
    kept, matched = expect(wrong, [asked])
    assert matched == [] and "EXP001" in {f.code for f in kept}
    [f] = [f for f in wrong if f.code == "FID014"]
    assert f.extra["after"].endswith("invoice.disputed sum withhold disputed amount.")


def _with_document(base_docx, tmp_path, name, old, new):
    document = read_part(base_docx, "word/document.xml")
    assert document.count(old) == 1
    return repack(base_docx, tmp_path / name,
                  {"word/document.xml": document.replace(old, new).encode()})


def _payment_box(base_docx, tmp_path, name, choice, fallback):
    paragraph = "<w:p><w:r><w:t>Payment due in {} days.</w:t></w:r></w:p>"
    wps = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
    box = f"""
      <w:p><w:r><mc:AlternateContent
        xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
        xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
        xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
        xmlns:wps="{wps}" xmlns:v="urn:schemas-microsoft-com:vml">
        <mc:Choice Requires="wps"><w:drawing><wp:inline>
          <wp:extent cx="914400" cy="457200"/><wp:docPr id="42" name="Payment terms"/>
          <a:graphic><a:graphicData uri="{wps}"><wps:wsp>
            <wps:cNvSpPr txBox="1"/><wps:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></wps:spPr>
            <wps:txbx><w:txbxContent>{paragraph.format(choice)}</w:txbxContent></wps:txbx>
            <wps:bodyPr/>
          </wps:wsp></a:graphicData></a:graphic>
        </wp:inline></w:drawing></mc:Choice>
        <mc:Fallback><w:pict><v:rect style="width:72pt;height:36pt"><v:textbox>
          <w:txbxContent>{paragraph.format(fallback)}</w:txbxContent>
        </v:textbox></v:rect></w:pict></mc:Fallback>
      </mc:AlternateContent></w:r></w:p>"""
    return _with_document(base_docx, tmp_path, name, "<w:body>", "<w:body>" + box)


@pytest.mark.parametrize("choice, fallback", [(30, 60), (60, 30)],
                         ids=["fallback-only", "choice-only"])
def test_expected_payment_term_in_a_word_text_box(base_docx, tmp_path, choice, fallback):
    source = _payment_box(base_docx, tmp_path, "source.docx", 30, 30)
    edited = _payment_box(base_docx, tmp_path, "edited.docx", choice, fallback)
    result = run_cli("check", str(edited), "--against", str(source), "--no-config", "--json",
                     "--expect", "FID014:story=document,before=Payment due in 30 days.,"
                     "after=Payment due in 60 days.")
    entry = json.loads(result.stdout)["files"][0]
    if choice == 60:
        assert result.returncode == 0, result.stdout + result.stderr
        assert [f["code"] for f in entry["expected"]] == ["FID014"]
        assert entry["findings"] == []
    else:
        assert result.returncode == 1, result.stdout + result.stderr
        assert entry["expected"] == []
        assert [f["code"] for f in entry["findings"]] == ["EXP001"]


def test_text_box_fallback_does_not_shift_later_paragraph_numbers(base_docx, tmp_path):
    source = _payment_box(base_docx, tmp_path, "source.docx", 30, 30)
    edited = _with_document(source, tmp_path, "edited.docx", "<w:t>Master Services Agreement</w:t>",
                            "<w:t>Revised Agreement</w:t>")
    [changed] = _changes(source, edited)
    # Paragraph 1 holds the drawing; paragraph 2 holds the text in the box.
    assert (changed.where, changed.extra["after"]) == ("document/p3", "Revised Agreement")


def test_inline_alternate_content_in_both_review_views():
    paragraph = fromstring(b'''
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
             xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
          <w:r><w:t xml:space="preserve">Net </w:t></w:r>
          <mc:AlternateContent>
            <mc:Choice Requires="w14">
              <w:del w:id="1" w:author="Editor"><w:r><w:delText>30</w:delText></w:r></w:del>
              <w:ins w:id="2" w:author="Editor"><w:r><w:t>60</w:t></w:r></w:ins>
            </mc:Choice>
            <mc:Fallback><w:r><w:t>45</w:t></w:r></mc:Fallback>
          </mc:AlternateContent>
          <w:r><w:t xml:space="preserve"> days</w:t></w:r>
        </w:p>''')
    assert paragraph_views(paragraph) == [ParagraphText("Net 60 days", "Net 30 days")]


def test_spacing_and_empty_paragraphs_are_not_text_changes(base_docx, tmp_path):
    title = "<w:t>Master Services Agreement</w:t>"
    spaced = _with_document(base_docx, tmp_path, "spaced.docx", title,
                            '<w:t xml:space="preserve">Master  Services Agreement </w:t>')
    assert _changes(base_docx, spaced) == []
    blank = _with_document(base_docx, tmp_path, "blank.docx", "<w:body>",
                           "<w:body><w:p/><w:p><w:r><w:t> </w:t></w:r></w:p>")
    assert _changes(base_docx, blank) == []


def test_added_and_removed_paragraphs_are_numbered_as_they_stand(base_docx, tmp_path):
    added = _with_document(base_docx, tmp_path, "added.docx", "<w:body>",
                           "<w:body><w:p><w:r><w:t>A new opening line</w:t></w:r></w:p>")
    [f] = _changes(base_docx, added)
    assert (f.extra["change"], f.where, f.extra["after"]) == ("added", "document/p1",
                                                               "A new opening line")
    [f] = _changes(added, base_docx)
    assert (f.extra["change"], f.where, f.extra["before"]) == ("removed", "document/p1 (source)",
                                                               "A new opening line")


@needs_evidence
def test_the_baseline_identity_holds_no_text():
    [f] = _changes(S2, BENCH / "captures/reference-1/K4-S2-plain.docx")
    key = fingerprint("out.docx", f)
    assert "paragraph-change-sha256=" in key
    assert "disputed" not in key and "Fees" not in key
