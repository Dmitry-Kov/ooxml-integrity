"""PKG005 / PKG010: an Override covers its part in any letters, but not escaped.

Word for Mac opens a package whose Override names /WORD/COMMENTS.XML for
word/comments.xml; through 0.8.3 PKG005 reported that part as uncovered once no
xml Default hid it. Word refuses an Override that escapes an unreserved
character, so an escaped name still covers nothing.
"""
from __future__ import annotations

import hashlib
import json
import zipfile

import pytest

from conftest import ROOT, needs_zlib_bytes
from ooxml_integrity import Severity, check
from ooxml_integrity.fix import fix
from research.case_overrides import SOURCE, VARIANTS, build

EVIDENCE = ROOT / "evidence" / "docx-case-overrides"
OBSERVED = json.loads((EVIDENCE / "observations.json").read_text())
RULES = ("PKG004", "PKG005", "PKG010", "PKG011")


def rules(path):
    return sorted(f.code for f in check(path) if f.code in RULES)


@needs_zlib_bytes
def test_variants_rebuild_byte_for_byte(tmp_path):
    manifest = build(tmp_path)
    assert manifest["source_sha256"] == OBSERVED["source_sha256"]
    for name, variant in manifest["variants"].items():
        assert variant["sha256"] == OBSERVED["variants"][name]["sha256"]
        committed = EVIDENCE / OBSERVED["variants"][name]["file"]
        assert hashlib.sha256(committed.read_bytes()).hexdigest() == variant["sha256"]


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_findings_are_the_recorded_ones(name):
    observed = OBSERVED["variants"][name]
    assert rules(EVIDENCE / observed["file"]) == observed["findings"]["now"]


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_what_word_opens_is_clean_and_what_it_refuses_fails(name):
    observed = OBSERVED["variants"][name]
    errors = [f for f in check(EVIDENCE / observed["file"]) if f.severity is Severity.ERROR]
    if observed["word"] == "opens":
        assert errors == []
    elif name == "override-absent-escaped":
        assert errors == []      # refused by Word, reported by no rule: a known gap
    else:
        assert errors


def test_names_are_compared_without_case_and_not_unescaped():
    from ooxml_integrity.content_types import covered

    assert covered("/WORD/Comments.XML") == covered("/word/comments.xml")
    assert covered("/word/%63omments.xml") != covered("/word/comments.xml")


def test_fix_repairs_a_wrong_type_on_an_override_in_capitals(tmp_path):
    source = EVIDENCE / OBSERVED["variants"]["override-capitals-wrong-type"]["file"]
    out = tmp_path / "fixed.docx"
    report = fix(source, out)
    assert report.status == "repaired"
    assert rules(out) == []
    with zipfile.ZipFile(out) as z:
        types = z.read("[Content_Types].xml").decode()
    assert ('<Override PartName="/WORD/COMMENTSEXTENDED.XML" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml"/>') in types
    assert OBSERVED["repaired"]["word"] == "opens"


def test_the_control_is_clean():
    assert OBSERVED["control"]["word"] == "opens"
    assert rules(SOURCE) == []
