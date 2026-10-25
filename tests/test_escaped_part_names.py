"""PKG012: an Override whose PartName has an escape Word does not accept.

Word for Mac refuses every committed variant that escapes an unreserved
character, a slash, a backslash or a non-ASCII character, or has a % that
starts no escape, and opens those that escape a space, % or #; the checker
reported none of them before.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from conftest import ROOT, needs_zlib_bytes, read_part, repack
from ooxml_integrity import Severity, check
from research.escaped_part_names import COMMENTS, SOURCE, VARIANTS, build

EVIDENCE = ROOT / "evidence" / "docx-escaped-part-names"
OBSERVED = json.loads((EVIDENCE / "observations.json").read_text())
TYPES = "[Content_Types].xml"


def pkg012(path):
    return [f for f in check(path) if f.code == "PKG012"]


def with_override(tmp_path, part_name, name="variant"):
    text = read_part(SOURCE, TYPES)
    added = f'<Override PartName="{part_name}" ContentType="application/xml"/>'
    return repack(SOURCE, tmp_path / f"{name}.docx", {TYPES: text.replace(COMMENTS, COMMENTS + added).encode()})


@needs_zlib_bytes
def test_variants_rebuild_byte_for_byte(tmp_path):
    manifest = build(tmp_path)
    assert manifest["source_sha256"] == OBSERVED["source_sha256"]
    for name, variant in manifest["variants"].items():
        assert variant["sha256"] == OBSERVED["variants"][name]["sha256"]
        committed = EVIDENCE / OBSERVED["variants"][name]["file"]
        assert hashlib.sha256(committed.read_bytes()).hexdigest() == variant["sha256"]


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_reported_exactly_where_word_refused(name):
    observed = OBSERVED["variants"][name]
    found = [(f.severity, f.part) for f in pkg012(EVIDENCE / observed["file"])]
    if observed["word"] == "refused":
        assert found == [(Severity.ERROR, TYPES)]
    else:
        assert found == []


def test_the_message_names_the_escape():
    def message(name):
        return pkg012(EVIDENCE / OBSERVED["variants"][name]["file"])[0].message

    assert message("letter-upper") == (
        "Override for /word/%6Eothere.xml escapes 'n' as %6E, an unreserved character a "
        "part name must not escape - Word asks to recover the document")
    assert "escapes '/' as %2F" in message("slash")
    assert "escapes the bytes of a non-ASCII character" in message("non-ascii")
    assert message("non-ascii").count("non-ASCII") == 1
    assert "has '%ZZ', which is not an escape" in message("malformed")


@pytest.mark.parametrize("part_name", ["/word/no%2", "/word/x%", "/word/%2-.xml"])
def test_an_escape_cut_short_is_not_an_escape(tmp_path, part_name):
    assert [f.severity for f in pkg012(with_override(tmp_path, part_name))] == [Severity.ERROR]


def test_one_finding_per_override(tmp_path):
    path = with_override(tmp_path, "/word/%6Eo%74here.xml")
    [finding] = pkg012(path)
    assert finding.message.count("escapes") == 2


def test_the_control_and_its_other_escapes_are_clean(tmp_path):
    assert OBSERVED["control"]["word"] == "opens"
    assert pkg012(SOURCE) == []
    assert pkg012(with_override(tmp_path, "/word/a%5Bb%5D%3B.xml")) == []
