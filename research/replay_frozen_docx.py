#!/usr/bin/env python3
"""Replay version-bound DOCX evidence with its exact archived checker, offline.

The current checker is tested separately. No hash gate, oracle, capture or saved
finding is rewritten to make historical evidence run on a changed checker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'evidence/docx-fid001-coalescence'
CHILD = 'OOXML_FROZEN_CHECKER_CHILD'
TEST_FILES = ['tests/test_docx_benchmark.py', 'tests/test_docx_boundaries.py',
              'tests/test_docx_agent.py', 'tests/test_word_revision_ids.py',
              'tests/test_revision_evidence.py', 'tests/test_windows_evidence.py',
              'tests/test_evidence_corpus.py']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def baseline():
    return json.loads((BASE / 'baseline.json').read_text())


def is_baseline_source():
    declared = baseline()['files']
    actual = {p.relative_to(ROOT).as_posix(): digest(p.read_bytes())
              for p in (ROOT/'src/ooxml_integrity').rglob('*.py')}
    return actual == declared


def prepare(directory):
    """Materialize only repository-owned files; no installed/network editor."""
    record = baseline()
    archive = BASE / 'baseline-checker.zip'
    if digest(archive.read_bytes()) != record['archive_sha256']:
        raise ValueError('Frozen checker archive drift')
    with ZipFile(archive) as z:
        if len(z.namelist()) != len(record['files']) or set(z.namelist()) != set(record['files']):
            raise ValueError('Frozen checker inventory drift')
        for name, expected in record['files'].items():
            path = directory / name
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Unsafe frozen checker path')
            data = z.read(name)
            if digest(data) != expected:
                raise ValueError('Frozen checker source drift')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store')
    for name in ('research', 'tests', 'corpus'):
        shutil.copytree(ROOT/name, directory/name, ignore=ignore)
    for name in ('docx-beta', 'docx-benchmark', 'docx-benchmark-boundaries', 'docx-revisions',
                 'docx-word-id-followup', 'docx-fid001-coalescence'):
        shutil.copytree(ROOT/'evidence'/name, directory/'evidence'/name, ignore=ignore)
    shutil.copyfile(ROOT/'pyproject.toml', directory/'pyproject.toml')
    return directory


def run_tests(directory, targets):
    env = dict(os.environ, **{CHILD: '1', 'PYTHONPATH': str(directory/'src')})
    return subprocess.run(
        [sys.executable, '-m', 'pytest', *targets, '-ra', '--basetemp', str(directory/'test-work')],
        cwd=directory, env=env, text=True, capture_output=True, timeout=120,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    (ROOT/'tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='frozen-docx-', dir=ROOT/'tmp') as temp:
        result = run_tests(prepare(Path(temp)), [*TEST_FILES, '-m', 'frozen_checker'])
        print(result.stdout, end='')
        print(result.stderr, end='', file=sys.stderr)
        if result.returncode:
            raise SystemExit(result.returncode)
    print(json.dumps({'checker_source_sha256': baseline()['source_tree_sha256'],
                      'mode': 'historical checker, frozen receipts unchanged'}))


if __name__ == '__main__':
    main()
