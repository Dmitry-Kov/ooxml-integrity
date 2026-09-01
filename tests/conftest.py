"""Shared fixtures.

The committed corpus and agent-run outputs are the fixtures: the suite tests
what actually ships, not a parallel set of hand-made files.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


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
