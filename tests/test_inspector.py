"""Inspector behaviour: the baseline must be clean, and each defect must fire."""
from __future__ import annotations

import pytest
from conftest import read_part, repack

from ooxml_integrity import Inspector, Severity, check, summarize, worst

DOC = "word/document.xml"


def codes(findings) -> set[str]:
    return {f.code for f in findings}


def test_baseline_is_clean(base_docx):
    """If this fails, every other assertion in the suite is meaningless."""
    findings = check(base_docx)
    assert findings == [], f"reference document is not clean: {findings}"


def test_baseline_summary_shape(base_docx):
    s = summarize(check(base_docx))
    assert s == {"error": 0, "warn": 0, "info": 0}
    assert worst(check(base_docx)) is None


def test_missing_file_is_reported_not_raised(tmp_path):
    findings = check(tmp_path / "nope.docx")
    assert codes(findings) == {"PKG000"}
    assert findings[0].severity is Severity.ERROR


def test_not_a_zip_is_reported_not_raised(tmp_path):
    p = tmp_path / "junk.docx"
    p.write_bytes(b"this is not a zip file at all")
    findings = check(p)
    assert codes(findings) == {"PKG002"}


def test_malformed_xml_is_reported(tmp_docx, tmp_path):
    out = repack(tmp_docx, tmp_path / "bad.docx",
                 {DOC: b"<w:document><w:body></w:document>"})
    assert "XML001" in codes(check(out))


@pytest.mark.parametrize("part", ["word/styles.xml", "word/numbering.xml"])
def test_findings_carry_a_location(tmp_docx, tmp_path, part):
    """Every finding must point somewhere - a code with no location is useless."""
    doc = read_part(tmp_docx, DOC)
    out = repack(tmp_docx, tmp_path / "loc.docx",
                 {DOC: doc.replace('w:val="ClauseBody"', 'w:val="Nope"').encode()})
    findings = [f for f in check(out) if f.code == "STY001"]
    assert findings
    assert all(f.where or f.part for f in findings)


