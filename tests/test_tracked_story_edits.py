"""A tracked edit to a note body or a header/footer is not a loss.

compare() matches comment, note and header/footer texts by content. A text
whose every change is a tracked revision still accounts for its source: with
the revisions rejected it is the source text. The same edit made untracked is
still reported. Items that already had pending revisions keep the strict
match, because rejecting one of those revisions leaves the same rejected text.
"""
from __future__ import annotations

import json

import pytest

from conftest import ROOT, read_part, repack, run_cli

from ooxml_integrity import Severity, compare
from ooxml_integrity.fidelity import W, _text_fact, _unmatched
from ooxml_integrity.xmlutil import fromstring

FOOTNOTES = "word/footnotes.xml"
HEADER = "word/header1.xml"
FOOTNOTE = " Measured across the reference corpus, Q2 2026."
HEADER_TEXT = "<w:r><w:t>Reference Agreement - Draft 7</w:t></w:r>"
REV = 'w:author="Benchmark Editor" w:date="2026-09-30T10:00:00Z"'
S2 = ROOT / "evidence" / "review-history-benchmark" / "sources"
STORY_CODES = {"FID004", "FID005", "FID006", "FID007", "FID008", "FID010"}


def _run(text: str, tag: str = "t") -> str:
    return f'<w:r><w:{tag} xml:space="preserve">{text}</w:{tag}></w:r>'


def _ins(rid: int, text: str) -> str:
    return f'<w:ins w:id="{rid}" {REV}>{_run(text)}</w:ins>'


def _del(rid: int, text: str) -> str:
    return f'<w:del w:id="{rid}" {REV}>{_run(text, "delText")}</w:del>'


def _edit(base, tmp_path, name: str, part: str, old: str, new: str):
    xml = read_part(base, part)
    assert xml.count(old) == 1, old
    return repack(base, tmp_path / f"{name}.docx", {part: xml.replace(old, new).encode()})


def _losses(source, edited):
    return sorted((f.code, f.severity.name) for f in compare(source, edited)
                  if f.code in STORY_CODES)


def _comments(base, path, first, second):
    part = "word/comments.xml"
    xml = read_part(base, part)
    for old, runs in [
        ("Confirm this figure against the source table before circulation.", first),
        ("Defined term must match the definitions schedule.", second),
    ]:
        run = f"<w:r><w:t>{old}</w:t></w:r>"
        assert xml.count(run) == 1
        xml = xml.replace(run, runs)
    return repack(base, path, {part: xml.encode()})


@pytest.mark.parametrize(("first", "second", "lost"), [
    # The current text of the second comment is the original text of the first.
    (_del(901, "Confirm tax") + _ins(902, "Check tax"),
     _del(903, "Confirm fee") + _ins(904, "Confirm tax"), None),
    # Both current texts survive. Reserving a match by rejected text first
    # would give the second comment to the wrong source.
    (_del(901, "Check tax") + _ins(902, "Confirm tax"),
     _del(903, "Confirm tax") + _ins(904, "Confirm fee"), None),
    # Only the first replacement is tracked. The second original text is lost.
    (_del(901, "Confirm tax") + _ins(902, "Check tax"),
     _run("Confirm tax"), "Confirm fee"),
], ids=["tracked-overlap", "current-texts-preserved", "untracked-loss"])
def test_overlapping_comment_texts_are_matched_once(base_docx, tmp_path, first, second, lost):
    source = _comments(base_docx, tmp_path / "source.docx", _run("Confirm tax"), _run("Confirm fee"))
    edited = _comments(base_docx, tmp_path / "edited.docx", first, second)
    result = run_cli("check", str(edited), "--against", str(source), "--no-config", "--json")
    findings = json.loads(result.stdout)["files"][0]["findings"]
    losses = [(f["severity"], f["extra"]["body"], f["extra"]["lost"])
              for f in findings if f["code"] == "FID004"]
    assert losses == ([] if lost is None else [("error", lost, 1)])
    assert result.returncode == (0 if lost is None else 1)


def test_matching_a_third_comment_can_require_reassigning_two_others():
    def body(runs):
        xml = f'<w:comment xmlns:w="{W[1:-1]}"><w:p>{runs}</w:p></w:comment>'
        return _text_fact(fromstring(xml.encode()))

    source = [body(_run(text)) for text in ("Fee", "Tax", "Notice")]
    edited = [body(_del(901, "Fee") + _ins(902, "Payment")),
              body(_del(903, "Tax") + _ins(904, "Fee")),
              body(_del(905, "Notice") + _ins(906, "Tax"))]
    assert not _unmatched(source, edited)


FOOTNOTE_RUN = f'<w:r><w:t xml:space="preserve">{FOOTNOTE}</w:t></w:r>'

