"""Strict Open XML is reported as unsupported, not passed or called unreadable.

Word and PowerPoint save Strict files: 17 Word and 4 PowerPoint Strict files
are in the public corpora. The rules read Transitional names only, so a Strict
DOCX used to pass with nothing checked and a Strict PPTX failed as unreadable.
"""
from __future__ import annotations

import zipfile

import pytest

from conftest import repack

from ooxml_integrity import check, check_pptx, compare
from ooxml_integrity.coverage import coverage_for

#: Transitional namespace and relationship-type prefixes and their Strict names
STRICT_NAMES = {
    b"http://schemas.openxmlformats.org/wordprocessingml/2006/main":
        b"http://purl.oclc.org/ooxml/wordprocessingml/main",
    b"http://schemas.openxmlformats.org/presentationml/2006/main":
        b"http://purl.oclc.org/ooxml/presentationml/main",
    b"http://schemas.openxmlformats.org/drawingml/2006/main":
        b"http://purl.oclc.org/ooxml/drawingml/main",
    b"http://schemas.openxmlformats.org/officeDocument/2006/relationships":
        b"http://purl.oclc.org/ooxml/officeDocument/relationships",
}


def _strict(source, target):
    """Rename every Transitional name the way a Strict save writes it."""
    with zipfile.ZipFile(source) as z:
        parts = {n: z.read(n) for n in z.namelist() if n.endswith((".xml", ".rels"))}
    edits = {}
    for name, data in parts.items():
        new = data
        for old, strict in STRICT_NAMES.items():
            new = new.replace(old, strict)
        if new != data:
            edits[name] = new
    return repack(source, target, edits)


@pytest.fixture
def strict_docx(base_docx, tmp_path):
    return _strict(base_docx, tmp_path / "strict.docx")


def test_strict_docx_is_one_unsupported_error(strict_docx, base_docx):
    findings = check(strict_docx)
    assert [(f.code, f.severity.value, f.part) for f in findings] == [
        ("PKG009", "error", "word/document.xml")]
    assert "NOT run" in findings[0].message
    assert "PKG009" not in [f.code for f in check(base_docx)]


def test_strict_docx_comparison_is_not_performed(strict_docx):
    with pytest.raises(ValueError, match="Strict Open XML"):
        compare(strict_docx, strict_docx)


def test_strict_docx_coverage_names_the_gap(strict_docx):
    items = {i.id: i for i in coverage_for(strict_docx, []).items}
    assert items["docx.strict-wordprocessingml"].status.value == "unsupported"
    assert items["docx.tables"].status.value == "skipped"
    assert "Strict Open XML" in items["docx.tables"].reason


def test_strict_pptx_is_one_unsupported_error(root, tmp_path):
    deck = root / "corpus" / "deck.pptx"
    strict = _strict(deck, tmp_path / "strict.pptx")
    assert [(f.code, f.severity.value, f.part) for f in check_pptx(strict)] == [
        ("PKG009", "error", "ppt/presentation.xml")]
    assert "PKG009" not in [f.code for f in check_pptx(deck)]
