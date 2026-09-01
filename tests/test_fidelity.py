"""Fidelity: what was lost relative to the source, and at what severity."""
from __future__ import annotations

import pytest
from conftest import read_part, repack

from ooxml_integrity import Severity, compare
from ooxml_integrity.fidelity import TRACKED

DOC = "word/document.xml"


def by_tag(findings) -> dict[str, object]:
    return {f.extra.get("tag"): f for f in findings if "tag" in f.extra}


def test_identical_files_have_no_losses(base_docx):
    assert compare(base_docx, base_docx) == []


def test_severity_table_is_complete_and_ordered():
    """Every tracked construct needs a severity, and errors come first."""
    assert all(len(row) == 3 for row in TRACKED)
    sevs = [row[2] for row in TRACKED]
    assert Severity.ERROR in sevs and Severity.WARN in sevs
    first_warn = sevs.index(Severity.WARN)
    assert all(s is Severity.WARN for s in sevs[first_warn:]), (
        "errors should be listed before warnings so the table reads as a priority"
    )


def test_losing_a_comment_anchor_is_an_error(tmp_docx, tmp_path, base_docx):
    doc = read_part(tmp_docx, DOC)
    stripped = doc.replace('<w:r><w:commentReference w:id="1"/></w:r>', "")
    assert stripped != doc
    out = repack(tmp_docx, tmp_path / "x.docx", {DOC: stripped.encode()})
    f = by_tag(compare(base_docx, out))["commentReference"]
    assert f.code == "FID001"
    assert f.severity is Severity.ERROR
    assert f.extra == {"tag": "commentReference", "before": 2, "after": 1}


def test_losing_a_style_reference_is_only_a_warning(tmp_docx, tmp_path, base_docx):
    """Formatting loss is visible to a human; an invisible note is not."""
    doc = read_part(tmp_docx, DOC)
    stripped = doc.replace('<w:pPr><w:pStyle w:val="ClauseBody"/></w:pPr>', "", 1)
    assert stripped != doc
    out = repack(tmp_docx, tmp_path / "y.docx", {DOC: stripped.encode()})
    f = by_tag(compare(base_docx, out))["pStyle"]
    assert f.severity is Severity.WARN


def test_losing_everything_is_an_error_whatever_the_construct(
        tmp_docx, tmp_path, base_docx):
    doc = read_part(tmp_docx, DOC)
    stripped = (doc
                .replace('<w:pStyle w:val="ClauseBody"/>', "")
                .replace('<w:pStyle w:val="Heading1"/>', "")
                .replace('<w:pStyle w:val="Heading2"/>', "")
                .replace('<w:pStyle w:val="ListParagraph"/>', ""))
    out = repack(tmp_docx, tmp_path / "z.docx", {DOC: stripped.encode()})
    f = by_tag(compare(base_docx, out))["pStyle"]
    assert f.severity is Severity.ERROR, "all-lost is always an error"
    assert "all lost" in f.message


def test_text_volume_collapse_is_reported(tmp_docx, tmp_path, base_docx):
    doc = read_part(tmp_docx, DOC)
    gutted = doc.split("<w:body>")[0] + "<w:body><w:p/></w:body></w:document>"
    out = repack(tmp_docx, tmp_path / "empty.docx", {DOC: gutted.encode()})
    findings = compare(base_docx, out)
    fid003 = [f for f in findings if f.code == "FID003"]
    assert fid003
    assert fid003[0].severity is Severity.ERROR
    assert "% of content lost" in fid003[0].message


def test_construct_absent_from_the_source_is_not_a_loss(tmp_path, tmp_docx):
    """No endnotes in the source means no complaint about endnotes."""
    findings = compare(tmp_docx, tmp_docx)
    assert findings == []


# ---------------------------------- identity, not counting
COMMENTS = "word/comments.xml"


