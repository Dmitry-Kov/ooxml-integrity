"""Untrusted Office files must not enable XML features OOXML never needs."""
from __future__ import annotations

import pytest

from conftest import read_part, repack

from ooxml_integrity import check
from ooxml_integrity.xmlutil import UnsafeXML, fromstring


def test_doctype_is_rejected_even_when_entity_resolution_is_disabled():
    xml = (
        b'<!DOCTYPE document [<!ENTITY injected "not OOXML">]>'
        b'<document>&injected;</document>'
    )
    with pytest.raises(UnsafeXML, match="DOCTYPE"):
        fromstring(xml)


def test_regular_xml_still_parses():
    root = fromstring(b'<document><text>safe</text></document>')
    assert root.findtext("text") == "safe"


def test_doctype_in_a_docx_part_is_reported_not_evaluated(
        tmp_docx, tmp_path):
    part = "word/document.xml"
    xml = read_part(tmp_docx, part)
    declaration_end = xml.index("?>") + 2
    xml = (xml[:declaration_end]
           + '<!DOCTYPE w:document [<!ENTITY injected "not OOXML">]>'
           + xml[declaration_end:])
    out = repack(tmp_docx, tmp_path / "doctype.docx", {part: xml.encode()})

    findings = [f for f in check(out) if f.code == "XML001" and f.part == part]
    assert len(findings) == 1
    assert "safely parsed" in findings[0].message
