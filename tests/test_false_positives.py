"""
Regression tests for the three false positives that real agent runs exposed.

These are the most valuable tests in the suite. Hand-written mutators never
triggered any of them - it took six runs of a frontier model editing a contract
properly to reveal that the checker was wrong, not the documents.

For a linter, precision matters more than recall: one that cries wolf on a
valid file gets switched off after the third time.
"""
from __future__ import annotations

from conftest import read_part, repack

from ooxml_integrity import Severity, check, compare

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def codes(findings) -> set[str]:
    return {f.code for f in findings}


class TestLegalRevisionNesting:
    """w:ins > w:del is legal OOXML and must not be reported.

    It means "inserted by one author, deleted by another before the change was
    accepted" - exactly what a careful agent produces when its edit falls
    inside somebody else's pending insertion. The check has to test the NEAREST
    revision ancestor, not any ancestor.
    """

    def test_del_nested_in_ins_is_clean(self, tmp_docx, tmp_path):
        doc = read_part(tmp_docx, "word/document.xml")
        original = (
            '<w:ins w:id="103" w:author="A. Counsel" w:date="2026-08-14T16:21:00Z">\n'
            '<w:r><w:t xml:space="preserve">EUR 44,500 </w:t></w:r></w:ins>'
        )
        assert original in doc, "fixture drifted: the base document changed shape"
        nested = (
            '<w:ins w:id="103" w:author="A. Counsel" w:date="2026-08-14T16:21:00Z">'
            '<w:del w:id="900" w:author="Second" w:date="2026-08-30T00:00:00Z">'
            '<w:r><w:delText xml:space="preserve">EUR 44,500 </w:delText></w:r>'
            "</w:del></w:ins>"
            '<w:ins w:id="901" w:author="Second" w:date="2026-08-30T00:00:00Z">'
            '<w:r><w:t xml:space="preserve">EUR 47,250 </w:t></w:r></w:ins>'
        )
        out = repack(tmp_docx, tmp_path / "nested.docx",
                     {"word/document.xml": doc.replace(original, nested).encode()})
        assert "REV003" not in codes(check(out))

    def test_plain_deltext_in_ins_is_still_an_error(self, tmp_docx, tmp_path):
        """The check must still fire when there is no nested w:del to justify it."""
        doc = read_part(tmp_docx, "word/document.xml")
        broken = doc.replace(
            '<w:ins w:id="101" w:author="A. Counsel" w:date="2026-08-14T16:20:00Z">\n'
            "<w:r><w:t>The Supplier shall maintain professional indemnity "
            "insurance.</w:t></w:r></w:ins>",
            '<w:ins w:id="101" w:author="A. Counsel" w:date="2026-08-14T16:20:00Z">'
            "<w:r><w:delText>The Supplier shall maintain professional indemnity "
            "insurance.</w:delText></w:r></w:ins>",
        )
        assert broken != doc, "fixture drifted: could not build the broken case"
        out = repack(tmp_docx, tmp_path / "broken.docx",
                     {"word/document.xml": broken.encode()})
        assert "REV003" in codes(check(out))


class TestZipDirectoryEntries:
    """Directory entries in the archive are not OPC parts.

    Some agents rezip with them. Word tolerates them, so flagging them as
    uncovered content types was wrong.
    """

    def test_directory_entries_are_not_uncovered_parts(self, tmp_docx, tmp_path):
        out = repack(tmp_docx, tmp_path / "withdirs.docx", {}, add_dirs=True)
        assert "PKG005" not in codes(check(out))

    def test_a_real_uncovered_part_is_still_an_error(self, tmp_docx, tmp_path):
        out = repack(tmp_docx, tmp_path / "uncovered.docx",
                     {"word/mystery.bin": b"\x00\x01"})
        assert "PKG005" in codes(check(out))


class TestCountIncrease:
    """More constructs than the source is not a loss.

    An agent asked to add a clause legitimately adds a numbered item; one that
    tracks its edits legitimately adds w:ins. Real duplication is a colliding
    revision id (REV001), not a bigger number.
    """

    def test_added_constructs_are_info_not_error(self, base_docx, runs_dir):
        careful = runs_dir / "t2_pres" / "agreement.docx"
        if not careful.exists():
            import pytest
            pytest.skip("agent run output missing")
        findings = compare(base_docx, careful)
        assert findings, "expected at least the FID002 informational notes"
        assert all(f.code == "FID002" for f in findings)
        assert all(f.severity is Severity.INFO for f in findings)

    def test_duplicate_revision_id_is_still_an_error(self, tmp_docx, tmp_path):
        doc = read_part(tmp_docx, "word/document.xml")
        block = (
            '<w:ins w:id="101" w:author="A. Counsel" w:date="2026-08-14T16:20:00Z">\n'
            "<w:r><w:t>The Supplier shall maintain professional indemnity "
            "insurance.</w:t></w:r></w:ins>"
        )
        assert block in doc, "fixture drifted"
        out = repack(tmp_docx, tmp_path / "dupid.docx",
                     {"word/document.xml": doc.replace(block, block + block).encode()})
        assert "REV001" in codes(check(out))
