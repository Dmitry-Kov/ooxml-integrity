"""Local-agent harness checks; no test invokes a model or a remote API."""
import ast
import json
import sys
from pathlib import Path

import pytest

from research import capture_docx_agent as agent
from research import docx_benchmark as bench


def test_fixed_prompts_options_and_repetitions():
    bench.frozen_protocol()
    for action in ("save", "edit"):
        for seed in (101, 102, 103):
            request = agent.request_body(action, seed)
            assert request["model"] == "qwen2.5-coder:7b"
            assert request["stream"] is False and request["think"] is False
            assert request["options"] == {"temperature": 0, "num_ctx": 8192, "num_predict": 4096, "seed": seed}
            assert len(request["messages"]) == 2
            assert "Do not use an integrity checker." in request["messages"][0]["content"]
            assert "EDITBEFORE" in request["messages"][1]["content"] if action == "edit" else "file copy" in request["messages"][1]["content"]


@pytest.mark.parametrize("content,expected", [
    ("print('ok')", "print('ok')"),
    ("```python\nprint('ok')\n```", "print('ok')\n"),
    ("Explanation\n```python\nprint('ok')\n```", "Explanation\n```python\nprint('ok')\n```"),
])
def test_extraction_never_repairs_model_output(content, expected):
    assert agent.extract_script(content)[0] == expected


def test_prepare_declares_all_thirty_cases_before_run(monkeypatch, tmp_path):
    details = {"version": "3.12.14", "packages": {"python-docx": "1.2.0", "lxml": "6.1.3"}}
    monkeypatch.setattr(agent, "python_details", lambda p: details)
    monkeypatch.setattr(agent, "model_record", lambda: {"test_only": True})
    receipt = tmp_path / "installation.json"
    receipt.write_text('{}')
    directory = tmp_path / "capture"
    declaration = agent.prepare(Path(sys.executable), directory, receipt)
    assert len(declaration["cases"]) == 30
    assert len({c["id"] for c in declaration["cases"]}) == 30
    assert declaration["rules"]["model_retries"] == 0
    assert not (directory / "capture.json").exists()


def test_macos_sandbox_allows_docx_save_but_blocks_other_files_and_network(tmp_path):
    python = bench.ROOT / "tmp/benchmark-runtime/python-env/bin/python"
    if sys.platform != "darwin" or not python.exists():
        pytest.skip("Optional local macOS agent runtime is not installed")
    details = agent.python_details(python)
    work = tmp_path / "work"
    work.mkdir()
    secret = tmp_path / "outside.txt"
    secret.write_text("must remain unread")
    profile = tmp_path / "sandbox.sb"
    profile.write_text(agent.sandbox_profile(work, python, details))
    code = '''import socket, subprocess, json
from pathlib import Path
from docx import Document
doc = Document()
doc.add_paragraph('Probe')
doc.save('output.docx')
checks = {}
for name, operation in [
    ('read', lambda: Path('../outside.txt').read_text()),
    ('write', lambda: Path('../forbidden.txt').write_text('bad')),
    ('network', lambda: socket.create_connection(('127.0.0.1', 11434), timeout=1)),
    ('process', lambda: subprocess.run(['/bin/echo', 'bad'], check=True))]:
    try:
        operation()
        checks[name] = False
    except PermissionError:
        checks[name] = True
Path('checks.json').write_text(json.dumps(checks))
'''
    (work / "edit.py").write_text(code)
    result = agent.execute(python, work, profile)
    assert result["returncode"] == 0, (work / "stderr.txt").read_text()
    assert (work / "output.docx").is_file()
    assert all(json.loads((work / "checks.json").read_text()).values())
    assert secret.read_text() == "must remain unread"
    assert not (tmp_path / "forbidden.txt").exists()


@pytest.mark.frozen_checker
def test_saved_agent_capture_replays_if_present():
    directory = bench.BASE / "agent-local-1"
    if not (directory / "capture.json").exists():
        pytest.skip("Agent capture has not completed")
    assert agent.evaluate(directory) == json.loads((directory / "evaluation.json").read_text())


def test_captured_generation_and_execution_code_remain_unchanged():
    archived = bench.BASE / "agent-local-1/capture-harness.py"
    if not archived.exists():
        pytest.skip("Agent capture has not been declared")
    names = {"messages", "request_body", "extract_script", "sandbox_profile", "execute", "prepare", "capture"}
    def functions(path):
        return {node.name: ast.dump(node) for node in ast.parse(path.read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name in names}
    assert functions(Path(agent.__file__)) == functions(archived)
