"""An explicit --against must never pass when comparison did not run."""
from __future__ import annotations

import json

from conftest import run_cli

from ooxml_integrity.cli import EXIT_FINDINGS, EXIT_OK


def _fid000(payload: dict) -> dict:
    findings = payload["files"][0]["findings"]
    matches = [f for f in findings if f["code"] == "FID000"]
    assert len(matches) == 1, findings
    return matches[0]


def test_corrupt_existing_source_fails_closed(base_docx, tmp_path):
    source = tmp_path / "corrupt-source.docx"
    source.write_bytes(b"not an OOXML package")

    result = run_cli(
        "check", str(base_docx), "--against", str(source), "--json",
    )

    assert result.returncode == EXIT_FINDINGS, result.stdout + result.stderr
    finding = _fid000(json.loads(result.stdout))
    assert finding["severity"] == "error"
    assert "comparison was NOT performed" in finding["message"]


def test_new_baseline_suppresses_the_document_defect_but_not_a_failed_comparison(
        tmp_path, runs_dir):
    edited = runs_dir / "t4_fast_fee" / "agreement.docx"  # known CMT005
    source = tmp_path / "original.docx"
    source.write_bytes(b"incomplete download")
    baseline = tmp_path / "baseline.json"
    args = ("check", str(edited), "--against", str(source), "--no-config")

    written = run_cli(*args, "--write-baseline", str(baseline))
    assert written.returncode == EXIT_OK, written.stderr
    recorded = json.loads(baseline.read_text(encoding="utf-8"))["findings"]
    assert not any("::FID000::" in key for key in recorded)
    assert "1 FID000 finding(s) not recorded" in written.stderr
    assert "the requested source comparison did not complete" in written.stderr

    repeated = run_cli(*args, "--baseline", str(baseline), "--json", "--coverage")
    assert repeated.returncode == EXIT_FINDINGS, repeated.stdout + repeated.stderr
    entry = json.loads(repeated.stdout)["files"][0]
    assert [(f["code"], f["severity"]) for f in entry["findings"]] == [("FID000", "error")]
    assert [(f["code"], f["suppressed_because"]) for f in entry["suppressed"]] == [
        ("CMT005", "in baseline")]
    coverage = {item["id"]: item["status"] for item in entry["coverage"]["items"]}
    assert coverage["docx.fidelity.main-story"] == "skipped"


def test_existing_v2_baseline_cannot_accept_a_failed_comparison(tmp_path, tmp_docx):
    source = tmp_path / "original.docx"
    source.write_bytes(b"incomplete download")
    baseline = tmp_path / "old-baseline.json"
    # Use the fingerprint an earlier CLI actually wrote for this path.
    # Calling the current writer would no longer exercise the old allowance.
    key = f"{tmp_docx.as_posix()}::FID000::"
    baseline.write_text(json.dumps({"version": 2, "findings": {key: 1}}), encoding="utf-8")
    args = ("check", str(tmp_docx), "--against", str(source), "--introduced",
            "--baseline", str(baseline), "--no-config", "--json", "--coverage")

    failed = run_cli(*args)
    assert failed.returncode == EXIT_FINDINGS, failed.stdout + failed.stderr
    payload = json.loads(failed.stdout)
    assert _fid000(payload)["severity"] == "error"
    assert payload["files"][0]["suppressed"] == []

    source.write_bytes(tmp_docx.read_bytes())
    restored = run_cli(*args)
    assert restored.returncode == EXIT_OK, restored.stdout + restored.stderr
    entry = json.loads(restored.stdout)["files"][0]
    assert entry["findings"] == entry["suppressed"] == []
    coverage = {item["id"]: item["status"] for item in entry["coverage"]["items"]}
    assert coverage["docx.fidelity.main-story"] == "checked"


def test_pptx_source_comparison_not_implemented_fails_closed(
        root, base_docx):
    deck = root / "corpus" / "deck.pptx"

    result = run_cli(
        "check", str(deck), "--against", str(base_docx), "--json",
    )

    assert result.returncode == EXIT_FINDINGS, result.stdout + result.stderr
    finding = _fid000(json.loads(result.stdout))
    assert finding["severity"] == "error"
    assert "comparison was NOT performed" in finding["message"]
    assert "not implemented for .pptx" in finding["message"]