class TestReferentialIntegrity:
    """Each defect class: schema-legal, renders fine, must still be caught."""

    def test_orphaned_comment(self, tmp_docx, tmp_path):
        doc = read_part(tmp_docx, DOC)
        stripped = (doc
                    .replace('<w:commentRangeStart w:id="1"/>', "")
                    .replace('<w:commentRangeEnd w:id="1"/>', "")
                    .replace('<w:r><w:commentReference w:id="1"/></w:r>', ""))
        assert stripped != doc
        out = repack(tmp_docx, tmp_path / "orphan.docx", {DOC: stripped.encode()})
        findings = check(out)
        assert "CMT005" in codes(findings)
        assert any(f.code == "CMT005" and f.severity is Severity.ERROR
                   for f in findings), "an invisible reviewer note must be an error"

    def test_dangling_comment_reference(self, tmp_docx, tmp_path):
        cm = read_part(tmp_docx, "word/comments.xml")
        out = repack(tmp_docx, tmp_path / "nocomment.docx", {
            "word/comments.xml": cm.replace('w:id="1"', 'w:id="77"').encode()})
        assert "CMT004" in codes(check(out))

    def test_range_without_end(self, tmp_docx, tmp_path):
        doc = read_part(tmp_docx, DOC)
        out = repack(tmp_docx, tmp_path / "noend.docx", {
            DOC: doc.replace('<w:commentRangeEnd w:id="2"/>', "").encode()})
        assert "CMT001" in codes(check(out))

    def test_dangling_footnote_reference(self, tmp_docx, tmp_path):
        fn = read_part(tmp_docx, "word/footnotes.xml")
        out = repack(tmp_docx, tmp_path / "nofn.docx", {
            "word/footnotes.xml": fn.replace('w:id="1"', 'w:id="88"').encode()})
        assert "FTN001" in codes(check(out))

    def test_undefined_style(self, tmp_docx, tmp_path):
        st = read_part(tmp_docx, "word/styles.xml")
        out = repack(tmp_docx, tmp_path / "nostyle.docx", {
            "word/styles.xml": st.replace('w:styleId="ClauseBody"',
                                          'w:styleId="Renamed"').encode()})
        findings = [f for f in check(out) if f.code == "STY001"]
        assert len(findings) == 4, "every reference to the renamed style must fire"

    def test_undefined_numid(self, tmp_docx, tmp_path):
        num = read_part(tmp_docx, "word/numbering.xml")
        out = repack(tmp_docx, tmp_path / "nonum.docx", {
            "word/numbering.xml": num.replace('<w:num w:numId="1">'
                                              '<w:abstractNumId w:val="0"/></w:num>',
                                              "").encode()})
        assert "NUM002" in codes(check(out))

    def test_missing_numbering_part(self, tmp_docx, tmp_path):
        import zipfile
        with zipfile.ZipFile(tmp_docx) as z:
            names = [n for n in z.namelist() if n != "word/numbering.xml"]
            parts = {n: z.read(n) for n in names}
        out = tmp_path / "nonumpart.docx"
        with zipfile.ZipFile(out, "w") as z:
            for n in names:
                z.writestr(n, parts[n])
        assert "NUM001" in codes(check(out))

    def test_unresolvable_relationship(self, tmp_docx, tmp_path):
        rels = read_part(tmp_docx, "word/_rels/document.xml.rels")
        out = repack(tmp_docx, tmp_path / "norel.docx", {
            "word/_rels/document.xml.rels": rels.replace('Id="rId7"',
                                                         'Id="rId70"').encode()})
        assert "REL001" in codes(check(out))

    def test_relationship_to_missing_part(self, tmp_docx, tmp_path):
        rels = read_part(tmp_docx, "word/_rels/document.xml.rels")
        out = repack(tmp_docx, tmp_path / "nopart.docx", {
            "word/_rels/document.xml.rels":
                rels.replace('Target="media/chart.png"',
                             'Target="media/gone.png"').encode()})
        assert "REL002" in codes(check(out))

    def test_missing_default_rels_content_type(self, tmp_docx, tmp_path):
        ct = read_part(tmp_docx, "[Content_Types].xml")
        line = ('<Default Extension="rels" ContentType="application/'
                'vnd.openxmlformats-package.relationships+xml"/>')
        assert line in ct
        out = repack(tmp_docx, tmp_path / "norels.docx", {
            "[Content_Types].xml": ct.replace(line, "").encode()})
        assert "PKG004" in codes(check(out))

    def test_table_grid_mismatch(self, tmp_docx, tmp_path):
        doc = read_part(tmp_docx, DOC)
        out = repack(tmp_docx, tmp_path / "grid.docx", {
            DOC: doc.replace('<w:gridCol w:w="3000"/><w:gridCol w:w="3000"/>'
                             '<w:gridCol w:w="3000"/>',
                             '<w:gridCol w:w="4500"/>'
                             '<w:gridCol w:w="4500"/>').encode()})
        assert "TBL002" in codes(check(out))

    def test_content_control_without_content(self, tmp_docx, tmp_path):
        doc = read_part(tmp_docx, DOC)
        out = repack(tmp_docx, tmp_path / "sdt.docx", {
            DOC: doc.replace("<w:sdtContent>", "<w:notContent>")
                    .replace("</w:sdtContent>", "</w:notContent>").encode()})
        assert "SDT002" in codes(check(out))

    def test_dropped_xml_space(self, tmp_docx, tmp_path):
        doc = read_part(tmp_docx, DOC)
        out = repack(tmp_docx, tmp_path / "space.docx", {
            DOC: doc.replace(' xml:space="preserve"', "").encode()})
        findings = [f for f in check(out) if f.code == "TXT001"]
        assert findings, "dropped xml:space must be reported"


def test_a_broken_check_does_not_hide_the_others(monkeypatch, base_docx):
    """One raising check must degrade to a warning, not lose the whole run."""
    def boom(self):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(Inspector, "CHECKS",
                        (boom, Inspector.check_comments), raising=True)
    findings = Inspector(base_docx).run()
    assert "INT001" in codes(findings)
