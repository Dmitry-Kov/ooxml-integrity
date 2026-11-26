"""Tests for PR #3: unified runner.py, verify() API, schema contract, and --json-out."""
from __future__ import annotations

import ast
import hashlib
import io
import json
from pathlib import Path

import pytest
from lxml import etree

from ooxml_integrity import (
    SCHEMA_VERSION,
    VERIFICATION_REPORT_SCHEMA,
    LoadedPackage,
    Severity,
    VerificationReport,
    __version__,
    cli,
    runner,
    verify,
)
from ooxml_integrity import archive as archive_mod
from tests.conftest import ROOT, read_part, repack

EXPECTED_VERIFICATION_DICT_KEYS = {
    "schema",
    "schema_version",
    "checker_version",
    "passed",
    "exit_code",
    "verdict",
    "fail_on",
    "profile",
    "path",
    "sha256",
    "source_path",
    "source_sha256",
    "config",
    "baseline",
    "introduced",
    "summary",
    "worst",
    "findings",
    "suppressed",
    "expected",
    "coverage",
}

EXPECTED_CLI_ENVELOPE_KEYS = {
    "version",
    "fail_on",
    "config",
    "baseline",
    "files",
}


class _NonSeekableStream:
    def seekable(self) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        return b""

    def seek(self, offset: int, whence: int = 0) -> int:
        raise io.UnsupportedOperation("seek")


