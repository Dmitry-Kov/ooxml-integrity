"""The Action's JSON report must preserve the documents it checked."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_action_contract import ACTION, _run_blocks


def _check_with_report(workdir, files, report, against=""):
    bash = shutil.which("bash")
    if os.name == "nt" and (git := shutil.which("git")):
        git_bash = Path(git).resolve().parents[1] / "bin" / "bash.exe"
        if git_bash.is_file():
            bash = str(git_bash)
    if bash is None:
        pytest.skip("the composite check step requires bash")

    env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
               PYTHONPATH=str(ACTION.parent / "src"), GITHUB_ACTION_PATH=str(ACTION.parent),
               GITHUB_OUTPUT="outputs",
               GITHUB_STEP_SUMMARY="summary", OOXML_FILES=files, OOXML_AGAINST=against,
               OOXML_JSON_REPORT=report, OOXML_FAIL_ON="error", OOXML_INTRODUCED="false",
               OOXML_CONFIG="none", OOXML_BASELINE="", OOXML_SARIF="")
    script = next(block for block in _run_blocks() if "GITHUB_STEP_SUMMARY" in block)
    return subprocess.run([bash, "-c", script], cwd=workdir, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True)


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

    result = _check_with_report(tmp_path, "edited/*.docx", report.relative_to(tmp_path).as_posix(),
                                against=tmp_docx.name)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "exit-code=2" in (tmp_path / "outputs").read_text().splitlines()
    assert "json-report" in result.stderr and target.name in result.stderr
    for document in (first, second, tmp_docx, report):
        assert document.read_bytes() == original


@pytest.mark.parametrize("existing", [False, True], ids=["new", "replace"])
def test_action_json_report_writes_a_separate_file(tmp_path, tmp_docx, existing):
    report = tmp_path / "report.json"
    if existing:
        report.write_text(json.dumps({"previous": "x" * 100_000}), encoding="utf-8")
    original = tmp_docx.read_bytes()
    result = _check_with_report(tmp_path, tmp_docx.name, report.name)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "exit-code=0" in (tmp_path / "outputs").read_text().splitlines()
    [entry] = json.loads(report.read_text(encoding="utf-8"))["files"]
    assert entry["path"] == tmp_docx.name
    assert entry["summary"] == {"error": 0, "warn": 0, "info": 0}
    assert tmp_docx.read_bytes() == original


def test_action_json_report_preserves_source_when_glob_matches_nothing(tmp_path, tmp_docx):
    original = tmp_docx.read_bytes()
    result = _check_with_report(tmp_path, "edited/*.docx", tmp_docx.name, against=tmp_docx.name)
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
    result = _check_with_report(tmp_path, tmp_docx.name, directory.name)
    assert result.returncode == 2, result.stdout + result.stderr
    assert tmp_docx.read_bytes() == alias.read_bytes() == original
