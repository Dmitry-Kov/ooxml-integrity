"""A tracked edit to a note body or a header/footer is not a loss.

compare() matches comment, note and header/footer texts by content. A text
whose every change is a tracked revision still accounts for its source: with
the revisions rejected it is the source text. The same edit made untracked is
still reported. Items that already had pending revisions keep the strict
match, because rejecting one of those revisions leaves the same rejected text.
"""
from __future__ import annotations

import pytest

from conftest import ROOT, read_part, repack

from ooxml_integrity import Severity, compare

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