def _break_comment_end(src: Path, dst: Path) -> Path:
    xml = read_part(src, "word/document.xml")
    tree = etree.fromstring(xml.encode("utf-8"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    end = tree.find(f".//{w}commentRangeEnd")
    assert end is not None
    parent = end.getparent()
    assert parent is not None
    parent.remove(end)
    return repack(src, dst, {"word/document.xml": etree.tostring(tree, xml_declaration=True, encoding="UTF-8")})


def _break_style(src: Path, dst: Path) -> Path:
    xml = read_part(src, "word/document.xml")
    assert 'w:val="ClauseBody"' in xml
    return repack(src, dst, {
        "word/document.xml": xml.replace('w:val="ClauseBody"', 'w:val="MissingStyle"', 1).encode("utf-8"),
    })


def test_verify_clean_docx_path_and_in_memory_parity(base_docx: Path) -> None:
    raw = base_docx.read_bytes()
    expected_sha = hashlib.sha256(raw).hexdigest()

    from_path = verify(base_docx, label="contract.docx")
    from_str = verify(str(base_docx), label="contract.docx")
    from_bytes = verify(raw, label="contract.docx")
    from_stream = verify(io.BytesIO(raw), label="contract.docx")
    from_pkg = verify(LoadedPackage.open(raw, label="contract.docx"))

    for report in (from_path, from_str, from_bytes, from_stream, from_pkg):
        assert isinstance(report, VerificationReport)
        assert report.schema == VERIFICATION_REPORT_SCHEMA == "ooxml-integrity.verification-report.v1"
        assert report.schema_version == SCHEMA_VERSION == 1
        assert report.checker_version == __version__
        assert report.passed is True
        assert report.exit_code == 0
        assert report.fail_on == Severity.ERROR
        assert report.profile == "default"
        assert report.path == "contract.docx"
        assert report.sha256 == expected_sha
        assert report.source_path is None
        assert report.source_sha256 is None
        assert report.findings == ()
        assert report.suppressed == ()
        assert report.expected == ()
        assert report.coverage is not None
        assert "no findings in checked surfaces" in report.verdict
        assert "no findings in checked surfaces" in report.to_text()

        as_dict = report.to_dict()
        assert set(as_dict) == EXPECTED_VERIFICATION_DICT_KEYS
        assert json.loads(report.to_json()) == as_dict
        assert as_dict["schema"] == "ooxml-integrity.verification-report.v1"
        assert as_dict["schema_version"] == 1
        assert as_dict["passed"] is True
        assert as_dict["sha256"] == expected_sha
        assert as_dict["summary"] == {"error": 0, "warn": 0, "info": 0}
        assert as_dict["worst"] is None

        # Multi-file CLI envelope keeps its own distinct key set (no schema_version collision).
        cli_payload = report.to_cli_report()
        assert set(cli_payload) == EXPECTED_CLI_ENVELOPE_KEYS
        assert "schema" not in cli_payload
        assert "schema_version" not in cli_payload
        assert cli_payload["version"] == __version__
        assert cli_payload["files"][0]["path"] == "contract.docx"

        sarif = report.to_sarif()
        assert sarif["version"] == "2.1.0"
        assert sarif["runs"][0]["results"] == []

    assert from_str.to_dict() == from_path.to_dict()
    assert from_bytes.to_dict() == from_path.to_dict()
    assert from_stream.to_dict() == from_path.to_dict()
    assert from_pkg.to_dict() == from_path.to_dict()

    without_cov = verify(base_docx, coverage=False, label="contract.docx")
    assert without_cov.coverage is None
    assert set(without_cov.to_dict()) == EXPECTED_VERIFICATION_DICT_KEYS
    assert "clean" in without_cov.verdict
    assert "clean" in without_cov.to_text()


def test_verify_against_introduced_and_expect(base_docx: Path, tmp_path: Path) -> None:
    # Source already has one STY001; edited inherits STY001 and introduces CMT001.
    source = _break_style(base_docx, tmp_path / "source.docx")
    edited = _break_comment_end(source, tmp_path / "edited.docx")

    report = verify(
        edited,
        against=source,
        introduced=True,
        expect=["CMT001"],
        coverage=True,
    )
    assert report.passed is True
    assert report.exit_code == 0
    assert report.introduced is True
    assert report.sha256 == hashlib.sha256(edited.read_bytes()).hexdigest()
    assert report.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert [s.finding.code for s in report.suppressed] == ["STY001"]
    assert [e.finding.code for e in report.expected] == ["CMT001"]
    assert report.findings == ()

    as_dict = report.to_dict()
    assert set(as_dict) == EXPECTED_VERIFICATION_DICT_KEYS
    assert as_dict["schema"] == VERIFICATION_REPORT_SCHEMA
    assert as_dict["introduced"] is True

    text = report.to_text(show_suppressed=True)
    assert "[expected]" in text
    assert "[hidden] STY001" in text

    cli_payload = report.to_cli_report()
    assert set(cli_payload) == EXPECTED_CLI_ENVELOPE_KEYS | {"introduced"}
    assert cli_payload["introduced"] is True
    assert "expected" in cli_payload["files"][0]
    assert len(cli_payload["files"][0]["expected"]) == 1
    assert len(cli_payload["files"][0]["suppressed"]) == 1

    sarif = report.to_sarif()
    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"][0]["results"]) == 2


def test_verify_matches_cli_findings_on_same_files(
    base_docx: Path, runs_dir: Path, capsys,
) -> None:
    fast = runs_dir / "t4_fast_fee" / "agreement.docx"
    deck = ROOT / "corpus" / "deck.pptx"
    cases: list[tuple[Path, Path | None, bool]] = [
        (base_docx, None, False),
        (fast, base_docx, False),
        (fast, base_docx, True),
    ]
    if deck.is_file():
        cases.append((deck, None, False))

    for target, source, introduced_flag in cases:
        argv = ["check", str(target), "--no-config", "--json", "--coverage"]
        if source is not None:
            argv.extend(["--against", str(source)])
        if introduced_flag:
            argv.append("--introduced")
        cli_rc = cli.main(argv)
        cli_json = json.loads(capsys.readouterr().out)

        report = verify(
            target,
            against=source,
            introduced=introduced_flag,
            coverage=True,
        )
        assert report.exit_code == cli_rc
        assert [f.as_dict() for f in report.findings] == cli_json["files"][0]["findings"]
        assert report.to_cli_report() == cli_json


def test_verify_single_pass_zip_reads(
    base_docx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    edited = _break_comment_end(base_docx, tmp_path / "edited.docx")
    opens: list[object] = []
    real_open = archive_mod._open_archive_with_stream

    def counting_open(source, limits):
        opens.append(source)
        return real_open(source, limits)

    monkeypatch.setattr(archive_mod, "_open_archive_with_stream", counting_open)

    report = verify(edited, against=base_docx, introduced=True, coverage=True)
    assert report.exit_code == 1
    assert len(opens) == 2


def test_verify_fail_closed_and_validation(
    base_docx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = verify(tmp_path / "absent.docx")
    assert missing.passed is False
    assert missing.exit_code == 1
    assert missing.sha256 is None
    assert [f.code for f in missing.findings] == ["PKG000"]

    corrupt = verify(b"not a zip", label="broken.docx")
    assert corrupt.passed is False
    assert corrupt.exit_code == 1
    assert corrupt.sha256 is None
    assert [f.code for f in corrupt.findings] == ["PKG002"]

    non_seekable = verify(_NonSeekableStream(), label="pipe.docx")  # type: ignore[arg-type]
    assert non_seekable.passed is False
    assert non_seekable.exit_code == 1
    assert non_seekable.sha256 is None
    assert [f.code for f in non_seekable.findings] == ["PKG002"]

    missing_source = verify(base_docx, against=tmp_path / "no-source.docx")
    assert missing_source.passed is False
    assert any(f.code == "FID000" for f in missing_source.findings)

    with pytest.raises(ValueError, match="introduced=True requires against"):
        verify(base_docx, introduced=True)

    with pytest.raises(ValueError, match="unknown profile"):
        verify(base_docx, profile="nonexistent")

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected checker bug")

    monkeypatch.setattr(runner, "check", boom)
    with pytest.raises(RuntimeError, match="unexpected checker bug"):
        verify(base_docx)


def test_cli_json_out_single_pass_and_safety(
    base_docx: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    doc = tmp_path / "copy.docx"
    doc.write_bytes(base_docx.read_bytes())
    json_out = tmp_path / "report.json"
    sarif_out = tmp_path / "report.sarif"

    opens: list[object] = []
    real_open = archive_mod._open_archive_with_stream

    def counting_open(source, limits):
        opens.append(source)
        return real_open(source, limits)

    monkeypatch.setattr(archive_mod, "_open_archive_with_stream", counting_open)

    rc = cli.main([
        "check", str(doc),
        "--json-out", str(json_out),
        "--sarif", str(sarif_out),
        "--no-config",
    ])
    captured = capsys.readouterr()
    assert rc == cli.EXIT_OK
    assert "clean" in captured.out
    assert not captured.out.lstrip().startswith("{")
    assert len(opens) == 1

    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert set(payload) == EXPECTED_CLI_ENVELOPE_KEYS
    assert payload["version"] == __version__
    assert payload["files"][0]["path"] == str(doc)
    assert payload["files"][0]["summary"] == {"error": 0, "warn": 0, "info": 0}
    assert json.loads(sarif_out.read_text(encoding="utf-8"))["version"] == "2.1.0"

    # Refuses overwriting input document.
    original_bytes = doc.read_bytes()
    rc = cli.main(["check", str(doc), "--json-out", str(doc), "--no-config"])
    err = capsys.readouterr().err
    assert rc == cli.EXIT_USAGE
    assert "--json-out" in err
    assert doc.read_bytes() == original_bytes

    # Refuses sharing the same path between --json-out and --sarif, writing neither.
    shared = tmp_path / "shared.json"
    rc = cli.main([
        "check", str(doc),
        "--json-out", str(shared), "--sarif", str(shared), "--no-config",
    ])
    err = capsys.readouterr().err
    assert rc == cli.EXIT_USAGE
    assert "--json-out" in err and "--sarif" in err
    assert not shared.exists()

    # Refuses directory destination for --json-out before writing --sarif.
    bad_dir = tmp_path / "as-dir"
    bad_dir.mkdir()
    fresh_sarif = tmp_path / "fresh.sarif"
    rc = cli.main([
        "check", str(doc),
        "--json-out", str(bad_dir), "--sarif", str(fresh_sarif), "--no-config",
    ])
    err = capsys.readouterr().err
    assert rc == cli.EXIT_USAGE
    assert "--json-out" in err
    assert not fresh_sarif.exists()


def test_no_private_cli_imports_or_runner_duplicates() -> None:
    for rel in ("src/ooxml_integrity/mcp_server.py", "src/ooxml_integrity/anonymize.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "cli", f"{rel} must not import from cli"
                for alias in node.names:
                    assert alias.name != "cli", f"{rel} must not import cli"

    bridge_path = ROOT / "demo" / "bridge.py"
    if bridge_path.is_file():
        bridge_tree = ast.parse(bridge_path.read_text(encoding="utf-8"))
        for node in ast.walk(bridge_tree):
            if isinstance(node, ast.ImportFrom) and node.module == "ooxml_integrity.cli":
                for alias in node.names:
                    assert not alias.name.startswith("_"), (
                        f"demo/bridge.py must not import private cli.{alias.name}"
                    )

    # cli.py must not keep duplicate helpers; only _run_one stays as a thin
    # alias to runner.run_checks for the SHA-256-pinned research/revision_evidence.py.
    assert cli._run_one is runner.run_checks
    for removed in ("_head", "_has_gaps", "_print_human", "_print_coverage"):
        assert not hasattr(cli, removed), f"cli.{removed} should have moved to runner.py"
