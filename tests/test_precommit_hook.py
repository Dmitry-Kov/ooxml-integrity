"""The pre-commit hook names a command this package installs and runs.

pre-commit installs the repository with pip and calls the hook's `entry` with
the staged files appended. Like the Action contract tests, this reads the file
without a YAML dependency: the hook is a flat list of `key: value` lines.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from ooxml_integrity.cli import main

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".pre-commit-hooks.yaml"


def _hook() -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in HOOKS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(?:- |  )(\w+): (.*)$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip().strip("'")
    return fields


def _console_scripts() -> set[str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    return set(re.findall(r"^([\w-]+) *=", block, re.MULTILINE))


def test_hook_installs_with_pip_and_calls_the_console_script():
    hook = _hook()
    assert hook["id"] == "ooxml-integrity"
    assert hook["language"] == "python"
    command, subcommand = hook["entry"].split()
    assert command in _console_scripts()
    assert subcommand == "check"


def test_hook_selects_documents_and_decks_only():
    files = re.compile(_hook()["files"])
    for name in ("contract.docx", "out/q3 review.pptx"):
        assert files.search(name)
    for name in ("notes.md", "contract.docx.bak", "sheet.xlsx", "docx", "template.dotx"):
        assert not files.search(name)


def test_entry_takes_the_staged_files_as_arguments(tmp_path):
    """pre-commit appends file names to the entry; several pass in one call."""
    subcommand = _hook()["entry"].split()[1]
    clean = tmp_path / "clean.docx"
    shutil.copy(ROOT / "corpus" / "base.docx", clean)
    again = tmp_path / "again.docx"
    shutil.copy(clean, again)
    assert main([subcommand, "--no-config", str(clean), str(again)]) == 0

    # A commit with a broken document fails the hook.
    broken = tmp_path / "broken.docx"
    shutil.copy(ROOT / "runs" / "t4_fast_fee" / "agreement.docx", broken)
    assert main([subcommand, "--no-config", str(clean), str(broken)]) == 1
