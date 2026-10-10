"""PKG010: a part the main document relates, declared with another content type.

Codex declared the commentsExtended part of all five K5-S1 outputs as
application/vnd.ms-word.commentsExtended+xml. Word for Mac refused them and
opened them once only that string was corrected
(evidence/review-history-benchmark/word-check-content-type).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from conftest import ROOT
from ooxml_integrity import Severity, check
from ooxml_integrity.coverage import CoverageStatus, coverage_for
from ooxml_integrity.policy import fingerprint

BENCH = ROOT / "evidence" / "review-history-benchmark"
CODEX = [BENCH / "captures" / f"codex-{n}" / "K5-S1-comment.docx" for n in range(1, 6)]
VARIANTS = BENCH / "word-check-content-type" / "variants"
WORD_WRITTEN = [BENCH / "sources" / "word-review.docx", BENCH / "sources" / "review-a.docx"]
WRONG = "application/vnd.ms-word.commentsExtended+xml"
RIGHT = "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml"
TYPES = "[Content_Types].xml"


def pkg010(path):
    return [f for f in check(path) if f.code == "PKG010"]


def rewrite(src: Path, dst: Path, edits: dict[str, bytes | None]) -> Path:
    """Copy a package, replacing or (None) removing members; the rest byte for byte."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            if info.filename not in edits:
                zout.writestr(info, zin.read(info.filename))
            elif edits[info.filename] is not None:
                zout.writestr(info, edits[info.filename])
    return dst


def types_of(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read(TYPES).decode("utf-8")


@pytest.mark.parametrize("capture", CODEX, ids=lambda p: p.parent.name)
def test_codex_k5_s1_commentsextended_type_is_an_error(capture):
    [finding] = pkg010(capture)
    assert finding.severity is Severity.ERROR
    assert finding.part == "word/commentsExtended.xml"
    assert finding.extra == {
        "relationship": finding.extra["relationship"],
        "relationship_type": "http://schemas.microsoft.com/office/2011/relationships/commentsExtended",
        "declared": WRONG,
        "expected": RIGHT,
        "relationships_part": "word/_rels/document.xml.rels",
    }
    assert WRONG in finding.message and RIGHT in finding.message


def test_correcting_only_the_content_type_removes_it_and_nothing_else(tmp_path):
    capture = CODEX[1]
    fixed = rewrite(capture, tmp_path / "d6.docx",
                    {TYPES: types_of(capture).replace(WRONG, RIGHT).encode()})
    before = [f for f in check(capture) if f.code != "PKG010"]
    assert pkg010(fixed) == [] and check(fixed) == before


def test_the_stored_word_variants_match_the_capture_and_do_not_fire():
    d6 = VARIANTS / "d6-codex-2-K5-S1-ct-fixed.docx"
    assert types_of(d6) == types_of(CODEX[1]).replace(WRONG, RIGHT)
    for variant in VARIANTS.glob("*.docx"):
        assert pkg010(variant) == [], variant.name


@pytest.mark.parametrize("path", WORD_WRITTEN, ids=lambda p: p.name)
def test_word_written_parts_do_not_fire(path):
    assert pkg010(path) == []


def test_a_default_with_another_type_is_a_declaration_too(tmp_path):
    types = types_of(CODEX[1])
    out = rewrite(CODEX[1], tmp_path / "default.docx", {TYPES: types.replace(
        f'<Override PartName="/word/commentsExtended.xml" ContentType="{WRONG}"/>', "").encode()})
    [finding] = pkg010(out)
    assert finding.extra["declared"] == "application/xml"


def test_no_content_type_or_no_part_is_left_to_pkg005_and_rel002(tmp_path):
    types = types_of(CODEX[1])
    assert '<Default Extension="xml"' in types
    bare = types.replace(f'<Override PartName="/word/commentsExtended.xml" ContentType="{WRONG}"/>', "")
    bare = bare.replace('<Default Extension="xml" ContentType="application/xml"/>', "")
    untyped = rewrite(CODEX[1], tmp_path / "untyped.docx", {TYPES: bare.encode()})
    codes = {f.code for f in check(untyped) if f.part == "word/commentsExtended.xml"}
    assert "PKG005" in codes and "PKG010" not in codes
    missing = rewrite(CODEX[1], tmp_path / "missing.docx", {"word/commentsExtended.xml": None})
    codes = {f.code for f in check(missing)}
    assert "REL002" in codes and "PKG010" not in codes


def test_case_and_parameters_do_not_make_a_mismatch(tmp_path):
    types = types_of(CODEX[1])
    upper = rewrite(CODEX[1], tmp_path / "upper.docx",
                    {TYPES: types.replace(WRONG, RIGHT.upper()).encode()})
    params = rewrite(CODEX[1], tmp_path / "params.docx",
                     {TYPES: types.replace(WRONG, RIGHT + "; charset=utf-8").encode()})
    name = rewrite(CODEX[1], tmp_path / "name.docx", {TYPES: types.replace(
        f'"/word/commentsExtended.xml" ContentType="{WRONG}"',
        f'"/WORD/commentsextended.xml" ContentType="{RIGHT}"').encode()})
    assert pkg010(upper) == pkg010(params) == pkg010(name) == []


@pytest.mark.parametrize("main_type", [
    "application/vnd.ms-word.document.macroEnabled.main+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
])
def test_templates_and_macro_enabled_documents_are_not_checked(tmp_path, main_type):
    plain = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    types = types_of(CODEX[1])
    assert plain in types
    out = rewrite(CODEX[1], tmp_path / "main.docx", {TYPES: types.replace(plain, main_type).encode()})
    assert pkg010(out) == []


def test_strict_is_not_checked(tmp_path):
    with zipfile.ZipFile(CODEX[1]) as z:
        document = z.read("word/document.xml").decode("utf-8")
    strict = document.replace("http://schemas.openxmlformats.org/wordprocessingml/2006/main",
                              "http://purl.oclc.org/ooxml/wordprocessingml/main")
    out = rewrite(CODEX[1], tmp_path / "strict.docx", {"word/document.xml": strict.encode()})
    codes = {f.code for f in check(out)}
    assert "PKG009" in codes and "PKG010" not in codes


def test_baseline_identity_is_the_part_and_coverage_names_the_surface(tmp_path):
    [finding] = pkg010(CODEX[0])
    assert fingerprint("out.docx", finding) == "out.docx::PKG010::word/commentsExtended.xml"
    items = {i.id: i for i in coverage_for(CODEX[0], check(CODEX[0])).items}
    item = items["package.related-content-types"]
    assert item.status is CoverageStatus.CHECKED and item.count == 8


def test_coverage_says_when_the_main_part_was_not_read(tmp_path):
    plain = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    template = "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
    out = rewrite(CODEX[1], tmp_path / "template.docx",
                  {TYPES: types_of(CODEX[1]).replace(plain, template).encode()})
    item = {i.id: i for i in coverage_for(out, check(out)).items}["package.related-content-types"]
    assert item.status is CoverageStatus.UNSUPPORTED and template in item.reason
