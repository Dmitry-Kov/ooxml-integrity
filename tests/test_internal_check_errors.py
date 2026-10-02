"""A check that raises must fail the run, show in coverage and stay out of baselines.

Until this was fixed, INT001 was a WARN: the default error gate exited 0, the
crashed check's surface stayed `checked` in coverage, and `--write-baseline`
recorded the crash so later runs hid it.
"""
from __future__ import annotations

import json

import pytest

from ooxml_integrity import pptx_checks
from ooxml_integrity.cli import EXIT_FINDINGS, EXIT_OK, main
from ooxml_integrity.coverage import CHECK_SURFACES, CoverageStatus, coverage_for
from ooxml_integrity.finding import Severity
from ooxml_integrity.inspector import Inspector, check
from ooxml_integrity.policy import Policy, apply_baseline, fingerprint
from ooxml_integrity.pptx_checks import check_pptx


def check_styles(self):  # stands in for Inspector.check_styles
    raise RuntimeError("synthetic")


def check_overlap(deck):  # stands in for pptx_checks.check_overlap
    raise RuntimeError("synthetic")


@pytest.fixture
def broken_styles(monkeypatch):
    checks = tuple(check_styles if c.__name__ == "check_styles" else c
                   for c in Inspector.CHECKS)
    assert checks != Inspector.CHECKS
    monkeypatch.setattr(Inspector, "CHECKS", checks)


@pytest.fixture
def deck(root):
    return root / "corpus" / "deck.pptx"


def _int001(findings):
    matches = [f for f in findings if f.code == "INT001"]
    assert len(matches) == 1, findings
    return matches[0]


def test_crash_is_an_error_that_names_the_check(broken_styles, base_docx):
    finding = _int001(check(base_docx))

    assert finding.severity is Severity.ERROR
    assert "check_styles did NOT complete: RuntimeError: synthetic" in finding.message
    assert finding.extra == {"check": "check_styles", "exception": "RuntimeError"}


def test_default_gate_fails_on_a_crash(broken_styles, base_docx, capsys):
    assert main(["check", str(base_docx), "--no-config", "--json"]) == EXIT_FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert [f["code"] for f in payload["files"][0]["findings"]] == ["INT001"]


def test_control_without_a_crash_passes(base_docx, capsys):
    assert main(["check", str(base_docx), "--no-config", "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"][0]["findings"] == []


def test_coverage_marks_only_the_crashed_surface_skipped(broken_styles, base_docx):
    control = {item.id: item for item in coverage_for(base_docx, []).items}
    crashed = {item.id: item for item in coverage_for(base_docx, check(base_docx)).items}

    assert control["docx.styles"].status is CoverageStatus.CHECKED
    styles = crashed.pop("docx.styles")
    assert styles.status is CoverageStatus.SKIPPED
    assert "check_styles did NOT complete" in styles.reason
    assert styles.count == control.pop("docx.styles").count
    assert crashed == control


def test_write_baseline_leaves_a_crash_out(broken_styles, base_docx, tmp_path, capsys):
    baseline = tmp_path / "baseline.json"

    assert main(["check", str(base_docx), "--no-config",
                 "--write-baseline", str(baseline)]) == EXIT_OK
    err = capsys.readouterr().err
    assert "1 INT001 finding(s) not recorded" in err
    assert json.loads(baseline.read_text())["findings"] == {}

    assert main(["check", str(base_docx), "--no-config",
                 "--baseline", str(baseline)]) == EXIT_FINDINGS


def test_a_baseline_entry_does_not_absorb_a_crash(broken_styles, base_docx):
    """Hand-edited or older baselines may already list INT001."""
    findings = check(base_docx)
    allowance = {fingerprint(str(base_docx), _int001(findings)): 1}

    kept, dropped = apply_baseline(str(base_docx), findings, allowance)

    assert [f.code for f in kept] == ["INT001"]
    assert dropped == []


def test_config_ignore_with_a_reason_still_turns_it_off(broken_styles, base_docx):
    policy = Policy._from_dict({"ignore": [
        {"code": "INT001", "reason": "upstream bug #1, styles checked by hand"},
    ]})

    kept, dropped = policy.apply(str(base_docx), check(base_docx))

    assert kept == []
    assert [f.code for f, _ in dropped] == ["INT001"]


def test_pptx_crash_is_an_error_and_skips_its_surface(monkeypatch, deck):
    control = {item.id: item for item in coverage_for(deck, check_pptx(deck)).items}
    monkeypatch.setattr(pptx_checks, "CHECKS", tuple(
        check_overlap if c.__name__ == "check_overlap" else c
        for c in pptx_checks.CHECKS
    ))

    findings = check_pptx(deck)
    finding = _int001(findings)
    crashed = {item.id: item for item in coverage_for(deck, findings).items}

    assert finding.severity is Severity.ERROR
    assert finding.extra["check"] == "check_overlap"
    assert control["pptx.text-shape-overlap"].status is CoverageStatus.CHECKED
    assert crashed.pop("pptx.text-shape-overlap").status is CoverageStatus.SKIPPED
    control.pop("pptx.text-shape-overlap")
    assert crashed == control


def test_every_check_has_coverage_surfaces(base_docx, deck):
    names = {c.__name__ for c in Inspector.CHECKS}
    names |= {c.__name__ for c in pptx_checks.CHECKS}
    assert names == set(CHECK_SURFACES)

    reported = {item.id for item in coverage_for(base_docx, []).items}
    reported |= {item.id for item in coverage_for(deck, []).items}
    for check_name, surfaces in CHECK_SURFACES.items():
        assert surfaces and set(surfaces) <= reported, check_name
