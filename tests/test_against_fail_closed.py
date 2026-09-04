"""An explicit --against must never pass when comparison did not run."""
from __future__ import annotations

import json

from conftest import run_cli

from ooxml_integrity.cli import EXIT_FINDINGS


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
