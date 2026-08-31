"""Fidelity: what was lost relative to the source, and at what severity."""
from __future__ import annotations

import pytest
from conftest import read_part, repack

from docx_integrity import Severity, compare
from docx_integrity.fidelity import TRACKED

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
