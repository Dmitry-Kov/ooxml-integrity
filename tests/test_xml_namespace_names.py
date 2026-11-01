"""XML001: a namespace name that is not a URI does not make a part malformed.

SharePoint writes `xmlns:ns3="$ListId:Shared Documents;"` into custom XML
parts; libxml2 2.14 reports it at error level, and the checker called such a
part malformed. Word for Mac opens the committed variant, and PowerPoint for
Mac a public deck with such a part, without a prompt.
"""
from __future__ import annotations

import hashlib
import json

import pytest
from lxml import etree

from conftest import ROOT, needs_zlib_bytes
from ooxml_integrity import check
from ooxml_integrity.xmlutil import UnsafeXML, fromstring
from research.namespace_names import VARIANTS, build

EVIDENCE = ROOT / "evidence" / "xml-namespace-names"
OBSERVED = json.loads((EVIDENCE / "observations.json").read_text())


@needs_zlib_bytes
def test_variants_rebuild_byte_for_byte(tmp_path):
    manifest = build(tmp_path)
    assert manifest["source_sha256"] == OBSERVED["source_sha256"]
    for name, variant in manifest["variants"].items():
        assert variant["sha256"] == OBSERVED["variants"][name]["sha256"]
        committed = EVIDENCE / OBSERVED["variants"][name]["file"]
        assert hashlib.sha256(committed.read_bytes()).hexdigest() == variant["sha256"]


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_no_finding_where_word_opened_the_document(name):
    observed = OBSERVED["variants"][name]
    assert observed["word"] == "opens"
    assert [f for f in check(EVIDENCE / observed["file"]) if f.code == "XML001"] == []


def test_the_part_is_read_as_written():
    root = fromstring(b'<a xmlns:n="$ListId:Shared Documents;"><n:b>x</n:b></a>')
    [child] = root
    assert child.tag == "{$ListId:Shared Documents;}b" and child.text == "x"


@pytest.mark.parametrize("data", [
    b'<a xmlns:n="$ListId:Shared Documents;"><b></a>',
    b'<a xmlns:n="$ListId:Shared Documents;" x="1" x="2"/>',
    b'<a xmlns:n="$ListId:Shared Documents;"><n:b>',
])
def test_any_other_error_still_fails_the_part(data):
    with pytest.raises(etree.XMLSyntaxError):
        fromstring(data)


def test_a_doctype_is_still_refused():
    with pytest.raises(UnsafeXML):
        fromstring(b'<!DOCTYPE a><a xmlns:n="$ListId:Shared Documents;"/>')
