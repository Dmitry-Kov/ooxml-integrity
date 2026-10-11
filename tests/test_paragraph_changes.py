"""FID014: paragraphs whose text an edit changed, so an expectation can name the result."""
from __future__ import annotations

from conftest import ROOT, read_part, repack

from ooxml_integrity import Expectation, Severity, compare, expect
from ooxml_integrity.policy import fingerprint

BENCH = ROOT / "evidence/review-history-benchmark"
S2 = BENCH / "sources/word-review.docx"
ASKED = ("Fees are payable within forty-five days of receipt of a valid invoice. "
         "The Client may withhold disputed sum.")


def _changes(source, edited):
    return [f for f in compare(source, edited) if f.code == "FID014"]


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


def test_the_baseline_identity_holds_no_text():
    [f] = _changes(S2, BENCH / "captures/reference-1/K4-S2-plain.docx")
    key = fingerprint("out.docx", f)
    assert "paragraph-change-sha256=" in key
    assert "disputed" not in key and "Fees" not in key
