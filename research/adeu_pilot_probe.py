#!/usr/bin/env python3
"""Synthetic regressions for adeu's pilot feedback; never runs an editor/API."""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import subprocess
import sys
import time
import zipfile

from lxml import etree
import ooxml_integrity
from ooxml_integrity import check, compare
from ooxml_integrity.inspector import Inspector

ROOT = Path(__file__).resolve().parents[1]
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'
DOC = 'word/document.xml'
RELS = 'word/_rels/document.xml.rels'
COMMENTS = 'word/comments.xml'
SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_parts(path):
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def write_parts(path, parts):
    path = Path(path)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return path


def renamed_comments(base, destination, name='word/comments1.xml', *, target=None,
                     decoy=False):
    parts = read_parts(base)
    blob = parts[COMMENTS]
    if not decoy:
        del parts[COMMENTS]
    parts[name] = blob
    rels = etree.fromstring(parts[RELS])
    for rel in rels:
        if rel.get('Type', '').endswith('/comments'):
            rel.set('Target', target if target is not None else '/' + name)
    parts[RELS] = etree.tostring(rels)
    types = etree.fromstring(parts['[Content_Types].xml'])
    for node in list(types):
        if node.get('PartName') == '/' + COMMENTS:
            if decoy:
                copy = etree.SubElement(types, node.tag, dict(node.attrib))
                copy.set('PartName', '/' + name)
            else:
                node.set('PartName', '/' + name)
    parts['[Content_Types].xml'] = etree.tostring(types)
    return write_parts(destination, parts)


def text_document(base, destination, text, *, paragraphs=1, runs=1,
                  inherited=None, local=None):
    parts = read_parts(base)
    doc = etree.fromstring(parts[DOC])
    body = doc.find(W + 'body')
    body.clear()
    if inherited is not None:
        body.set(SPACE, inherited)
    for _ in range(paragraphs):
        p = etree.SubElement(body, W + 'p')
        for _ in range(runs):
            t = etree.SubElement(etree.SubElement(p, W + 'r'), W + 't')
            if local is not None:
                t.set(SPACE, local)
            t.text = text
    # Keep the package reference specimen; only whitespace-rule results are
    # relevant for this deliberately reduced main story.
    parts[DOC] = etree.tostring(doc)
    return write_parts(destination, parts)


def whitespace_findings(path):
    inspector = Inspector(path)
    inspector.load()
    inspector.findings.clear()
    inspector.check_whitespace()
    return inspector.findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile-sizes', type=int, nargs='+', default=[4000, 16000])
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    directory = args.output.parent / (args.output.stem + '-fixtures')
    directory.mkdir(exist_ok=True)
    base = ROOT / 'corpus/base.docx'
    checker_root = Path(ooxml_integrity.__file__).resolve().parent
    result = {
        'scope': 'Synthetic checker probes; no native Windows or editor execution',
        'python': sys.version, 'platform': platform.platform(),
        'command': [sys.executable, *sys.argv],
        'checker_module_path': str(checker_root),
        'PYTHONPATH': os.environ.get('PYTHONPATH'),
        'script_sha256': digest(__file__), 'base_sha256': digest(base),
        'checker_files_sha256': {
            p.name: digest(p) for p in sorted(checker_root.glob('*.py'))
        }, 'fixtures_sha256': {}, 'cli': [], 'comments': {}, 'whitespace': {},
        'performance': [],
    }
    # Add a Unicode excerpt without changing any existing review structures.
    parts = read_parts(base)
    doc = etree.fromstring(parts[DOC])
    p = etree.SubElement(doc.find(W + 'body'), W + 'p')
    etree.SubElement(etree.SubElement(p, W + 'r'), W + 't').text = ' \u2012 Пример '
    parts[DOC] = etree.tostring(doc)
    unicode_file = write_parts(directory/'unicode.docx', parts)
    env = dict(os.environ, PYTHONIOENCODING='cp1252:strict', PYTHONUTF8='0')
    for json_mode in (False, True):
        for threshold in ('error', 'warn'):
            command = [sys.executable, '-m', 'ooxml_integrity', 'check',
                       str(unicode_file), '--no-config', '--fail-on', threshold]
            if json_mode:
                command.append('--json')
            proc = subprocess.run(command, capture_output=True, env=env, timeout=60)
            stdout = proc.stdout.decode('cp1252')
            result['cli'].append({
                'json': json_mode, 'threshold': threshold, 'command': command,
                'env': {k: env[k] for k in ('PYTHONIOENCODING', 'PYTHONUTF8')},
                'exit': proc.returncode, 'stdout': stdout,
                'stderr': proc.stderr.decode('cp1252'),
            })
    named = renamed_comments(base, directory/'renamed.docx')
    parts = read_parts(named)
    parts['word/comments1.xml'] = parts['word/comments1.xml'].replace(
        b'Confirm this figure', b'Changed reviewer text')
    lost = write_parts(directory/'changed-comment.docx', parts)
    for key, path in (('retained', named), ('changed', lost)):
        result['comments'][key] = {
            'check': [f.as_dict() for f in check(path)],
            'compare': [f.as_dict() for f in compare(named if key == 'changed' else base, path)],
        }
    for name, text, inherited, local in (
        ('ascii', ' ordinary ', None, None),
        ('nbsp', '\u00a0ordinary\u00a0', None, None),
        ('inherited', ' ordinary ', 'preserve', None),
        ('override', ' ordinary ', 'preserve', 'default'),
    ):
        path = text_document(base, directory/(name+'.docx'), text,
                             inherited=inherited, local=local)
        result['whitespace'][name] = [f.as_dict() for f in whitespace_findings(path)]
    for size in args.profile_sizes:
        path = text_document(base, directory/f'large-{size}.docx', ' edge ',
                             paragraphs=size, runs=6)
        inspector = Inspector(path)
        inspector.load()
        inspector.findings.clear()
        profile = cProfile.Profile()
        start = time.perf_counter()
        profile.runcall(inspector.check_whitespace)
        elapsed = time.perf_counter() - start
        stats = pstats.Stats(profile)
        hot = sorted(stats.stats.items(), key=lambda pair: pair[1][3], reverse=True)[:8]
        result['performance'].append({
            'paragraphs': size, 'text_nodes': size*6,
            'scope': 'check_whitespace only; XML load excluded; cProfile enabled',
            'seconds': elapsed, 'count': len(inspector.findings),
            'findings_sha256': hashlib.sha256(json.dumps(
                [f.as_dict() for f in inspector.findings], sort_keys=True).encode()).hexdigest(),
            'hot_functions': [{'function': str(key), 'calls': stat[1],
                               'self_seconds': stat[2], 'cumulative_seconds': stat[3]}
                              for key, stat in hot],
        })
        print(f'{size} paragraphs: {elapsed:.3f}s, {len(inspector.findings)} findings', flush=True)
    result['fixtures_sha256'] = {p.name: digest(p) for p in sorted(directory.glob('*.docx'))}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True)+'\n', encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
