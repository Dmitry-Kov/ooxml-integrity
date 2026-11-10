"""`server.json` is what MCP catalogs read; it must describe this release.

The MCP Registry keeps one immutable entry per version, and proves ownership
by reading the README that PyPI serves for exactly that version: it must
contain `mcp-name: NAME`. A `server.json` left on the previous version, or a
README without the line, is refused at publication, after the package is out.
The limits below are the ones the registry's schema (2025-12-11) enforces.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest
from conftest import ROOT

from ooxml_integrity import __version__


@pytest.fixture(scope="module")
def server() -> dict:
    return json.loads((ROOT / "server.json").read_text(encoding="utf-8"))


def test_versions_match_the_package(server):
    assert server["version"] == __version__
    assert [p["version"] for p in server["packages"]] == [__version__]


def test_package_is_the_one_pyproject_builds(server):
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package, = server["packages"]
    assert package["registryType"] == "pypi"
    assert package["identifier"] == re.search(r'^name = "([^"]+)"$', project, re.M)[1]
    assert package["transport"] == {"type": "stdio"}


def test_readme_carries_the_ownership_line(server):
    """As the registry matches it: the name must end at a boundary."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    token = "mcp-name: " + server["name"]
    rest = [readme[m.end():] for m in re.finditer(re.escape(token), readme)]
    assert any(not r or r.startswith("-->") or not re.match(r"[A-Za-z0-9._/-]", r)
               for r in rest), f"README.md has no '{token}' line"


def test_name_and_description_fit_the_registry_limits(server):
    # GitHub login grants `io.github.<login>/*`, compared case-sensitively.
    assert server["name"].startswith("io.github.Dmitry-Kov/")
    assert re.fullmatch(r"[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+", server["name"])
    assert 1 <= len(server["description"]) <= 100
    assert 1 <= len(server["title"]) <= 100
    assert server["repository"] == {
        "url": "https://github.com/Dmitry-Kov/ooxml-integrity", "source": "github"}


def test_declared_arguments_start_the_server(server):
    """A catalog client runs the package with these arguments and nothing else."""
    package, = server["packages"]
    assert all(a["type"] == "positional" for a in package["packageArguments"])
    args = [a["value"] for a in package["packageArguments"]]
    request = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "pytest", "version": "0"}}}
    result = subprocess.run(
        [sys.executable, "-m", "ooxml_integrity.cli", *args],
        input=json.dumps(request) + "\n", capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    reply = json.loads(result.stdout.splitlines()[0])
    assert reply["result"]["serverInfo"] == {"name": "ooxml-integrity",
                                             "version": __version__}
