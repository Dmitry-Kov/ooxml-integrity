"""FID017: two unchanged review notes trade their places in a contract."""
from copy import deepcopy
import json
import re

from lxml import etree
import pytest

from conftest import read_part, repack, run_cli
from ooxml_integrity import compare
from ooxml_integrity.comments import W
from ooxml_integrity.xmlutil import fromstring

DOC = "word/document.xml"
COMMENTS = "word/comments.xml"
ID = W + "id"
MARKERS = tuple(W + name for name in ("commentRangeStart", "commentRangeEnd", "commentReference"))


def _root(path, part):
    return fromstring(read_part(path, part).encode())


def _swap(source, output, *, renumber_definitions=False):
    # Only comment IDs change. Footnote and revision IDs in this fixture
    # also include 1 and 2 and must stay attached to their own constructs.
    swap = {"1": "2", "2": "1"}
    doc = _root(source, DOC)
    for marker in doc.iter(*MARKERS):
        marker.set(ID, swap[marker.get(ID)])
    edits = {DOC: etree.tostring(doc)}
    if renumber_definitions:
        comments = _root(source, COMMENTS)
        for comment in comments.findall(W + "comment"):
            comment.set(ID, swap[comment.get(ID)])
        edits[COMMENTS] = etree.tostring(comments)
    return repack(source, output, edits)


def _insert_paragraph(source, output, text):
    doc = _root(source, DOC)
    paragraph = etree.Element(W + "p")
    etree.SubElement(etree.SubElement(paragraph, W + "r"), W + "t").text = text
    doc.find(W + "body").insert(0, paragraph)
    return repack(source, output, {DOC: etree.tostring(doc)})


def _swaps(source, edited):
    return [f for f in compare(source, edited) if f.code == "FID017"]


