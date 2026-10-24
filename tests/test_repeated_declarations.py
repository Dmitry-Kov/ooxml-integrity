"""PKG011 / REL004: a content type or relationship Id declared twice.

Word for Mac refuses every committed variant, including the ones whose second
declaration repeats the first; the checker reported none of them before.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from conftest import ROOT, needs_zlib_bytes, read_part, repack
from ooxml_integrity import Severity, check
from research.opc_duplicates import SOURCE, VARIANTS, build

EVIDENCE = ROOT / "evidence" / "docx-opc-duplicates"
OBSERVED = json.loads((EVIDENCE / "observations.json").read_text())
TYPES = "[Content_Types].xml"
RELS = "word/_rels/document.xml.rels"


def codes(path, *wanted):
    return [(f.code, f.severity) for f in check(path) if f.code in wanted]


def edited(tmp_path, name, entry, old, new):
    text = read_part(SOURCE, entry)
    assert text.count(old) == 1
    return repack(SOURCE, tmp_path / f"{name}.docx", {entry: text.replace(old, new).encode()})


@needs_zlib_bytes
def test_variants_rebuild_byte_for_byte(tmp_path):
    manifest = build(tmp_path)
    assert manifest["source_sha256"] == OBSERVED["source_sha256"]
    for name, variant in manifest["variants"].items():
        assert variant["sha256"] == OBSERVED["variants"][name]["sha256"]
        committed = EVIDENCE / OBSERVED["variants"][name]["file"]
        assert hashlib.sha256(committed.read_bytes()).hexdigest() == variant["sha256"]


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_each_variant_word_refused_reports_its_rule(name):
    observed = OBSERVED["variants"][name]
    assert observed["word"] == "refused"
    rule = observed["expected_finding"]
    path = EVIDENCE / observed["file"]
    assert codes(path, "PKG011", "REL004") == [(rule, Severity.ERROR)]


def test_the_control_word_opened_is_clean():
    assert OBSERVED["control"]["word"] == "opens"
    assert codes(SOURCE, "PKG011", "REL004") == []


def test_messages_say_what_differs():
    def message(name):
        path = EVIDENCE / OBSERVED["variants"][name]["file"]
        return next(f.message for f in check(path) if f.code in ("PKG011", "REL004"))

    assert message("default-repeated") == (
        'Default for extension "xml" declared 2 times - Word asks to recover the document')
    assert "(xml, XML)" in message("default-case")
    assert "different content types (application/xml, text/xml)" in message("default-conflicting")
    assert "(/word/comments.xml, /WORD/COMMENTS.XML)" in message("override-case")
    assert message("relationship-repeated").startswith("rId7 is the Id of 2 relationships - ")
    assert "for different targets or types" in message("relationship-conflicting")


def test_a_percent_escaped_part_name_is_the_same_part(tmp_path):
    # OPC compares part names unescaped; Word was not shown this spelling.
    override = '<Override PartName="/word/comments.xml"'
    path = edited(tmp_path, "escaped", TYPES, override, override.replace(
        "/word/comments.xml", "/word/%63omments.xml") + ' ContentType="application/xml"/>'
        + override)
    assert codes(path, "PKG011") == [("PKG011", Severity.ERROR)]


def test_distinct_declarations_are_not_repeats(tmp_path):
    xml = '<Default Extension="xml" ContentType="application/xml"/>'
    path = edited(tmp_path, "distinct", TYPES, xml,
                  xml + '<Default Extension="xmlx" ContentType="application/xml"/>'
                  '<Override PartName="/word/comments2.xml" ContentType="application/xml"/>')
    assert codes(path, "PKG011") == []


def test_ids_are_per_relationship_part(tmp_path):
    # rId1 is also an Id in _rels/.rels; each relationship part has its own.
    assert 'Id="rId1"' in read_part(SOURCE, "_rels/.rels")
    assert 'Id="rId1"' in read_part(SOURCE, RELS)
    assert codes(SOURCE, "REL004") == []


def test_repeated_id_in_the_package_relationships(tmp_path):
    rels = read_part(SOURCE, "_rels/.rels")
    first = rels[rels.index("<Relationship "):rels.index("/>", rels.index("<Relationship ")) + 2]
    path = edited(tmp_path, "root", "_rels/.rels", first, first * 2)
    found = [f for f in check(path) if f.code == "REL004"]
    assert [(f.severity, f.part) for f in found] == [(Severity.ERROR, "_rels/.rels")]


def test_relationships_without_an_id_are_not_repeats(tmp_path):
    rel = ('<Relationship Type="http://schemas.openxmlformats.org/officeDocument/2006/'
           'relationships/hyperlink" Target="https://example.org/" TargetMode="External"/>')
    styles = VARIANTS["relationship-conflicting"][1]
    path = edited(tmp_path, "no-id", RELS, styles, styles + rel * 2)
    assert codes(path, "REL004") == []
