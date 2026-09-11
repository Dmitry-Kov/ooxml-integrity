"""A1 regression: removing styles and their declarations must not hide references."""
from __future__ import annotations

import json
import zipfile
from collections import Counter

import pytest
from lxml import etree

from conftest import read_part, repack, run_cli

from ooxml_integrity import check
from ooxml_integrity.archive import DEFAULT_ARCHIVE_LIMITS
from ooxml_integrity.cli import EXIT_FINDINGS, EXIT_OK, _run_one
from ooxml_integrity.coverage import docx_coverage


DOC = "word/document.xml"
STYLES = "word/styles.xml"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
STYLE_TAGS = {W + tag for tag in ("pStyle", "rStyle", "tblStyle")}


def _without_styles(source, target):
    """Keep the document bytes, removing the part and both package declarations."""
    with zipfile.ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()
                 if name != STYLES}
    for part, attribute, value in (
        ("word/_rels/document.xml.rels", "Type",
         "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"),
        ("[Content_Types].xml", "PartName", "/word/styles.xml"),
    ):
        tree = etree.fromstring(parts[part])
        entries = [el for el in tree if el.get(attribute) == value]
        assert len(entries) == 1, "the corpus package declarations changed"
        tree.remove(entries[0])
        parts[part] = etree.tostring(tree)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return target


def _keep_style_refs(source, target, tag):
    """Retain one kind of style reference, or none, before making an edited copy."""
    document = etree.fromstring(read_part(source, DOC).encode())
    for element in list(document.iter()):
        if element.tag in STYLE_TAGS and element.tag != W + tag:
            element.getparent().remove(element)
    return repack(source, target, {DOC: etree.tostring(document)})


@pytest.fixture
def missing_styles(base_docx, tmp_path):
    return _without_styles(base_docx, tmp_path / "missing-styles.docx")


def _style_coverage(report):
    return next(item for item in report["items"] if item["id"] == "docx.styles")


@pytest.mark.parametrize("against", [False, True], ids=["self-check", "against"])
def test_original_missing_styles_reproduction(base_docx, missing_styles, against):
    assert read_part(missing_styles, DOC) == read_part(base_docx, DOC)
    source = base_docx if against else None
    findings = _run_one(missing_styles, source, DEFAULT_ARCHIVE_LIMITS)

    assert len(findings) == 17
    assert {f.code for f in findings} == {"STY001"}
    assert Counter(f.severity.value for f in findings) == {"error": 13, "warn": 4}
    document = etree.fromstring(read_part(missing_styles, DOC).encode())
    for finding in findings:
        assert finding.part == DOC
        elements = document.xpath(finding.where, namespaces={"w": W[1:-1]})
        assert len(elements) == 1 and elements[0].tag in STYLE_TAGS

    report = docx_coverage(missing_styles, findings, source=source).as_dict()
    styles = _style_coverage(report)
    assert styles["status"] == "checked"
    assert styles["count"] == 17
    assert "styles.xml is missing" in styles["reason"]


@pytest.mark.parametrize("against", [False, True], ids=["self-check", "against"])
def test_missing_styles_cli_json_sarif_and_human(
        base_docx, missing_styles, tmp_path, against):
    args = ["check", str(missing_styles), "--no-config"]
    if against:
        args.extend(["--against", str(base_docx)])
    sarif_path = tmp_path / "report.sarif"
    result = run_cli(*args, "--json", "--coverage", "--sarif", str(sarif_path))

    assert result.returncode == EXIT_FINDINGS, result.stdout + result.stderr
    payload = json.loads(result.stdout)["files"][0]
    assert payload["summary"] == {"error": 13, "warn": 4, "info": 0}
    assert payload["worst"] == "error"
    assert payload["suppressed"] == []
    assert len(payload["findings"]) == 17
    assert {f["code"] for f in payload["findings"]} == {"STY001"}
    assert payload["coverage"]["schema_version"] == 1
    assert _style_coverage(payload["coverage"])["status"] == "checked"
    assert _style_coverage(payload["coverage"])["count"] == 17

    sarif = json.loads(sarif_path.read_text(encoding="utf-8"))
    assert sarif["version"] == "2.1.0"
    results = sarif["runs"][0]["results"]
    assert len(results) == 17
    assert {r["ruleId"] for r in results} == {"STY001"}
    assert Counter(r["level"] for r in results) == {"error": 13, "warning": 4}
    assert {r["properties"]["where"] for r in results} == {
        f["where"] for f in payload["findings"]
    }
    assert all(r["properties"]["part"] == DOC for r in results)

    human = run_cli(*args, "--coverage-details")
    assert human.returncode == EXIT_FINDINGS
    assert "STY001" in human.stdout
    assert "[checked] docx.styles" in human.stdout
    assert "styles.xml is missing" in human.stdout


@pytest.mark.parametrize("tag,count,severity,default_exit", [
    ("pStyle", 12, "error", EXIT_FINDINGS),
    ("tblStyle", 1, "error", EXIT_FINDINGS),
    ("rStyle", 4, "warn", EXIT_OK),
    ("", 0, None, EXIT_OK),
], ids=["paragraph-only", "table-only", "character-only", "no-references"])
def test_missing_styles_severity_and_clean_control(
        base_docx, tmp_path, tag, count, severity, default_exit):
    source = _keep_style_refs(base_docx, tmp_path / "source.docx", tag)
    assert check(source) == []
    edited = _without_styles(source, tmp_path / "edited.docx")
    args = ["check", str(edited), "--against", str(source), "--no-config"]
    result = run_cli(*args, "--json", "--coverage")

    assert result.returncode == default_exit, result.stdout + result.stderr
    payload = json.loads(result.stdout)["files"][0]
    assert len(payload["findings"]) == count
    assert all(f["code"] == "STY001" and f["severity"] == severity
               for f in payload["findings"])
    styles = _style_coverage(payload["coverage"])
    assert styles["status"] == ("checked" if count else "not-present")
    assert styles["count"] == count

    strict = run_cli(*args, "--fail-on", "warn")
    assert strict.returncode == (EXIT_FINDINGS if count else EXIT_OK)