def _swap_a_comment(tmp_docx, tmp_path, dst_name="swapped.docx"):
    """Remove comment 1 and add a different one, keeping every count equal.

    Anchors are renumbered to 9 and comments.xml loses entry 1 and gains a
    complete entry 9. Nothing is orphaned, no count changes, and the file opens
    without complaint - the reviewer's sentence is simply gone.
    """
    doc = read_part(tmp_docx, DOC).replace('w:id="1"', 'w:id="9"')
    comments = read_part(tmp_docx, COMMENTS)
    start = comments.index('<w:comment w:id="1"')
    end = comments.index("</w:comment>", start) + len("</w:comment>")
    removed = comments[start:end]
    replacement = (
        '<w:comment w:id="9" w:author="Bot" w:initials="B" '
        'w:date="2026-09-01T00:00:00Z">'
        "<w:p><w:r><w:t>Updated per instruction.</w:t></w:r></w:p>"
        "</w:comment>"
    )
    comments = comments[:start] + replacement + comments[end:]
    assert "Confirm this figure" not in comments
    assert "Confirm this figure" in removed
    return repack(tmp_docx, tmp_path / dst_name,
                  {DOC: doc.encode(), COMMENTS: comments.encode()})


def test_a_swapped_comment_is_caught_even_though_counts_match(
        tmp_docx, tmp_path, base_docx):
    """The hole that counting leaves, and the reason FID004 exists.

    Before FID004 this exact file came back as `0 error(s), 0 warning(s),
    0 info - clean`: the counts matched, nothing was orphaned, so both halves
    of the tool were satisfied while the reviewer's note had been destroyed.
    """
    out = _swap_a_comment(tmp_docx, tmp_path)

    # the premise of the test: counting really cannot see this
    counted = [f for f in compare(base_docx, out) if "tag" in f.extra]
    assert not [f for f in counted if f.code == "FID001"], (
        "if a count now drops, this fixture no longer tests what it claims to"
    )

    found = [f for f in compare(base_docx, out) if f.code == "FID004"]
    assert len(found) == 1, "the destroyed comment was not reported"
    f = found[0]
    assert f.severity is Severity.ERROR
    assert "M. Reviewer" in f.message
    assert "Confirm this figure" in f.message
    assert f.extra["author"] == "M. Reviewer"


def test_matching_is_by_text_not_by_id(tmp_docx, tmp_path, base_docx):
    """Renumbering is a producer's business; the words are what must survive."""
    doc = read_part(tmp_docx, DOC).replace('w:id="1"', 'w:id="77"')
    comments = read_part(tmp_docx, COMMENTS).replace(
        '<w:comment w:id="1"', '<w:comment w:id="77"')
    out = repack(tmp_docx, tmp_path / "renumbered.docx",
                 {DOC: doc.encode(), COMMENTS: comments.encode()})
    assert not [f for f in compare(base_docx, out) if f.code == "FID004"], (
        "a comment that only changed id was reported as lost"
    )


def test_reflowed_whitespace_is_not_a_loss(tmp_docx, tmp_path, base_docx):
    comments = read_part(tmp_docx, COMMENTS).replace(
        "Confirm this figure against",
        "Confirm   this\n figure\tagainst")
    out = repack(tmp_docx, tmp_path / "reflowed.docx", {COMMENTS: comments.encode()})
    assert not [f for f in compare(base_docx, out) if f.code == "FID004"]


def test_losing_a_footnote_body_is_caught(tmp_docx, tmp_path, base_docx):
    from conftest import read_part as rp
    footnotes = rp(tmp_docx, "word/footnotes.xml")
    start = footnotes.index('<w:footnote w:id="2"')
    end = footnotes.index("</w:footnote>", start) + len("</w:footnote>")
    gutted = footnotes[:start] + footnotes[end:]
    assert gutted != footnotes
    out = repack(tmp_docx, tmp_path / "nofoot.docx",
                 {"word/footnotes.xml": gutted.encode()})
    codes = {f.code for f in compare(base_docx, out)}
    assert "FID005" in codes


def test_the_careful_agent_runs_stay_clean_under_body_comparison(
        runs_dir, base_docx):
    """The check that matters most: real edits must not trip the new rule.

    Two of these rewrote paragraphs wholesale. If body matching were brittle -
    id-based, or whitespace-sensitive - they would light up, and the rule would
    be worse than the hole it closes.
    """
    from conftest import CAREFUL_RUNS
    for name in CAREFUL_RUNS:
        p = runs_dir / name / "agreement.docx"
        if not p.exists():
            continue
        bad = [f for f in compare(base_docx, p)
               if f.code in ("FID004", "FID005", "FID006")]
        assert not bad, f"{name}: false positive {[f.message for f in bad]}"
