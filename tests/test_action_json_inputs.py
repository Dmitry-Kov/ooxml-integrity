"""The Action's JSON report must preserve the run's inputs and existing documents."""
from __future__ import annotations

import json
import os

import pytest
from test_action_contract import _check_step

from ooxml_integrity.policy import make_baseline


@pytest.mark.parametrize("role", ["checked", "against"])
@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_action_json_report_preserves_input_documents(tmp_path, tmp_docx, role, alias):
    original = tmp_docx.read_bytes()
    edited = tmp_path / "edited"
    edited.mkdir()
    first, second = edited / "first.docx", edited / "second.docx"
    for document in (first, second):
        document.write_bytes(original)
    target = second if role == "checked" else tmp_docx
    report = target if alias == "direct" else tmp_path / "report.json"
    try:
        if alias == "hardlink":
            os.link(target, report)
        elif alias == "symlink":
            report.symlink_to(target)
    except (NotImplementedError, OSError) as e:
        pytest.skip(f"{alias} unavailable: {e}")

    result, outputs = _check_step(tmp_path, {"files": "edited/*.docx", "against": tmp_docx.name,
                                             "json-report": report.relative_to(tmp_path).as_posix()})
    assert result.returncode == 2, result.stdout + result.stderr
    assert outputs["exit-code"] == "2"
    assert "json-report" in result.stderr and target.name in result.stderr
    for document in (first, second, tmp_docx, report):
        assert document.read_bytes() == original


@pytest.mark.parametrize("existing", [False, True], ids=["new", "replace"])
def test_action_json_report_writes_a_separate_file(tmp_path, tmp_docx, existing):
    report = tmp_path / "report.json"
    if existing:
        report.write_text(json.dumps({"previous": "x" * 100_000}), encoding="utf-8")
    original = tmp_docx.read_bytes()
    result, outputs = _check_step(tmp_path, {"files": tmp_docx.name, "json-report": report.name})
    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs["exit-code"] == "0"
    [entry] = json.loads(report.read_text(encoding="utf-8"))["files"]
    assert entry["path"] == tmp_docx.name
    assert entry["summary"] == {"error": 0, "warn": 0, "info": 0}
    assert tmp_docx.read_bytes() == original


def test_action_json_report_preserves_source_when_glob_matches_nothing(tmp_path, tmp_docx):
    original = tmp_docx.read_bytes()
    result, _ = _check_step(tmp_path, {"files": "edited/*.docx", "against": tmp_docx.name,
                                       "json-report": tmp_docx.name})
    assert result.returncode == 2, result.stdout + result.stderr
    assert tmp_docx.read_bytes() == original


def test_action_json_report_directory_cannot_redirect_copy_to_input(tmp_path, tmp_docx):
    original = tmp_docx.read_bytes()
    directory = tmp_path / "reports"
    directory.mkdir()
    # A directory argument to cp would write to this existing child.
    alias = directory / "report.json"
    try:
        os.link(tmp_docx, alias)
    except OSError as exc:
        pytest.skip(f"hardlink unavailable: {exc}")
    result, _ = _check_step(tmp_path, {"files": tmp_docx.name, "json-report": directory.name})
    assert result.returncode == 2, result.stdout + result.stderr
    assert tmp_docx.read_bytes() == alias.read_bytes() == original


@pytest.mark.parametrize("conflict,separate", [("json-report", "sarif"), ("sarif", "json-report")])
@pytest.mark.parametrize("existing", [False, True], ids=["new", "previous"])
def test_action_reports_preserve_baseline_and_separate_report(tmp_path, tmp_docx, conflict, separate,
                                                              existing):
    baseline = tmp_path / "accepted.json"
    original = json.dumps(make_baseline({})).encode()
    baseline.write_bytes(original)
    other = tmp_path / "separate-report.json"
    if existing:
        other.write_bytes(b"previous report")
    result, outputs = _check_step(tmp_path, {"files": tmp_docx.name, "baseline": baseline.name,
                                             conflict: baseline.name, separate: other.name})
    assert result.returncode == 2, result.stdout + result.stderr
    assert outputs["exit-code"] == "2" and "reports-ready" not in outputs
    assert conflict in result.stderr and baseline.name in result.stderr
    assert baseline.read_bytes() == original
    if existing:
        assert other.read_bytes() == b"previous report"
    else:
        assert not other.exists()


@pytest.mark.parametrize("existing", [False, True], ids=["new", "previous"])
def test_action_refuses_a_shared_destination_for_both_reports(tmp_path, tmp_docx, existing):
    destination = tmp_path / "report.json"
    if existing:
        destination.write_bytes(b"previous report")
    result, outputs = _check_step(tmp_path, {"files": tmp_docx.name, "sarif": destination.name,
                                             "json-report": destination.name})
    assert result.returncode == 2, result.stdout + result.stderr
    assert outputs["exit-code"] == "2" and "reports-ready" not in outputs
    assert "json-report" in result.stderr and "sarif" in result.stderr
    if existing:
        assert destination.read_bytes() == b"previous report"
    else:
        assert not destination.exists()


@pytest.mark.parametrize("filename, explicit", [
    ("policy.toml", True), (".ooxml-integrity.toml", False), ("pyproject.toml", False),
])
def test_action_json_report_preserves_loaded_config(tmp_path, tmp_docx, filename, explicit):
    config = tmp_path / filename
    original = b'fail-on = "warn"\n'
    if filename == "pyproject.toml":
        original = b"[tool.ooxml-integrity]\n" + original
    config.write_bytes(original)
    destination = config
    if filename == ".ooxml-integrity.toml":
        destination = tmp_path / "report.json"
        try:
            os.link(config, destination)
        except OSError as exc:
            pytest.skip(f"hardlink unavailable: {exc}")
    inputs = {"files": tmp_docx.name, "json-report": destination.name}
    if explicit:
        inputs["config"] = config.name
    result, outputs = _check_step(tmp_path, inputs)
    assert result.returncode == 2, result.stdout + result.stderr
    assert outputs["exit-code"] == "2"
    assert "json-report" in result.stderr and destination.name in result.stderr
    assert config.read_bytes() == destination.read_bytes() == original


def test_action_json_report_with_config_disabled(tmp_path, tmp_docx):
    unused = tmp_path / ".ooxml-integrity.toml"
    unused.write_text('fail-on = "warn"\n', encoding="utf-8")
    result, outputs = _check_step(tmp_path, {"files": tmp_docx.name, "config": "none",
                                             "json-report": unused.name})
    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs["exit-code"] == "0"
    assert json.loads(unused.read_text(encoding="utf-8"))["config"] is None


@pytest.mark.parametrize("suffix,symlink", [
    (".docx", False), (".PPTX", False), (".potx", False), (".ppsx", False), (".docx", True),
], ids=["docx", "PPTX", "potx", "ppsx", "json-link-to-docx"])
def test_action_json_report_preserves_unselected_office_file(tmp_path, tmp_docx, root, suffix, symlink):
    document = tmp_path / ("review-copy" + suffix)
    source = tmp_docx if suffix == ".docx" else root / "corpus" / "deck.pptx"
    original = source.read_bytes()
    document.write_bytes(original)
    destination = document
    if symlink:
        destination = tmp_path / "report.json"
        try:
            destination.symlink_to(document)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"symlink unavailable: {exc}")
    result, outputs = _check_step(tmp_path, {"files": tmp_docx.name, "json-report": destination.name})
    assert result.returncode == 2, result.stdout + result.stderr
    assert outputs["exit-code"] == "2"
    assert "json-report" in result.stderr and destination.name in result.stderr
    assert document.read_bytes() == original
