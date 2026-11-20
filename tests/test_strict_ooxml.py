"""Strict Open XML is reported as unsupported, not passed or called unreadable.

Word and PowerPoint save Strict files: 17 Word and 4 PowerPoint Strict files
are in the public corpora. The rules read Transitional names only, so a Strict
DOCX used to pass with nothing checked and a Strict PPTX failed as unreadable.
"""
from __future__ import annotations

import json
import zipfile

import pytest

from conftest import repack, run_cli

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


@pytest.fixture(params=[("base.docx", "word/document.xml"), ("deck.pptx", "ppt/presentation.xml")],
                ids=["docx", "pptx"])
def strict_package(root, tmp_path, request):
    name, main_part = request.param
    source = root / "corpus" / name
    return _strict(source, tmp_path / ("strict" + source.suffix)), main_part


def test_write_baseline_omits_strict_but_still_records_a_checked_defect(strict_package, runs_dir, tmp_path):
    strict, _ = strict_package
    reviewed = runs_dir / "t4_fast_fee" / "agreement.docx"  # one orphaned comment
    baseline = tmp_path / "baseline.json"
    written = run_cli("check", str(strict), str(reviewed), "--no-config", "--write-baseline", str(baseline))
    assert written.returncode == 0, written.stderr
    assert "PKG009" in written.stderr and "Strict" in written.stderr
    recorded = json.loads(baseline.read_bytes())["findings"]
    assert recorded == {f"{reviewed.as_posix()}::CMT005::word/comments.xml": 1}

    accepted = run_cli("check", str(reviewed), "--no-config", "--baseline", str(baseline), "--json")
    assert accepted.returncode == 0, accepted.stderr
    [entry] = json.loads(accepted.stdout)["files"]
    assert entry["findings"] == []
    assert [(f["code"], f["suppressed_because"]) for f in entry["suppressed"]] == [("CMT005", "in baseline")]


def test_existing_v2_baseline_leaves_strict_visible_at_the_configured_severity(strict_package, tmp_path):
    strict, main_part = strict_package
    # Earlier releases wrote this allowance. Build it independently of today's writer.
    key = f"{strict.as_posix()}::PKG009::{main_part}"
    baseline = tmp_path / "old-baseline.json"
    baseline.write_text(json.dumps({"version": 2, "findings": {key: 1}}), encoding="utf-8")
    args = ("check", str(strict), "--baseline", str(baseline), "--json")
    config = tmp_path / "policy.toml"
    config.write_text('[severity]\nPKG009 = "warn"\n', encoding="utf-8")

    for options, severity, code in [(("--no-config",), "error", 1), (("--config", str(config)), "warn", 0)]:
        result = run_cli(*args, *options)
        assert result.returncode == code, result.stdout + result.stderr
        [entry] = json.loads(result.stdout)["files"]
        assert [(f["code"], f["severity"], f["part"]) for f in entry["findings"]] == [
            ("PKG009", severity, main_part)]
        assert entry["suppressed"] == []