@pytest.mark.parametrize("xml", [
    b'<w:styles xmlns:w="' + W[1:-1].encode() + b'">',
    b'<!DOCTYPE w:styles [<!ENTITY injected "not OOXML">]>'
    b'<w:styles xmlns:w="' + W[1:-1].encode() + b'"/>',
], ids=["malformed", "unsafe"])
@pytest.mark.parametrize("with_refs", [False, True], ids=["no-refs", "with-refs"])
def test_unparseable_styles_skip_resolution_without_a_cascade(
        base_docx, tmp_path, xml, with_refs):
    source = base_docx if with_refs else _keep_style_refs(
        base_docx, tmp_path / "no-refs.docx", "",
    )
    edited = repack(source, tmp_path / "bad-styles.docx", {STYLES: xml})
    result = run_cli("check", str(edited), "--no-config", "--json", "--coverage")

    assert result.returncode == EXIT_FINDINGS, result.stdout + result.stderr
    payload = json.loads(result.stdout)["files"][0]
    assert len(payload["findings"]) == 1
    finding = payload["findings"][0]
    assert (finding["code"], finding["severity"], finding["part"]) == (
        "XML001", "error", STYLES,
    )
    styles = _style_coverage(payload["coverage"])
    assert styles["status"] == "skipped"
    assert styles["count"] == (17 if with_refs else 0)
    assert "could not be safely parsed" in styles["reason"]


@pytest.mark.parametrize("suppression", ["config", "baseline"])
def test_missing_styles_suppression_remains_scoped_and_auditable(
        base_docx, missing_styles, tmp_path, suppression):
    args = ["check", str(missing_styles), "--against", str(base_docx)]
    if suppression == "config":
        config = tmp_path / "config.toml"
        config.write_text(
            '[[ignore]]\ncode = "STY001"\n'
            'path = "**/missing-styles.docx"\nreason = "accepted test fixture"\n',
            encoding="utf-8",
        )
        policy_args = ["--config", str(config)]
    else:
        baseline = tmp_path / "baseline.json"
        recorded = run_cli(*args, "--no-config", "--write-baseline", str(baseline))
        assert recorded.returncode == EXIT_OK, recorded.stdout + recorded.stderr
        saved = json.loads(baseline.read_text(encoding="utf-8"))
        assert saved["version"] == 2
        assert sum(saved["findings"].values()) == 17
        policy_args = ["--no-config", "--baseline", str(baseline)]

    sarif_path = tmp_path / "suppressed.sarif"
    result = run_cli(*args, *policy_args, "--json", "--coverage",
                     "--sarif", str(sarif_path))
    assert result.returncode == EXIT_OK, result.stdout + result.stderr
    payload = json.loads(result.stdout)["files"][0]
    assert payload["findings"] == []
    assert len(payload["suppressed"]) == 17
    assert all(f["code"] == "STY001" for f in payload["suppressed"])
    assert _style_coverage(payload["coverage"])["status"] == "checked"
    assert _style_coverage(payload["coverage"])["count"] == 17
    sarif = json.loads(sarif_path.read_text(encoding="utf-8"))
    results = sarif["runs"][0]["results"]
    assert len(results) == 17
    expected_reason = "accepted test fixture" if suppression == "config" else "in baseline"
    assert all(expected_reason in r["suppressions"][0]["justification"]
               for r in results)

    another = tmp_path / "another.docx"
    another.write_bytes(missing_styles.read_bytes())
    uncovered = run_cli("check", str(another), *policy_args, "--json")
    assert uncovered.returncode == EXIT_FINDINGS, uncovered.stdout + uncovered.stderr
    payload = json.loads(uncovered.stdout)["files"][0]
    assert len(payload["findings"]) == 17
    assert payload["suppressed"] == []


def test_existing_style_baseline_does_not_hide_new_losses(
        base_docx, missing_styles, tmp_path):
    target = tmp_path / "edited.docx"
    styles = read_part(base_docx, STYLES)
    repack(base_docx, target, {
        STYLES: styles.replace('w:styleId="DefinedTerm"',
                               'w:styleId="Renamed"').encode(),
    })
    findings = check(target)
    assert len(findings) == 1 and findings[0].code == "STY001"
    baseline = tmp_path / "existing-v2.json"
    args = ["check", str(target), "--against", str(base_docx), "--no-config"]
    recorded = run_cli(*args, "--write-baseline", str(baseline))
    assert recorded.returncode == EXIT_OK, recorded.stdout + recorded.stderr
    saved = json.loads(baseline.read_text(encoding="utf-8"))
    assert saved["version"] == 2 and sum(saved["findings"].values()) == 1

    target.write_bytes(missing_styles.read_bytes())
    result = run_cli(*args, "--baseline", str(baseline), "--json")
    assert result.returncode == EXIT_FINDINGS, result.stdout + result.stderr
    payload = json.loads(result.stdout)["files"][0]
    assert len(payload["findings"]) == 16
    assert payload["summary"] == {"error": 13, "warn": 3, "info": 0}
    assert len(payload["suppressed"]) == 1
    assert payload["suppressed"][0]["where"] == findings[0].where
