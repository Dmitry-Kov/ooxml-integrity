#!/usr/bin/env python3
"""Recheck saved outputs under the candidate checker, without editor/model calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import docx_benchmark as b

BASE = ROOT/'evidence/docx-fid001-coalescence'


def pair(ident, source, output, source_hash, output_hash, prior):
    if b.digest(source) != source_hash or b.digest(output) != output_hash:
        raise ValueError('Saved input/output drift: ' + ident)
    current = b.checker_findings(source, output)
    return {'id': ident, 'source': str(source.relative_to(ROOT)),
            'output': str(output.relative_to(ROOT)), 'source_sha256': source_hash,
            'output_sha256': output_hash, 'before': prior, 'after': current,
            'changed': prior != current}


def review():
    cases, unavailable, receipts = [], [], {}
    for cohort in ('docx-benchmark', 'docx-benchmark-boundaries'):
        base = ROOT/'evidence'/cohort
        for directory in sorted((base/'captures').iterdir()) + [base/'agent-local-1']:
            agent = directory.name == 'agent-local-1'
            capture = directory/'capture.json'
            evaluation = directory/('evaluation.reviewed.json' if cohort == 'docx-benchmark' and not agent else 'evaluation.json')
            receipt, prior = json.loads(capture.read_text()), json.loads(evaluation.read_text())
            if prior['capture_sha256'] != b.digest(capture):
                raise ValueError('Historical capture receipt drift')
            for path in (capture, evaluation):
                receipts[str(path.relative_to(ROOT))] = b.digest(path)
            old = {c['id']: c for c in prior['cases']}
            for c in receipt['cases']:
                ident = '/'.join((cohort, directory.name, c['id']))
                if agent:
                    source, source_hash = ROOT/c['path'], c['sha256']
                    output, output_hash = directory/c['id']/'output.docx', c['artifacts_sha256'].get('output.docx')
                else:
                    source, source_hash = ROOT/c['source'], c['source_sha256']
                    output = directory/c['output'] if c['output'] else None
                    output_hash = c.get('output_sha256')
                if not output_hash:
                    if c['status'] == 'ok' or (output is not None and output.exists()):
                        raise ValueError('Unexpected missing output receipt')
                    unavailable.append({'id': ident, 'status': c['status'], 'checker': 'not_evaluated_no_output'})
                    continue
                cases.append(pair(ident, source, output, source_hash, output_hash, old[c['id']]['checker_findings']))
    base = ROOT/'evidence/docx-word-id-followup'
    capture, evaluation = base/'capture.json', base/'evaluation.json'
    prior = json.loads(evaluation.read_text())
    if prior['capture_sha256'] != b.digest(capture):
        raise ValueError('Word capture drift')
    old = {c['id']: c for c in prior['cases']}
    for path in (capture, evaluation):
        receipts[str(path.relative_to(ROOT))] = b.digest(path)
    for c in json.loads(capture.read_text())['cases']:
        cases.append(pair('word/'+c['id'], ROOT/c['path'], ROOT/c['output'], c['sha256'],
                          c['output_sha256'], old[c['id']]['checker_after']))
    return {'scope': 'Current checker re-evaluation of stored outputs; no fresh editor/model observations',
            'checker_source_sha256': b.tree_hash(ROOT/'src/ooxml_integrity'),
            'review_script_sha256': b.digest(__file__), 'historical_receipts_sha256': receipts,
            'output_pairs': len(cases), 'changed_pairs': [c['id'] for c in cases if c['changed']],
            'cases': cases, 'not_evaluated': unavailable}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write', action='store_true')
    args = p.parse_args()
    result = review()
    if args.write:
        b.save_json(BASE/'candidate.json', result)
    elif result != json.loads((BASE/'candidate.json').read_text()):
        raise ValueError('Candidate review drift')
    print(json.dumps({k: result[k] for k in ('output_pairs', 'changed_pairs')}))


if __name__ == '__main__':
    main()
