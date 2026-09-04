"""Static contracts for the composite GitHub Action.

These tests deliberately avoid a YAML dependency.  Composite-action run blocks
have a fixed indentation in this file, so extracting them is enough to guard the
two security properties without coupling the test suite to an Action runner.
"""
from __future__ import annotations

import re
from pathlib import Path


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
    assert 'python -m pip install --quiet "$GITHUB_ACTION_PATH"' in install
