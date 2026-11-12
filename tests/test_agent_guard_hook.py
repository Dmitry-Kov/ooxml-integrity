"""The agent guard hook: which shell commands it denies, asks about or lets through.

`.qwen/hooks/guard_git.py` runs before an agent's shell command. It is tooling
for this repository, not part of the package, so the sdist does not carry it
and these tests skip there.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".qwen" / "hooks" / "guard_git.py"
SETTINGS = ROOT / ".qwen" / "settings.json"

pytestmark = pytest.mark.skipif(not HOOK.is_file(), reason="the agent hook is not in this tree")


def _judge(command: str, branch):
    spec = importlib.util.spec_from_file_location("guard_git", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verdict = module.judge(command, branch)
    return verdict[0] if verdict else None


@pytest.mark.parametrize("command", [
    "git status",
    "git log --oneline -3",
    "git diff --stat",
    "git add README.md",
    "git tag",
    "git tag -l 'v0.10*'",
    "git branch --list",
    "git stash",
    "gh pr view 126 --json state",
    "gh pr checks 126",
    "gh api repos/a/b/traffic/views",
    ".venv/bin/python -m pytest -q",
    ".venv/bin/python -m twine check --strict dist/*",
    "rm -f out/report.json",
    "grep -rn 'git push' docs",
    "git log --grep 'commit on main'",
])
def test_reading_and_local_work_pass_on_main(command):
    assert _judge(command, "main") is None


@pytest.mark.parametrize("command", [
    "git commit -m 'x'",
    "git -C /tmp/x commit -m x",
    "git add .\ngit commit -m 'fix'",
    "cd src && git commit -m x",
    "git merge topic",
    "git rebase origin/main",
    "git cherry-pick abc",
    "git revert abc",
    "echo $(git commit -m x)",
    "sh -c 'cd x && git commit -m y'",
    "git commit -m 'explain git push in docs'",
])
@pytest.mark.parametrize("branch", ["main", "master"])
def test_changing_history_on_the_default_branch_is_denied(command, branch):
    assert _judge(command, branch) == "deny"


@pytest.mark.parametrize("command", [
    "git commit -m 'x'",
    "git commit -m 'explain git push in docs'",
    "git rebase origin/main",
    "git restore --staged README.md",
])
def test_the_same_commands_pass_on_a_topic_branch(command):
    assert _judge(command, "docs/topic") is None


@pytest.mark.parametrize("command", [
    "git switch -c topic && git commit -m 'x'",
    "git checkout -b topic\ngit add .\ngit commit -m x",
])
def test_a_branch_created_in_the_same_command_counts(command):
    assert _judge(command, "main") is None


def test_switching_back_to_main_in_the_command_counts_too():
    assert _judge("git switch main && git merge topic", "topic") == "deny"


@pytest.mark.parametrize("command", [
    "git push",
    "git push origin topic",
    "git push --force",
    "git add . && git commit -m x && git push",
    'bash -c "git push origin main"',
    "git tag -a v0.10.1 -m x",
    "git branch -D old",
    "git reset --hard HEAD~1",
    "git clean -fdx",
    "git restore README.md",
    "git checkout -- README.md",
    "git stash drop",
    "gh pr create --title x --body y",
    "gh pr create --title 'git push notes' --body y",
    "gh pr merge 126 --merge",
    "gh repo edit --description x",
    "gh issue comment 1 --body hi",
    "gh release create v1",
    "gh api -X POST repos/a/b/issues -f title=x",
    "twine upload dist/*",
    "python -m twine upload dist/*",
    "mcp-publisher publish",
    "rm -rf tmp/cache",
    "rm -rf drafts",
    "rm evidence/docx-beta/RESULTS.md",
])
def test_what_leaves_the_machine_or_discards_work_asks_first(command):
    assert _judge(command, "topic") == "ask"


def test_an_unreadable_command_or_branch_asks_instead_of_passing():
    assert _judge('git commit -m "unbalanced', "main") == "ask"
    assert _judge("git commit -m x", None) == "ask"


def _run(event) -> subprocess.CompletedProcess:
    payload = event if isinstance(event, str) else json.dumps(event)
    return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True,
                          text=True, timeout=30)


def test_the_hook_answers_in_the_shape_qwen_code_reads(tmp_path):
    done = _run({"tool_name": "run_shell_command", "cwd": str(tmp_path),
                 "tool_input": {"command": "git push origin HEAD"}})
    assert done.returncode == 0
    answer = json.loads(done.stdout)["hookSpecificOutput"]
    assert answer["hookEventName"] == "PreToolUse"
    assert answer["permissionDecision"] == "ask"
    assert "push" in answer["permissionDecisionReason"]


def test_other_tools_and_unreadable_input_are_left_to_the_usual_rules(tmp_path):
    for event in ({"tool_name": "read_file", "tool_input": {"file_path": "x"}},
                  {"tool_name": "run_shell_command", "cwd": str(tmp_path),
                   "tool_input": {"command": "ls"}},
                  "not json"):
        done = _run(event)
        assert (done.returncode, done.stdout) == (0, "")


def test_the_project_settings_register_the_hook_for_shell_commands():
    hooks = json.loads(SETTINGS.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    entry, = hooks
    assert entry["matcher"] == "run_shell_command"
    command = entry["hooks"][0]["command"]
    assert entry["hooks"][0]["type"] == "command"
    assert ".qwen/hooks/guard_git.py" in command and "$QWEN_PROJECT_DIR" in command
