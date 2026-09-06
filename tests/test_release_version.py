"""The CLI, import and package metadata must identify the same release."""
from __future__ import annotations

import re

from conftest import run_cli
from ooxml_integrity import __version__


def test_declared_package_version_matches_import(root):
    project = (root / "pyproject.toml").read_text()
    assert re.search(r'^version = "([^"]+)"$', project, re.M)[1] == __version__


def test_cli_version_matches_import():
    result = run_cli("--version")
    assert result.returncode == 0 and result.stdout.strip().endswith(__version__)