#: name -> (part, old, new, expected losses)
EDITS = {
    "footnote-tracked-replacement": (
        FOOTNOTES, FOOTNOTE_RUN,
        _run(" Measured across the reference corpus, ") + _del(901, "Q2")
        + _ins(902, "Q3") + _run(" 2026."), []),
    "footnote-untracked-replacement": (
        FOOTNOTES, FOOTNOTE_RUN,
        _run(" Measured across the reference corpus, Q3 2026."), [("FID005", "ERROR")]),
    "footnote-tracked-deletion-of-all-text": (
        FOOTNOTES, FOOTNOTE_RUN, _del(901, FOOTNOTE), []),
    "footnote-text-removed": (
        FOOTNOTES, FOOTNOTE_RUN, "", [("FID005", "ERROR")]),
    "footnote-tracked-insertion": (
        FOOTNOTES, FOOTNOTE_RUN, FOOTNOTE_RUN + _ins(901, " Excludes pilots."), []),
    "header-tracked-replacement": (
        HEADER, HEADER_TEXT,
        _run("Reference Agreement - Draft ") + _del(901, "7") + _ins(902, "8"), []),
    "header-untracked-replacement": (
        HEADER, HEADER_TEXT, _run("Reference Agreement - Draft 8"), [("FID007", "ERROR")]),
    "header-tracked-deletion": (
        HEADER, HEADER_TEXT,
        _run("Reference Agreement") + _del(901, " - Draft 7"), []),
    "header-untracked-deletion": (
        HEADER, HEADER_TEXT, _run("Reference Agreement"), [("FID007", "ERROR")]),
}


@pytest.mark.parametrize("name", sorted(EDITS))
def test_tracked_edits_keep_notes_and_stories(base_docx, tmp_path, name):
    part, old, new, expected = EDITS[name]
    assert _losses(base_docx, _edit(base_docx, tmp_path, name, part, old, new)) == expected


def test_a_rejected_pending_note_insertion_is_still_reported(base_docx, tmp_path):
    """Rejecting it restores the rejected text, so only the strict match applies."""
    pending = FOOTNOTE_RUN + _ins(901, " Excludes pilots.")
    source = _edit(base_docx, tmp_path, "pending", FOOTNOTES, FOOTNOTE_RUN, pending)
    rejected = _edit(source, tmp_path, "rejected", FOOTNOTES, pending, FOOTNOTE_RUN)
    assert _losses(source, rejected) == [("FID005", "ERROR")]


def test_a_rejected_pending_header_deletion_is_still_reported(base_docx, tmp_path):
    pending = _run("Reference Agreement") + _del(901, " - Draft 7")
    source = _edit(base_docx, tmp_path, "pending", HEADER, HEADER_TEXT, pending)
    rejected = _edit(source, tmp_path, "rejected", HEADER, pending, HEADER_TEXT)
    assert ("FID007", "ERROR") in _losses(source, rejected)


def test_a_footer_revision_cannot_account_for_a_lost_header(base_docx, tmp_path):
    header = _ins(901, "Draft").replace("Benchmark Editor", "Header Reviewer")
    footer = _ins(902, "Draft").replace("Benchmark Editor", "Footer Reviewer")
    footer_part = "word/footer1.xml"
    source = repack(base_docx, tmp_path / "source.docx", {
        HEADER: read_part(base_docx, HEADER).replace(HEADER_TEXT, header).encode(),
        footer_part: read_part(base_docx, footer_part).replace(
            "<w:r><w:t>Confidential</w:t></w:r>", footer).encode(),
    })
    # The two reviewers' insertions traded places. The footer still matches
    # its source by current text. Rejecting the new suffix in the header
    # restores the footer reviewer's insertion, not the header reviewer's.
    edited = repack(source, tmp_path / "edited.docx", {
        HEADER: read_part(source, HEADER).replace(header, footer + _ins(903, " revised")).encode(),
        footer_part: read_part(source, footer_part).replace(footer, header).encode(),
    })
    found = [f for f in compare(source, edited) if f.code == "FID007"]
    assert [(f.where, f.severity, f.extra["body"]) for f in found] == [
        ("header/default", Severity.ERROR, "Draft")]


