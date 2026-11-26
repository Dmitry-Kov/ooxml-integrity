"""Shared fixtures.

The committed corpus and agent-run outputs are the fixtures: the suite tests
what actually ships, not a parallel set of hand-made files.
"""
from __future__ import annotations

import ast
import shutil
import os
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "evidence"
RESEARCH_DIR = ROOT / "research"

needs_evidence = pytest.mark.skipif(
    not EVIDENCE_DIR.is_dir(),
    reason="evidence/ corpus is not shipped in the PyPI sdist",
)
needs_research = pytest.mark.skipif(
    not RESEARCH_DIR.is_dir(),
    reason="research/ scripts are not shipped in the PyPI sdist",
)


def _imports_research_at_module_level(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    for node in tree.body:
        if isinstance(node, ast.Import):
            if any(a.name == "research" or a.name.startswith("research.")
                   for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "research" or mod.startswith("research."):
                return True
    return False


def pytest_ignore_collect(collection_path: Path, config) -> bool | None:
    """In an unpacked PyPI sdist (without research/), skip repo-only research tests."""
    if RESEARCH_DIR.is_dir():
        return None
    if collection_path.suffix == ".py" and collection_path.name.startswith("test_"):
        if _imports_research_at_module_level(collection_path):
            return True
    return None

#: The committed ZIP fixtures were deflated by zlib. Windows builds of CPython
#: 3.14 use zlib-ng, which deflates the same data into other bytes, so a test
#: that rebuilds fixtures byte for byte cannot pass there. Any other zlib still
#: runs it, so a difference elsewhere fails instead of being skipped.
needs_zlib_bytes = pytest.mark.skipif(
    "zlib-ng" in zlib.ZLIB_RUNTIME_VERSION,
    reason=f"zlib {zlib.ZLIB_RUNTIME_VERSION} deflates into other bytes than the "
           "zlib the fixtures were built with")


@pytest.fixture(scope="session")
def frozen_checker_workspace(tmp_path_factory):
    from research.replay_frozen_docx import prepare
    return prepare(tmp_path_factory.mktemp("frozen-checker"))


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """Version-bound receipts execute against their real historical source."""
    if pyfuncitem.get_closest_marker("frozen_checker") is None:
        return None
    from research import replay_frozen_docx as replay
    if os.environ.get(replay.CHILD):
        import ooxml_integrity
        assert replay.is_baseline_source(), "Historical checker source drift"
        assert Path(ooxml_integrity.__file__).resolve().parent == ROOT/'src/ooxml_integrity'
        return None
    if replay.is_baseline_source():
        return None
    directory = pyfuncitem._request.getfixturevalue("frozen_checker_workspace")
    result = replay.run_tests(directory, [pyfuncitem.nodeid])
    assert result.returncode == 0, result.stdout + result.stderr
    return True


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def base_docx() -> Path:
    """The reference document: every construct that matters, nothing broken."""
    p = ROOT / "corpus" / "base.docx"
    if not p.exists():
        pytest.skip("corpus/base.docx is missing; run research/build_corpus.py")
    return p


@pytest.fixture(scope="session")
def runs_dir() -> Path:
    p = ROOT / "runs"
    if not p.exists():
        pytest.skip("runs/ is missing")
    return p


#: (directory, expected finding codes) for the real agent runs.
#: The six careful runs must stay clean; the two fast runs must report exactly
#: the orphaned comment and its fidelity counterpart.
CAREFUL_RUNS = (
    "t1_bare", "t1_pres", "t2_bare", "t2_pres",
    "t5_rewrite_bare", "t5_rewrite_pres",
)
FAST_RUNS = ("t4_fast_fee", "t4_fast_table")


@pytest.fixture
def tmp_docx(tmp_path: Path, base_docx: Path) -> Path:
    """A writable copy of the reference document."""
    dst = tmp_path / "copy.docx"
    shutil.copy(base_docx, dst)
    return dst


def repack(src: Path, dst: Path, edits: dict[str, bytes], *,
           add_dirs: bool = False) -> Path:
    """Rewrite a package with some parts replaced. Order is preserved."""
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        parts = {n: z.read(n) for n in names}
    parts.update(edits)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        if add_dirs:
            for d in ("word/", "word/_rels/", "docProps/", "_rels/"):
                z.writestr(d, b"")
        for n in names:
            z.writestr(n, parts[n])
        for n, data in edits.items():
            if n not in names:
                z.writestr(n, data)
    return dst


def read_part(path: Path, part: str) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read(part).decode("utf-8")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Invoke the CLI the way a user would, in its own process."""
    return subprocess.run(
        [sys.executable, "-m", "ooxml_integrity.cli", *args],
        capture_output=True, text=True, cwd=ROOT,
    )


#: The package rules that run on a deck before its layout is read.
PACKAGE_RULES = {"XML001", "PKG003", "PKG004", "PKG005", "PKG011", "PKG012",
                 "REL001", "REL002", "REL004"}


def aborted(found):
    """The layout read stopped with one PKG002 after the package findings, if any."""
    from ooxml_integrity import ERROR
    *package, last = found
    return (last.code == "PKG002" and last.severity == ERROR
            and {f.code for f in package} <= PACKAGE_RULES)
