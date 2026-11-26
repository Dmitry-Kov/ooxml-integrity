"""Contracts for the composite GitHub Action.

Run its check step with local fixtures, using the declared input defaults and
environment bindings. The manifest's indentation lets us extract those and
the shell blocks without adding a YAML dependency.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import run_cli


ACTION = Path(__file__).resolve().parent.parent / "action.yml"
INPUT_EXPRESSION = re.compile(r"\$\{\{[^}]*\binputs(?:\.|\[)")


def _run_blocks() -> list[str]:
    lines = ACTION.read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    for i, line in enumerate(lines):
        if line != "      run: |":
            continue
        body: list[str] = []
        for nested in lines[i + 1:]:
            if nested and not nested.startswith("        "):
                break
            body.append(nested[8:] if nested else "")
        blocks.append("\n".join(body))
    assert blocks, "action.yml contains no composite run blocks"
    return blocks


def test_inputs_are_not_interpolated_into_shell_source():
    for block in _run_blocks():
        assert INPUT_EXPRESSION.search(block) is None


def test_default_install_uses_the_selected_action_ref():
    install = next(block for block in _run_blocks()
                   if "python -m pip install" in block)
    assert 'python -m pip install --quiet "${GITHUB_ACTION_PATH}[pptx]"' in install
    assert 'python -m pip install --quiet "ooxml-integrity[pptx]==$OOXML_VERSION"' in install


def _check_step(workdir, inputs):
    bash = shutil.which("bash")
    if os.name == "nt" and (git := shutil.which("git")):
        # GitHub's Windows runner uses Git Bash, even if WSL bash is on PATH.
        git_bash = Path(git).resolve().parents[1] / "bin" / "bash.exe"
        if git_bash.is_file():
            bash = str(git_bash)
    if bash is None:
        pytest.skip("the composite check step requires bash")

    manifest = ACTION.read_text(encoding="utf-8")
    declared = manifest.split("\ninputs:\n", 1)[1].split("\noutputs:", 1)[0]
    check = manifest.split("    - name: Check documents\n", 1)[1]
    env = os.environ.copy()
    for var, name in re.findall(r"(OOXML_\w+): \$\{\{ inputs\.([\w-]+) \}\}", check):
        field = re.search(rf"^  {re.escape(name)}:\n((?:    [^\n]*\n)*)", declared, re.M)
        assert field is not None, name
        default = re.search(r"^    default: (.*)$", field[1], re.M)
        env[var] = inputs.get(name, default[1].strip("\"'") if default else "")
    env.update(PATH=str(Path(sys.executable).parent) + os.pathsep + env["PATH"],
               PYTHONPATH=str(ACTION.parent / "src"), GITHUB_ACTION_PATH=str(ACTION.parent),
               GITHUB_STEP_SUMMARY="step-summary.md", GITHUB_OUTPUT="step-output")
    script = next(block for block in _run_blocks() if "GITHUB_STEP_SUMMARY" in block)
    result = subprocess.run([bash, "-c", script], env=env, cwd=workdir,
                            capture_output=True, text=True)
    outputs = dict(line.split("=", 1) for line in
                   (workdir / "step-output").read_text(encoding="utf-8").splitlines())
    return result, outputs


@pytest.fixture
def one_warning(tmp_path, root):
    source = root / "evidence/review-history-benchmark/captures/docx-cli-1/K1-S1-plain.docx"
    if not source.is_file():
        pytest.skip("evidence/ corpus is not shipped in the PyPI sdist")
    return shutil.copy(source, tmp_path / "edited.docx")


@pytest.mark.parametrize("override, expected_exit", [(None, 1), ("error", 0), ("warn", 1)])
def test_action_uses_the_same_threshold_as_cli(tmp_path, one_warning, override, expected_exit):
    config = tmp_path / ".ooxml-integrity.toml"
    config.write_text('fail-on = "warn"\n', encoding="utf-8")
    inputs = {"files": one_warning.name, "json-report": "report.json", "sarif": "report.sarif"}
    cli_args = ["check", str(one_warning), "--config", str(config), "--json"]
    if override is not None:
        inputs["fail-on"] = override
        cli_args.extend(["--fail-on", override])

    cli = run_cli(*cli_args)
    assert cli.returncode == expected_exit, cli.stdout + cli.stderr
    result, outputs = _check_step(tmp_path, inputs)
    assert result.returncode == cli.returncode, result.stdout + result.stderr
    assert outputs["exit-code"] == str(expected_exit)
    assert outputs["reports-ready"] == "true"
    assert (outputs["errors"], outputs["warnings"]) == ("0", "1")
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["fail_on"] == json.loads(cli.stdout)["fail_on"]
    assert [f["code"] for f in report["files"][0]["findings"]] == ["TXT002"]
    sarif = json.loads((tmp_path / "report.sarif").read_text(encoding="utf-8"))
    assert [f["ruleId"] for f in sarif["runs"][0]["results"]] == ["TXT002"]


def test_clean_action_summary_uses_the_config_threshold(tmp_path, tmp_docx):
    (tmp_path / ".ooxml-integrity.toml").write_text('fail-on = "warn"\n', encoding="utf-8")
    result, outputs = _check_step(tmp_path, {"files": tmp_docx.name})
    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs["reports-ready"] == "true"
    assert "`warn`" in (tmp_path / "step-summary.md").read_text(encoding="utf-8")


def test_action_runs_checker_in_a_single_pass(tmp_path, one_warning, monkeypatch):
    # Count how many times the Action invokes the checker CLI. With --json-out,
    # human output, JSON counts, and optional SARIF come from one single pass.
    counter = tmp_path / "check-calls.log"
    setup = tmp_path / "count-calls.bash"
    setup.write_text(
        'python() {\n'
        f'  if [[ "$1" == "-m" && "$2" == "ooxml_integrity" && "$3" == "check" ]]; then\n'
        f'    echo call >> "{counter.name}"\n'
        '  fi\n'
        '  command python "$@"\n'
        '}\n', encoding="utf-8")
    monkeypatch.setenv("BASH_ENV", setup.name)
    result, outputs = _check_step(tmp_path, {
        "files": one_warning.name, "fail-on": "warn",
        "json-report": "report.json", "sarif": "report.sarif",
    })
    assert result.returncode == 1, result.stdout + result.stderr
    assert (outputs["exit-code"], outputs["warnings"]) == ("1", "1")
    assert counter.read_text(encoding="utf-8").splitlines() == ["call"]
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert [f["code"] for f in report["files"][0]["findings"]] == ["TXT002"]
    sarif = json.loads((tmp_path / "report.sarif").read_text(encoding="utf-8"))
    assert [f["ruleId"] for f in sarif["runs"][0]["results"]] == ["TXT002"]


@pytest.mark.parametrize("previous", [False, True], ids=["new-json", "existing-json"])
def test_action_reports_failure_to_write_sarif(tmp_path, one_warning, previous):
    (tmp_path / "directory").mkdir()
    report = tmp_path / "report.json"
    if previous:
        report.write_text('{"previous":true}', encoding="utf-8")
    result, outputs = _check_step(tmp_path, {"files": one_warning.name, "fail-on": "error",
                                             "json-report": "report.json", "sarif": "directory"})
    assert result.returncode == 2, result.stdout + result.stderr
    assert outputs["exit-code"] == "2"
    assert "reports-ready" not in outputs
    assert "--sarif" in result.stderr
    if previous:
        assert report.read_text(encoding="utf-8") == '{"previous":true}'
    else:
        assert not report.exists()
    assert "No findings at or above" not in (tmp_path / "step-summary.md").read_text(encoding="utf-8")


def test_action_reports_failure_to_publish_json(tmp_path, one_warning):
    destination = tmp_path / "directory"
    destination.mkdir()
    result, outputs = _check_step(tmp_path, {"files": one_warning.name,
                                             "json-report": destination.name, "sarif": "report.sarif"})
    assert result.returncode == 2, result.stdout + result.stderr
    assert outputs["exit-code"] == "2"
    assert "reports-ready" not in outputs
    assert list(destination.iterdir()) == []