def test_each_edited_note_accounts_for_one_source_note(base_docx, tmp_path):
    """Two identical notes: one tracked-edited, one emptied - one loss of two."""
    twin = read_part(base_docx, FOOTNOTES).replace(
        " ECMA-376 Part 1, 5th edition, section 17.3.1.", FOOTNOTE)
    assert twin.count(FOOTNOTE) == 2
    source = repack(base_docx, tmp_path / "twins.docx", {FOOTNOTES: twin.encode()})
    edited = twin.replace(FOOTNOTE_RUN, _del(901, FOOTNOTE), 1).replace(FOOTNOTE_RUN, "", 1)
    output = repack(source, tmp_path / "one-lost.docx", {FOOTNOTES: edited.encode()})
    findings = [f for f in compare(source, output) if f.code == "FID005"]
    assert [(f.severity, f.extra["lost"], f.extra["in_source"]) for f in findings] == [
        (Severity.ERROR, 1, 2)]


@pytest.mark.parametrize(("source", "edited"), [
    ("review-base.docx", "review-a.docx"),
    ("review-base.docx", "word-review.docx"),
    ("review-a.docx", "word-review.docx"),
])
def test_word_for_mac_review_record_has_no_story_losses(source, edited):
    """S2: Word's own tracked header and endnote edits (see its README)."""
    assert _losses(S2 / source, S2 / edited) == []


# Items that already have pending revisions: a tracked edit on top keeps them.

S2_HEADER = "word/header1.xml"
S2_HEADER_RUN = '<w:r><w:t xml:space="preserve">Consulting Services Agreement - Draft </w:t></w:r>'
S2_PENDING_INS = ('<w:ins w:id="17" w:author="Reviewer A" w:date="2026-09-29T14:26:00Z" '
                  'w16du:dateUtc="2026-09-29T09:26:00Z"><w:r w:rsidR="001B7773" w:rsidRPr="001B7773">'
                  '<w:t>4</w:t></w:r></w:ins>')
TRACKED_S2_HEADER = (_del(901, "Consulting") + _ins(902, "Consultancy")
                     + _run(" Services Agreement - Draft "))


def _header(tmp_path, name, *edits):
    path = S2 / "word-review.docx"
    for index, (old, new) in enumerate(edits):
        path = _edit(path, tmp_path, f"{name}-{index}", S2_HEADER, old, new)
    return path


def test_a_tracked_edit_beside_a_pending_header_revision_is_kept(tmp_path):
    output = _header(tmp_path, "tracked", (S2_HEADER_RUN, TRACKED_S2_HEADER))
    assert _losses(S2 / "word-review.docx", output) == []


def test_accepting_the_pending_header_revision_is_still_reported(tmp_path):
    output = _header(tmp_path, "accepted", (S2_HEADER_RUN, TRACKED_S2_HEADER),
                     (S2_PENDING_INS, '<w:r><w:t>4</w:t></w:r>'))
    assert ("FID007", "ERROR") in _losses(S2 / "word-review.docx", output)


def test_redating_the_pending_header_revision_is_still_reported(tmp_path):
    output = _header(tmp_path, "redated", (S2_HEADER_RUN, TRACKED_S2_HEADER),
                     (S2_PENDING_INS, S2_PENDING_INS.replace('w:date="2026-09-29T14:26:00Z"',
                                                             'w:date="2026-10-01T00:00:00Z"')))
    assert ("FID007", "ERROR") in _losses(S2 / "word-review.docx", output)


def test_a_tracked_edit_in_a_note_with_a_pending_insertion_is_kept(base_docx, tmp_path):
    pending = FOOTNOTE_RUN + _ins(801, " Excludes pilots.").replace(
        "Benchmark Editor", "A. Counsel")
    source = _edit(base_docx, tmp_path, "pending", FOOTNOTES, FOOTNOTE_RUN, pending)
    edited = (_run(" Measured across the reference corpus, ") + _del(901, "Q2") + _ins(902, "Q3")
              + _run(" 2026.") + pending[len(FOOTNOTE_RUN):])
    output = _edit(source, tmp_path, "edited", FOOTNOTES, pending, edited)
    assert _losses(source, output) == []
    rejected = _edit(source, tmp_path, "edited-rejected", FOOTNOTES, pending,
                     edited[:-len(pending[len(FOOTNOTE_RUN):])])
    assert _losses(source, rejected) == [("FID005", "ERROR")]


def test_a_tracked_edit_in_the_word_endnote_with_a_pending_revision_is_kept(tmp_path):
    source = S2 / "word-review.docx"
    endnotes = read_part(source, "word/endnotes.xml")
    old = '<w:t xml:space="preserve"> Company details are taken from the public register on </w:t>'
    assert endnotes.count(old) == 1
    new = ('<w:t xml:space="preserve"> Company details are taken from the </w:t></w:r>'
           + _del(901, "public") + _ins(902, "official")
           + '<w:r><w:t xml:space="preserve"> register on </w:t>')
    output = repack(source, tmp_path / "endnote.docx", {"word/endnotes.xml": endnotes.replace(old, new).encode()})
    assert _losses(source, output) == []