def test_swapped_reviews_fail_the_default_gate_only_with_a_source(base_docx, tmp_path):
    edited = _swap(base_docx, tmp_path / "edited.docx")
    single_file = run_cli("check", str(edited), "--no-config", "--json")
    assert single_file.returncode == 0
    assert json.loads(single_file.stdout)["files"][0]["findings"] == []
    result = run_cli("check", str(edited), "--against", str(base_docx), "--no-config", "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    findings = json.loads(result.stdout)["files"][0]["findings"]
    assert [(f["code"], f["severity"]) for f in findings] == [("FID017", "error")]
    for phrase in ("Effective Date", "EUR 12,000", "Defined term", "Confirm this figure"):
        assert phrase in findings[0]["message"]


def test_renumbering_ranges_and_definitions_together_is_clean(base_docx, tmp_path):
    renumbered = _swap(base_docx, tmp_path / "renumbered.docx", renumber_definitions=True)
    assert compare(base_docx, renumbered) == []


def test_paragraph_inserted_above_the_anchors_does_not_change_their_identity(base_docx, tmp_path):
    shifted = _insert_paragraph(base_docx, tmp_path / "shifted.docx", "Addendum")
    assert not _swaps(base_docx, shifted)
    assert len(_swaps(base_docx, _swap(shifted, tmp_path / "swapped.docx"))) == 1


@pytest.mark.parametrize("swap_first", [False, True], ids=["one-move", "two-moves-without-return"])
def test_moving_to_a_third_clause_is_not_a_swap(base_docx, tmp_path, swap_first):
    source = _insert_paragraph(base_docx, tmp_path / "source.docx", "Payment schedule")
    doc = _root(_swap(source, tmp_path / "swapped.docx") if swap_first else source, DOC)
    destination = doc.find(f"{W}body/{W}p")
    start, end, reference = [doc.find(f".//{tag}[@{ID}='2']") for tag in MARKERS]
    destination.insert(0, start)
    destination.extend([end, reference.getparent()])
    edited = repack(source, tmp_path / "moved.docx", {DOC: etree.tostring(doc)})
    assert not _swaps(source, edited)


@pytest.mark.parametrize("ambiguity", ["repeated-paragraph", "repeated-comment", "empty-range"])
def test_ambiguous_swaps_are_not_reported(base_docx, tmp_path, ambiguity):
    source = tmp_path / "source.docx"
    if ambiguity == "repeated-paragraph":
        _insert_paragraph(base_docx, source, "EUR 12,000")
    elif ambiguity == "repeated-comment":
        comments = _root(base_docx, COMMENTS)
        duplicate = deepcopy(comments.find(W + "comment"))
        duplicate.set(ID, "3")  # Even an unanchored copy makes this body ambiguous.
        comments.append(duplicate)
        repack(base_docx, source, {COMMENTS: etree.tostring(comments)})
    else:
        doc = _root(base_docx, DOC)
        end = doc.find(f".//{MARKERS[1]}[@{ID}='1']")
        end.addprevious(doc.find(f".//{MARKERS[0]}[@{ID}='1']"))
        repack(base_docx, source, {DOC: etree.tostring(doc)})
    # Ambiguity in either version is enough to lose the proof of a swap.
    assert not _swaps(source, _swap(base_docx, tmp_path / "swapped.docx"))
    assert not _swaps(base_docx, _swap(source, tmp_path / "swapped-ambiguous.docx"))


def test_changing_the_clause_around_a_swapped_selection_is_inconclusive(base_docx, tmp_path):
    swapped = _swap(base_docx, tmp_path / "swapped.docx")
    doc = read_part(swapped, DOC)
    old = "is the date of last signature."
    assert old in doc
    edited = repack(swapped, tmp_path / "edited.docx", {DOC: doc.replace(
        old, "is the date of first delivery.").encode()})
    assert not _swaps(base_docx, edited)


def test_same_quoted_words_in_distinct_clauses_identify_both_locations(base_docx, tmp_path):
    doc = _root(base_docx, DOC)
    start = doc.find(f".//{MARKERS[0]}[@{ID}='1']")
    start.getnext().find(W + "t").text = "Effective Date"
    lead = etree.Element(W + "r")
    etree.SubElement(lead, W + "t").text = "Payment falls on the "
    start.addprevious(lead)
    source = repack(base_docx, tmp_path / "source.docx", {DOC: etree.tostring(doc)})
    [finding] = _swaps(source, _swap(source, tmp_path / "swapped.docx"))
    assert finding.severity.value == "error"
    by_text = "Payment falls" in finding.message and "services described" in finding.message
    by_number = all(re.search(rf"(?<!\d){n}(?!\d)", finding.message) for n in (2, 15))
    assert by_text or by_number, finding.message


def test_range_containing_a_field_result_is_outside_the_rule(base_docx, tmp_path):
    doc = _root(base_docx, DOC)
    run = doc.find(f".//{MARKERS[0]}[@{ID}='1']").getnext()
    field = etree.Element(W + "fldSimple", {W + "instr": " DOCPROPERTY FeeAmount "})
    run.addprevious(field)
    field.append(run)  # Same cached words, but their value depends on a field.
    source = repack(base_docx, tmp_path / "source.docx", {DOC: etree.tostring(doc)})
    assert not _swaps(source, _swap(source, tmp_path / "swapped.docx"))


def test_baseline_distinguishes_swaps_without_storing_review_or_clause_text(base_docx, tmp_path):
    source = repack(base_docx, tmp_path / "source.docx", {})
    edited = _swap(source, tmp_path / "edited.docx")
    baseline = tmp_path / "baseline.json"
    args = ("check", str(edited), "--against", str(source), "--no-config", "--json")
    assert run_cli(*args, "--write-baseline", str(baseline)).returncode == 0
    recorded = baseline.read_text()
    for private_text in ("EUR 12,000", "Effective Date", "Confirm this figure", "Defined term"):
        assert private_text not in recorded
    accepted = run_cli(*args, "--baseline", str(baseline))
    assert accepted.returncode == 0
    assert [f["code"] for f in json.loads(accepted.stdout)["files"][0]["suppressed"]] == ["FID017"]

    # Paragraph numbers only locate the exchange. It is still the accepted pair.
    _insert_paragraph(base_docx, source, "Addendum")
    _swap(source, edited)
    assert run_cli(*args, "--baseline", str(baseline)).returncode == 0

    # A different review note on the same two clauses is a new exchange.
    comments = read_part(base_docx, COMMENTS).replace("Confirm this figure", "Confirm the negotiated fee")
    repack(base_docx, source, {COMMENTS: comments.encode()})
    _swap(source, edited)
    other = run_cli(*args, "--baseline", str(baseline))
    assert other.returncode == 1
    [finding] = json.loads(other.stdout)["files"][0]["findings"]
    assert finding["code"] == "FID017" and "Confirm the negotiated fee" in finding["message"]

    # Same paths and reviewers, but one of the two selected clauses is different.
    doc = read_part(base_docx, DOC).replace("EUR 12,000", "EUR 24,000")
    repack(base_docx, source, {DOC: doc.encode()})
    _swap(source, edited)
    changed = run_cli(*args, "--baseline", str(baseline))
    assert changed.returncode == 1, changed.stdout + changed.stderr
    [finding] = json.loads(changed.stdout)["files"][0]["findings"]
    assert finding["code"] == "FID017" and "EUR 24,000" in finding["message"]
