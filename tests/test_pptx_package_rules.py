"""The package rules run on a .pptx, as PowerPoint reads its package.

PowerPoint for Mac asked to repair, and on Cancel opened nothing, for every
committed variant whose defect Word refuses, and opened the others; a picture
whose relationship is broken it showed as one it can't display. Through 0.8.4
check_pptx reported none of these defects but a malformed slide.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

import pytest

from conftest import ROOT, needs_zlib_bytes
from ooxml_integrity import Severity, check_pptx
from ooxml_integrity.coverage import pptx_coverage
from ooxml_integrity.doctor import UNAVAILABLE_CHECKS
from ooxml_integrity.inspector import Inspector
from research.pptx_package import SOURCE, VARIANTS, build

EVIDENCE = ROOT / "evidence" / "pptx-package-rules"
OBSERVED = json.loads((EVIDENCE / "observations.json").read_text())
PACKAGE = ("PKG", "REL", "XML")


def package(path):
    return [f for f in check_pptx(path) if f.code.startswith(PACKAGE)]


def recorded(path):
    return [{"code": f.code, "severity": f.severity.value, "part": f.part} for f in package(path)]


@needs_zlib_bytes
def test_variants_rebuild_byte_for_byte(tmp_path):
    manifest = build(tmp_path)
    assert manifest["source_sha256"] == OBSERVED["seed"]["sha256"]
    for name, variant in manifest["variants"].items():
        assert variant["sha256"] == OBSERVED["variants"][name]["sha256"]
        committed = EVIDENCE / OBSERVED["variants"][name]["file"]
        assert hashlib.sha256(committed.read_bytes()).hexdigest() == variant["sha256"]


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_an_error_exactly_where_powerpoint_refused_or_lost_the_picture(name):
    observed = OBSERVED["variants"][name]
    errors = [f for f in package(EVIDENCE / observed["file"]) if f.severity is Severity.ERROR]
    lost = "The picture can't be displayed" in observed.get("shows", "")
    assert bool(errors) == (observed["powerpoint"] == "refused" or lost)
    assert recorded(EVIDENCE / observed["file"]) == observed["findings"]


def test_the_seed_and_the_decks_of_this_repository_have_no_package_finding():
    assert OBSERVED["control"]["powerpoint"] == "opens"
    assert package(SOURCE) == []
    decks = subprocess.run(["git", "ls-files", "*.pptx"], cwd=ROOT, capture_output=True,
                           text=True, check=True).stdout.split()
    assert decks and all(package(ROOT / deck) == []
                         for deck in decks if not deck.startswith("evidence/pptx-package-rules/"))


def message(name, code):
    [finding] = [f for f in package(EVIDENCE / f"variants/{name}.pptx") if f.code == code]
    return finding.message


def test_the_messages_say_what_powerpoint_does():
    assert message("default-repeated", "PKG011") == (
        'Default for extension "xml" declared 2 times - PowerPoint asks to repair the presentation')
    assert message("office-document-missing", "REL001") == (
        "_rels/.rels has no officeDocument relationship - PowerPoint asks to repair the presentation")
    assert message("hyperlink-dangling", "REL001").endswith(
        "- PowerPoint asks to repair the presentation or shows the object as missing")
    assert message("thumbnail-missing", "REL002") == (
        "rId2 points at a missing part: docProps/thumbnail.jpeg - PowerPoint opens the deck without it")
    assert message("target-missing", "REL002") == "rId3 points at a missing part: ../media/image2.png"
    assert "Word" not in " ".join(f.message for name in VARIANTS
                                  for f in package(EVIDENCE / f"variants/{name}.pptx"))


def test_the_word_rules_for_the_main_part_and_unused_relationships_do_not_run():
    # Inspector reads the seed as a Word document: its main part is not one,
    # and PowerPoint relates layouts without naming them in the slide.
    word = {f.code for f in Inspector(SOURCE).run()}
    assert {"PKG006", "REL003"} <= word
    assert {f.code for f in check_pptx(SOURCE)}.isdisjoint({"PKG006", "PKG009", "PKG010", "REL003"})


def test_an_unreadable_archive_is_reported_as_before(tmp_path):
    path = tmp_path / "not-a-zip.pptx"
    path.write_bytes(b"not a zip")
    findings = check_pptx(path)
    assert [(f.code, f.severity) for f in findings] == [("PKG002", Severity.ERROR)]
    assert findings[0].message == "invalid or unsupported ZIP directory: missing or truncated end record"
    assert [f.code for f in check_pptx(tmp_path / "missing.pptx")] == ["PKG000"]


def test_coverage_marks_package_integrity_checked_or_skipped(monkeypatch):
    def items(findings):
        return {i.id: i for i in pptx_coverage(SOURCE, findings).items}

    item = items(check_pptx(SOURCE))["pptx.package-integrity"]
    assert item.status.value == "checked"
    assert "pptx.package-integrity" not in {c["id"] for c in UNAVAILABLE_CHECKS}

    def check_relationships(self):
        raise RuntimeError("boom")
    from ooxml_integrity.inspector import PresentationInspector
    monkeypatch.setattr(PresentationInspector, "CHECKS",
                        (Inspector.check_content_types, check_relationships))
    findings = check_pptx(SOURCE)
    assert [f.code for f in findings if f.code == "INT001"] == ["INT001"]
    assert items(findings)["pptx.package-integrity"].status.value == "skipped"
