"""CLI contract: exit codes are what CI depends on, so they get real tests."""
from __future__ import annotations

import json

import pytest
from conftest import read_part, repack, run_cli

from ooxml_integrity.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main


def test_clean_file_exits_zero(base_docx):
    r = run_cli("check", str(base_docx))
    assert r.returncode == EXIT_OK, r.stderr
    assert "clean" in r.stdout


def test_defect_exits_one(runs_dir, base_docx):
    fast = runs_dir / "t4_fast_table" / "agreement.docx"
    if not fast.exists():
        pytest.skip("agent run output missing")
    r = run_cli("check", str(fast), "--against", str(base_docx))
    assert r.returncode == EXIT_FINDINGS, r.stdout + r.stderr
    assert "CMT005" in r.stdout


def test_careful_run_exits_zero(runs_dir, base_docx):
    careful = runs_dir / "t2_pres" / "agreement.docx"
    if not careful.exists():
        pytest.skip("agent run output missing")
    r = run_cli("check", str(careful), "--against", str(base_docx))
    assert r.returncode == EXIT_OK, r.stdout


def test_fail_on_info_catches_the_informational_notes(runs_dir, base_docx):
    careful = runs_dir / "t2_pres" / "agreement.docx"
    if not careful.exists():
        pytest.skip("agent run output missing")
    r = run_cli("check", str(careful), "--against", str(base_docx),
                "--fail-on", "info")
    assert r.returncode == EXIT_FINDINGS


def test_missing_file_exits_one_not_two(tmp_path):
    """A missing input is a finding about the file, not a usage error."""
    r = run_cli("check", str(tmp_path / "absent.docx"))
    assert r.returncode == EXIT_FINDINGS
    assert "PKG000" in r.stdout


def test_bad_fail_on_is_a_usage_error(base_docx):
    r = run_cli("check", str(base_docx), "--fail-on", "catastrophic")
    assert r.returncode == EXIT_USAGE
    assert "unknown severity" in r.stderr


def test_missing_against_is_a_usage_error(base_docx, tmp_path):
    r = run_cli("check", str(base_docx), "--against", str(tmp_path / "no.docx"))
    assert r.returncode == EXIT_USAGE
    assert "not found" in r.stderr


def test_no_match_is_a_usage_error():
    r = run_cli("check", "definitely/nothing/here/*.docx")
    assert r.returncode == EXIT_USAGE


def test_json_output_is_valid_and_shaped(runs_dir, base_docx):
    fast = runs_dir / "t4_fast_table" / "agreement.docx"
    if not fast.exists():
        pytest.skip("agent run output missing")
    r = run_cli("check", str(fast), "--against", str(base_docx), "--json")
    assert r.returncode == EXIT_FINDINGS
    payload = json.loads(r.stdout)
    assert payload["fail_on"] == "error"
    assert len(payload["files"]) == 1
    f = payload["files"][0]
    assert set(f) == {"path", "summary", "worst", "findings", "suppressed"}
    assert f["suppressed"] == [], "nothing should be suppressed without config"
    assert f["worst"] == "error"
    assert f["summary"]["error"] >= 1
    assert any(x["code"] == "CMT005" for x in f["findings"])
    for x in f["findings"]:
        assert x["severity"] in ("error", "warn", "info")
        assert x["message"]


def test_several_files_at_once(base_docx, runs_dir):
    fast = runs_dir / "t4_fast_table" / "agreement.docx"
    if not fast.exists():
        pytest.skip("agent run output missing")
    r = run_cli("check", str(base_docx), str(fast), "--json")
    payload = json.loads(r.stdout)
    assert len(payload["files"]) == 2


def test_glob_expansion(runs_dir, base_docx):
    r = run_cli("check", "runs/*/agreement.docx", "--json")
    if r.returncode == EXIT_USAGE:
        pytest.skip("runs/ not populated")
    payload = json.loads(r.stdout)
    assert len(payload["files"]) >= 2


def test_quiet_hides_below_threshold(runs_dir, base_docx):
    careful = runs_dir / "t2_pres" / "agreement.docx"
    if not careful.exists():
        pytest.skip("agent run output missing")
    loud = run_cli("check", str(careful), "--against", str(base_docx))
    quiet = run_cli("check", str(careful), "--against", str(base_docx), "--quiet")
    assert "FID002" in loud.stdout
    assert "FID002" not in quiet.stdout


def test_main_is_importable_and_returns_codes(base_docx):
    """Callable in-process, so it can be used from other Python without shelling."""
    assert main(["check", str(base_docx)]) == EXIT_OK


def test_version_flag():
    r = run_cli("--version")
    assert r.returncode == EXIT_OK
    assert "ooxml-integrity" in r.stdout


def test_comparison_against_a_corrupt_file_degrades_gracefully(
        base_docx, tmp_path, tmp_docx):
    junk = tmp_path / "junk.docx"
    junk.write_bytes(b"not a zip")
    r = run_cli("check", str(junk), "--against", str(base_docx))
    assert r.returncode == EXIT_FINDINGS
    assert "PKG002" in r.stdout
    assert "Traceback" not in r.stderr


def test_named_missing_file_is_a_finding_but_empty_glob_is_usage(tmp_path, base_docx):
    """Two different situations, two different exit codes, both messages sensible."""
    named = run_cli("check", str(tmp_path / "absent.docx"))
    assert named.returncode == EXIT_FINDINGS
    assert "PKG000" in named.stdout

    empty = run_cli("check", "nothing/here/*.docx")
    assert empty.returncode == EXIT_USAGE
    assert "no files matched" in empty.stderr
    assert "PKG000" not in empty.stdout


def test_partial_glob_match_warns_but_proceeds(base_docx):
    r = run_cli("check", str(base_docx), "nothing/here/*.docx")
    assert r.returncode == EXIT_OK
    assert "no files matched" in r.stderr
    assert "clean" in r.stdout
